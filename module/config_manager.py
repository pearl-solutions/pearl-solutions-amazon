import time

from utils.config import load_config, save_config
from utils.title import print_title


def _safe_tail(value: str | None, tail: int = 20) -> str:
    """Return a safe shortened representation of a sensitive string.

    Args:
        value: Original string (possibly None).
        tail: Number of trailing characters to keep.

    Returns:
        "Not set" if value is falsy, otherwise a redacted value (e.g. "...abcd").
    """
    if not value:
        return "Not set"
    if len(value) <= tail:
        return value
    return f"...{value[-tail:]}"


def config_manager() -> None:
    """Interactive configuration menu (CLI).

    This menu displays a few key configuration values and provides access
    to product (ASIN) management.

    The function loops until the user chooses to return.
    """
    while True:
        config = load_config()

        print_title()
        print("")
        print(" (1) Manage products")
        print(" (2) Return")
        print("")
        print(" SMS Pool key: ", config.get("sms_pool", "Not set"))

        imap_cfg = config.get("imap") or {}
        print(" Imap email: ", imap_cfg.get("email", "Not set"))
        print(" Imap server: ", imap_cfg.get("server", "Not set"))

        # Avoid printing full webhook URL (sensitive value) to the terminal/logs.
        print(" Discord webhook: ", _safe_tail(config.get("webhook")))

        choice = input("\nPlease enter your choice : ")
        try:
            choice_int = int(choice)
        except ValueError:
            # Invalid input: re-render the menu.
            continue

        match choice_int:
            case 1:
                products_manager()
            case 2:
                break
            case _:
                print("Invalid choice. Please try again.")


def products_manager() -> None:
    """Interactive menu to view/add/remove Amazon ASINs from the config.

    The ASIN list is stored in the config under the key: "amazon_asins".
    Changes are persisted using :func:`utils.config.save_config`.
    """
    while True:
        print_title()
        print("")
        print(" (1) View current products")
        print(" (2) Add a new product")
        print(" (3) Remove a product")
        print(" (4) Return")

        choice = input("\nPlease enter your choice : ")
        try:
            choice_int = int(choice)
        except ValueError:
            # Invalid input: re-render the menu.
            continue

        match choice_int:
            case 1:
                config = load_config()
                print("\nCurrent products in configuration:\n")
                for item in config.get("amazon_asins", []):
                    print(f" - {item}")
                input("\nPress Enter to return to the menu...")

            case 2:
                config = load_config()
                new_product = input("\nEnter the new product ASIN: ").strip()

                # Validate user input before saving.
                if not new_product:
                    print("Invalid ASIN. Please try again.")
                    time.sleep(1)
                    continue

                asins = config.get("amazon_asins") or []
                if new_product in asins:
                    print("Product already exists in the configuration.")
                    time.sleep(1)
                    continue

                asins.append(new_product)
                config["amazon_asins"] = asins

                print(f"Adding product {new_product}...")
                save_config(config)
                time.sleep(1)

            case 3:
                config = load_config()
                asins = config.get("amazon_asins") or []

                print("\nCurrent products in configuration:\n")
                for i, item in enumerate(asins, 1):
                    print(f" ({i}) {item}")

                remove_choice = input("\nEnter the number of the product to remove: ")
                try:
                    remove_index = int(remove_choice)
                    if 1 <= remove_index <= len(asins):
                        removed_item = asins.pop(remove_index - 1)
                        config["amazon_asins"] = asins

                        print(f"Removing product {removed_item}...")
                        save_config(config)
                        time.sleep(1)
                    else:
                        print("Invalid choice. Please try again.")
                except ValueError:
                    print("Invalid choice. Please try again.")

            case 4:
                break

            case _:
                print("Invalid choice. Please try again.")