# ai_system_utility/core/ai_interpreter.py

"""
AI command interpreter for AI System Utility.

Responsibilities:
- Take a natural language request (string)
- Decide which registered actions best match
- For CLI (`main.py`): expose choose_actions_for_request(text) -> List[Action]
- For GUI (`gui.py`): expose interpret_command(text) -> str (summary of what ran)

Uses Google Gemini if configured, with a safe fallback to keyword-based
matching if the API or library is not available.
"""

from __future__ import annotations

import json
import os
from typing import List

from .actions import ACTIONS, Action
from .logger import log_event, log_action

# Optional Gemini support ----------------------------------------------------

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # library not installed or other import error
    genai = None


def _is_gemini_configured() -> bool:
    """
    Returns True if google.generativeai is importable and an API key is set.
    """
    if genai is None:
        return False
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return bool(api_key)


def _ensure_gemini_client() -> None:
    """
    Configure the Gemini client if needed.
    """
    if not _is_gemini_configured():
        return
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        log_event(f"Failed to configure Gemini client: {e}")


# ---------------------------------------------------------------------------
# Fallback keyword-based matching
# ---------------------------------------------------------------------------


def _fallback_choose_action_ids(request: str) -> List[str]:
    """
    Very simple keyword-based mapping from user text to action IDs.

    This is used when Gemini is not set up or fails. It will never be
    perfect, but it's a reasonable, safe backup.
    """
    text = request.lower()

    selected: List[str] = []

    # Cleanup
    if any(k in text for k in ["cleanup", "clean up", "clean my pc", "temp", "cache", "junk", "space"]):
        selected.append("cleanup_recommended")
    elif "prefetch" in text:
        selected.append("cleanup_prefetch")
    elif "windows update" in text and "cache" in text:
        selected.append("cleanup_windows_update_cache")
    elif "temp" in text or "temporary" in text:
        selected.append("cleanup_temp")

    # Health
    if "sfc" in text or "system file checker" in text:
        selected.append("health_sfc")
    if "dism" in text or "component store" in text:
        selected.append("health_dism")
    if "chkdsk" in text or "disk check" in text:
        selected.append("health_chkdsk")
    if any(k in text for k in ["health", "corrupt", "integrity", "fix system files"]):
        selected.append("health_full")

    # Network
    if any(k in text for k in ["no internet", "network", "wifi", "ethernet", "dns", "winsock", "reset network"]):
        selected.append("network_reset")

    # Tools
    if "task manager" in text:
        selected.append("tools_task_manager")
    if "device manager" in text:
        selected.append("tools_device_manager")
    if "services" in text:
        selected.append("tools_services")
    if "system restore" in text or "restore point" in text:
        selected.append("tools_system_restore")

    # Privacy
    if "privacy" in text and "strict" in text:
        selected.append("privacy_strict")
    elif "privacy" in text and "default" in text:
        selected.append("privacy_restore_defaults")
    elif "privacy" in text:
        selected.append("privacy_recommended")
    elif "telemetry" in text or "tracking" in text:
        selected.append("privacy_recommended")

    # If still nothing, try some generic mappings
    if not selected:
        if "clean" in text:
            selected.append("cleanup_recommended")
        elif "fix" in text or "repair" in text:
            selected.append("health_full")

    # De-duplicate while preserving order, only keep valid IDs
    seen = set()
    result: List[str] = []
    for aid in selected:
        if aid in ACTIONS and aid not in seen:
            seen.add(aid)
            result.append(aid)

    return result


# ---------------------------------------------------------------------------
# Gemini-based action selection
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """
You are an assistant that maps a Windows maintenance request to a list of internal action IDs.

You will be given:
- A natural language request from the user.
- A dictionary of known actions with their IDs, names, descriptions, and groups.

Your job:
- Choose the MOST relevant 1-3 action IDs that should be executed to satisfy the request.
- Only use action IDs that exist in the given dictionary.
- If nothing matches well, return an empty list.

Return ONLY a JSON array of strings, e.g.:
["cleanup_recommended", "health_full"]
"""

def _gemini_choose_action_ids(request: str) -> List[str]:
    """
    Uses Gemini to choose actions, if configured. Falls back to an empty list
    if something goes wrong, allowing the keyword-based logic to kick in.
    """
    if not _is_gemini_configured():
        return []

    _ensure_gemini_client()

    try:
        # Build a compact dictionary of actions that Gemini can see
        actions_summary = {
            action_id: {
                "name": action.name,
                "description": action.description,
                "group": action.group,
            }
            for action_id, action in ACTIONS.items()
        }

        prompt = (
            _SYSTEM_PROMPT
            + "\n\nKNOWN_ACTIONS_JSON:\n"
            + json.dumps(actions_summary, indent=2)
            + "\n\nUSER_REQUEST:\n"
            + request
            + "\n\nRemember: respond ONLY with a JSON array of action IDs."
        )

        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)  # type: ignore
        response = model.generate_content(prompt)
        raw = ""

        # Different versions of the client expose text differently
        if hasattr(response, "text") and response.text:
            raw = response.text
        elif getattr(response, "candidates", None):
            try:
                raw = response.candidates[0].content.parts[0].text  # type: ignore
            except Exception:
                raw = ""
        else:
            raw = str(response)

        raw = raw.strip()

        # Some models might wrap JSON in code fences
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()

        data = json.loads(raw)

        if isinstance(data, list):
            valid_ids = [aid for aid in data if isinstance(aid, str) and aid in ACTIONS]
            return valid_ids
        else:
            return []
    except Exception as e:
        log_event(f"Gemini action selection failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def choose_actions_for_request(request: str) -> List[Action]:
    """
    Main entrypoint for CLI (used by main.py).

    Returns a list of Action objects that should be run for the given
    natural-language request. May return an empty list if nothing matched.
    """
    request = (request or "").strip()
    if not request:
        return []

    # 1) Try Gemini if configured
    action_ids = _gemini_choose_action_ids(request)

    # 2) Fallback if Gemini is unavailable or returned nothing
    if not action_ids:
        action_ids = _fallback_choose_action_ids(request)

    actions: List[Action] = []
    for aid in action_ids:
        action = ACTIONS.get(aid)
        if action:
            actions.append(action)

    if actions:
        log_event(f"choose_actions_for_request: '{request}' -> {[a.id for a in actions]}")
    else:
        log_event(f"choose_actions_for_request: '{request}' -> no actions")

    return actions


def interpret_command(request: str) -> str:
    """
    Main entrypoint for GUI.

    - Selects the best actions for the request
    - Executes them immediately
    - Returns a human-readable summary string for display in the GUI log
    """
    actions = choose_actions_for_request(request)

    if not actions:
        msg = "I couldn't match that to any known action yet. Try rephrasing or be more specific."
        log_event(f"interpret_command: no actions for '{request}'")
        return msg

    results: List[str] = []
    for action in actions:
        log_action(action.name, "START")
        try:
            result = action.func()
            if result:
                results.append(f"{action.name}: {result}")
            else:
                results.append(f"{action.name}: completed.")
            log_action(action.name, "SUCCESS")
        except Exception as e:
            msg = f"{action.name}: ERROR - {e}"
            results.append(msg)
            log_action(action.name, "ERROR", str(e))

    return "\n".join(results)
