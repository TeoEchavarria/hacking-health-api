import logging
import sys
from typing import Any

def setup_logging() -> None:
    """
    Configure the global logging settings.
    """
    # Define the format
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure the root logger
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Adjust uvicorn loggers
    # We want to keep uvicorn.error but might want to silence uvicorn.access
    # if we are doing our own request logging to avoid duplicates.
    # For now, let's keep them but they will follow the root config format.
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers = []
    uvicorn_access_logger.propagate = True

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
