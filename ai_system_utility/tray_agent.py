# ai_system_utility/tray_agent.py

"""
System tray agent for AI System Utility.

Run with:
    python -m ai_system_utility.tray_agent
    (or pythonw -m ai_system_utility.tray_agent for no console window)

Features:
- Tray icon in the Windows notification area.
- Quick actions from the tray menu:
    * Open AI System Utility GUI
    * Run Recommended Cleanup
    * Run Full Health Check
    * Reset Network Stack
    * Apply Recommended Privacy Profile
- Background health monitor:
    * Periodically checks CPU, RAM, and disk usage.
    * Shows notifications when thresholds are exceeded.
- Exit option to stop the tray agent.

Requires:
    pip install pystray pillow
"""

from __future__ import annotations

import os
import sys
import threading
import time
import subprocess
from typing import Optional

import ctypes

try:
    import pystray
    from pystray import MenuItem as Item, Menu
    from PIL import Image, ImageDraw
except ImportError:
    print(
        "ERROR: pystray and pillow are required for the tray agent.\n"
        "Install them with:\n"
        "    pip install pystray pillow"
    )
    raise

from .core.logger import get_logger
from .core.actions import get_action_by_id
from .core.version import get_version
from .core.system_info import get_system_info

logger = get_logger("tray_agent")


# ---------------------------------------------------------------------------
# Elevation helpers
# ---------------------------------------------------------------------------


def _is_windows() -> bool:
    return os.name == "nt"


def _is_admin() -> bool:
    if not _is_windows():
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin() -> None:
    """
    Ensures the tray agent is running elevated on Windows.

    Relaunches this module via an elevated pythonw.exe when possible to avoid
    an extra console window.

    Command:
        pythonw -m ai_system_utility.tray_agent
    """
    if not _is_windows():
        return

    if _is_admin():
        return

    # Prefer pythonw.exe to avoid an extra console window
    exe = sys.executable
    exe_lower = exe.lower()
    if exe_lower.endswith("python.exe"):
        pythonw = exe[:-10] + "pythonw.exe"  # replace tail "python.exe"
        if os.path.exists(pythonw):
            exe = pythonw

    params = "-m ai_system_utility.tray_agent"
    if len(sys.argv) > 1:
        params += " " + " ".join(sys.argv[1:])

    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe,
            params,
            None,
            1,
        )
    except Exception:
        rc = 0

    if rc <= 32:
        sys.stderr.write(
            "Failed to relaunch AI System Utility Tray Agent with administrator privileges.\n"
        )
    sys.exit(0)


# ---------------------------------------------------------------------------
# Simple Windows message box helper (for feedback)
# ---------------------------------------------------------------------------


def _show_message(title: str, text: str) -> None:
    """
    Show a simple notification. On Windows, use a MessageBox.
    On other platforms, just print to stdout.
    """
    logger.info("%s: %s", title, text)
    if _is_windows():
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                text,
                title,
                0x40,  # MB_ICONINFORMATION
            )
        except Exception as e:
            logger.debug("Failed to show MessageBox: %s", e)
            print(f"{title}: {text}")
    else:
        print(f"{title}: {text}")


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------


def _run_action_in_thread(action_id: str, display_name: Optional[str] = None) -> None:
    """
    Run an action from the actions registry in a background thread so the
    tray UI stays responsive.
    """

    def target() -> None:
        name = display_name or action_id
        try:
            action = get_action_by_id(action_id)
        except Exception as e:
            logger.error("Failed to look up action '%s': %s", action_id, e)
            _show_message("Action Error", f"Failed to look up '{name}': {e}")
            return

        if not action:
            _show_message("Action Not Found", f"Action '{name}' not found.")
            return

        logger.info("Tray: running action '%s' (%s)", name, action_id)

        try:
            func = getattr(action, "func", None)
            if func is None:
                raise RuntimeError("Action has no callable 'func' attribute.")
            result = func()
            summary = str(result) if result else "Action completed successfully."
            _show_message(f"{name} finished", summary)
        except Exception as e:
            logger.exception("Action '%s' failed", name)
            _show_message("Action Failed", f"{name} failed:\n{e}")

    t = threading.Thread(target=target, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Tray icon + menu
# ---------------------------------------------------------------------------


def _create_icon_image() -> "Image.Image":
    """
    Create a simple tray icon image (in-memory).
    """
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Outer circle (blue-ish)
    draw.ellipse((4, 4, size - 4, size - 4), fill=(0, 120, 215, 255))

    # Inner wrench-like shape
    draw.rectangle(
        (size * 0.35, size * 0.25, size * 0.65, size * 0.7),
        fill=(255, 255, 255, 255),
    )
    draw.ellipse(
        (size * 0.25, size * 0.55, size * 0.45, size * 0.75),
        fill=(255, 255, 255, 255),
    )

    return image


def _open_main_gui() -> None:
    """
    Launch the main GUI (ai_system_utility.gui) as a separate process.
    """
    logger.info("Tray: launching main GUI...")
    try:
        if _is_windows():
            params = "-m ai_system_utility.gui"
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                params,
                None,
                1,
            )
        else:
            subprocess.Popen([sys.executable, "-m", "ai_system_utility.gui"])
    except Exception as e:
        logger.error("Failed to launch main GUI: %s", e)
        _show_message("Launch Failed", f"Could not open GUI:\n{e}")


def _create_menu(icon: pystray.Icon) -> Menu:
    """
    Build the tray context menu.
    """

    def open_gui(_icon, _item):
        _open_main_gui()

    def run_cleanup(_icon, _item):
        _run_action_in_thread("cleanup_recommended", "Recommended Cleanup")

    def run_health(_icon, _item):
        _run_action_in_thread("health_full", "Full Health Check")

    def reset_network(_icon, _item):
        _run_action_in_thread("network_reset", "Network Reset")

    def privacy_recommended(_icon, _item):
        _run_action_in_thread("privacy_recommended", "Recommended Privacy Profile")

    def exit_app(_icon, _item):
        logger.info("Tray agent exiting by user request.")
        icon.stop()

    return Menu(
        Item("Open AI System Utility", open_gui),
        Item("Recommended Cleanup", run_cleanup),
        Item("Full Health Check", run_health),
        Item("Reset Network", reset_network),
        Item("Apply Recommended Privacy", privacy_recommended),
        pystray.Menu.SEPARATOR,
        Item("Exit Tray Agent", exit_app),
    )


# ---------------------------------------------------------------------------
# Background health monitor
# ---------------------------------------------------------------------------


def _start_health_monitor() -> None:
    """
    Starts a daemon thread that periodically checks system health stats
    and shows notifications if thresholds are exceeded.
    """

    def monitor() -> None:
        CPU_WARN = 90.0    # percent
        RAM_WARN = 90.0    # percent
        DISK_WARN = 95.0   # percent used
        CHECK_INTERVAL = 60  # seconds
        MIN_NOTIFY_INTERVAL = 5 * 60  # seconds between notifications of same type

        last_cpu_notify = 0.0
        last_ram_notify = 0.0
        last_disk_notify = 0.0

        while True:
            try:
                info = get_system_info()
            except Exception as e:
                logger.error("Health monitor: failed to get system info: %s", e)
                time.sleep(CHECK_INTERVAL)
                continue

            now = time.time()

            # CPU
            try:
                cpu = float(info.cpu_percent)
            except Exception:
                cpu = -1.0

            if cpu >= CPU_WARN and now - last_cpu_notify >= MIN_NOTIFY_INTERVAL:
                last_cpu_notify = now
                msg = (
                    f"High CPU usage detected: {cpu:.1f}%.\n\n"
                    "Consider running 'Full Health Check' from the tray menu "
                    "or closing heavy applications."
                )
                _show_message("High CPU Usage", msg)

            # RAM
            try:
                ram = float(info.ram_percent)
            except Exception:
                ram = -1.0

            if ram >= RAM_WARN and now - last_ram_notify >= MIN_NOTIFY_INTERVAL:
                last_ram_notify = now
                msg = (
                    f"High memory usage detected: {ram:.1f}%.\n\n"
                    "Consider closing unused applications or restarting the system."
                )
                _show_message("High Memory Usage", msg)

            # Disks
            try:
                disks = info.disks or []
            except Exception:
                disks = []

            # Find the worst disk usage
            worst = None
            for d in disks:
                try:
                    if worst is None or d.percent_used > worst.percent_used:
                        worst = d
                except Exception:
                    continue

            if worst is not None and worst.percent_used >= DISK_WARN and now - last_disk_notify >= MIN_NOTIFY_INTERVAL:
                last_disk_notify = now
                msg = (
                    f"Low disk space detected on {worst.device} ({worst.mountpoint}).\n\n"
                    f"Used: {worst.used_gb:.1f}/{worst.total_gb:.1f} GB "
                    f"({worst.percent_used:.1f}% used).\n\n"
                    "Consider running 'Recommended Cleanup' from the tray menu "
                    "or freeing up space manually."
                )
                _show_message("Low Disk Space", msg)

            time.sleep(CHECK_INTERVAL)

    t = threading.Thread(target=monitor, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Entry point for the tray agent.
    """
    ensure_admin()

    version = get_version()
    logger.info("Starting AI System Utility Tray Agent (v%s)", version)

    image = _create_icon_image()
    tooltip = f"AI System Utility v{version}"

    icon = pystray.Icon(
        "ai_system_utility_tray",
        image,
        tooltip,
        menu=_create_menu(None),  # will be replaced below
    )

    icon.menu = _create_menu(icon)

    # Start background health monitor
    _start_health_monitor()

    # Run the tray icon event loop (blocking)
    icon.run()


if __name__ == "__main__":
    main()
