"""Itential SSoT Job Logger fixtures."""

import logging


class Logger:
    """Logger."""

    def info(self, msg: str):
        """Info logging."""
        logging.info(msg)

    def warning(self, msg: str):
        """Warning logging."""
        logging.warning(msg)

    def failure(self, msg: str):
        """Failure logging."""
        logging.error(msg)


class JobLogger:
    """Job Logger."""

    def __init__(self):
        self.logger = Logger()
