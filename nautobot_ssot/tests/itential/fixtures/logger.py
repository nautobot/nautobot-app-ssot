"""Itential SSoT Job Logger fixtures."""

import logging


class Logger:
    """Logger."""

    def info(self, message: str):
        """Info logging."""
        logging.info(message)

    def warning(self, message: str):
        """Warning logging."""
        logging.warning(message)

    def failure(self, message: str):
        """Failure logging."""
        logging.error(message)


class JobLogger:
    """Job Logger."""

    def __init__(self):
        self.logger = Logger()
