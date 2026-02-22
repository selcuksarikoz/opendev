import logging
import os
from pathlib import Path

# Configure logger to write to log.txt in the project root
log_file = Path("log.txt").absolute()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # logging.FileHandler(log_file, mode='a', encoding='utf-8'),
    ]
)

logger = logging.getLogger("OpenDev")


def log_error(msg: str, exc: Exception = None):
    if exc:
        logger.exception(f"{msg}: {str(exc)}")
    else:
        logger.error(msg)


def log_debug(msg: str):
    logger.debug(msg)
