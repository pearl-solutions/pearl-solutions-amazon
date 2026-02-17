"""Project entry-point (CLI menu loop).

This module:
- Loads and validates configuration
- Validates the license key and starts periodic re-validation
- Displays the interactive menu and dispatches user actions
"""

import time

import utils.config
import utils.menu
import utils.title
from module.config_manager import config_manager
from module.generator import generate_handler
from module.opener import open_account
from module.raffle_checker import check_raffle_manager
from module.raffle_entry import entry_raffle_manager

CURRENT_VERSION = "v1.0"


def run_cli() -> None:
    """Run the main interactive CLI loop.

    Notes:
        This function intentionally uses an infinite loop and relies on the user
        selecting "Exit" to terminate the program.
    """

    # Clear terminal once before entering the menu loop.
    print("\033[H\033[J", end="")

    while True:
        utils.title.print_title(CURRENT_VERSION)
        utils.menu.print_menu()

        choice = utils.menu.get_selection()

        match choice:
            case 1:
                generate_handler()
                time.sleep(1)
            case 2:
                open_account()
                time.sleep(1)
            case 3:
                entry_raffle_manager()
                time.sleep(1)
            case 4:
                check_raffle_manager()
                time.sleep(5)
            case 5:
                config_manager()
            case _:
                # Exit
                print("\033[H\033[J", end="")
                print("Thanks for using Pearl Solutions!")
                raise SystemExit(0)


if __name__ == "__main__":
    run_cli()