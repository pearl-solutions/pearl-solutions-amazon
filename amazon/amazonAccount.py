from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from http.cookiejar import Cookie
from pathlib import Path
from typing import Any, Optional, TypedDict

import requests
from browserforge.fingerprints import Screen
from camoufox.sync_api import Camoufox
from faker import Faker


ACCOUNTS_DIR = Path(".accounts")


class AccountData(TypedDict):
    """Serializable representation of an Amazon account stored on disk."""
    email: str
    password: str
    proxy: str
    cookies: list[dict[str, Any]]


def _sanitize_filename(name: str, max_len: int = 255) -> str:
    """
    Make a string safe to use as a filename on most OSes.

    Notes:
        - Replaces any character not in [A-Za-z0-9._-] with "_".
        - Truncates to `max_len` to avoid OS path limits.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return safe[:max_len]


def proxy_string_to_dict(proxy_str: str) -> dict[str, str]:
    """
    Convert a proxy string formatted as 'host:port:username:password'
    into the dict expected by Camoufox/Playwright-like APIs.

    Raises:
        ValueError: If the string doesn't match the expected format.
    """
    if not isinstance(proxy_str, str):
        raise ValueError("proxy_str must be a string")

    s = proxy_str.strip()

    # Split into 4 parts max (allows ':' in password if present)
    parts = s.split(":", 3)
    if len(parts) != 4:
        raise ValueError("format: 'host:port:username:password'")

    host, port, username, password = (p.strip() for p in parts)

    if not host or not port or not username:
        raise ValueError("host, port and username must be non-empty")

    # Build server URL (default to http:// if scheme not provided)
    if host.startswith(("http://", "https://")):
        server = f"{host}:{port}" if ":" not in host.split("://", 1)[1] else host
    else:
        server = f"http://{host}:{port}"

    return {"server": server, "username": username, "password": password}


def dict_to_cookie(cookie_dict: dict[str, Any]) -> Cookie:
    """
    Convert a dict-based cookie (e.g. from a browser context) into a requests Cookie.
    """
    return Cookie(
        version=0,
        name=str(cookie_dict["name"]),
        value=str(cookie_dict["value"]),
        port=None,
        port_specified=False,
        domain=str(cookie_dict["domain"]),
        domain_specified=True,
        domain_initial_dot=str(cookie_dict["domain"]).startswith("."),
        path=str(cookie_dict["path"]),
        path_specified=True,
        secure=bool(cookie_dict.get("secure", False)),
        expires=cookie_dict.get("expires"),
        discard=False,
        comment=None,
        comment_url=None,
        rest={
            "HttpOnly": bool(cookie_dict.get("httpOnly", False)),
            "SameSite": cookie_dict.get("sameSite", None),
        },
        rfc2109=False,
    )


def generate_name() -> str:
    """Generate a French-looking full name (used for form filling)."""
    fake = Faker("fr_FR")
    return fake.name()


@dataclass(slots=True)
class AmazonAccount:
    """
    In-memory representation of an account plus its persisted state.
    """
    email: str
    password: str
    proxy: str
    cookies: list[dict[str, Any]]

    def save_account(self) -> bool:
        """
        Save the account to `.accounts/<sanitized_email>.json`.

        Returns:
            True if successfully saved, False otherwise.
        """
        account_data: AccountData = {
            "email": self.email,
            "password": self.password,
            "proxy": self.proxy,
            "cookies": self.cookies,
        }

        # Ensure storage folder exists
        ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)

        safe_name = _sanitize_filename(self.email)
        account_path = ACCOUNTS_DIR / f"{safe_name}.json"

        try:
            with account_path.open("w", encoding="utf-8") as f:
                json.dump(account_data, f, indent=2, ensure_ascii=False)

            print(f"Successfully saved account: {account_path}")
            return True
        except Exception as exc:
            print(f"Error while saving account: {exc}")
            return False

    def delete_account(self) -> bool:
        """
        Delete the persisted account file if it exists.
        """
        safe_name = _sanitize_filename(self.email)
        account_path = ACCOUNTS_DIR / f"{safe_name}.json"

        try:
            if account_path.exists():
                account_path.unlink()
                print(f"Successfully deleted account : {account_path}")
                return True

            print(f"Cannot find path : {account_path}")
            return False
        except Exception as exc:
            print(f"Error while deleting account : {exc}")
            return False

    def open_tab_till_close(self) -> None:
        """
        Open a browser tab with the current cookies and persist updated cookies when closed.

        Note:
            Browser automation behavior is left unchanged; this method only adds typing and structure.
        """
        with Camoufox(
            os="windows",
            window=(1280, 720),
            humanize=True,
            locale="fr-FR",
            disable_coop=True,
            i_know_what_im_doing=True,
            proxy=proxy_string_to_dict(self.proxy),
            geoip=True,
        ) as browser:
            try:
                page = browser.new_page()
                page.context.add_cookies(self.cookies)

                page.goto("https://www.amazon.fr", timeout=60_000)
                page.wait_for_load_state("networkidle", timeout=60_000)

                input("Press enter to close tab...")

                # Persist the latest cookies back to disk
                self.cookies = page.context.cookies()
                self.save_account()

            except Exception as exc:
                print(f"Error while opening account tab : {exc}")

    def get_session_with_cookies(self) -> requests.Session:
        """
        Build a requests.Session preloaded with the account cookies.
        """
        session = requests.Session()
        jar = session.cookies

        for c in self.cookies:
            jar.set_cookie(dict_to_cookie(c))

        return session

    def get_email(self) -> str:
        return self.email

    def get_password(self) -> str:
        return self.password

    def get_proxy(self) -> str:
        return self.proxy

    def get_cookies(self) -> list[dict[str, Any]]:
        return self.cookies


def load_all_accounts() -> list[AmazonAccount]:
    """
    Load all account files from `.accounts/*.json`.

    Skips invalid or incomplete files.
    """
    accounts: list[AmazonAccount] = []
    ACCOUNTS_DIR.mkdir(exist_ok=True)

    for file in ACCOUNTS_DIR.glob("*.json"):
        try:
            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            email = data.get("email")
            password = data.get("password")
            proxy = data.get("proxy")
            cookies = data.get("cookies")

            # Minimal validation to avoid crashing on malformed files
            if not isinstance(email, str) or not isinstance(password, str) or not isinstance(proxy, str):
                continue
            if not isinstance(cookies, list):
                continue

            accounts.append(AmazonAccount(email=email, password=password, proxy=proxy, cookies=cookies))
        except Exception:
            # Ignore invalid files to keep loading resilient.
            continue

    return accounts


def generate_account(
    email: str,
    password: str,
    proxy: str,
    waiter: Any,
    sms_manager: Any,
) -> Optional[AmazonAccount]:
    with Camoufox(
        os="windows",
        screen=Screen(max_width=1920, max_height=1080),
        window=(850 + int(random.random() * 10), 700 + int(random.random() * 10)),
        humanize=True,
        locale="fr-FR",
        disable_coop=True,
        i_know_what_im_doing=True,
        proxy=proxy_string_to_dict(proxy),
        geoip=True,
    ) as browser:
        try:
            page = browser.new_page()
            page.goto("https://www.amazon.fr")
            page.wait_for_load_state("networkidle")

            try:
                continuer_button = page.locator('button.a-button-text:has-text("Continuer les achats")')
                time.sleep(random.random() * 2)
                page.wait_for_load_state("networkidle")
                if continuer_button.is_visible(timeout=5000):
                    continuer_button.click()
                    page.wait_for_load_state("networkidle")
            except Exception:
                pass

            time.sleep(random.random())

            page.hover("#nav-link-accountList")
            page.click("text=Commencer ici.")
            page.wait_for_load_state("networkidle")

            time.sleep(random.random())

            createTrigger = True

            if not page.query_selector("#ap_customer_name"):
                page.type("#ap_email_login", email, delay=80)

                time.sleep(random.random())

                page.click(".a-button-input")

                time.sleep(random.random())

                page.click(".a-button-input")

                time.sleep(2)

                createTrigger = False

            page.wait_for_selector("#ap_customer_name", state="visible")
            time.sleep(random.random())

            page.type("#ap_customer_name", generate_name(), delay=80)
            time.sleep(random.random())
            if createTrigger:
                page.type("#ap_email", email, delay=80)
                time.sleep(random.random())
            page.type("#ap_password", password, delay=80)
            time.sleep(random.random())
            page.type("#ap_password_check", password, delay=80)
            time.sleep(random.random())

            page.wait_for_selector("#continue", state="visible")
            page.click("#continue")

            page.wait_for_load_state("networkidle")

            if page.query_selector(".a-alert-error"):
                print("Error while creating account")
                return None

            time.sleep(3)

            page.wait_for_selector("#cvf-input-code", timeout=600 * 1000)

            otp_code = waiter.wait_for_otp(
                target_email=email,
                timeout=500,
                check_interval=3,
                thread_id=email,
            )

            page.type("#cvf-input-code", otp_code, delay=80)
            time.sleep(random.random())
            page.wait_for_selector("#cvf-submit-otp-button")
            page.click("#cvf-submit-otp-button")
            for i in range(3):
                page.wait_for_load_state('networkidle', timeout=60000)

                page.locator("span.a-dropdown-prompt").click()

                menu = page.locator("ul[role='listbox'], .a-popover-inner")

                target = menu.locator("text=Royaume-Uni").first

                target.evaluate(
                    "el => el.scrollIntoView({ block: 'center', behavior: 'instant' })"
                )

                target.click()

                number, activationId = sms_manager.get_number()

                if not number:
                    break

                page.type("#cvfPhoneNumber", number, delay=80)
                time.sleep(random.random())

                page.wait_for_selector("#a-autoid-0")
                page.click("#a-autoid-0")

                time.sleep(random.random())

                page.wait_for_load_state('networkidle')

                time.sleep(random.random())

                code = sms_manager.get_code_from_number(activationId, timeout=90)

                if code is not None:
                    break

                page.click(".cvf-widget-link-collect-change")

                page.wait_for_load_state('networkidle')

                time.sleep(random.random())

            try:
                error_message = page.locator(".a-section.cvf-alert-section.cvf-widget-alert-message")
                if error_message.is_visible():
                    print(f"Error while creating account: phone number already taken")
            except:
                ...

            try:
                page.type("#cvf-input-code", code, delay=80)
                time.sleep(random.random())
                page.wait_for_selector("#cvf-submit-otp-button")
                page.click("#cvf-submit-otp-button")
            except Exception as e:
                print(f"Error while sending code")

            time.sleep(random.random())

            page.wait_for_load_state('networkidle', timeout=60000)
            time.sleep(random.random())

            test = input("Press enter to continue...")
            if test != '':
                return None

            account = AmazonAccount(
                email=email,
                password=password,
                proxy=proxy,
                cookies=page.context.cookies()
            )

            account.save_account()

            browser.close()

            return account
        except Exception:
            print("Error while creating account")
            return None
        finally:
            try:
                if page:
                    page.close()
            except Exception:
                pass
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
