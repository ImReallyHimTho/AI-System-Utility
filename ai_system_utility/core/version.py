# ai_system_utility/core/version.py

"""
Version information for AI System Utility.

This module defines the application version in a single place.
Other modules (GUI, updater, etc.) should call get_version()
instead of hardcoding version strings.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Application version
# ---------------------------------------------------------------------------

# Bump this whenever you ship a new build.
# Example formats:
#   "1.0.0"
#   "1.1.0"
#   "2.0.0-beta1"
__version__ = "1.0.0"


def get_version() -> str:
    """
    Returns the current application version string.
    """
    return __version__
