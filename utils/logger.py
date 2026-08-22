"""
Application-wide logging configuration supporting verbose debugging (-v / --verbose).
"""

import logging
import sys

LOGGER_NAME = "szenergypro"


def setup_logging(verbose: bool = False) -> logging.Logger:
    """
    Configures root and application logger based on the verbose command line flag.
    - verbose=True: Logs DEBUG, INFO, WARNING, and ERROR with timestamps and module names.
    - verbose=False: Logs only WARNING and ERROR to keep terminal output clean by default.
    """
    level = logging.DEBUG if verbose else logging.WARNING

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear pre-existing handlers to prevent duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Suppress verbose noisy third-party loggers
    logging.getLogger("nptdms").setLevel(logging.WARNING)

    logger = logging.getLogger(LOGGER_NAME)
    if verbose:
        logger.debug("Verbose debug logging enabled (-v)")

    return logger
