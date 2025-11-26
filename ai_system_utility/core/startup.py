# ai_system_utility/core/startup.py

"""
Startup/auto-run helpers for AI System Utility.

This module manages an optional "Start tray agent with Windows" feature
using the Windows Run registry key under the current user:

    HKCU\Software\Microsoft\Windows\CurrentVersion\Run

It is Windows-only. On non-Windows platforms the functions either do
nothing or report that the feature is not supported.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from .logger import get_logger

logger = get_logger("startup")

try:
    if os.name == "nt":
        import winreg  # type: ignore[import-not-found]
    else:
        winreg = None  # type: ignore[assignment]
except Exception:  # very defensive
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AI_System_Utility_Tray"


def _get_pythonw_command() -> str:
    """
    Builds the command that will be stored in the Run key.

    Example:
        "C:\Path\To\pythonw.exe" -m ai_system_utility.tray_agent
    """
    exe = sys.executable
    exe_lower = exe.lower()

    # Prefer pythonw.exe if available (no console window)
    if exe_lower.endswith("python.exe"):
        pythonw = exe[:-10] + "pythonw.exe"  # strip "python.exe"
        if os.path.exists(pythonw):
            exe = pythonw

    cmd = f'"{exe}" -m ai_system_utility.tray_agent'
    return cmd


def is_tray_autostart_supported() -> bool:
    """
    Returns True if this platform supports tray auto-start (Windows + winreg).
    """
    return os.name == "nt" and winreg is not None


def is_tray_autostart_enabled() -> bool:
    """
    Returns True if the Run key entry for the tray agent exists.
    """
    if not is_tray_autostart_supported():
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:  # type: ignore[attr-defined]
            try:
                value, _ = winreg.QueryValueEx(key, VALUE_NAME)  # type: ignore[attr-defined]
            except FileNotFoundError:
                return False
            except Exception as e:
                logger.warning("Failed to query Run key value '%s': %s", VALUE_NAME, e)
                return False
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning("Failed to open Run key: %s", e)
        return False

    if not isinstance(value, str):
        return False

    # Heuristic: our command should contain the module name.
    return "ai_system_utility.tray_agent" in value


def enable_tray_autostart() -> None:
    """
    Creates or updates the Run key value to start the tray agent at login.
    """
    if not is_tray_autostart_supported():
        raise RuntimeError("Tray auto-start is not supported on this platform.")

    cmd = _get_pythonw_command()
    logger.info("Enabling tray auto-start with command: %s", cmd)

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:  # type: ignore[attr-defined]
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)  # type: ignore[attr-defined]
    except Exception as e:
        logger.error("Failed to set Run key value '%s': %s", VALUE_NAME, e)
        raise RuntimeError(f"Failed to enable tray auto-start: {e}") from e


def disable_tray_autostart() -> None:
    """
    Removes the Run key value so the tray agent does not start at login.
    """
    if not is_tray_autostart_supported():
        raise RuntimeError("Tray auto-start is not supported on this platform.")

    logger.info("Disabling tray auto-start (removing Run key value).")

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:  # type: ignore[attr-defined]
            try:
                winreg.DeleteValue(key, VALUE_NAME)  # type: ignore[attr-defined]
            except FileNotFoundError:
                # Already not present
                return
    except FileNotFoundError:
        # Run key itself missing: nothing to do
        return
    except Exception as e:
        logger.error("Failed to delete Run key value '%s': %s", VALUE_NAME, e)
        raise RuntimeError(f"Failed to disable tray auto-start: {e}") from e
