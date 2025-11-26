# ai_system_utility/core/self_updater.py

"""
Self-updater logic for AI System Utility.

This module is responsible for:
- Checking a remote JSON "update feed" for the latest version info.
- Comparing the remote version against the current app version.
- Returning a structured result to the GUI.
- Downloading the update file (portable EXE or installer) when requested.

The update feed is expected to be a small JSON document hosted online,
for example on GitHub (raw.githubusercontent.com):

    {
      "latest_version": "1.0.0",
      "minimum_supported_version": "1.0.0",
      "download_url": "https://github.com/YOUR_USERNAME/YOUR_REPO/releases/download/v1.0.0/AI_System_Utility_Portable.exe",
      "changelog": "Initial public release of AI System Utility."
    }

Only HTTPS URLs should be used.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal

from .logger import get_logger
from .version import get_version

logger = get_logger("self_updater")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# IMPORTANT:
# Replace this with the raw URL to your latest.json on GitHub once you create it.
#
# Example:
#   UPDATE_FEED_URL = (
#       "https://github.com/ImReallyHimTho/AI-System-Utility/blob/main/latest.json"
#   )
#
# For now it's a placeholder so that the function fails gracefully with
# a clear message until you set up GitHub.
UPDATE_FEED_URL = "https://raw.githubusercontent.com/ImReallyHimTho/AI-System-Utility/main/latest.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class UpdateInfo:
    """
    Represents a specific update that can be downloaded.
    """

    version: str
    download_url: str
    changelog: Optional[str] = None
    minimum_supported_version: Optional[str] = None


@dataclass
class UpdateCheckResult:
    """
    Result of check_for_updates().

    status:
        "error"           -> update check failed (network, parse error, etc.)
        "no_update"       -> no newer version available
        "update_available"-> a newer version is available

    message:
        Human-readable summary the GUI can display directly.

    current_version:
        The current app version (from version.get_version()).

    remote_version:
        The version reported by the update feed, if any.

    update_info:
        Populated when status == "update_available".
    """

    status: Literal["error", "no_update", "update_available"]
    message: str
    current_version: str
    remote_version: Optional[str]
    update_info: Optional[UpdateInfo]


# ---------------------------------------------------------------------------
# Version comparison helpers
# ---------------------------------------------------------------------------


def _parse_version(v: str) -> tuple:
    """
    Parse a version string like '1.2.3' into a tuple of integers so that
    it can be compared lexicographically.

    Non-numeric parts (e.g. '1.0.0-beta1') are handled in a very simple way:
    - The numeric components are parsed normally.
    - Any non-numeric part is ignored for ordering purposes.

    This is not a full semantic version parser, but it's good enough
    for typical 'major.minor.patch' style versions.
    """
    parts = v.split(".")
    numeric_parts = []
    for p in parts:
        num_str = ""
        for ch in p:
            if ch.isdigit():
                num_str += ch
            else:
                break
        if num_str == "":
            numeric_parts.append(0)
        else:
            numeric_parts.append(int(num_str))
    return tuple(numeric_parts)


def _is_remote_newer(current: str, remote: str) -> bool:
    """
    Returns True if remote_version > current_version.
    """
    return _parse_version(remote) > _parse_version(current)


# ---------------------------------------------------------------------------
# Update feed fetching / parsing
# ---------------------------------------------------------------------------


def _fetch_update_feed(url: str) -> dict:
    """
    Fetches and parses the remote update feed JSON.

    Raises RuntimeError on failure.
    """
    logger.info("Fetching update feed from: %s", url)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AI-System-Utility-Updater/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Update feed HTTP error: {resp.status}")
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        logger.error("Failed to fetch update feed: %s", e)
        raise RuntimeError(f"Failed to reach update server: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse update feed JSON: %s", e)
        raise RuntimeError(f"Invalid update feed JSON: {e}") from e

    if not isinstance(data, dict):
        raise RuntimeError("Update feed JSON must be an object at the top level.")

    return data


def check_for_updates() -> UpdateCheckResult:
    """
    Checks the remote update feed and determines if a newer version is available.

    Returns an UpdateCheckResult that the GUI can safely consume.
    """
    current_version = get_version()

    if not UPDATE_FEED_URL or UPDATE_FEED_URL.startswith("https://example.com"):
        msg = (
            "Update feed URL is not configured. "
            "Please set UPDATE_FEED_URL in self_updater.py to your GitHub latest.json URL."
        )
        logger.warning(msg)
        return UpdateCheckResult(
            status="error",
            message=msg,
            current_version=current_version,
            remote_version=None,
            update_info=None,
        )

    try:
        data = _fetch_update_feed(UPDATE_FEED_URL)
    except Exception as e:
        msg = f"Update check failed: {e}"
        logger.error(msg)
        return UpdateCheckResult(
            status="error",
            message=msg,
            current_version=current_version,
            remote_version=None,
            update_info=None,
        )

    latest_version = str(data.get("latest_version", "")).strip()
    minimum_supported_version = str(data.get("minimum_supported_version", "")).strip() or None
    download_url = str(data.get("download_url", "")).strip()
    changelog = data.get("changelog")

    if not latest_version or not download_url:
        msg = "Update feed is missing required fields (latest_version or download_url)."
        logger.error(msg)
        return UpdateCheckResult(
            status="error",
            message=msg,
            current_version=current_version,
            remote_version=None,
            update_info=None,
        )

    logger.info("Current version: %s, Remote latest: %s", current_version, latest_version)

    if not _is_remote_newer(current_version, latest_version):
        msg = f"You are up to date. Current version: {current_version}."
        return UpdateCheckResult(
            status="no_update",
            message=msg,
            current_version=current_version,
            remote_version=latest_version,
            update_info=None,
        )

    # Remote is newer
    info = UpdateInfo(
        version=latest_version,
        download_url=download_url,
        changelog=changelog if isinstance(changelog, str) else None,
        minimum_supported_version=minimum_supported_version,
    )

    msg_lines = [
        f"A new version is available: {latest_version}",
        f"Current version: {current_version}",
    ]
    if info.changelog:
        msg_lines.append("")
        msg_lines.append("Changelog:")
        msg_lines.append(info.changelog)

    msg = "\n".join(msg_lines)

    return UpdateCheckResult(
        status="update_available",
        message=msg,
        current_version=current_version,
        remote_version=latest_version,
        update_info=info,
    )


# ---------------------------------------------------------------------------
# Downloading updates
# ---------------------------------------------------------------------------


def download_update_file(
    update_info: UpdateInfo,
    dest_dir: Optional[os.PathLike] = None,
) -> Path:
    """
    Downloads the update file specified by UpdateInfo.download_url.

    If dest_dir is None, a temporary directory will be used.

    Returns the Path to the downloaded file.

    Raises RuntimeError on failure.
    """
    url = update_info.download_url
    if not url:
        raise RuntimeError("UpdateInfo.download_url is empty.")

    if dest_dir is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="ai_sys_utility_update_"))
    else:
        tmp_dir = Path(dest_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

    # Decide on a filename
    # Try to infer from URL, fallback to a generic name.
    filename = url.split("/")[-1] or f"AI_System_Utility_{update_info.version}.exe"
    dest_path = tmp_dir / filename

    logger.info("Downloading update from %s to %s", url, dest_path)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AI-System-Utility-Updater/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Download HTTP error: {resp.status}")
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
    except urllib.error.URLError as e:
        logger.error("Failed to download update: %s", e)
        raise RuntimeError(f"Failed to download update: {e}") from e

    logger.info("Update downloaded to %s", dest_path)
    return dest_path
