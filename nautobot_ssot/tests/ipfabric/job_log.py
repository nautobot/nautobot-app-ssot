"""Reading back what a sync reported to the Job Result log.

The adapters, their models and the bulk write collector all report through the job's logger, which
is what reaches `JobLogEntry` and so what an operator sees. A test holds that logger as a mock, so
asserting on a message means asserting on the calls it was given.
"""

import unittest.mock


def job_logger():
    """Return a stand-in for a job's logger, to hand to whatever is under test."""
    return unittest.mock.MagicMock()


def job_log_text(logger, level):
    """Return the messages a job logger was given at `level`, as one string.

    Args:
        logger: The mock standing in for the job's logger.
        level: The level name to read, such as `warning`.
    """
    return " ".join(_formatted(call) for call in getattr(logger, level).call_args_list)


def _formatted(call):
    """Render one logging call the way a handler would, so lazy `%s` arguments read as text."""
    template, *args = call.args
    try:
        return template % tuple(args) if args else str(template)
    except (TypeError, ValueError):
        # A message whose arguments do not fit its template is still worth reading back.
        return " ".join(str(part) for part in call.args)
