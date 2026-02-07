import os


def load_proxies(filename: str = "proxies.txt") -> list[str]:
    """Load proxies from a text file (one proxy per line).

    Behavior:
        - If the file does not exist, it is created empty and an empty list
          is returned.

    Args:
        filename: Path to the proxy file.

    Returns:
        A list of non-empty, stripped proxy lines.
    """
    if not os.path.exists(filename):
        # Create an empty file so the user knows where to put proxies.
        with open(filename, "w", encoding="utf-8"):
            pass

    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]