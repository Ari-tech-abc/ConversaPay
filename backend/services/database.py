"""Compatibility helpers for PostgREST optional single-row responses."""
from types import SimpleNamespace


def optional_result(value):
    # postgrest 2.x returns None, rather than an object with data=None, on zero rows.
    return value if value is not None else SimpleNamespace(data=None, count=0)
