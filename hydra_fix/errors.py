"""Exceptions with user-facing meanings."""
from __future__ import annotations


class HydraFixError(Exception):
    """Base class for expected, actionable failures."""


class FatalError(HydraFixError):
    """The run cannot safely continue."""
