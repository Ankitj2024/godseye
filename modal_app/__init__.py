"""God's Eye Modal workers (the compute plane).

Deployed with::

    modal deploy modal_app/app.py

Note on the package name: this is ``modal_app/`` rather than ``modal/`` on
purpose. A top-level ``modal/`` directory in the repo root would shadow the
``modal`` pip package for anything run from the root, which would break the
client immediately.
"""
