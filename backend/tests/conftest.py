"""Keep pytest off the live panel. The scheduler otherwise fires on startup."""

import os

os.environ["HTPP_DISABLE_SCHEDULER"] = "1"
