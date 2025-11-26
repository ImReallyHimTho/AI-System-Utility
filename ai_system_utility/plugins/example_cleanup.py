# plugins/example_cleanup.py
from typing import Dict
from ai_system_utility.core.actions import Action
from ai_system_utility.core import system_tools

def register(actions: Dict[str, Action]) -> None:
    """
    Example plugin that adds a combined cleanup action.
    """
    def deep_cleanup():
        system_tools.clean_temp()
        system_tools.clean_prefetch()

    actions["deep_cleanup"] = Action(
        "deep_cleanup",
        "Run a deeper cleanup: TEMP + Prefetch.",
        deep_cleanup,
        dangerous=False,
        group="cleanup",
    )
