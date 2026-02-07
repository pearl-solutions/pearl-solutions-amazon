from typing import Optional

import amazon.amazonAccount
from utils.config import load_config


def print_menu() -> None:
    """Print the main CLI menu with a summary of loaded accounts and products."""
    config = load_config()
    accounts = amazon.amazonAccount.load_all_accounts()

    account_count = len(accounts)
    asin_count = len(config.get("amazon_asins", []))

    account_label = "" if account_count <= 1 else "s"
    asin_label = "" if asin_count <= 1 else "s"

    print("")
    print(
        "Welcome to our new Amazon accounts manager, "
        f"{account_count} account{account_label} loaded, "
        f"{asin_count} product{asin_label} loaded."
    )

    print("")
    print(" (1) Generate account")
    print(" (2) Open account browser")
    print(" (3) Enter raffle")
    print(" (4) Check for invitations")
    print(" (5) Settings")
    print(" (6) Exit")


def get_selection() -> Optional[int]:
    """Prompt the user for a menu selection.

    Returns:
        The selected option as an integer if parsing succeeds.
        This function keeps prompting until it gets an integer.
    """
    print("")
    while True:
        choice = input("Please select an option: ")
        try:
            return int(choice)
        except ValueError:
            # Non-numeric input: prompt again.
            continue