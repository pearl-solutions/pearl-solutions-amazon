"""Discord embed payloads for account generation events."""

from __future__ import annotations

from datetime import datetime, timezone

from amazon.amazonAccount import AmazonAccount
from discord import client


def send_private_webhook_gen(
    account: AmazonAccount,
) -> None:
    """Send a Discord webhook embed for a successful account generation.

    Args:
        account: Generated account object.
    """
    payload = {
        "username": "Pearl Solutions",
        "avatar_url": "https://i.ibb.co/fdYpNgWC/Pearl-Solutions-Tavola-disegno-1-03.png",
        "embeds": [
            {
                "title": ":tada: Successfully generated an account!",
                "color": 0xFFFFFF,
                "fields": [
                    {"name": "`Email`", "value": f"||{account.get_email()}||", "inline": True},
                ],
                "thumbnail": {"url": "https://i.ibb.co/pjXR4QTc/amazon.jpg"},
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