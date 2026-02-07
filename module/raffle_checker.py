import csv
import datetime
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from bs4 import BeautifulSoup

import amazon.amazonAccount
from amazon.amazonAccount import AmazonAccount
from utils.config import load_config
from utils.loader import Loader
from utils.title import print_title


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
    "Gecko/20100101 Firefox/135.0"
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}


def check_raffle(account: AmazonAccount, asins: list[str]) -> dict[str, dict[str, str]]:
    """Check raffle availability for a set of ASINs for a given account.

    The check works by:
        1) Opening amazon.fr home page using the account session + proxy.
        2) Searching for items matching the ASINs.
        3) Parsing the result list and collecting items that appear available.

    Args:
        account: Amazon account instance.
        asins: List of ASIN strings to search for.

    Returns:
        A mapping keyed by ASIN containing:
            - image: image URL
            - name: product name
            - link: product URL (amazon.fr/dp/<asin>)
        Returns an empty dict if the session is invalid or requests fail.
    """
    session = account.get_session_with_cookies()
    proxies = amazon.amazonAccount.proxy_string_to_dict(account.get_proxy())

    response = session.get(
        "https://amazon.fr/",
        headers=DEFAULT_HEADERS,
        proxies=proxies,
    )
    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    tag = soup.find("span", id="nav-link-accountList-nav-line-1")

    # Defensive: if we can't confirm the account is logged in, bail out.
    # (Keep same behavior intent, but avoid accessing `tag.text` when tag is None.)
    if not tag or ("vous" in tag.text):
        return {}

    # Small randomized delay to reduce hammering in parallel runs.
    time.sleep(random.random())

    # Build the query exactly as before, but more efficiently and safely.
    search_query = "|".join(asins)
    search_query += "&rh=p_6%3AA1X6FK5RDHNB96"

    response = session.get(
        f"https://www.amazon.fr/s?k={search_query}",
        headers=DEFAULT_HEADERS,
        proxies=proxies,
    )
    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.find_all("div", role="listitem")

    available: dict[str, dict[str, str]] = {}

    for div in items:
        item_asin = div.get("data-asin")
        price_span = div.find("span", class_="a-size-base a-color-price")
        img_tag = div.find("img", class_="s-image")

        if not item_asin or not img_tag or not price_span or not img_tag.get("src"):
            continue

        # Keep the same detection logic used previously.
        if "vous" in price_span.text:
            available.setdefault(item_asin, {})
            available[item_asin]["image"] = img_tag.get("src")
            available[item_asin]["name"] = img_tag.get("alt") or ""
            available[item_asin]["link"] = f"https://www.amazon.fr/dp/{item_asin}"

    return available


def check_raffle_manager() -> None:
    """Interactive CLI manager for checking raffles across ASINs and accounts.

    The flow allows:
        - checking all ASINs or a selected one
        - checking all accounts in parallel or a single selected account
        - exporting results to a timestamped CSV file
    """
    config = load_config()
    asins: list[str] = config["amazon_asins"]

    print_title()
    print("")

    if len(asins) == 0:
        print("No asins loaded")
        time.sleep(3)
        return

    choice = input("Whould you like to check raffles for all asins? (y/n) ").lower()
    if choice == "n":
        print("")
        for a in asins:
            print(f" - {a}")
        print("")
        selected_asin = input("Enter the ASIN you want to check raffles for: ")
        asins = [selected_asin]

    choice = input("Whould you like to check raffles for all accounts? (y/n) ").lower()
    if choice == "y":
        loader = Loader("Getting invitations...", 0.05).start()
        invitations = get_invitations_parallel(asins)
        loader.stop()

        save_invitations_csv(invitations)
        print("Raffle check completed for all accounts. Please check the latest invitations.csv file.")
        print(f"We found {len([email for email in invitations if invitations[email] != {}])} invitations.")
        return

    while True:
        accounts = amazon.amazonAccount.load_all_accounts()
        print("Select an account to check raffles:")
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

        if not (1 <= choice_int <= len(accounts)):
            print("Invalid choice. Please try again.")
            continue

        selected_account = accounts[choice_int - 1]
        loader = Loader("Getting invitations...", 0.05).start()
        invitations = check_raffle(selected_account, asins)
        loader.stop()

        save_invitations_csv({selected_account.email: invitations})
        print(f"Raffle check completed for {selected_account.email}. Please check the latest invitations.csv file.")
        print(f"We found {len([asin for asin in invitations if invitations[asin] != {}])} invitations.")
        break


def get_invitations_parallel(asins: list[str]) -> dict[str, dict[str, dict[str, str]]]:
    """Check raffles for all saved accounts in parallel.

    Args:
        asins: List of ASINs to check.

    Returns:
        Dict mapping account email -> availability dict returned by :func:`check_raffle`.
    """
    accounts = amazon.amazonAccount.load_all_accounts()
    invitations: dict[str, dict[str, dict[str, str]]] = {}

    # Keep the existing cap of 20 workers, but avoid max_workers=0.
    max_workers = max(1, min(20, len(accounts)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_account = {
            executor.submit(check_raffle, account, asins): account
            for account in accounts
        }

        for future in as_completed(future_to_account):
            account = future_to_account[future]
            try:
                invitations[account.email] = future.result()
            except Exception:
                # Best-effort aggregation: skip accounts that fail.
                pass

    return invitations


def save_invitations_csv(invitations: dict[str, dict[str, dict[str, str]]]) -> None:
    """Save invitation results to a timestamped CSV file.

    Args:
        invitations: Mapping of email -> items mapping (asin -> item data).
    """
    filename = f"invitations-{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.csv"
    with open(filename, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["email", "item", "link", "asin"])

        for email_addr, data_inv in invitations.items():
            for asin, item_data in data_inv.items():
                name = (item_data.get("name") or "").replace("\u202f", " ")
                writer.writerow([email_addr, name, item_data.get("link") or "", asin])