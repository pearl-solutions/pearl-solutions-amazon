import json
import os
import time
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "webhook": "",
    "sms_pool": "",
    "hero_sms": "",
    "imap": {
        "email": "",
        "password": "",
        "server": "",
        "port": 993,
    },
    "amazon_asins": [],
}


def load_config(path: str = "config.json") -> dict[str, Any]:
    """Load and validate the project configuration from a JSON file.

    Behavior:
        - If the config file does not exist, it is created with defaults and the
          program exits to force the user to fill it in.
        - If required top-level fields are missing/empty (except "amazon_asins"),
          the program prints the missing fields and exits.

    Notes:
        The current validation checks only top-level keys. Nested keys (e.g. imap
        email/password/server) are not validated here.

    Args:
        path: Path to the JSON config file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        json.JSONDecodeError: If the file exists but contains invalid JSON.
        OSError: If the file cannot be read/written.
    """
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)

        print(f"[!] Config file '{path}' was created. Please fill it in and restart the program.")
        time.sleep(5)
        raise SystemExit(1)

    with open(path, "r", encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)

    # Validate required top-level keys (excluding the product list).
    missing = [
        key
        for key, value in config.items()
        if (not value) and key != "amazon_asins" and key != "hero_sms"
    ]
    if missing:
        print("[!] The following required fields are missing in config.json:")
        for field in missing:
            print(f"   - {field}")
        print("[!] Please complete the file and restart the program.")
        time.sleep(5)
        raise SystemExit(1)

    return config


def save_config(config: dict[str, Any], path: str = "config.json") -> None:
    """Persist the given configuration to disk as pretty-printed JSON.

    Args:
        config: Configuration dictionary to write.
        path: Destination path for the JSON config file.

    Raises:
        OSError: If the file cannot be written.
        TypeError: If `config` contains non-JSON-serializable values.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)