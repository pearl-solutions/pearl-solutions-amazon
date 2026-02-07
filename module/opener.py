import amazon.amazonAccount
from utils.title import print_title


def display_menu(accounts: list) -> None:
    """Render the account selection menu.

    Args:
        accounts: List of account objects (must expose an `email` attribute).
    """
    print_title()
    print("")

    for i, account in enumerate(accounts, 1):
        print(f"({i}) {account.email}")

    print(f"({len(accounts) + 1}) Return")


def get_user_choice(max_choice: int) -> int:
    """Prompt the user to select an integer choice within bounds.

    Args:
        max_choice: Maximum allowed choice (inclusive). Minimum is always 1.

    Returns:
        A validated integer choice in the range [1, max_choice].
    """
    while True:
        try:
            choice = int(input("\nPlease enter your choice : "))
            if 1 <= choice <= max_choice:
                return choice

            print("Invalid choice. Please try again.")
        except ValueError:
            print("Invalid choice. Please try again.")


def open_account() -> None:
    """Interactive flow to open an account browser tab for a selected account.

    Behavior:
        - Loads all saved accounts.
        - Lets the user pick an account to open.
        - Opens the tab and blocks until the tab is closed (handled by the account object).
        - Optionally repeats until the user stops.
    """
    accounts = amazon.amazonAccount.load_all_accounts()
    if not accounts:
        print("No accounts found.")
        return

    while True:
        display_menu(accounts)
        choice = get_user_choice(len(accounts) + 1)

        # "Return" option
        if choice == len(accounts) + 1:
            break

        selected_account = accounts[choice - 1]
        print(f"\nAccount selected: {selected_account.email}")
        print("Opening tab...\n")

        # Account object is expected to implement this method.
        selected_account.open_tab_till_close()

        continue_choice = input("\nWould you like to open another account ? (y/n) : ")
        if continue_choice.lower() != "y":
            break