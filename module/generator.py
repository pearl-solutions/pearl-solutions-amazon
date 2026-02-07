import queue
import random
import threading
from typing import Optional

import requests

from amazon.amazonAccount import generate_account, load_all_accounts
from amazon.amazonImap import AmazonEmailManager
from amazon.amazonSms import AmazonSmsManagerPool
from utils.config import load_config
from utils.title import print_title


def generate_handler() -> None:
    """CLI entry-point to generate Amazon accounts.

    Steps:
        1) Load config and display title.
        2) Ask for email/proxy input files.
        3) Ask for generation parameters (threads, amount, password).
        4) Remove already-used emails/proxies based on saved accounts.
        5) Run the threaded generation pipeline.
    """
    config = load_config()
    print_title()
    print("")

    email_file = input("Please drag and drop your email file: ")
    try:
        with open(email_file, "r", encoding="utf-8") as file:
            emails = [line.rstrip() for line in file if line.strip()]
        if not emails:
            print("Error while loading email file (no emails)")
            return
    except FileNotFoundError:
        print("Error while loading email file (no file)")
        return

    proxy_file = input("Please drag and drop your proxy file: ")
    try:
        with open(proxy_file, "r", encoding="utf-8") as file:
            proxies = [line.rstrip() for line in file if line.strip()]
        if not proxies:
            print("Error while loading proxy file (no proxies)")
            return
    except FileNotFoundError:
        print("Error while loading proxy file (no file)")
        return

    while True:
        thread_count = input("Please enter the number of threads: ")
        try:
            thread_count = int(thread_count)
            if thread_count <= 0:
                raise ValueError
            break
        except ValueError:
            print("Please enter a positive integer")

    while True:
        amount = input("Please enter the number of accounts you want to generate: ")
        try:
            amount = int(amount)
            if amount <= 0:
                raise ValueError
            break
        except ValueError:
            print("Please enter a positive integer")

    password = input("Please enter the password for the accounts: ")

    # Avoid reusing resources that are already stored in local accounts.
    proxies = remove_used_proxies(proxies)
    emails = remove_used_email(emails)

    imap_manager = AmazonEmailManager(
        imap_server=config["imap"]["server"],
        email_address=config["imap"]["email"],
        password=config["imap"]["password"],
    )
    sms_manager = AmazonSmsManagerPool(config["sms_pool"])

    main(emails, password, proxies, amount, thread_count, imap_manager, sms_manager)


def remove_used_proxies(proxies: list[str]) -> list[str]:
    """Filter out proxies already used by existing saved accounts.

    Args:
        proxies: Proxy lines (expected format: 'ip:port:user:pass').

    Returns:
        A new list containing only proxies not already used.
    """
    accounts = load_all_accounts()
    used = {account.proxy for account in accounts if getattr(account, "proxy", None)}
    return [proxy for proxy in proxies if proxy not in used]


def remove_used_email(emails: list[str]) -> list[str]:
    """Filter out emails already used by existing saved accounts.

    Args:
        emails: Email list to process.

    Returns:
        A new list containing only emails not already used.
    """
    accounts = load_all_accounts()
    used = {account.email for account in accounts if getattr(account, "email", None)}
    return [email for email in emails if email not in used]


def is_proxy_valid(proxy: str, timeout: int = 4) -> bool:
    """Quickly check whether a proxy can reach Amazon.

    Notes:
        This is a lightweight health-check to skip dead proxies early.
        It does not guarantee the proxy will work for account creation.

    Args:
        proxy: Proxy string in the format 'ip:port:user:pass'.
        timeout: Timeout for the HTTP request in seconds.

    Returns:
        True if the test request returns HTTP 200, otherwise False.
    """
    try:
        formatted_proxy = format_proxy(proxy)
        response = requests.get("https://www.amazon.fr/", timeout=timeout, proxies=formatted_proxy)
        return response.status_code == 200
    except Exception:
        # Any exception indicates the proxy is not usable for this quick test.
        return False


def format_proxy(proxy: str) -> dict[str, str]:
    """Convert a proxy string into a `requests` proxies dictionary.

    Args:
        proxy: Proxy string in the format 'ip:port:user:pass'.

    Returns:
        Dict compatible with `requests`, containing both "http" and "https".

    Raises:
        ValueError: If the proxy string does not match the expected format.
    """
    ip, port, user, password = proxy.split(":")
    uri = f"http://{user}:{password}@{ip}:{port}"
    return {"http": uri, "https": uri}


def _safe_proxy_label(proxy: str) -> str:
    """Return a safe-to-log proxy label without credentials.

    Args:
        proxy: Proxy string in the format 'ip:port:user:pass'.

    Returns:
        Redacted label (e.g. 'ip:port') suitable for logs/GitHub.
    """
    parts = proxy.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return "<invalid-proxy>"


def worker(
    semaphore: threading.BoundedSemaphore,
    email_queue: queue.Queue,
    proxy_queue: queue.Queue,
    password: str,
    imap_manager: AmazonEmailManager,
    sms_manager: AmazonSmsManagerPool,
) -> None:
    """Worker thread: takes one email and one valid proxy, then generates an account.

    Args:
        semaphore: Concurrency limiter.
        email_queue: Queue containing emails to process.
        proxy_queue: Queue containing proxies to test/consume.
        password: Password used for generated accounts.
        imap_manager: IMAP manager used to read verification emails.
        sms_manager: SMS manager used to receive verification codes.
    """
    with semaphore:
        try:
            email = email_queue.get_nowait()
        except queue.Empty:
            return

        proxy: Optional[str] = None

        # Consume proxies until we find one that passes the health-check.
        while not proxy_queue.empty():
            candidate = proxy_queue.get_nowait()
            if is_proxy_valid(candidate):
                proxy = candidate
                break

            print(f"Proxy skipped (timeout): {_safe_proxy_label(candidate)}")

        if proxy is None:
            print("No valid proxy available, skipping account")
            email_queue.task_done()
            return

        try:
            generate_account(email, password, proxy, imap_manager, sms_manager)
        finally:
            # Always mark as done to avoid blocking the queue in case of errors.
            email_queue.task_done()


def main(
    emails: list[str],
    password: str,
    proxies: list[str],
    amount: int,
    max_threads: int,
    imap_manager: AmazonEmailManager,
    sms_manager: AmazonSmsManagerPool,
) -> None:
    """Run the threaded generation process.

    Args:
        emails: Emails to use (only the first `amount` will be consumed).
        password: Password for created accounts.
        proxies: Proxies to rotate through.
        amount: Number of accounts to generate.
        max_threads: Maximum number of concurrent threads.
        imap_manager: Shared IMAP manager instance.
        sms_manager: Shared SMS manager instance.
    """
    semaphore = threading.BoundedSemaphore(max_threads)

    # Randomize to distribute domains/proxies and reduce repeated patterns.
    random.shuffle(emails)
    random.shuffle(proxies)

    email_queue: queue.Queue[str] = queue.Queue()
    proxy_queue: queue.Queue[str] = queue.Queue()

    for email in emails[:amount]:
        email_queue.put_nowait(email)

    for proxy in proxies:
        proxy_queue.put_nowait(proxy)

    threads: list[threading.Thread] = []
    for _ in range(amount):
        thread = threading.Thread(
            target=worker,
            args=(semaphore, email_queue, proxy_queue, password, imap_manager, sms_manager),
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

