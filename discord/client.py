"""Discord webhook client initialization.

This module exposes a single `client` instance configured from `config.json`.
"""

from __future__ import annotations

import utils.config
from discord.webhook import WebhookClient


def _build_webhook_client() -> WebhookClient:
    """Create the WebhookClient using the configured webhook URL.

    Returns:
        A WebhookClient instance. If the webhook is empty, the client will still
        be created, but sending will fail at runtime with a clear error.
    """
    config = utils.config.load_config()
    webhook_url = config.get("webhook") or ""
    return WebhookClient(webhook_url)


client = _build_webhook_client()