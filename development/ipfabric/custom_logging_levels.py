"""Custom_loggin_levels.py.

Override logging level for specific modules.
Relies on PYTHONSTARTUP="custom_loggin_levels.py" in environment
to run automatically when a python shell is started.
"""

import logging

logging.getLogger("parso").setLevel(logging.INFO)
