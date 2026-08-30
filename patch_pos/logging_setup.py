"""Error/crash logging -- this is a packaged desktop app with no visible
terminal for the end user, so errors write to a log file (alongside the
catalog DB) in addition to being surfaced in-app. See
PROJECT_INSTRUCTIONS.md section 6, "Decision -- error/crash surfacing".
"""

import logging
from pathlib import Path

LOGGER_NAME = "patch_pos"


def data_dir_for_library(library_root: Path) -> Path:
    """Where the catalog DB, order history, and log file live -- a
    sibling folder to the scanned library root, on the same drive, so it
    travels with the drive across machines (section 8, step 3)."""
    return Path(library_root).parent / "patch_pos_data"


def configure_logging(data_dir: Path) -> logging.Logger:
    data_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)

    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        handler = logging.FileHandler(data_dir / "app.log")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
