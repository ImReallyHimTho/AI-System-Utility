# ai_system_utility/main.py

import sys
import ctypes

from ai_system_utility.core.ai_interpreter import choose_actions_for_request
from ai_system_utility.core.actions import ACTIONS, Action
from ai_system_utility.core import system_tools  # for keyword fallback mapping
from ai_system_utility.core.logger import log_action, log_event


# -----------------------------
# Auto-elevation helpers
# -----------------------------

def _is_admin() -> bool:
    """
    Check if the current process is running as Administrator.
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def _ensure_admin():
    """
    If not running as Administrator, relaunch this module with elevation (UAC prompt)
    and exit the current (non-admin) process.
    """
    if _is_admin():
        return  # already elevated

    print("\n[INFO] Elevation required. Requesting administrator privileges...\n")

    # Relaunch this module as: python -m ai_system_utility.main
    params = "-m ai_system_utility.main"

    # ShellExecuteW(None, "runas", <python.exe>, params, None, 1) -> UAC prompt
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1
    )

    if rc <= 32:
        # Failed to start elevated process
        print("[ERROR] Failed to elevate the process. Please run PowerShell as Administrator and try again.")
    # Exit the current non-admin process either way
    sys.exit(0)


# -----------------------------
# Core CLI logic
# -----------------------------

def ask_confirmation(action: Action) -> bool:
    """
    Ask user to confirm dangerous actions.
    """
    print(f"\n[WARNING] The action '{action.name}' is marked as DANGEROUS.")
    print(f"Description: {action.description}")
    ans = input("Proceed? [y/N]: ").strip().lower()
    return ans == "y"


def interpret_command_keyword(text: str):
    """
    Simple keyword fallback interpreter (if AI returns nothing).
    Returns an Action or None.
    """
    t = text.lower()

    # ---- Health / repair ----
    if "sfc" in t or "system file" in t:
        return ACTIONS.get("run_sfc")

    if "dism" in t or "restore health" in t or "image health" in t:
        return ACTIONS.get("run_dism_health_restore")

    if "chkdsk" in t or "check disk" in t or "disk check" in t:
        return ACTIONS.get("run_chkdsk")

    # ---- Cleanup ----
    if "clean temp" in t or "temp files" in t or "temporary files" in t:
        return ACTIONS.get("clean_temp")

    if "prefetch" in t:
        return ACTIONS.get("clean_prefetch")

    if "software distribution" in t or "windows update cache" in t:
        return ACTIONS.get("clean_software_distribution")

    # ---- Network ----
    if "advanced" in t and "network" in t and "reset" in t:
        return ACTIONS.get("network_reset_advanced")

    if "network" in t and "reset" in t:
        return ACTIONS.get("network_reset_basic")

    # ---- System tools ----
    if "task manager" in t:
        return ACTIONS.get("open_task_manager")

    if "device manager" in t:
        return ACTIONS.get("open_device_manager")

    if "services" in t:
        return ACTIONS.get("open_services")

    if "system restore" in t or "restore point" in t:
        return ACTIONS.get("open_system_restore")

    # ---- Privacy profiles ----
    if "privacy" in t or "telemetry" in t or "tracking" in t:
        # Strict vs recommended vs restore
        if "strict" in t or "lock down" in t or "lockdown" in t or "maximum" in t or "paranoid" in t:
            return ACTIONS.get("privacy_strict")
        if "restore" in t or "default" in t or "defaults" in t or "undo" in t:
            return ACTIONS.get("privacy_restore_defaults")
        # Generic "tighten my privacy", "improve privacy", etc. -> recommended profile
        return ACTIONS.get("privacy_recommended")

    return None


def print_help():
    print("""
You can describe problems in natural language, for example:
  - "my pc is slow and acting weird"
  - "fix my internet, it keeps dropping"
  - "windows updates are stuck"
  - "open something to see running processes"
  - "tighten my privacy"
  - "lock down telemetry"
  - "restore privacy defaults"

The AI may run multiple actions in sequence.

You can also use explicit commands such as:
  - run sfc
  - run dism
  - run chkdsk
  - clean temp
  - clean prefetch
  - clean software distribution
  - reset network
  - advanced network reset
  - open task manager
  - open device manager
  - open services
  - open system restore
  - privacy recommended
  - privacy strict
  - privacy restore defaults

Type 'help' to see this again, 'exit' to quit.
""")


def main():
    print("=== AI System Utility (Gemini, Multi-Step, Plugins, Logging) ===")
    print("Describe issues in natural language, or use direct commands.")
    print("Type 'help' for options, 'exit' to quit.")

    while True:
        try:
            user = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            sys.exit(0)

        if not user:
            continue

        if user.lower() in {"exit", "quit"}:
            print("Goodbye.")
            sys.exit(0)

        if user.lower() in {"help", "commands"}:
            print_help()
            continue

        # 1. Try AI multi-step interpreter
        log_event(f"User input: {user}")
        action_names = choose_actions_for_request(user)

        if action_names:
            print(f"[AI] Planned actions (in order): {', '.join(action_names)}")
            for name in action_names:
                action = ACTIONS.get(name)
                if not action:
                    continue

                print(f"\n[STEP] {action.name}: {action.description}")

                if action.dangerous:
                    if not ask_confirmation(action):
                        print(f"[SKIP] {action.name}")
                        log_action(action.name, "SKIP", "User declined dangerous action.")
                        continue

                log_action(action.name, "START")
                try:
                    action.fn()
                    log_action(action.name, "SUCCESS")
                except Exception as e:
                    log_action(action.name, "ERROR", str(e))
                    print(f"[ERROR] Action '{action.name}' failed: {e}")
            continue

        # 2. Fallback: keyword interpreter (single action)
        fallback_action = interpret_command_keyword(user)
        if fallback_action:
            action = fallback_action
            print(f"[Fallback] Selected: {action.name}")
            print(action.description)

            if action.dangerous:
                if not ask_confirmation(action):
                    print(f"[SKIP] {action.name}")
                    log_action(action.name, "SKIP", "User declined dangerous action (fallback).")
                    continue

            log_action(action.name, "START", "Fallback keyword interpreter.")
            try:
                action.fn()
                log_action(action.name, "SUCCESS")
            except Exception as e:
                log_action(action.name, "ERROR", str(e))
                print(f"[ERROR] Action '{action.name}' failed: {e}")
        else:
            print("I couldn't understand that yet. Try rephrasing or type 'help'.")
            log_event("No action matched for input.")


if __name__ == "__main__":
    # Auto-elevate before doing anything else
    _ensure_admin()
    main()
