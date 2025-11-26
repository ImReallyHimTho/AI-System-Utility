# ai_system_utility/core/actions.py

"""
Actions registry for AI System Utility.

This module provides a unified registry of all actions the assistant
can perform, including:

- Name / description
- Group (cleanup, privacy, network, health, tools, etc.)
- Dangerous flag
- Python function to execute

It also supports plugin actions via `ai_system_utility.plugins`.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .logger import get_logger

logger = get_logger("actions")


# ---------------------------------------------------------------------------
# Action model
# ---------------------------------------------------------------------------


@dataclass
class Action:
    """
    Represents a single executable action.

    Attributes:
        id:          Unique identifier for the action.
        name:        Human-friendly name (displayed in GUI).
        description: What the action does (displayed in GUI/CLI).
        group:       Logical group, e.g. "cleanup", "privacy", "network",
                     "health", "tools".
        dangerous:   If True, GUI/CLI should ask for confirmation.
        func:        Callable with no arguments that performs the action.
    """

    id: str
    name: str
    description: str
    group: str
    dangerous: bool
    func: Callable[[], Optional[str]]

    @property
    def fn(self) -> Callable[[], Optional[str]]:
        """
        Backwards-compatibility alias for .func, so older code that expects
        action.fn() will still work.
        """
        return self.func


# Registry: id -> Action
_ACTIONS: Dict[str, Action] = {}


# ---------------------------------------------------------------------------
# Registration API
# ---------------------------------------------------------------------------


def register_action(
    action_id: str,
    name: str,
    description: str,
    group: str,
    func: Callable[[], Optional[str]],
    dangerous: bool = False,
) -> Action:
    """
    Register a new action in the global registry.

    Can be used by core modules or by plugins.
    """
    global _ACTIONS

    if action_id in _ACTIONS:
        logger.warning("Overwriting existing action with id '%s'", action_id)

    action = Action(
        id=action_id,
        name=name,
        description=description,
        group=group,
        dangerous=dangerous,
        func=func,
    )
    _ACTIONS[action_id] = action
    logger.debug("Registered action '%s' (%s)", action_id, name)
    return action


def get_action_by_id(action_id: str) -> Optional[Action]:
    """
    Returns the Action associated with the given id, or None if not found.
    """
    return _ACTIONS.get(action_id)


def get_actions_by_group(group: str) -> List[Action]:
    """
    Returns a list of actions belonging to the specified group,
    sorted by name.
    """
    actions = [a for a in _ACTIONS.values() if a.group == group]
    actions.sort(key=lambda a: a.name.lower())
    return actions


def list_actions() -> List[Action]:
    """
    Returns a list of all registered actions, sorted by group then name.
    """
    return sorted(_ACTIONS.values(), key=lambda a: (a.group, a.name.lower()))


# ---------------------------------------------------------------------------
# Built-in actions (core functionality)
# ---------------------------------------------------------------------------


def _register_builtin_actions() -> None:
    """
    Registers core actions that ship with the main application.

    These call into `system_tools.py` and `privacy_tools.py`. If those
    modules are missing or functions are not available, the actions will
    raise a user-friendly error at runtime rather than breaking import.
    """
    try:
        from . import system_tools
    except Exception as e:
        logger.warning("system_tools module not available: %s", e)
        system_tools = None  # type: ignore

    try:
        from . import privacy_tools
    except Exception as e:
        logger.warning("privacy_tools module not available: %s", e)
        privacy_tools = None  # type: ignore

    # ---- Cleanup actions ----
    def _cleanup_temp() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "cleanup_temp_files"):
            raise RuntimeError("Temp cleanup tool is not available.")
        return system_tools.cleanup_temp_files()

    register_action(
        action_id="cleanup_temp",
        name="Clean Temp Files",
        description="Deletes temporary files from standard Windows temp locations.",
        group="cleanup",
        func=_cleanup_temp,
        dangerous=False,
    )

    def _cleanup_prefetch() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "cleanup_prefetch"):
            raise RuntimeError("Prefetch cleanup tool is not available.")
        return system_tools.cleanup_prefetch()

    register_action(
        action_id="cleanup_prefetch",
        name="Clean Prefetch Folder",
        description="Cleans the Windows Prefetch folder to clear stale launch data.",
        group="cleanup",
        func=_cleanup_prefetch,
        dangerous=False,
    )

    def _cleanup_windows_update_cache() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "cleanup_windows_update_cache"):
            raise RuntimeError("Windows Update cache cleanup is not available.")
        return system_tools.cleanup_windows_update_cache()

    register_action(
        action_id="cleanup_windows_update_cache",
        name="Clean Windows Update Cache",
        description="Deletes and resets Windows Update cache to fix update issues.",
        group="cleanup",
        func=_cleanup_windows_update_cache,
        dangerous=True,
    )

    def _cleanup_recommended() -> Optional[str]:
        """
        A higher-level action that runs a recommended safe cleanup set.
        """
        messages = []
        for func_name in (
            "cleanup_temp_files",
            "cleanup_prefetch",
            "cleanup_windows_update_cache",
        ):
            if not system_tools or not hasattr(system_tools, func_name):
                continue
            try:
                result = getattr(system_tools, func_name)()
                if result:
                    messages.append(str(result))
            except Exception as e:
                messages.append(f"{func_name} failed: {e}")
        if messages:
            return "\n".join(messages)
        return "Cleanup completed."

    register_action(
        action_id="cleanup_recommended",
        name="Recommended Cleanup",
        description="Runs a recommended set of cleanup operations: temp, prefetch, and update cache.",
        group="cleanup",
        func=_cleanup_recommended,
        dangerous=True,
    )

    # ---- Health actions ----
    def _run_sfc() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "run_sfc_scan"):
            raise RuntimeError("SFC scan tool is not available.")
        return system_tools.run_sfc_scan()

    register_action(
        action_id="health_sfc",
        name="System File Checker (SFC)",
        description="Runs 'sfc /scannow' to check and repair system files.",
        group="health",
        func=_run_sfc,
        dangerous=True,
    )

    def _run_dism() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "run_dism_health_scan"):
            raise RuntimeError("DISM health scan tool is not available.")
        return system_tools.run_dism_health_scan()

    register_action(
        action_id="health_dism",
        name="DISM Health Scan",
        description="Runs DISM to check and repair the Windows component store.",
        group="health",
        func=_run_dism,
        dangerous=True,
    )

    def _run_chkdsk() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "schedule_chkdsk"):
            raise RuntimeError("CHKDSK scheduling tool is not available.")
        return system_tools.schedule_chkdsk()

    register_action(
        action_id="health_chkdsk",
        name="CHKDSK (Next Boot)",
        description="Schedules CHKDSK on the system drive for the next reboot.",
        group="health",
        func=_run_chkdsk,
        dangerous=True,
    )

    def _health_full() -> Optional[str]:
        """
        Runs SFC + DISM in sequence (and optionally CHKDSK schedule).
        """
        messages = []
        for func_name in ("run_sfc_scan", "run_dism_health_scan"):
            if not system_tools or not hasattr(system_tools, func_name):
                continue
            try:
                result = getattr(system_tools, func_name)()
                if result:
                    messages.append(str(result))
            except Exception as e:
                messages.append(f"{func_name} failed: {e}")
        if messages:
            return "\n".join(messages)
        return "Health checks completed."

    register_action(
        action_id="health_full",
        name="Full Health Check",
        description="Runs SFC and DISM to verify system health. You may still choose to schedule CHKDSK.",
        group="health",
        func=_health_full,
        dangerous=True,
    )

    # ---- Network actions ----
    def _network_reset() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "reset_network_stack"):
            raise RuntimeError("Network reset tool is not available.")
        return system_tools.reset_network_stack()

    register_action(
        action_id="network_reset",
        name="Reset Network Stack",
        description="Resets Winsock, IP stack, and flushes DNS to fix common network issues.",
        group="network",
        func=_network_reset,
        dangerous=True,
    )

    # ---- Tools actions ----
    def _open_task_manager() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "open_task_manager"):
            raise RuntimeError("Task Manager tool is not available.")
        return system_tools.open_task_manager()

    register_action(
        action_id="tools_task_manager",
        name="Open Task Manager",
        description="Opens Windows Task Manager.",
        group="tools",
        func=_open_task_manager,
        dangerous=False,
    )

    def _open_device_manager() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "open_device_manager"):
            raise RuntimeError("Device Manager tool is not available.")
        return system_tools.open_device_manager()

    register_action(
        action_id="tools_device_manager",
        name="Open Device Manager",
        description="Opens Windows Device Manager.",
        group="tools",
        func=_open_device_manager,
        dangerous=False,
    )

    def _open_services() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "open_services_console"):
            raise RuntimeError("Services console tool is not available.")
        return system_tools.open_services_console()

    register_action(
        action_id="tools_services",
        name="Open Services",
        description="Opens the Windows Services management console.",
        group="tools",
        func=_open_services,
        dangerous=False,
    )

    def _open_system_restore() -> Optional[str]:
        if not system_tools or not hasattr(system_tools, "open_system_restore"):
            raise RuntimeError("System Restore tool is not available.")
        return system_tools.open_system_restore()

    register_action(
        action_id="tools_system_restore",
        name="Open System Restore",
        description="Opens the System Restore configuration UI.",
        group="tools",
        func=_open_system_restore,
        dangerous=False,
    )

    # ---- Privacy actions ----
    def _privacy_recommended() -> Optional[str]:
        if not privacy_tools or not hasattr(privacy_tools, "apply_recommended_privacy_profile"):
            raise RuntimeError("Recommended privacy profile is not available.")
        return privacy_tools.apply_recommended_privacy_profile()

    register_action(
        action_id="privacy_recommended",
        name="Recommended Privacy Profile",
        description="Applies a balanced set of privacy tweaks recommended for most users.",
        group="privacy",
        func=_privacy_recommended,
        dangerous=True,
    )

    def _privacy_strict() -> Optional[str]:
        if not privacy_tools or not hasattr(privacy_tools, "apply_strict_privacy_profile"):
            raise RuntimeError("Strict privacy profile is not available.")
        return privacy_tools.apply_strict_privacy_profile()

    register_action(
        action_id="privacy_strict",
        name="Strict Privacy Profile",
        description="Applies a strict set of privacy tweaks, potentially disabling some Windows features.",
        group="privacy",
        func=_privacy_strict,
        dangerous=True,
    )

    def _privacy_restore_defaults() -> Optional[str]:
        if not privacy_tools or not hasattr(privacy_tools, "restore_privacy_defaults"):
            raise RuntimeError("Privacy defaults restore is not available.")
        return privacy_tools.restore_privacy_defaults()

    register_action(
        action_id="privacy_restore_defaults",
        name="Restore Privacy Defaults",
        description="Restores Windows privacy-related settings to their default values.",
        group="privacy",
        func=_privacy_restore_defaults,
        dangerous=True,
    )


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------


def _get_plugins_package_name() -> Optional[str]:
    """
    Determines the full package name for the plugins package,
    e.g. 'ai_system_utility.plugins'.
    """
    package = __package__ or ""
    # Typically this module is 'ai_system_utility.core.actions'
    # We want 'ai_system_utility.plugins'
    parts = package.split(".")
    if "core" in parts:
        core_index = parts.index("core")
        base = ".".join(parts[:core_index])
    else:
        # Fallback: assume parent is base
        base = ".".join(parts[:-1])
    if not base:
        return None
    return f"{base}.plugins"


def load_plugins() -> None:
    """
    Imports all plugin modules under ai_system_utility.plugins.

    Each plugin module may define a function:

        def register(registry): ...

    and call:

        registry.register_action(...)

    to add its own actions.
    """
    package_name = _get_plugins_package_name()
    if not package_name:
        logger.debug("Could not determine plugins package name.")
        return

    try:
        plugins_pkg = importlib.import_module(package_name)
    except ModuleNotFoundError:
        logger.debug("Plugins package '%s' not found (which is fine).", package_name)
        return
    except Exception as e:
        logger.warning("Failed to import plugins package '%s': %s", package_name, e)
        return

    # Iterate over modules in the plugins package
    for module_info in pkgutil.iter_modules(plugins_pkg.__path__):
        mod_name = module_info.name
        if mod_name.startswith("_"):
            continue  # skip private modules

        full_name = f"{package_name}.{mod_name}"
        try:
            module = importlib.import_module(full_name)
        except Exception as e:
            logger.warning("Failed to import plugin module '%s': %s", full_name, e)
            continue

        # If the plugin exposes a register() function, call it.
        register_fn = getattr(module, "register", None)
        if callable(register_fn):
            try:
                register_fn(registry=_RegistryFacade())
                logger.info("Plugin '%s' registered successfully.", full_name)
            except Exception as e:
                logger.warning("Plugin '%s' register() failed: %s", full_name, e)


class _RegistryFacade:
    """
    Simple facade object passed to plugins so they can register actions
    without importing this module directly (though they still can if they want).
    """

    @staticmethod
    def register_action(
        action_id: str,
        name: str,
        description: str,
        group: str,
        func: Callable[[], Optional[str]],
        dangerous: bool = False,
    ) -> Action:
        return register_action(
            action_id=action_id,
            name=name,
            description=description,
            group=group,
            func=func,
            dangerous=dangerous,
        )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

# Register built-in actions first
_register_builtin_actions()

# Then load any plugin-defined actions
load_plugins()

# ---------------------------------------------------------------------------
# Legacy alias for compatibility with older code
# ---------------------------------------------------------------------------

# Some existing modules do:
#     from .actions import ACTIONS
# We expose this alias so they still work.
ACTIONS = _ACTIONS
