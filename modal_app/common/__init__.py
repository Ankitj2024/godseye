"""Shared worker plumbing.

Intentionally free of imports: submodules here are imported explicitly by the
code that needs them. That keeps pure logic (for example the COLMAP output
parsers) importable and testable without pulling in the Modal client.
"""
