"""Discord embed payloads for raffle entry events."""

from __future__ import annotations

from datetime import datetime, timezone

from amazon.amazonAccount import AmazonAccount
from discord import client


def _truncate(text: str, max_len: int) -> str:
    """Truncate a string with an ellipsis if needed.

    Args:
        text: Input string.
        max_len: Maximum length of the returned string.

    Returns:
        The original text if it fits, otherwise a shortened version ending with "...".
    """
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return f"{text[: max_len - 3]}..."


def send_private_webhook_entries(
    account: AmazonAccount,
    product_name: str,
    product_img: str,
    product_asin: str,
) -> None:
    """Send a Discord webhook embed for a successful raffle entry.

    Args:
        account: Account used to submit the raffle entry.
        product_name: Product display name.
        product_img: Product image URL.
        product_asin: ASIN entered.
    """
    payload = {
        "username": "Pearl Solutions",
        "avatar_url": "https://i.ibb.co/fdYpNgWC/Pearl-Solutions-Tavola-disegno-1-03.png",
        "embeds": [
            {
                "title": ":tada: Successfully entered the raffle",
                "url": f"https://www.amazon.fr/dp/{product_asin}?pearl=solutions",
                "color": 0xFFFFFF,
                "description": f"- {_truncate(product_name, 40)}",
                "fields": [
                    {"name": "`Merchant`", "value": "Amazon FR", "inline": True},
                    {"name": "`Asin`", "value": product_asin, "inline": True},
                    {"name": "`Email`", "value": f"||{account.get_email()}||", "inline": False},
                ],
                "thumbnail": {"url": product_img},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {
                    "text": "Pearl Solutions",
                    "icon_url": "https://i.ibb.co/fdYpNgWC/Pearl-Solutions-Tavola-disegno-1-03.png",
                },
            }
        ],
    }

    # Queue payload for background sending (rate-limit safe).
    client.add_payload(payload)