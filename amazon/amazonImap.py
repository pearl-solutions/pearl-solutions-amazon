import email
import imaplib
import re
import time
import threading
import queue
from datetime import timezone, datetime, timedelta
from email.header import decode_header
from typing import Any, Optional
from bs4 import BeautifulSoup


class AmazonEmailManager:
    """IMAP helper for reading Amazon verification and invitation emails.

    This class maintains a single IMAP SSL connection and provides helpers to:
    - decode MIME headers
    - extract OTP codes from email bodies
    - poll for OTP emails addressed to a target email
    - scan recent inbox messages for invitation emails and extract product/link
    """

    INVITATION_SUBJECT_FR = "Félicitations, vous êtes invité à passer commande!"

    def __init__(
        self,
        imap_server: str,
        email_address: str,
        password: str,
        port: int = 993,
    ) -> None:
        self.imap_server = imap_server
        self.email_address = email_address
        self.password = password.replace(" ", "")
        self.port = port

        self.mail = imaplib.IMAP4_SSL(self.imap_server, self.port)
        self.mail.login(self.email_address, self.password)

        # OTP dispatcher: single IMAP consumer thread -> per-recipient queues
        self._otp_dispatcher_thread: Optional[threading.Thread] = None
        self._otp_dispatcher_stop = threading.Event()
        self._otp_dispatcher_lock = threading.Lock()
        self._otp_queues: dict[str, "queue.Queue[str]"] = {}
        self._otp_seen_ids: set[bytes] = set()
        self._otp_dispatcher_last_since: Optional[str] = None

    def decode_mime_words(self, text: str) -> str:
        if not text:
            return ""

        decoded_parts = decode_header(text)
        decoded_text = ""

        for content, charset in decoded_parts:
            if isinstance(content, bytes):
                decoded_text += content.decode(charset or "utf-8", errors="ignore")
            else:
                decoded_text += str(content)

        return decoded_text

    def extract_otp_from_create_body(self, body: str) -> Optional[str]:
        """Extract a 6-digit OTP from an email body."""
        try:
            soup = BeautifulSoup(body, "html.parser")
            td = soup.find("td", class_="data")
            if td:
                code = td.get_text(strip=True)
                if code and len(code) == 6 and code.isdigit():
                    return code
        except Exception:
            pass

        # Fallback patterns (more tolerant)
        patterns = [
            r'class="data">\s*(\d{6})\s*<',
            r">\s*(\d{6})\s*</td>",
            r":\s*(\d{6})\b",
            r"\b(\d{6})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                code = match.group(1)
                if len(code) == 6 and code.isdigit():
                    return code

        return None

    def get_email_body(self, msg: Any) -> str:
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type in ("text/plain", "text/html") and "attachment" not in content_disposition:
                    try:
                        payload = part.get_payload(decode=True)
                        if not payload:
                            continue
                        charset = part.get_content_charset() or "utf-8"
                        body += payload.decode(charset, errors="ignore")
                    except Exception:
                        continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="ignore")
            except Exception:
                return ""

        return body

    def _imap_date(self, dt: datetime) -> str:
        """Format a datetime to IMAP date: DD-Mon-YYYY (e.g. 09-Feb-2026)."""
        return dt.strftime("%d-%b-%Y")

    def _normalize_to_address(self, to_header: str) -> str:
        """Extract a single email address from a To header."""
        to_header = (to_header or "").strip()
        match = re.search(r"<([^>]+)>", to_header)
        addr = (match.group(1) if match else to_header).strip()
        return addr.lower()

    def _get_or_create_otp_queue(self, target_email: str) -> "queue.Queue[str]":
        key = (target_email or "").strip().lower()
        with self._otp_dispatcher_lock:
            q = self._otp_queues.get(key)
            if q is None:
                q = queue.Queue()
                self._otp_queues[key] = q
            return q

    def _ensure_otp_dispatcher_started(self) -> None:
        with self._otp_dispatcher_lock:
            if self._otp_dispatcher_thread and self._otp_dispatcher_thread.is_alive():
                return
            self._otp_dispatcher_stop.clear()
            t = threading.Thread(target=self._otp_dispatcher_loop, name="AmazonEmailOTPDispatcher", daemon=True)
            self._otp_dispatcher_thread = t
            t.start()

    def _otp_dispatcher_loop(self) -> None:
        """Single IMAP consumer loop that routes OTPs to per-recipient queues."""
        # Build a stable SINCE date once (yesterday) to limit server-side scan
        now_utc = datetime.now(timezone.utc)
        cutoff_utc = now_utc - timedelta(days=1)
        since_dt = cutoff_utc.date()
        since_str = self._imap_date(datetime(since_dt.year, since_dt.month, since_dt.day))
        self._otp_dispatcher_last_since = since_str

        while not self._otp_dispatcher_stop.is_set():
            try:
                self.mail.select("INBOX")

                # Fetch all unread messages since yesterday.
                # (We dispatch by reading To: locally instead of server-side TO filtering per target.)
                status, messages = self.mail.search("UTF-8", f'(UNSEEN SINCE "{since_str}")'.encode("utf-8"))
                if status != "OK":
                    time.sleep(1.0)
                    continue

                ids = messages[0].split()
                if not ids:
                    time.sleep(1.0)
                    continue

                # Process oldest -> newest (so queues get codes in chronological order)
                for eid in ids:
                    if eid in self._otp_seen_ids:
                        continue

                    status, msg_data = self.mail.fetch(eid, "(RFC822)")
                    if status != "OK" or not msg_data or not msg_data[0]:
                        self._otp_seen_ids.add(eid)
                        continue

                    try:
                        msg = email.message_from_bytes(msg_data[0][1])
                    except Exception:
                        self._otp_seen_ids.add(eid)
                        continue

                    to_header = msg.get("To", "")
                    to_address = self._normalize_to_address(to_header)

                    body = self.get_email_body(msg)
                    otp = self.extract_otp_from_create_body(body)

                    # Mark as "seen" in our process to avoid re-fetch loops
                    self._otp_seen_ids.add(eid)

                    if not otp or not to_address:
                        continue

                    q = self._get_or_create_otp_queue(to_address)
                    q.put_nowait(otp)

                time.sleep(0.5)
            except Exception:
                # Any transient IMAP issue: wait a bit and retry
                time.sleep(1.0)

    def stop_otp_dispatcher(self) -> None:
        """Optional: stop background dispatcher (usually not needed for CLI scripts)."""
        self._otp_dispatcher_stop.set()

    def check_for_otp(self, mail: imaplib.IMAP4_SSL, target_email: str) -> Optional[str]:
        """Check the inbox for the latest unread OTP email addressed to a target.

        NOTE: This legacy method still works, but in multithread it is better to use wait_for_otp(),
        which now uses a single shared dispatcher thread to avoid concurrent IMAP access.
        """
        try:
            mail.select("INBOX")

            now_utc = datetime.now(timezone.utc)
            cutoff_utc = now_utc - timedelta(days=1)
            since_dt = cutoff_utc.date()
            since_str = self._imap_date(datetime(since_dt.year, since_dt.month, since_dt.day))

            status, messages = mail.search(
                "UTF-8",
                f'(TO "{target_email}" UNSEEN SINCE "{since_str}")'.encode("utf-8"),
            )
            if status != "OK":
                return None

            email_ids = messages[0].split()
            if not email_ids:
                return None

            email_id = email_ids[-1]
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                return None

            msg = email.message_from_bytes(msg_data[0][1])
            body = self.get_email_body(msg)
            return self.extract_otp_from_create_body(body)

        except Exception:
            return None

    def wait_for_otp(
        self,
        target_email: str,
        timeout: int = 120,
        check_interval: int = 3,
        thread_id: str = "",
    ) -> Optional[str]:
        """Poll the inbox until an OTP is received or the timeout is reached.

        Signature unchanged: now relies on a single dispatcher thread that routes OTPs
        to per-recipient queues (no per-thread IMAP search loops).
        """
        if not self.mail:
            return None

        self._ensure_otp_dispatcher_started()
        q = self._get_or_create_otp_queue(target_email)

        start_time = time.time()
        prefix = f"[{thread_id}] " if thread_id else ""
        target_norm = (target_email or "").strip().lower()
        print(f"{prefix}Waiting OTP for {target_email}...")

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"{prefix}Timeout ({timeout}s) - {target_email}")
                return None

            remaining = max(0.1, timeout - elapsed)

            try:
                # We keep check_interval behavior by bounding each wait
                otp = q.get(timeout=min(check_interval, remaining))
                if otp:
                    print(f"{prefix}OTP received: {otp} - {target_email}")
                    return otp
            except queue.Empty:
                # No OTP yet for this target; loop until timeout
                pass

    def get_connection(self) -> imaplib.IMAP4_SSL:
        """Return the underlying IMAP connection."""
        return self.mail

    def _decode_header(self, value: str) -> str:
        parts = decode_header(value)
        decoded = ""
        for text, charset in parts:
            if isinstance(text, bytes):
                decoded += text.decode(charset or "utf-8", errors="ignore")
            else:
                decoded += str(text)
        return decoded

    def fetch_invitation_emails(self) -> list[tuple[str, str, str]]:
        self.mail.select("INBOX")
        results: list[tuple[str, str, str]] = []

        status, data = self.mail.search(None, "ALL")
        if status != "OK":
            print("Error while searching emails")
            return results

        ids = data[0].split()
        if not ids:
            print("No invitation emails found")
            return results

        ids = ids[-200:]

        for eid in ids:
            status, msg_data = self.mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            raw_subject = msg.get("Subject", "")
            subject = self._decode_header(raw_subject)

            if subject.strip() != self.INVITATION_SUBJECT_FR:
                continue

            to_header = msg.get("To", "").strip()
            match = re.search(r"<([^>]+)>", to_header)
            to_address = match.group(1) if match else to_header

            product_name: Optional[str] = None
            link: Optional[str] = None

            def scan_body_text(body_text: str) -> tuple[Optional[str], Optional[str]]:
                found_product: Optional[str] = None
                found_link: Optional[str] = None

                for raw_line in body_text.split("\n"):
                    line = raw_line.strip()

                    if "Vous pouvez maintenant acheter" in line or "eures  à compter de l'envoi de cet e-mail pour effe" in line:
                        m = re.search(r"acheter\s+(.*?)\s*\.", line)
                        if m:
                            found_product = m.group(1)

                    if "www.amazon.fr/dp/" in line:
                        found_link = line

                return found_product, found_link

            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_maintype() == "multipart":
                        continue
                    if "attachment" in str(part.get("Content-Disposition")):
                        continue

                    try:
                        charset = part.get_content_charset() or "utf-8"
                        payload = part.get_payload(decode=True) or b""
                        body = payload.decode(charset, errors="ignore")
                    except Exception:
                        continue

                    p, l = scan_body_text(body)
                    product_name = product_name or p
                    link = link or l
            else:
                try:
                    charset = msg.get_content_charset() or "utf-8"
                    payload = msg.get_payload(decode=True) or b""
                    body = payload.decode(charset, errors="ignore")
                except Exception:
                    body = ""

                product_name, link = scan_body_text(body)

            if product_name and link:
                results.append((to_header, product_name, link))

        return results