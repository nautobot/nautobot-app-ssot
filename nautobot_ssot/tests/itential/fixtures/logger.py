"""Itential SSoT Job Logger fixtures."""

import logging


class JobLogger:
    """Job Logger."""

    def log_info(message: str):
        """Info logging."""
        logging.info(message)

    def log_warning(message: str):
        """Warning logging."""
        logging.warning(message)

    def log_failure(message: str):
        """Failure logging."""
        logging.error(message)
