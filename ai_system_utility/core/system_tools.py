# ai_system_utility/core/system_tools.py

"""
Core system tools for AI System Utility.

This module provides concrete implementations for:
- System cleanup (temp, prefetch, Windows Update cache)
- System health checks (SFC, DISM, CHKDSK scheduling)
- Network repair (reset network stack)
- Launching common Windows tools (Task Manager, Device Manager, Services, System Restore)

All functions are designed to be:
- Non-silent: they return a human-readable string summarizing what happened.
- Safe-ish: they avoid obviously destructive operations beyond what the user expects.
- Windows-focused: on non-Windows platforms, they will fail gracefully.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Tuple

from .logger import get_logger

logger = get_logger("system_tools")


# ---------------------------------------------------------------------------
# Helpers / platform checks
# ---------------------------------------------------------------------------


def _is_windows() -> bool:
    return os.name == "nt"


def _ensure_windows() -> None:
    """
    Raise RuntimeError if not running on Windows.
    """
    if not _is_windows():
        raise RuntimeError("This action is only supported on Windows.")


def _run_command(
    command: Iterable[str],
    *,
    check: bool = True,
    capture_output: bool = True,
) -> Tuple[int, str, str]:
    """
    Run a subprocess command with logging.

    Returns: (returncode, stdout, stderr)
    """
    cmd_list = list(command)
    logger.info("Running command: %s", " ".join(cmd_list))

    try:
        result = subprocess.run(
            cmd_list,
            shell=False,
            check=False,  # we handle check manually
            capture_output=capture_output,
            text=True,
        )
    except Exception as e:
        logger.error("Command failed to start: %s", e)
        raise RuntimeError(f"Failed to start command {' '.join(cmd_list)}: {e}") from e

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    logger.debug(
        "Command finished rc=%s, stdout_len=%d, stderr_len=%d",
        result.returncode,
        len(stdout),
        len(stderr),
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command {' '.join(cmd_list)} failed with code {result.returncode}: {stderr.strip()}"
        )

    return result.returncode, stdout, stderr


def _delete_in_dir(path: Path) -> Tuple[int, int]:
    """
    Deletes files and directories inside 'path' (but not the directory itself).

    Returns: (files_deleted, dirs_deleted)
    """
    files_deleted = 0
    dirs_deleted = 0

    if not path.exists():
        return 0, 0

    for entry in path.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
                dirs_deleted += 1
            else:
                entry.unlink(missing_ok=True)
                files_deleted += 1
        except Exception as e:
            logger.warning("Failed to delete %s: %s", entry, e)

    return files_deleted, dirs_deleted


# ---------------------------------------------------------------------------
# Cleanup tools
# ---------------------------------------------------------------------------


def cleanup_temp_files() -> str:
    """
    Cleans common temp directories:
    - %TEMP%
    - C:\\Windows\\Temp
    """
    _ensure_windows()

    temp_paths: List[Path] = []

    # User temp
    user_temp = os.getenv("TEMP") or os.getenv("TMP")
    if user_temp:
        temp_paths.append(Path(user_temp))

    # Windows temp
    windir = os.getenv("WINDIR", r"C:\Windows")
    temp_paths.append(Path(windir) / "Temp")

    total_files = 0
    total_dirs = 0

    for p in temp_paths:
        files, dirs = _delete_in_dir(p)
        total_files += files
        total_dirs += dirs
        logger.info("Cleaned temp folder %s: %d files, %d dirs", p, files, dirs)

    return f"Temp cleanup completed. Removed approximately {total_files} files and {total_dirs} folders."


def cleanup_prefetch() -> str:
    """
    Cleans the Windows Prefetch folder.
    """
    _ensure_windows()

    windir = os.getenv("WINDIR", r"C:\Windows")
    prefetch_dir = Path(windir) / "Prefetch"

    files, dirs = _delete_in_dir(prefetch_dir)
    logger.info("Cleaned Prefetch folder %s: %d files, %d dirs", prefetch_dir, files, dirs)

    return f"Prefetch cleanup completed. Removed approximately {files} files and {dirs} folders."


def cleanup_windows_update_cache() -> str:
    """
    Cleans the Windows Update cache by:
    - Stopping Windows Update related services
    - Deleting SoftwareDistribution and catroot2 contents
    - Restarting services

    Requires administrator privileges.
    """
    _ensure_windows()

    services = ["wuauserv", "bits", "cryptsvc"]

    # Stop services
    for svc in services:
        try:
            _run_command(["sc", "stop", svc], check=False)
        except Exception as e:
            logger.warning("Failed to stop service %s: %s", svc, e)

    windir = os.getenv("WINDIR", r"C:\Windows")
    sd = Path(windir) / "SoftwareDistribution"
    catroot2 = Path(windir) / "System32" / "catroot2"

    files_sd, dirs_sd = _delete_in_dir(sd)
    files_cat, dirs_cat = _delete_in_dir(catroot2)

    logger.info(
        "Cleaned Windows Update cache: SoftwareDistribution(%d files, %d dirs), catroot2(%d files, %d dirs)",
        files_sd,
        dirs_sd,
        files_cat,
        dirs_cat,
    )

    # Restart services
    for svc in services:
        try:
            _run_command(["sc", "start", svc], check=False)
        except Exception as e:
            logger.warning("Failed to start service %s: %s", svc, e)

    return (
        "Windows Update cache cleanup completed.\n"
        "SoftwareDistribution and catroot2 contents were cleared. "
        "Windows Update services were restarted."
    )


# ---------------------------------------------------------------------------
# Health tools (SFC, DISM, CHKDSK)
# ---------------------------------------------------------------------------


def run_sfc_scan() -> str:
    """
    Runs System File Checker:
        sfc /scannow
    """
    _ensure_windows()

    rc, stdout, stderr = _run_command(["sfc", "/scannow"], check=False)

    if rc == 0:
        status = "SFC scan completed successfully."
    else:
        status = f"SFC scan finished with code {rc}. Check details."

    summary = stdout.strip() or stderr.strip() or status
    logger.info("SFC result: rc=%s", rc)

    return f"{status}\n\nLast output lines:\n{summary[-2000:]}"


def run_dism_health_scan() -> str:
    """
    Runs DISM component store repair:
        DISM /Online /Cleanup-Image /RestoreHealth
    """
    _ensure_windows()

    rc, stdout, stderr = _run_command(
        ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"],
        check=False,
    )

    if rc == 0:
        status = "DISM health scan completed successfully."
    else:
        status = f"DISM health scan finished with code {rc}. Check details."

    summary = stdout.strip() or stderr.strip() or status
    logger.info("DISM result: rc=%s", rc)

    return f"{status}\n\nLast output lines:\n{summary[-2000:]}"


def schedule_chkdsk(drive: str = "C:") -> str:
    """
    Schedules CHKDSK on the given drive for the next reboot.

    We use:
        chkdsk C: /F /R /X

    This may prompt the user in the console to confirm scheduling.
    """
    _ensure_windows()

    logger.info("Scheduling CHKDSK on %s", drive)

    cmd = ["cmd.exe", "/c", "chkdsk", drive, "/F", "/R", "/X"]
    try:
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as e:
        logger.error("Failed to start CHKDSK: %s", e)
        raise RuntimeError(f"Failed to start CHKDSK on {drive}: {e}") from e

    return (
        f"CHKDSK has been started in a separate console for {drive}.\n"
        "If prompted, confirm scheduling at next reboot."
    )


# ---------------------------------------------------------------------------
# Network repair
# ---------------------------------------------------------------------------


def reset_network_stack() -> str:
    """
    Resets Winsock, IP stack, and flushes DNS:
        netsh winsock reset
        netsh int ip reset
        ipconfig /flushdns
    """
    _ensure_windows()

    messages: List[str] = []

    for cmd in (
        ["netsh", "winsock", "reset"],
        ["netsh", "int", "ip", "reset"],
        ["ipconfig", "/flushdns"],
    ):
        try:
            rc, stdout, stderr = _run_command(cmd, check=False)
            text = stdout.strip() or stderr.strip()
            messages.append(f"{' '.join(cmd)} (rc={rc}): {text}")
        except Exception as e:
            logger.error("Network command failed: %s", e)
            messages.append(f"{' '.join(cmd)}: ERROR - {e}")

    return "Network reset sequence completed.\n\n" + "\n".join(messages)


# ---------------------------------------------------------------------------
# Launching common Windows tools
# ---------------------------------------------------------------------------


def open_task_manager() -> str:
    """
    Opens Windows Task Manager.
    """
    _ensure_windows()

    logger.info("Opening Task Manager")
    try:
        subprocess.Popen(["taskmgr"], shell=False)
        return "Task Manager opened."
    except Exception as e:
        logger.error("Failed to open Task Manager: %s", e)
        raise RuntimeError(f"Failed to open Task Manager: {e}") from e


def open_device_manager() -> str:
    """
    Opens Windows Device Manager.

    Use os.startfile on devmgmt.msc so Windows launches it via MMC.
    """
    _ensure_windows()

    logger.info("Opening Device Manager")
    try:
        windir = os.getenv("WINDIR", r"C:\Windows")
        msc_path = os.path.join(windir, "System32", "devmgmt.msc")
        if os.path.exists(msc_path):
            os.startfile(msc_path)  # type: ignore[attr-defined]
        else:
            # Fallback: let Windows resolve it on PATH / registered handler
            os.startfile("devmgmt.msc")  # type: ignore[attr-defined]
        return "Device Manager opened."
    except Exception as e:
        logger.error("Failed to open Device Manager: %s", e)
        raise RuntimeError(f"Failed to open Device Manager: {e}") from e


def open_services_console() -> str:
    """
    Opens the Services management console.

    Use os.startfile on services.msc so Windows launches it via MMC.
    """
    _ensure_windows()

    logger.info("Opening Services console")
    try:
        windir = os.getenv("WINDIR", r"C:\Windows")
        msc_path = os.path.join(windir, "System32", "services.msc")
        if os.path.exists(msc_path):
            os.startfile(msc_path)  # type: ignore[attr-defined]
        else:
            os.startfile("services.msc")  # type: ignore[attr-defined]
        return "Services console opened."
    except Exception as e:
        logger.error("Failed to open Services console: %s", e)
        raise RuntimeError(f"Failed to open Services console: {e}") from e


def open_system_restore() -> str:
    """
    Opens the System Restore configuration window.
    """
    _ensure_windows()

    logger.info("Opening System Restore UI")

    try:
        windir = os.getenv("WINDIR", r"C:\Windows")
        exe_path = os.path.join(windir, "System32", "rstrui.exe")
        if os.path.exists(exe_path):
            subprocess.Popen([exe_path], shell=False)
        else:
            subprocess.Popen(["rstrui.exe"], shell=False)
        return "System Restore UI opened."
    except Exception as e:
        logger.error("Failed to open System Restore: %s", e)
        raise RuntimeError(f"Failed to open System Restore: {e}") from e
