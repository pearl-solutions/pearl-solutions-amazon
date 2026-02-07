import time
from itertools import cycle
from shutil import get_terminal_size
from threading import Thread
from time import sleep
from typing import Optional, Type


class Loader:
    """Terminal spinner/loader implemented as a context manager.

    Example:
        >>> with Loader("Generating account..."):
        ...     long_running_task()

    Notes:
        - The spinner runs in a daemon thread and stops automatically when the
          context exits.
        - Use :meth:`stop` if you need to stop it manually.
    """

    def __init__(self, desc: str = "Loading...", timeout: float = 0.1) -> None:
        """Create a new loader.

        Args:
            desc: Text displayed before the spinner.
            timeout: Delay (in seconds) between spinner frames.
        """
        self.desc = desc
        self.timeout = timeout

        self.steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
        self.done = False
        self._thread = Thread(target=self._animate, daemon=True)

    def start(self) -> "Loader":
        """Start the spinner thread.

        Returns:
            Self, allowing fluent usage.
        """
        self._thread.start()
        return self

    def _animate(self) -> None:
        """Continuously print spinner frames until :attr:`done` becomes True."""
        for c in cycle(self.steps):
            if self.done:
                break
            print(f"\r{self.desc} {c}", flush=True, end="")
            sleep(self.timeout)

    def __enter__(self) -> "Loader":
        """Enter the context and start the spinner.

        Returns:
            Self, in case the caller wants to keep a reference.
        """
        return self.start()

    def stop(self) -> None:
        """Stop the spinner and clear the current terminal line."""
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + (" " * cols), end="", flush=True)

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        tb,
    ) -> None:
        """Exit the context and stop the spinner.

        Args:
            exc_type: Exception type if an exception occurred, else None.
            exc_value: Exception instance if an exception occurred, else None.
            tb: Traceback if an exception occurred, else None.
        """
        self.stop()


def wait(seconds: float = 2.0) -> None:
    """Sleep for a short period (utility helper used by CLI flows).

    Args:
        seconds: Duration to sleep in seconds.
    """
    time.sleep(seconds)