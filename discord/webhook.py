"""Lightweight Discord webhook client with rate-limit handling.

Design:
- A background worker thread drains a queue of payloads.
- Sends are serialized with a lock to avoid concurrent rate-limit collisions.
- 429 responses are handled with a retry-after delay.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Optional

import requests


class RateLimitError(Exception):
    """Raised when Discord returns HTTP 429 (rate limited)."""

    def __init__(self, retry_after: float, global_limit: bool):
        """
        Args:
            retry_after: Seconds to wait before retrying.
            global_limit: Whether the rate limit is global.
        """
        self.retry_after = retry_after
        self.global_limit = global_limit
        super().__init__(f"rate limited, retry after {retry_after:.2f}s")


class WebhookClient:
    """Background-threaded webhook sender with basic retry semantics."""

    def __init__(self, webhook_url: str, queue_size: int = 10_000) -> None:
        """Create a new webhook client.

        Args:
            webhook_url: Discord webhook URL.
            queue_size: Maximum number of pending payloads in memory.

        Notes:
            The worker thread is started immediately.
        """
        self.url = webhook_url
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=queue_size)
        self.session = requests.Session()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def add_payload(self, payload: dict[str, Any], files: Optional[list[dict[str, Any]]] = None) -> None:
        """Enqueue a payload to be sent to Discord.

        Args:
            payload: JSON-serializable Discord webhook payload.
            files: Optional list of file dicts: {"name": str, "content": bytes}.
        """
        item = dict(payload)  # avoid mutating caller payload
        if files:
            item["_files"] = files
        self.queue.put(item)

    def _worker(self) -> None:
        """Worker loop: pop payloads and send them until stopped."""
        while not self.stop_event.is_set():
            try:
                payload = self.queue.get(timeout=0.01)
            except queue.Empty:
                continue

            try:
                self._send_with_retry(payload)
            finally:
                self.queue.task_done()

    def _send_with_retry(self, payload: dict[str, Any], max_retries: int = 5) -> None:
        """Send a payload with rate-limit aware retries.

        Args:
            payload: Payload dictionary (may include internal `_files`).
            max_retries: Maximum number of retries on rate limit.
        """
        retries = 0
        while retries < max_retries:
            try:
                self._send(payload)
                return
            except RateLimitError as exc:
                time.sleep(exc.retry_after)
                retries += 1
            except Exception:
                # Fail fast on unexpected errors (invalid webhook, payload, network issues, etc.).
                return

    def _send(self, payload: dict[str, Any]) -> None:
        """Send a payload using either JSON or multipart encoding."""
        with self.lock:
            files = payload.get("_files")
            if files:
                self._send_multipart(payload, files)
            else:
                self._send_json(payload)

    def _send_json(self, payload: dict[str, Any]) -> None:
        """Send a JSON webhook request."""
        clean_payload = dict(payload)
        clean_payload.pop("_files", None)

        resp = self.session.post(self.url, json=clean_payload, timeout=15)
        self._handle_response(resp)

    def _send_multipart(self, payload: dict[str, Any], files: list[dict[str, Any]]) -> None:
        """Send a multipart webhook request with file attachments."""
        clean_payload = dict(payload)
        clean_payload.pop("_files", None)

        multipart_files: dict[str, tuple[str, Any]] = {}
        for i, f in enumerate(files):
            multipart_files[f"file{i}"] = (f["name"], f["content"])

        resp = self.session.post(
            self.url,
            data={"payload_json": json.dumps(clean_payload)},
            files=multipart_files,
            timeout=15,
        )
        self._handle_response(resp)

    def _handle_response(self, resp: requests.Response) -> None:
        """Interpret Discord webhook responses and raise on error."""
        if resp.status_code == 429:
            data = resp.json()
            raise RateLimitError(
                retry_after=float(data.get("retry_after", 1.0)),
                global_limit=bool(data.get("global", False)),
            )

        if not (200 <= resp.status_code < 300):
            raise RuntimeError(f"webhook failed {resp.status_code}: {resp.text}")

    def stop(self) -> None:
        """Stop the background worker thread and wait for it to exit."""
        self.stop_event.set()
        self.worker_thread.join()

    def queue_size(self) -> int:
        """Return the current number of queued payloads."""
        return self.queue.qsize()
