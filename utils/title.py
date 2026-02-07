TITLE = (
    " ____  ____   __   ____  __   \n"
    "(  _ \\(  __) / _\\ (  _ \\(  )  \n"
    " ) __/ ) _) /    \\ )   // (_/\\\n"
    "(__)  (____)\\_/\\_/(__\\_)\\____/"
)


def print_title(version: str = "v1.0") -> None:
    """Clear the terminal and print the ASCII banner.

    Args:
        version: Version label appended to the title output.
    """
    # ANSI escape sequence: move cursor home + clear screen.
    print("\033[H\033[J", end="")
    print(f"{TITLE}    Solutions Amazon {version}")