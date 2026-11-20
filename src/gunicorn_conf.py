"""Gunicorn configuration: route the server's own logging to the standard.

Gunicorn's master writes its start-up lines to stderr before any worker
imports the application, and the uvicorn worker copies gunicorn's error-log
handlers onto its own logger. So the application cannot reach those lines
from inside; this file, which gunicorn reads before it starts, can. The
platform counted seven of them on stderr at 0.19.0, and they were exactly
these. `src/logging_standard.py` holds the format and the reasoning.
"""

from __future__ import annotations

import pathlib
import sys

# Gunicorn executes this file before it has put the working directory on the
# import path, so the repository root is added here, explicitly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Imported under its own name, never as `logconfig`: gunicorn reads every
# top-level name in this file that matches one of its settings, and
# `logconfig` is one (a path to a logging config file). Found by running it.
from src.logging_standard import server_logconfig

logconfig_dict = server_logconfig()

# Requests are logged by the application, with the caller's request id. A
# gunicorn access log as well would write every request twice, once without
# the id.
accesslog = None
