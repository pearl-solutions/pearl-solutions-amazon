import email
import imaplib
import re
import time
from email.header import decode_header
from typing import Any, Optional


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
        """Create and authenticate an IMAP connection.

        Args:
            imap_server: IMAP hostname (e.g. "imap.gmail.com").
            email_address: Mailbox username/login (usually the email address).
            password: Mailbox password (or app password).
            port: IMAP SSL port (default: 993).

        Raises:
            imaplib.IMAP4.error: If connection or login fails.
            OSError: If network-related errors occur.
        """
        self.imap_server = imap_server
        self.email_address = email_address
        self.password = password.replace(" ", "")
        self.port = port

        self.mail = imaplib.IMAP4_SSL(self.imap_server, self.port)
        self.mail.login(self.email_address, self.password)

    def decode_mime_words(self, text: str) -> str:
        """Decode a MIME-encoded header value into a readable string.

        Args:
            text: Raw header value (possibly MIME encoded).

        Returns:
            Decoded header string. Returns an empty string for falsy input.
        """
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
        """Extract a 6-digit OTP from an email body.

        Args:
            body: Email body as plain text or HTML.

        Returns:
            The 6-digit OTP if found, otherwise None.
        """
        patterns = [
            r'class="data">(\d{6})<',
            r">(\d{6})</td>",
            r":(\d{6})",
            r"(\d{6})",
        ]

        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                code = match.group(1)
                if len(code) == 6 and code.isdigit():
                    return code

        return None

    def get_email_body(self, msg: Any) -> str:
        """Extract the message body from an email message object.

        The function tries to gather both text/plain and text/html parts while
        skipping attachments.

        Args:
            msg: `email.message.Message`-like object.

        Returns:
            The decoded body as a string (may be empty if parsing fails).
        """
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
                        # Ignore malformed parts; keep parsing remaining parts.
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

    def check_for_otp(self, mail: imaplib.IMAP4_SSL, target_email: str) -> Optional[str]:
        """Check the inbox for the latest unread OTP email addressed to a target.

        Args:
            mail: IMAP connection to use.
            target_email: Recipient email address to filter on.

        Returns:
            Extracted OTP if found, otherwise None.
        """
        try:
            mail.select("INBOX")

            # Search for unread emails whose "To" matches the target email.
            status, messages = mail.search("UTF-8", f'(TO "{target_email}" UNSEEN)'.encode("utf-8"))
            if status != "OK":
                return None

            email_ids = messages[0].split()
            if not email_ids:
                return None

            # Fetch the most recent matching email.
            email_id = email_ids[-1]
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                return None

            msg = email.message_from_bytes(msg_data[0][1])
            body = self.get_email_body(msg)
            return self.extract_otp_from_create_body(body)

        except Exception:
            # Avoid leaking server or credentials info; caller can retry.
            return None

    def wait_for_otp(
        self,
        target_email: str,
        timeout: int = 120,
        check_interval: int = 3,
        thread_id: str = "",
    ) -> Optional[str]:
        """Poll the inbox until an OTP is received or the timeout is reached.

        Args:
            target_email: Recipient email address used during account creation.
            timeout: Maximum polling duration in seconds.
            check_interval: Delay between checks in seconds.
            thread_id: Optional label used to prefix logs in multi-thread scenarios.

        Returns:
            OTP code if received, otherwise None.
        """
        if not self.mail:
            return None

        start_time = time.time()
        prefix = f"[{thread_id}] " if thread_id else ""
        print(f"{prefix}Waiting OTP for {target_email}...")

        while True:
            if time.time() - start_time > timeout:
                print(f"{prefix}Timeout ({timeout}s) - {target_email}")
                return None

            try:
                otp = self.check_for_otp(self.mail, target_email)
                if otp:
                    print(f"{prefix}OTP received: {otp} - {target_email}")
                    return otp
            except Exception:
                # Any unexpected parsing/IMAP issues: keep polling until timeout.
                pass

            time.sleep(check_interval)

    def get_connection(self) -> imaplib.IMAP4_SSL:
        """Return the underlying IMAP connection."""
        return self.mail

    def _decode_header(self, value: str) -> str:
        """Decode a header value; internal helper.

        Args:
            value: Raw header string.

        Returns:
            Decoded string.
        """
        parts = decode_header(value)
        decoded = ""
        for text, charset in parts:
            if isinstance(text, bytes):
                decoded += text.decode(charset or "utf-8", errors="ignore")
            else:
                decoded += str(text)
        return decoded

    def fetch_invitation_emails(self) -> list[tuple[str, str, str]]:
        """Fetch invitation emails and extract recipient/product/link.

        This scans the last ~200 messages and matches the exact French subject:
        :attr:`INVITATION_SUBJECT_FR`.

        Returns:
            A list of tuples: (to_header, product_name, amazon_link).
        """
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

        # Limit scan to the most recent messages to keep it fast.
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
                """Extract product name and link from a decoded email body."""
                found_product: Optional[str] = None
                found_link: Optional[str] = None

                for raw_line in body_text.split("\n"):
                    line = raw_line.strip()

                    # Try to extract product name from common phrasing.
                    if "Vous pouvez maintenant acheter" in line or "eures  à compter de l'envoi de cet e-mail pour effe" in line:
                        m = re.search(r"acheter\s+(.*?)\s*\.", line)
                        if m:
                            found_product = m.group(1)

                    # Capture Amazon product link if present.
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
                # Keep original `To` header in output (useful for display),
                # but we compute `to_address` above if you need it later.
                results.append((to_header, product_name, link))

        return results