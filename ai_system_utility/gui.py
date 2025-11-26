# ai_system_utility/gui.py

import os
import sys
import ctypes
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

# IMPORTANT: use absolute imports so they work in a frozen EXE too
from ai_system_utility.core.ai_interpreter import interpret_command
from ai_system_utility.core.logger import get_logger
from ai_system_utility.core.system_info import get_system_info
from ai_system_utility.core.actions import get_actions_by_group, get_action_by_id
from ai_system_utility.core.version import get_version
from ai_system_utility.core.self_updater import check_for_updates, download_update_file
from ai_system_utility.core import startup


# ---------------------- Elevation Helpers ----------------------


def _is_windows() -> bool:
    return os.name == "nt"


def _is_admin() -> bool:
    if not _is_windows():
        # On non-Windows, assume permissions are fine
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        # If we can't determine, play it safe and say not admin
        return False


def ensure_admin() -> None:
    """
    Ensures the process is running elevated on Windows.

    Relaunches the current module via:
        python -m ai_system_utility.gui [args...]
    with ShellExecuteW + 'runas'.
    """
    if not _is_windows():
        return

    if _is_admin():
        return

    # Rebuild command line as a module invocation.
    params = "-m ai_system_utility.gui"
    if len(sys.argv) > 1:
        params += " " + " ".join(sys.argv[1:])

    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            None,
            1,
        )
    except Exception:
        rc = 0

    # On error, ShellExecuteW returns <= 32.
    if rc <= 32:
        sys.stderr.write(
            "Failed to relaunch AI System Utility with administrator privileges.\n"
        )
    # Always exit the non-elevated instance; if elevation succeeded, new process takes over.
    sys.exit(0)


# ---------------------- Main GUI Class ----------------------


class SystemUtilityGUI(tk.Tk):
    """
    Main GUI for AI System Utility.

    - Home tab:
        * Natural-language command input
        * Quick actions (incl. Full Maintenance)
        * Activity log
        * System Info panel (live)
    - Additional tabs:
        * Privacy / Cleanup / Network / Health / Tools
          Populated dynamically from actions registry.
    - Menu bar:
        * Settings -> Start tray agent with Windows (toggle)
        * Help -> Check for Updates (with auto-download option)
        * Help -> About
    """

    SYSTEM_INFO_REFRESH_MS = 5000  # 5 seconds

    def __init__(self) -> None:
        super().__init__()

        self.logger = get_logger("gui")

        version = get_version()
        self.title(f"AI System Utility v{version}")
        self.geometry("1150x750")
        self.minsize(950, 650)

        self._create_style()
        self._create_menu()
        self._create_widgets()
        self._start_system_info_updater()

    # ---------------------- Styling / Theme ----------------------

    def _create_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            # Fall back to default theme
            pass

        bg = "#1e1e1e"
        panel_bg = "#252526"
        text_fg = "#f0f0f0"
        accent = "#0078d4"
        border = "#3c3c3c"

        self.configure(bg=bg)

        style.configure(
            ".",
            background=bg,
            foreground=text_fg,
            fieldbackground=panel_bg,
            bordercolor=border,
        )

        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text_fg)

        # Notebook (tabs)
        style.configure(
            "TNotebook",
            background=bg,
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            padding=(14, 8),
            background="#2d2d30",
            foreground=text_fg,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", accent)],
            foreground=[("selected", "#ffffff")],
        )

        # LabelFrames
        style.configure(
            "Quick.TLabelframe",
            background=bg,
            foreground=text_fg,
            bordercolor=border,
        )
        style.configure(
            "Log.TLabelframe",
            background=bg,
            foreground=text_fg,
            bordercolor=border,
        )
        style.configure(
            "SystemInfo.TLabelframe",
            background=bg,
            foreground=text_fg,
            bordercolor=border,
        )
        style.configure(
            "GroupActions.TLabelframe",
            background=bg,
            foreground=text_fg,
            bordercolor=border,
        )

        # Buttons
        style.configure(
            "Action.TButton",
            padding=(10, 6),
            relief="flat",
        )
        style.map(
            "Action.TButton",
            background=[("!disabled", "#2d2d30"), ("active", "#3e3e42")],
            foreground=[("!disabled", text_fg)],
        )

        style.configure(
            "Primary.TButton",
            padding=(10, 6),
            relief="flat",
        )
        style.map(
            "Primary.TButton",
            background=[("!disabled", accent), ("active", "#1490ff")],
            foreground=[("!disabled", "#ffffff")],
        )

        # System info labels
        style.configure(
            "SystemInfo.TLabel",
            background=bg,
            foreground=text_fg,
        )

    # ---------------------- Menu Bar ----------------------

    def _create_menu(self) -> None:
        menubar = tk.Menu(self)

        # Settings menu
        settings_menu = tk.Menu(menubar, tearoff=0)

        self.tray_autostart_var = tk.BooleanVar(value=False)

        if startup.is_tray_autostart_supported():
            try:
                self.tray_autostart_var.set(startup.is_tray_autostart_enabled())
            except Exception as e:
                self.logger.warning("Failed to read tray autostart state: %s", e)
                self.tray_autostart_var.set(False)

            settings_menu.add_checkbutton(
                label="Start tray agent with Windows",
                variable=self.tray_autostart_var,
                command=self._on_toggle_tray_autostart,
            )
        else:
            settings_menu.add_command(
                label="Start tray agent with Windows (not supported)",
                state="disabled",
            )

        menubar.add_cascade(label="Settings", menu=settings_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Check for Updates...", command=self._on_check_for_updates)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._on_about)

        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    # ---------------------- Top-level Layout ----------------------

    def _create_widgets(self) -> None:
        # The whole window is a Notebook with tabs.
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Define tabs
        self.home_tab = ttk.Frame(self.notebook)
        self.privacy_tab = ttk.Frame(self.notebook)
        self.cleanup_tab = ttk.Frame(self.notebook)
        self.network_tab = ttk.Frame(self.notebook)
        self.health_tab = ttk.Frame(self.notebook)
        self.tools_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.home_tab, text="Home")
        self.notebook.add(self.privacy_tab, text="Privacy")
        self.notebook.add(self.cleanup_tab, text="Cleanup")
        self.notebook.add(self.network_tab, text="Network")
        self.notebook.add(self.health_tab, text="Health")
        self.notebook.add(self.tools_tab, text="Tools")

        self._create_home_tab()
        self._create_group_tabs()

    # ---------------------- Home Tab ----------------------

    def _create_home_tab(self) -> None:
        """
        Home tab layout:
        - Row 0: command input + Run button (spans both columns)
        - Row 1:
            * Column 0: Quick Actions + Activity Log
            * Column 1: System Info panel
        """
        self.home_tab.columnconfigure(0, weight=3)
        self.home_tab.columnconfigure(1, weight=2)
        self.home_tab.rowconfigure(0, weight=0)
        self.home_tab.rowconfigure(1, weight=1)

        # Input row
        input_frame = ttk.Frame(self.home_tab)
        input_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        input_frame.columnconfigure(1, weight=0)

        self.command_var = tk.StringVar()
        self.command_entry = ttk.Entry(input_frame, textvariable=self.command_var)
        self.command_entry.grid(row=0, column=0, sticky="ew")
        self.command_entry.bind("<Return>", lambda e: self._on_run_command())

        run_button = ttk.Button(
            input_frame,
            text="Run",
            style="Primary.TButton",
            command=self._on_run_command,
        )
        run_button.grid(row=0, column=1, sticky="w", padx=(5, 0))

        # Left side: quick actions + log
        left_frame = ttk.Frame(self.home_tab)
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left_frame.rowconfigure(0, weight=0)
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        self._create_quick_actions(left_frame)
        self._create_log(left_frame)

        # Right side: system info
        self._create_system_info_panel(self.home_tab)

    def _create_quick_actions(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Quick Actions", style="Quick.TLabelframe")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for i in range(6):
            frame.columnconfigure(i, weight=1)

        buttons = [
            ("Privacy", lambda: self._run_quick_action("privacy")),
            ("Cleanup", lambda: self._run_quick_action("cleanup")),
            ("Network", lambda: self._run_quick_action("network")),
            ("Health", lambda: self._run_quick_action("health")),
            ("Tools", lambda: self._run_quick_action("tools")),
            ("Full Maintenance", self._run_full_maintenance),
        ]

        for col, (text, cmd) in enumerate(buttons):
            btn = ttk.Button(
                frame,
                text=text,
                style="Action.TButton",
                command=cmd,
            )
            btn.grid(row=0, column=col, padx=3, pady=5, sticky="ew")

    def _create_log(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Activity Log", style="Log.TLabelframe")
        frame.grid(row=1, column=0, sticky="nsew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            frame,
            wrap="word",
            state="disabled",
            bg="#252526",
            fg="#f0f0f0",
            height=20,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _create_system_info_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="System Info", style="SystemInfo.TLabelframe")
        frame.grid(row=1, column=1, sticky="nsew")

        for i in range(8):
            frame.rowconfigure(i, weight=0)
        frame.rowconfigure(8, weight=1)
        frame.columnconfigure(0, weight=1)

        self.sysinfo_labels = {}

        fields = [
            "OS",
            "Hostname",
            "Machine",
            "Processor",
            "Uptime",
            "CPU Usage",
            "RAM Usage",
        ]
        for idx, field in enumerate(fields):
            lbl = ttk.Label(
                frame,
                text=f"{field}:",
                style="SystemInfo.TLabel",
                anchor="w",
            )
            lbl.grid(row=idx, column=0, sticky="w", padx=5, pady=2)
            self.sysinfo_labels[field] = lbl

        self.disk_text = tk.Text(
            frame,
            wrap="word",
            height=8,
            state="disabled",
            bg="#252526",
            fg="#f0f0f0",
        )
        self.disk_text.grid(row=len(fields), column=0, sticky="nsew", padx=5, pady=(8, 5))

    # ---------------------- Group Tabs ----------------------

    def _create_group_tabs(self) -> None:
        self._populate_group_tab(self.privacy_tab, "privacy")
        self._populate_group_tab(self.cleanup_tab, "cleanup")
        self._populate_group_tab(self.network_tab, "network")
        self._populate_group_tab(self.health_tab, "health")
        self._populate_group_tab(self.tools_tab, "tools")

    def _populate_group_tab(self, tab: ttk.Frame, group: str) -> None:
        """
        Creates a scrollable list of actions for a given group.
        Each action is shown with name, description, and a 'Run' button.
        """
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)

        # Use a canvas + inner frame for scrollable content
        canvas = tk.Canvas(tab, highlightthickness=0, bg="#1e1e1e")
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")

        canvas.configure(yscrollcommand=scrollbar.set)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: tk.Event) -> None:
            # Make inner frame match canvas width
            canvas.itemconfig(inner_id, width=event.width)

        inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        header = ttk.Label(
            inner,
            text=f"{group.capitalize()} Actions",
            style="SystemInfo.TLabel",
        )
        header.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        actions = []
        try:
            actions = get_actions_by_group(group)
        except Exception as e:
            err_lbl = ttk.Label(inner, text=f"Error loading actions: {e}")
            err_lbl.grid(row=1, column=0, sticky="w", padx=10, pady=5)
            return

        if not actions:
            no_lbl = ttk.Label(inner, text="No actions registered for this group.")
            no_lbl.grid(row=1, column=0, sticky="w", padx=10, pady=5)
            return

        for idx, action in enumerate(actions, start=1):
            frame = ttk.LabelFrame(
                inner,
                text=action.name,
                style="GroupActions.TLabelframe",
            )
            frame.grid(row=idx, column=0, sticky="ew", padx=10, pady=6)
            frame.columnconfigure(0, weight=1)
            frame.columnconfigure(1, weight=0)

            desc = getattr(action, "description", "") or ""
            desc_lbl = ttk.Label(frame, text=desc, style="SystemInfo.TLabel", wraplength=600, justify="left")
            desc_lbl.grid(row=0, column=0, sticky="w", padx=8, pady=5)

            btn = ttk.Button(
                frame,
                text="Run",
                style="Action.TButton",
                command=lambda a=action: self._on_run_action(a),
            )
            btn.grid(row=0, column=1, sticky="e", padx=8, pady=5)

    # ---------------------- System Info Updating ----------------------

    def _start_system_info_updater(self) -> None:
        self._update_system_info()
        self.after(self.SYSTEM_INFO_REFRESH_MS, self._start_system_info_updater)

    def _format_uptime(self, seconds: int) -> str:
        if seconds <= 0:
            return "Unknown"

        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)

        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes or not parts:
            parts.append(f"{minutes}m")
        return " ".join(parts)

    def _update_system_info(self) -> None:
        try:
            info = get_system_info()
        except Exception as e:
            self._log(f"Failed to get system info: {e}")
            return

        self.sysinfo_labels["OS"].configure(
            text=f"OS: {info.os} ({info.os_version})"
        )
        self.sysinfo_labels["Hostname"].configure(
            text=f"Hostname: {info.hostname}"
        )
        self.sysinfo_labels["Machine"].configure(
            text=f"Machine: {info.machine}"
        )
        self.sysinfo_labels["Processor"].configure(
            text=f"Processor: {info.processor}"
        )
        self.sysinfo_labels["Uptime"].configure(
            text=f"Uptime: {self._format_uptime(info.uptime_seconds)}"
        )
        self.sysinfo_labels["CPU Usage"].configure(
            text=f"CPU Usage: {info.cpu_percent:.1f}%"
        )
        self.sysinfo_labels["RAM Usage"].configure(
            text=(
                f"RAM Usage: {info.used_ram_gb:.1f} / "
                f"{info.total_ram_gb:.1f} GB ({info.ram_percent:.1f}%)"
            )
        )

        self.disk_text.configure(state="normal")
        self.disk_text.delete("1.0", "end")

        if not info.disks:
            self.disk_text.insert("end", "No disk info available.\n")
        else:
            for d in info.disks:
                self.disk_text.insert(
                    "end",
                    (
                        f"{d.device} ({d.mountpoint}) - "
                        f"{d.used_gb:.1f}/{d.total_gb:.1f} GB "
                        f"({d.percent_used:.1f}% used)\n"
                    ),
                )

        self.disk_text.configure(state="disabled")

    # ---------------------- Logging ----------------------

    def _log(self, message: str) -> None:
        self.logger.info(message)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ---------------------- Command + Action Handling ----------------------

    def _on_run_command(self) -> None:
        text = self.command_var.get().strip()
        if not text:
            return

        self._log(f"> {text}")
        self.command_var.set("")

        try:
            result = interpret_command(text)
            if result:
                self._log(str(result))
        except Exception as e:
            self._log(f"Error while interpreting command: {e}")
            messagebox.showerror("Error", str(e))

    def _run_quick_action(self, category: str) -> None:
        """
        Quick action buttons on Home tab.

        For now they send high-level natural-language prompts into the interpreter.
        Later we can wire them directly to specific action IDs if you want.
        """
        mapping = {
            "privacy": "Apply the recommended privacy profile for Windows.",
            "cleanup": "Run a safe system cleanup: temp files, prefetch, and Windows Update cache.",
            "network": "Perform a standard network reset including DNS flush and Winsock reset.",
            "health": "Run system health checks such as SFC and DISM.",
            "tools": "Open useful system tools like Task Manager, Device Manager, Services, and System Restore.",
        }

        text = mapping.get(category)
        if not text:
            return

        # Confirm for potentially impactful categories
        if category in {"cleanup", "network", "health"}:
            if not messagebox.askyesno(
                "Confirm Quick Action",
                f"This quick action will perform system-level changes.\n\n"
                f"Proceed with '{category.capitalize()}'?",
            ):
                return

        self._log(f"> [Quick] {text}")
        try:
            result = interpret_command(text)
            if result:
                self._log(str(result))
        except Exception as e:
            self._log(f"Quick action error: {e}")
            messagebox.showerror("Quick Action Error", str(e))

    def _on_run_action(self, action) -> None:
        """
        Runs an Action object from the actions registry.
        Respects the 'dangerous' flag with a confirmation dialog.
        """
        dangerous = getattr(action, "dangerous", False)
        name = getattr(action, "name", getattr(action, "id", "Unknown Action"))

        if dangerous:
            if not messagebox.askyesno(
                "Confirm Action",
                f"This action is marked as dangerous and may affect system stability.\n\n"
                f"Run '{name}'?",
            ):
                return

        self._log(f"Running action: {name}")
        try:
            func = getattr(action, "func", None)
            if func is None:
                raise RuntimeError("Action has no callable 'func' attribute.")
            result = func()
            if result:
                self._log(str(result))
            self._log(f"Action completed: {name}")
        except Exception as e:
            self._log(f"Action failed: {e}")
            messagebox.showerror("Action Failed", str(e))

    def _run_action_by_id(self, action_id: str) -> None:
        """
        Helper if you want to call specific actions directly by ID.
        Currently not wired to quick actions, but ready to use.
        """
        try:
            action = get_action_by_id(action_id)
        except Exception as e:
            self._log(f"Failed to lookup action '{action_id}': {e}")
            messagebox.showerror("Action Lookup Failed", str(e))
            return

        if not action:
            self._log(f"Action '{action_id}' not found.")
            messagebox.showerror("Action Not Found", f"Action '{action_id}' not found.")
            return

        self._on_run_action(action)

    # ---------------------- Full Maintenance ----------------------

    def _run_full_maintenance(self) -> None:
        """
        One-click full maintenance:
        - Recommended Cleanup
        - Full Health Check
        - Recommended Privacy Profile
        - Network Reset

        All in sequence, with a single confirmation at the start.
        """
        if not messagebox.askyesno(
            "Full Maintenance",
            "This will run a full maintenance sequence:\n\n"
            "- Recommended cleanup\n"
            "- Full health check (SFC + DISM)\n"
            "- Recommended privacy profile\n"
            "- Network reset\n\n"
            "Proceed?",
        ):
            return

        steps = [
            ("cleanup_recommended", "Recommended Cleanup"),
            ("health_full", "Full Health Check"),
            ("privacy_recommended", "Recommended Privacy Profile"),
            ("network_reset", "Network Reset"),
        ]

        self._log("[Full Maintenance] Starting full maintenance sequence...")

        for action_id, label in steps:
            try:
                action = get_action_by_id(action_id)
            except Exception as e:
                self._log(f"[Full Maintenance] Failed to lookup '{label}': {e}")
                continue

            if not action:
                self._log(f"[Full Maintenance] Action '{action_id}' not found.")
                continue

            self._log(f"[Full Maintenance] Running: {label}")
            try:
                result = action.func()
                if result:
                    self._log(f"[Full Maintenance] {label}: {result}")
                else:
                    self._log(f"[Full Maintenance] {label}: completed.")
            except Exception as e:
                self._log(f"[Full Maintenance] {label} failed: {e}")

        self._log("[Full Maintenance] Sequence completed.")
        messagebox.showinfo(
            "Full Maintenance",
            "Full maintenance sequence completed.\n\n"
            "Check the Activity Log for detailed results.",
        )

    # ---------------------- Updater / About / Settings ----------------------

    def _on_check_for_updates(self) -> None:
        """
        Called when the user selects Help -> Check for Updates.
        Uses self_updater.check_for_updates() and shows dialogs accordingly.
        """
        self._log("Checking for updates...")
        result = check_for_updates()

        if result.status == "error":
            self._log(result.message)
            messagebox.showerror("Update Check Failed", result.message)
            return

        if result.status == "no_update":
            self._log(result.message)
            messagebox.showinfo("Up to Date", result.message)
            return

        if result.status == "update_available" and result.update_info:
            self._log("Update available:")
            self._log(result.message)

            # Ask if user wants auto-download
            auto_download = messagebox.askyesno(
                "Update Available",
                f"A new version ({result.remote_version}) is available.\n\n"
                "Do you want to download the installer now?",
            )

            if auto_download:
                try:
                    file_path = download_update_file(result.update_info)
                    self._log(f"Update downloaded to: {file_path}")

                    # Ask to run installer
                    run_now = messagebox.askyesno(
                        "Installer Downloaded",
                        "The update installer has been downloaded.\n\n"
                        "Run it now?",
                    )
                    if run_now:
                        try:
                            if os.name == "nt":
                                os.startfile(str(file_path))  # type: ignore[attr-defined]
                            else:
                                subprocess.Popen([str(file_path)])
                        except Exception as e:
                            messagebox.showerror(
                                "Failed to Launch Installer",
                                f"Could not start installer:\n{e}",
                            )
                    else:
                        messagebox.showinfo(
                            "Installer Saved",
                            f"You can run the installer later from:\n{file_path}",
                        )

                except Exception as e:
                    self._log(f"Update download failed: {e}")
                    messagebox.showerror(
                        "Download Failed",
                        f"Could not download update:\n{e}",
                    )
            else:
                # Fallback: offer to open the download page
                if messagebox.askyesno(
                    "Open Download Page",
                    "Do you want to open the download page in your browser instead?",
                ):
                    try:
                        webbrowser.open(result.update_info.download_url)
                    except Exception as e:
                        messagebox.showerror("Failed to Open Browser", str(e))
                else:
                    messagebox.showinfo(
                        "Update Info",
                        "You can update later via Help -> Check for Updates.\n\n"
                        "Details:\n\n" + result.message,
                    )

            return

        # Fallback, shouldn't normally hit here
        messagebox.showinfo("Update Check", result.message)

    def _on_about(self) -> None:
        version = get_version()
        text = (
            f"AI System Utility\n"
            f"Version: {version}\n\n"
            "Windows maintenance assistant with:\n"
            "- AI-powered natural language commands\n"
            "- System cleanup, health checks, and tools\n"
            "- Privacy profiles and network repair\n"
            "- Tray agent and background health monitoring\n"
        )
        messagebox.showinfo("About", text)

    def _on_toggle_tray_autostart(self) -> None:
        """
        Handles the Settings -> Start tray agent with Windows checkbox.
        """
        if not startup.is_tray_autostart_supported():
            messagebox.showerror(
                "Not Supported",
                "Tray auto-start is not supported on this platform.",
            )
            self.tray_autostart_var.set(False)
            return

        enable = self.tray_autostart_var.get()
        try:
            if enable:
                startup.enable_tray_autostart()
                self._log("Tray auto-start enabled (Run key updated).")
            else:
                startup.disable_tray_autostart()
                self._log("Tray auto-start disabled (Run key value removed).")
        except Exception as e:
            self._log(f"Failed to update tray auto-start: {e}")
            messagebox.showerror(
                "Tray Auto-start Failed",
                f"Could not update tray auto-start setting:\n{e}",
            )
            # Re-sync checkbox with actual state
            try:
                self.tray_autostart_var.set(startup.is_tray_autostart_enabled())
            except Exception:
                self.tray_autostart_var.set(False)


# ---------------------- Entry Point ----------------------


def main() -> None:
    ensure_admin()
    app = SystemUtilityGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
