import random
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

import discord.entries
from amazon import amazonAccount
from amazon.amazonAccount import AmazonAccount
from utils.config import load_config
from utils.title import print_title


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
    "Gecko/20100101 Firefox/135.0"
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}

ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


def _prompt_yes_no(prompt: str) -> str:
    """Prompt until the user enters a valid y/n answer.

    Returns:
        "y" or "n"
    """
    while True:
        raw = input(prompt).strip().lower()
        if raw in ("y", "n"):
            return raw
        print("Invalid input. Please enter 'y' or 'n'.")


def _prompt_int(prompt: str, *, min_value: int = 1, max_value: int | None = None) -> int:
    """Prompt until the user enters a valid integer within bounds."""
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            print("Invalid input. Please enter a whole number.")
            continue

        if value < min_value:
            print(f"Invalid input. Please enter a number >= {min_value}.")
            continue

        if max_value is not None and value > max_value:
            print(f"Invalid input. Please enter a number <= {max_value}.")
            continue

        return value


def _normalize_asin(value: str) -> str:
    """Normalize an ASIN input (trim + uppercase)."""
    return (value or "").strip().upper()


def _is_valid_asin(value: str) -> bool:
    """Return True if value looks like a valid ASIN (10 alphanumeric characters)."""
    return bool(ASIN_RE.fullmatch(_normalize_asin(value)))


def _prompt_asin(prompt: str) -> str:
    """Prompt until the user enters a valid ASIN."""
    while True:
        asin = _normalize_asin(input(prompt))
        if _is_valid_asin(asin):
            return asin
        print("Invalid ASIN. Expected 10 alphanumeric characters (e.g. B0ABCDEF12).")


def entry_raffle_manager():
    config = load_config()
    asins: list[str] = [a for a in (_normalize_asin(x) for x in config.get("amazon_asins", [])) if a]

    print_title()
    print("")

    if len(asins) == 0:
        print("No ASINs loaded in config.json (key: amazon_asins).")
        time.sleep(3)
        return

    # Clamp thread count later to account count; here we only validate input type/range.
    thread = _prompt_int("How many threads do you want to use? ", min_value=1)

    choice = _prompt_yes_no("Would you like to enter raffles for all ASINs? (y/n) ")
    if choice == "n":
        selected_asin = _prompt_asin("Enter the ASIN you want to enter raffles for: ")

        # Keep the original behavior: allow entering an ASIN even if it's not in config.
        if selected_asin not in asins:
            print("Note: this ASIN is not in config.json. Proceeding anyway.")
        asins = [selected_asin]

    choice = _prompt_yes_no("Would you like to enter raffles for all accounts? (y/n) ")
    if choice == "y":
        print("")
        accounts = amazonAccount.load_all_accounts()
        if not accounts:
            print("No accounts found. Please generate/import accounts first.")
            time.sleep(3)
            return
        enter_raffles(asins, accounts, thread)
        return

    while True:
        accounts = amazonAccount.load_all_accounts()
        if not accounts:
            print("No accounts found. Please generate/import accounts first.")
            time.sleep(3)
            return

        print("Select an account to enter raffles:\n")

        for i, account in enumerate(accounts, 1):
            email_display = (account.email or "").strip() or "unknown-email"
            print(f" ({i}) {email_display}")
        print(f" ({len(accounts) + 1}) Return")

        choice_int = _prompt_int("\nPlease enter your choice: ", min_value=1, max_value=len(accounts) + 1)

        if choice_int == len(accounts) + 1:
            break

        selected_account = accounts[choice_int - 1]
        print("")
        enter_raffles(asins, [selected_account], thread)
        break


def enter_raffles(asins: list[str], accounts: list[AmazonAccount], max_workers: int = 5) -> None:
    """Enter raffles for multiple accounts concurrently.

    Args:
        asins: List of ASINs to enter.
        accounts: Accounts to use for entry.
        max_workers: Maximum number of concurrent threads.
    """
    if not accounts or not asins:
        return

    # Never spawn more workers than accounts.
    max_workers = max(1, min(int(max_workers), len(accounts)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_account, account, asins) for account in accounts]
        for _ in as_completed(futures):
            # Best-effort: we only wait for completion. Errors are handled per task.
            pass


def process_account(account: AmazonAccount, asins: list[str]) -> None:
    """Process a single account: validate session, normalize ASINs, and submit raffle entries.

    Args:
        account: Amazon account object.
        asins: List of ASINs to process.
    """
    session = account.get_session_with_cookies()
    proxies = amazonAccount.proxy_string_to_dict(account.get_proxy())

    try:
        print(f"({account.email}) · Getting session...")

        response = session.get(
            "https://amazon.fr/",
            headers=DEFAULT_HEADERS,
            proxies=proxies,
            timeout=7,
        )
        if response.status_code != 200:
            print(f"({account.email}) · Error while getting session")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        tag = soup.find("span", id="nav-link-accountList-nav-line-1")

        # Avoid `tag.text` access when tag is None.
        if not tag or ("vous" in tag.text):
            print(f"({account.email}) · Error while getting session")
            return

    except Exception as e:
        print(e)
        return

    time.sleep(1.5 + random.random() * 2)

    for asin in asins:
        asin_norm = _normalize_asin(asin)
        if not _is_valid_asin(asin_norm):
            print(f"({account.email}) · Skipping invalid ASIN: {asin!r}")
            continue

        print(f"({account.email}) · Getting raffle details...")

        # Make sure to get the right offer/listing by amazon
        response = session.get(
            f"https://www.amazon.fr/dp/{asin_norm}?m=A1X6FK5RDHNB96",
            headers=DEFAULT_HEADERS,
            proxies=proxies,
        )
        if response.status_code != 200:
            print(f"({account.email}) · Error while getting raffle details...")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        if not soup.find("input", {"name": "submit.inviteButton"}):
            print(f"({account.email}) · There is no raffle available for this product or already in ({asin_norm})")
            time.sleep(1.5 + random.random() * 2)
            continue

        encrypted_slate_token_elt = soup.find("meta", {"name": "encrypted-slate-token"})
        csrf_token_elt = soup.find("input", {"id": "hdp-ib-csrf-token"})
        endpoint_elt = soup.find("input", {"id": "hdp-ib-ajax-endpoint"})

        title_elt = soup.find("span", {"id": "productTitle"})
        image_elt = soup.find("img", {"id": "landingImage"})

        product_title = title_elt.text.strip() if title_elt else "N/A"
        product_image = (
            image_elt.get("src")
            if image_elt and image_elt.get("src")
            else "https://i.ibb.co/Y4SwwjKC/amazon.png"
        )

        if not encrypted_slate_token_elt or not csrf_token_elt or not endpoint_elt:
            print(f"({account.email}) · Error while getting raffle details...")
            time.sleep(1.5 + random.random() * 2)
            continue

        time.sleep(1.5 + random.random() * 2)

        print(f"({account.email}) · Submitting entry...")

        response = session.post(
            f"https://{endpoint_elt.get('value')}",
            headers={
                **DEFAULT_HEADERS,
                "Accept": 'application/vnd.com.amazon.api+json; type="aapi.highdemandproductcontracts.request-invite/v1"',
                "Accept-Language": "fr-FR",
                "Connection": "keep-alive",
                "Content-Type": 'application/vnd.com.amazon.api+json; type="aapi.highdemandproductcontracts.request-invite.request/v1"',
                "Origin": "https://www.amazon.fr",
                "Referer": "https://www.amazon.fr/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
                "Sec-GPC": "1",
                "x-amzn-encrypted-slate-token": encrypted_slate_token_elt.get("content"),
                "x-api-csrf-token": csrf_token_elt.get("value"),
            },
            data="{}",
            proxies=proxies,
        )

        if response.status_code == 200:
            print(f"({account.email}) · Successfully entered the raffle")

            discord.entries.send_private_webhook_entries(account, product_title, product_image, asin_norm)
        else:
            print(f"({account.email}) · Error while entering raffle")

        time.sleep(1.5 + random.random() * 2)
