# ai_system_utility/core/logger.py

"""
Central logging helper for AI System Utility.

Provides two styles of logging:

1) Simple file logging functions (used by existing code):
   - log_event(message: str)
   - log_action(action_name: str, status: str, info: str = "")

2) Standard Python logger (used by newer modules):
   - get_logger(name: str) -> logging.Logger

All logs are written under:
    <project_root>/ai_system_utility/logs/<YYYY-MM-DD>.log
"""

from __future__ import annotations

import os
import datetime
import logging
from typing import Dict

# Figure out base directory (ai_system_utility/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Logs directory inside the package
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Make sure logs folder exists
os.makedirs(LOG_DIR, exist_ok=True)

# Cache of created loggers
_LOGGERS: Dict[str, logging.Logger] = {}


def _get_log_file_path() -> str:
    """
    Return the full path to today's log file.
    """
    date_str = datetime.date.today().isoformat()
    return os.path.join(LOG_DIR, f"{date_str}.log")


# ---------------------------------------------------------------------------
# Old-style logging API (used by ai_interpreter.py and others)
# ---------------------------------------------------------------------------

def log_event(message: str) -> None:
    """
    Write a timestamped message to the daily log file.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    log_file = _get_log_file_path()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)


def log_action(action_name: str, status: str, info: str = "") -> None:
    """
    Log a structured action entry.
    status example: 'START', 'SUCCESS', 'SKIP', 'ERROR'
    """
    msg = f"ACTION {status}: {action_name}"
    if info:
        msg += f" | {info}"
    log_event(msg)


# ---------------------------------------------------------------------------
# New-style logging API (used by actions.py, tray_agent.py, etc.)
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """
    Return a Python logger configured to write into the same log files
    that log_event/log_action use.
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(f"ai_system_utility.{name}")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        try:
            log_file = _get_log_file_path()
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception:
            # If file logging fails for some reason, fall back to stdout
            sh = logging.StreamHandler()
            sh.setLevel(logging.INFO)
            logger.addHandler(sh)

    _LOGGERS[name] = logger
    return logger
