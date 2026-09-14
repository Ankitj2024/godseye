"""COLMAP-based exact reconstruction.

The Modal function lives in ``modal_app.reconstruction.worker`` and is registered
by ``modal_app/app.py``. It is deliberately not imported here so that
``modal_app.reconstruction.colmap`` (pure parsing/driver logic) can be imported
without the Modal client.
"""
