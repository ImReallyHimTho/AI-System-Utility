# ai_system_utility/core/privacy_tools.py

"""
Windows privacy tools for AI System Utility.

Implements 3 high-level profiles:
- Recommended privacy profile (safe defaults)
- Strict privacy profile (maximum privacy, may disable features)
- Restore privacy defaults (undo changes)

Settings are applied via Windows Registry.
Every change is logged and backed up in-memory per session.
"""

from __future__ import annotations

import winreg
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .logger import get_logger

logger = get_logger("privacy_tools")


# ---------------------------------------------------------------------------
# Registry helper layer
# ---------------------------------------------------------------------------


@dataclass
class RegSetting:
    """
    Represents a single registry setting.
    """
    root: int                      # e.g., winreg.HKEY_LOCAL_MACHINE
    path: str                      # registry path string
    name: str                      # value name
    value: int                     # DWORD value to set
    value_type: int = winreg.REG_DWORD


# In-memory backup so user can restore defaults.
_BACKUP: Dict[Tuple[int, str, str], Optional[int]] = {}


def _read_reg_value(root: int, path: str, name: str) -> Optional[int]:
    """
    Reads REG_DWORD from registry. Returns None if value does not exist.
    """
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
            v, _ = winreg.QueryValueEx(key, name)
            return int(v)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.debug("Failed to read registry value %s\\%s (%s): %s", path, name, root, e)
        return None


def _write_reg_value(root: int, path: str, name: str, value: int, value_type: int) -> None:
    """
    Writes registry key/value.
    Creates the key if it does not exist.
    """
    try:
        with winreg.CreateKey(root, path) as key:
            winreg.SetValueEx(key, name, 0, value_type, value)
    except Exception as e:
        logger.error("Failed to write registry value: %s\\%s = %s (%s)", path, name, value, root, e)
        raise RuntimeError(f"Failed to write registry: {path}\\{name} → {value} ({e})")


def _backup_setting(setting: RegSetting) -> None:
    """
    Backup original registry value once per session.
    """
    key = (setting.root, setting.path, setting.name)
    if key in _BACKUP:
        return  # already backed up

    original = _read_reg_value(setting.root, setting.path, setting.name)
    _BACKUP[key] = original
    logger.debug("Backed up %s\\%s: %s", setting.path, setting.name, original)


def _apply_setting(setting: RegSetting) -> str:
    """
    Apply one registry setting.
    Returns human-readable summary.
    """
    _backup_setting(setting)

    before = _read_reg_value(setting.root, setting.path, setting.name)
    _write_reg_value(
        setting.root,
        setting.path,
        setting.name,
        setting.value,
        setting.value_type,
    )
    after = _read_reg_value(setting.root, setting.path, setting.name)

    msg = f"{setting.path}\\{setting.name}: {before} → {after}"
    logger.info(msg)
    return msg


def _apply_settings(settings: List[RegSetting]) -> str:
    """
    Apply a group of registry settings and return a combined summary.
    """
    messages = []
    for s in settings:
        try:
            messages.append(_apply_setting(s))
        except Exception as e:
            logger.error("Failed to apply %s: %s", s, e)
            messages.append(f"ERROR: {s.path}\\{s.name}: {e}")
    return "\n".join(messages)


# ---------------------------------------------------------------------------
# Privacy Profiles
# ---------------------------------------------------------------------------

# === Recommended profile (balanced) ===
_RECOMMENDED_SETTINGS = [
    # Disable advertising ID
    RegSetting(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
        "Enabled",
        0,
    ),

    # Disable tailored experiences
    RegSetting(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Privacy",
        "TailoredExperiencesWithDiagnosticDataEnabled",
        0,
    ),

    # Disable app launch tracking
    RegSetting(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "Start_TrackProgs",
        0,
    ),

    # Limit background apps
    RegSetting(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
        "GlobalUserDisabled",
        1,
    ),

    # Disable location tracking
    RegSetting(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Services\lfsvc\Service\Configuration",
        "Status",
        0,
    ),
]

# === Strict profile (maximum privacy, may disable features) ===
_STRICT_SETTINGS = [
    *_RECOMMENDED_SETTINGS,

    # Disable telemetry (requires reboot)
    RegSetting(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
        "AllowTelemetry",
        0,
    ),

    # Disable Windows error reporting
    RegSetting(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\Windows Error Reporting",
        "Disabled",
        1,
    ),

    # Disable camera for apps
    RegSetting(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam",
        "Value",
        0,
        winreg.REG_SZ,  # string type
    ),

    # Disable microphone for apps
    RegSetting(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone",
        "Value",
        0,
        winreg.REG_SZ,
    ),
]


# ---------------------------------------------------------------------------
# Public functions (called by actions.py)
# ---------------------------------------------------------------------------


def apply_recommended_privacy_profile() -> str:
    """
    Applies the recommended privacy profile.
    """
    logger.info("Applying recommended privacy profile...")
    result = _apply_settings(_RECOMMENDED_SETTINGS)
    return "Recommended privacy profile applied.\n\n" + result


def apply_strict_privacy_profile() -> str:
    """
    Applies the strict privacy profile.
    """
    logger.info("Applying strict privacy profile...")
    result = _apply_settings(_STRICT_SETTINGS)
    return (
        "Strict privacy profile applied.\n"
        "(Some changes require reboot to take effect.)\n\n" + result
    )


def restore_privacy_defaults() -> str:
    """
    Restores original registry values saved during this session.
    If a value had no previous state (was not modified), it is deleted.
    """
    logger.info("Restoring privacy defaults...")

    messages = []

    for (root, path, name), original_value in _BACKUP.items():
        try:
            if original_value is None:
                # Value did not exist originally → delete it
                with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
                    try:
                        winreg.DeleteValue(key, name)
                        messages.append(f"{path}\\{name}: deleted (default)")
                    except FileNotFoundError:
                        messages.append(f"{path}\\{name}: already missing")
            else:
                # Restore original value
                with winreg.CreateKey(root, path) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(original_value))
                messages.append(f"{path}\\{name}: restored to {original_value}")

        except Exception as e:
            logger.error("Failed to restore %s\\%s: %s", path, name, e)
            messages.append(f"ERROR restoring {path}\\{name}: {e}")

    if not messages:
        return "No previous privacy settings to restore."

    return "Privacy defaults restored.\n\n" + "\n".join(messages)
