import random
import time
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


def entry_raffle_manager():
    config = load_config()
    asins: list[str] = config["amazon_asins"]

    print_title()
    print("")

    if len(asins) == 0:
        print("No asins loaded")
        time.sleep(3)
        return

    choice = input("Whould you like to enter raffles for all asins? (y/n) ").lower()
    if choice == "n":
        selected_asin = input("Enter the ASIN you want to enter raffles for: ").strip()
        # Keep the original behavior: allow entering an ASIN even if it's not in config.
        asins = [selected_asin]

    choice = input("Whould you like to enter raffles for all accounts? (y/n) ").lower()
    if choice == "y":
        print("")
        accounts = amazonAccount.load_all_accounts()
        enter_raffles(asins, accounts)
        return

    while True:
        accounts = amazonAccount.load_all_accounts()
        print("Select an account to enter raffles:")
        print("")
        for i, account in enumerate(accounts, 1):
            print(f" ({i}) {account.email}")
        print(f" ({len(accounts) + 1}) Return")

        try:
            choice_int = int(input("\nPlease enter your choice : "))
        except ValueError:
            print("Invalid choice. Please try again.")
            continue

        if choice_int == len(accounts) + 1:
            break

        if 1 <= choice_int <= len(accounts):
            selected_account = accounts[choice_int - 1]
            print("")
            enter_raffles(asins, [selected_account])
            break

        print("Invalid choice. Please try again.")


def enter_raffles(asins: list[str], accounts: list[AmazonAccount], max_workers: int = 5) -> None:
    """Enter raffles for multiple accounts concurrently.

    Args:
        asins: List of ASINs to enter.
        accounts: Accounts to use for entry.
        max_workers: Maximum number of concurrent threads.
    """
    if not accounts or not asins:
        return

    max_workers = max(1, min(max_workers, len(accounts)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_account, account, asins) for account in accounts]
        for _ in as_completed(futures):
            # Best-effort: we only wait for completion. Errors are handled per task.
            pass


def process_account(account: AmazonAccount, asins: list[str]) -> None:
    """Process a single account: validate session and submit raffle entries.

    Args:
        account: Amazon account object.
        asins: List of ASINs to process.
    """
    session = account.get_session_with_cookies()
    proxies = amazonAccount.proxy_string_to_dict(account.get_proxy())

    start = time.time()

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
        print(f"({account.email}) · Getting raffle details...")

        response = session.get(
            f"https://www.amazon.fr/dp/{asin}?m=A1X6FK5RDHNB96",
            headers=DEFAULT_HEADERS,
            proxies=proxies,
        )
        if response.status_code != 200:
            print(f"({account.email}) · Error while getting raffle details...")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        if not soup.find("input", {"name": "submit.inviteButton"}):
            print(f"({account.email}) · There is no raffle available for this product or already in ({asin})")
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

            discord.entries.send_private_webhook_entries(account, product_title, product_image, asin)
        else:
            print(f"({account.email}) · Error while entering raffle")

        time.sleep(1.5 + random.random() * 2)
