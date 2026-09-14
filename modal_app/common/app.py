"""The shared ``modal.App`` instance.

This module holds nothing but the App so worker modules can import it without
creating a circular import with the deploy entrypoint (``modal_app/app.py``),
which imports the workers.
"""

from __future__ import annotations

import modal

from modal_app.common.config import APP_NAME

app = modal.App(APP_NAME)
