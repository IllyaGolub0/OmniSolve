from datetime import datetime
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog
import webbrowser
from typing import Callable, Dict, List, Optional

from core.config import AppConfig, PROVIDERS, PROMPT_PROFILES, LANGUAGE_MODES
from core.providers import MultiLLMClient, SolveResult, fetch_provider_models
from core.capture import ScreenCapturer, copy_to_clipboard, send_toast_notification
from core.hotkeys import GlobalHotkeyManager
from ui.theme import THEMES
from ui.components import HoverButton, RegionSelectorOverlay, Tooltip


class OmniSolveApp:
    """Modern Multi-LLM Floating HUD & Desktop Interface for AI Screen & Exam Solving."""

    def __init__(
        self,
        root: tk.Tk,
        config: AppConfig,
        llm_client: MultiLLMClient,
        capturer: ScreenCapturer,
        ui_queue: queue.Queue,
        trigger_event: threading.Event,
        pause_event: threading.Event,
        exit_event: threading.Event,
    ):
        self.root = root
        self.config = config
        self.llm_client = llm_client
        self.capturer = capturer
        self.ui_queue = ui_queue
        self.trigger_event = trigger_event
        self.pause_event = pause_event
        self.exit_event = exit_event

        self.palette = THEMES.get(self.config.theme, THEMES["mocha"])
        self.is_collapsed = False
        self.is_hidden_boss = False
        self.is_stealth_opacity = False
        self.expanded_width = 530
        self.expanded_height = 520
        self.active_tab = "solver"

        self.history_items: List[Dict] = []
        self.current_short_answer: str = ""

        # Provider display maps
        self.provider_ids = list(PROVIDERS.keys())
        self.provider_names = [PROVIDERS[k]["name"] for k in self.provider_ids]
        self.provider_short_names = [PROVIDERS[k]["short"] for k in self.provider_ids]

        self._setup_window()
        self._setup_ttk_styles()
        self._build_title_bar()
        self._build_mini_answer_strip()
        self._build_tab_bar()

        # Container for tabs
        self.content_container = tk.Frame(self.root, bg=self.palette["bg_panel"])
        self.content_container.pack(fill="both", expand=True, padx=10, pady=(4, 0))

        self.tab_frames: Dict[str, tk.Frame] = {}
        self._build_solver_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self._build_footer_bar()

        self.switch_tab("solver")
        self._sync_pause_button()
        self._update_region_button_ui()

        # Global Windows Hotkeys
        self.hotkeys = GlobalHotkeyManager(
            {
                "solve": lambda: self.root.after(0, self.trigger_solve_now),
                "pause": lambda: self.root.after(0, self.toggle_pause),
                "region": lambda: self.root.after(0, self.open_region_selector),
                "boss_key": lambda: self.root.after(0, self.toggle_boss_key),
            }
        )
        self.hotkeys.start()

        # Start UI queue polling
        self.root.after(80, self._poll_queue)

    # ========================================================================
    # Window & Styling Setup
    # ========================================================================
    def _setup_window(self) -> None:
        self.root.title("OmniSolve AI — Exam & Screen Assistant")
        self.root.configure(
            bg=self.palette["bg_root"],
            highlightbackground=self.palette["border"],
            highlightcolor=self.palette["border_focus"],
            highlightthickness=1,
        )
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", self.config.always_on_top)
        self.root.attributes("-alpha", self.config.window_opacity)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(20, sw - self.expanded_width - 30)
        y = max(20, sh - self.expanded_height - 70)
        self.root.geometry(f"{self.expanded_width}x{self.expanded_height}+{x}+{y}")

    def _setup_ttk_styles(self) -> None:
        p = self.palette
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=p["bg_input"],
            background=p["bg_hover"],
            foreground=p["fg_primary"],
            darkcolor=p["bg_panel"],
            lightcolor=p["bg_panel"],
            arrowcolor=p["fg_primary"],
            bordercolor=p["border"],
            selectbackground=p["bg_input"],
            selectforeground=p["fg_primary"],
            padding=3,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", p["bg_input"]), ("!disabled", p["bg_input"])],
            foreground=[("readonly", p["fg_primary"]), ("!disabled", p["fg_primary"])],
            selectbackground=[("readonly", p["bg_input"])],
            selectforeground=[("readonly", p["fg_primary"])],
        )
        self.root.option_add("*TCombobox*Listbox.background", p["bg_card"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["fg_primary"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["accent_fg"])
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))

    # ========================================================================
    # Custom Title Bar & Mini-HUD Strip
    # ========================================================================
    def _build_title_bar(self) -> None:
        p = self.palette
        self.title_bar = tk.Frame(self.root, bg=p["bg_title"], height=38)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        self.title_label = tk.Label(
            self.title_bar,
            text="✨ OmniSolve AI",
            fg=p["fg_primary"],
            bg=p["bg_title"],
            font=("Segoe UI", 10, "bold"),
        )
        self.title_label.pack(side="left", padx=(12, 6))

        # Active Provider + Model Pill Badge
        self.model_badge = tk.Label(
            self.title_bar,
            text=self._format_badge_text(),
            fg=p["accent"],
            bg=p["bg_card"],
            font=("Segoe UI", 8, "bold"),
            padx=7,
            pady=2,
            cursor="hand2",
        )
        self.model_badge.pack(side="left", padx=4, pady=7)
        self.model_badge.bind("<Button-1>", lambda _e: self.switch_tab("settings"))
        Tooltip(self.model_badge, "Click to configure AI provider & model")

        # Drag bindings
        for w in (self.title_bar, self.title_label):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # Window Control Buttons (Right side)
        self.btn_close = HoverButton(
            self.title_bar,
            text="✕",
            bg_normal=p["bg_title"],
            bg_hover=p["danger"],
            fg_normal=p["fg_secondary"],
            fg_hover="#11111b",
            font=("Segoe UI", 9, "bold"),
            padx=11,
            command=self.on_close,
        )
        self.btn_close.pack(side="right", fill="y")
        Tooltip(self.btn_close, "Close application")

        self.btn_collapse = HoverButton(
            self.title_bar,
            text="➖",
            bg_normal=p["bg_title"],
            bg_hover=p["bg_hover"],
            fg_normal=p["warning"],
            font=("Segoe UI", 9),
            padx=9,
            command=self.toggle_collapse,
        )
        self.btn_collapse.pack(side="right", fill="y")
        Tooltip(self.btn_collapse, "Collapse to compact Mini-HUD")

        self.btn_stealth = HoverButton(
            self.title_bar,
            text="👻",
            bg_normal=p["bg_title"],
            bg_hover=p["bg_hover"],
            fg_normal=p["fg_secondary"],
            font=("Segoe UI", 9),
            padx=8,
            command=self.toggle_stealth_opacity,
        )
        self.btn_stealth.pack(side="right", fill="y")
        Tooltip(self.btn_stealth, "Toggle Ghost Opacity (45% / 96%)")

        pin_fg = p["success"] if self.config.always_on_top else p["fg_muted"]
        self.btn_pin = HoverButton(
            self.title_bar,
            text="📌",
            bg_normal=p["bg_title"],
            bg_hover=p["bg_hover"],
            fg_normal=pin_fg,
            font=("Segoe UI", 9),
            padx=8,
            command=self.toggle_pin,
        )
        self.btn_pin.pack(side="right", fill="y")
        Tooltip(self.btn_pin, "Toggle Always-on-Top")

    def _build_mini_answer_strip(self) -> None:
        """Compact answer bar shown only when the window is collapsed into Mini-HUD mode."""
        p = self.palette
        self.mini_strip = tk.Frame(self.root, bg=p["bg_panel"], padx=10, pady=6)
        self.mini_status_dot = tk.Label(
            self.mini_strip, text="●", fg=p["success"], bg=p["bg_panel"], font=("Segoe UI", 10)
        )
        self.mini_status_dot.pack(side="left", padx=(0, 6))

        self.mini_answer_lbl = tk.Label(
            self.mini_strip,
            text="Ready — Press Alt+S or Solve",
            fg=p["fg_primary"],
            bg=p["bg_panel"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.mini_answer_lbl.pack(side="left", fill="x", expand=True)

        self.mini_solve_btn = HoverButton(
            self.mini_strip,
            text="⚡ Solve",
            bg_normal=p["accent"],
            bg_hover=p["accent_hover"],
            fg_normal=p["accent_fg"],
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            command=self.trigger_solve_now,
        )
        self.mini_solve_btn.pack(side="right", padx=(6, 0))

    # ========================================================================
    # Segmented Navigation Tabs
    # ========================================================================
    def _build_tab_bar(self) -> None:
        p = self.palette
        self.tab_bar = tk.Frame(self.root, bg=p["bg_root"], padx=10, pady=6)
        self.tab_bar.pack(fill="x", side="top")

        self.tab_buttons: Dict[str, tk.Button] = {}
        tabs = [
            ("solver", "🎯 Solver HUD"),
            ("history", "📜 History (0)"),
            ("settings", "⚙ Settings & Models"),
        ]
        for tab_id, label in tabs:
            btn = tk.Button(
                self.tab_bar,
                text=label,
                bd=0,
                relief="flat",
                font=("Segoe UI", 9, "bold"),
                pady=5,
                cursor="hand2",
                command=lambda t=tab_id: self.switch_tab(t),
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.tab_buttons[tab_id] = btn

    def switch_tab(self, tab_id: str) -> None:
        p = self.palette
        self.active_tab = tab_id
        for tid, frame in self.tab_frames.items():
            frame.pack_forget()
        if tab_id in self.tab_frames:
            self.tab_frames[tab_id].pack(fill="both", expand=True)

        for tid, btn in self.tab_buttons.items():
            if tid == tab_id:
                btn.configure(
                    bg=p["accent"],
                    fg=p["accent_fg"],
                    activebackground=p["accent_hover"],
                    activeforeground=p["accent_fg"],
                )
            else:
                btn.configure(
                    bg=p["bg_card"],
                    fg=p["fg_secondary"],
                    activebackground=p["bg_hover"],
                    activeforeground=p["fg_primary"],
                )

    # ========================================================================
    # TAB 1: Solver HUD
    # ========================================================================
    def _build_solver_tab(self) -> None:
        p = self.palette
        frame = tk.Frame(self.content_container, bg=p["bg_panel"])
        self.tab_frames["solver"] = frame

        # 1. Status & Cooldown Progress Header
        status_container = tk.Frame(frame, bg=p["bg_panel"])
        status_container.pack(fill="x", side="top", pady=(2, 6))

        status_top = tk.Frame(status_container, bg=p["bg_panel"])
        status_top.pack(fill="x")

        self.status_dot = tk.Label(
            status_top, text="●", fg=p["success"], bg=p["bg_panel"], font=("Segoe UI", 11)
        )
        self.status_dot.pack(side="left")

        self.status_label = tk.Label(
            status_top,
            text="Ready to solve",
            fg=p["fg_primary"],
            bg=p["bg_panel"],
            font=("Segoe UI", 9, "bold"),
        )
        self.status_label.pack(side="left", padx=5)

        self.meta_label = tk.Label(
            status_top,
            text=f"{self.config.mode.upper()} MODE",
            fg=p["fg_muted"],
            bg=p["bg_panel"],
            font=("Segoe UI", 8),
        )
        self.meta_label.pack(side="right")

        # Thin progress bar canvas
        self.progress_canvas = tk.Canvas(
            status_container, height=3, bg=p["bg_input"], highlightthickness=0
        )
        self.progress_canvas.pack(fill="x", pady=(4, 0))
        self.progress_rect = self.progress_canvas.create_rectangle(
            0, 0, 0, 3, fill=p["accent"], width=0
        )

        # 2. Highlighted Short Answer Banner Card
        self.answer_card = tk.Frame(
            frame,
            bg=p["bg_card"],
            highlightbackground=p["border"],
            highlightthickness=1,
            padx=10,
            pady=7,
        )
        self.answer_card.pack(fill="x", side="top", pady=(0, 8))

        ans_header = tk.Frame(self.answer_card, bg=p["bg_card"])
        ans_header.pack(fill="x")

        self.ans_tag_lbl = tk.Label(
            ans_header,
            text="📌 CORRECT ANSWER",
            fg=p["cyan"],
            bg=p["bg_card"],
            font=("Segoe UI", 7, "bold"),
        )
        self.ans_tag_lbl.pack(side="left")

        self.btn_copy_ans = HoverButton(
            ans_header,
            text="📋 Copy",
            bg_normal=p["bg_input"],
            bg_hover=p["accent"],
            fg_normal=p["fg_primary"],
            fg_hover=p["accent_fg"],
            font=("Segoe UI", 8, "bold"),
            padx=7,
            pady=1,
            command=self.copy_current_answer,
        )
        self.btn_copy_ans.pack(side="right")

        self.short_answer_label = tk.Label(
            self.answer_card,
            text="Waiting for first screen capture...",
            fg=p["fg_primary"],
            bg=p["bg_card"],
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=460,
        )
        self.short_answer_label.pack(fill="x", pady=(3, 0))

        # 3. Bottom Quick Switcher Bar & Primary Action Controls (packed bottom-up so explanation fills middle)
        quick_bar = tk.Frame(frame, bg=p["bg_card"], padx=8, pady=6)
        quick_bar.pack(fill="x", side="bottom", pady=(0, 2))

        # Provider Quick Selector
        tk.Label(quick_bar, text="AI:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8, "bold")).pack(
            side="left", padx=(0, 3)
        )
        self.quick_prov_var = tk.StringVar(value=PROVIDERS[self.config.provider]["short"])
        self.quick_prov_cb = ttk.Combobox(
            quick_bar,
            textvariable=self.quick_prov_var,
            values=self.provider_short_names,
            state="readonly",
            style="Dark.TCombobox",
            width=10,
        )
        self.quick_prov_cb.pack(side="left", padx=(0, 6))
        self.quick_prov_cb.bind("<<ComboboxSelected>>", self._on_quick_provider_change)

        # Model Quick Selector
        tk.Label(quick_bar, text="Model:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).pack(
            side="left", padx=(0, 3)
        )
        self.quick_model_var = tk.StringVar(value=self.config.model)
        self.quick_model_cb = ttk.Combobox(
            quick_bar,
            textvariable=self.quick_model_var,
            values=PROVIDERS[self.config.provider]["models"],
            style="Dark.TCombobox",
            width=19,
        )
        self.quick_model_cb.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.quick_model_cb.bind("<<ComboboxSelected>>", self._on_quick_model_change)
        self.quick_model_cb.bind("<Return>", self._on_quick_model_change)

        # Delay Quick Selector
        tk.Label(quick_bar, text="⏱", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).pack(
            side="left", padx=(0, 2)
        )
        self.quick_delay_var = tk.StringVar(value=f"{self.config.cooldown_delay}s")
        self.quick_delay_cb = ttk.Combobox(
            quick_bar,
            textvariable=self.quick_delay_var,
            values=["3s", "5s", "10s", "15s", "20s", "30s", "45s", "60s"],
            state="readonly",
            style="Dark.TCombobox",
            width=4,
        )
        self.quick_delay_cb.pack(side="left")
        self.quick_delay_cb.bind("<<ComboboxSelected>>", self._on_quick_delay_change)

        # Primary Action Buttons Row
        controls_row = tk.Frame(frame, bg=p["bg_panel"])
        controls_row.pack(fill="x", side="bottom", pady=(0, 8))

        self.btn_pause = HoverButton(
            controls_row,
            text="⏸ Pause",
            bg_normal=p["bg_input"],
            bg_hover=p["bg_hover"],
            fg_normal=p["fg_primary"],
            font=("Segoe UI", 9, "bold"),
            pady=6,
            command=self.toggle_pause,
        )
        self.btn_pause.pack(side="left", expand=True, fill="x", padx=(0, 4))
        Tooltip(self.btn_pause, "Pause or resume automatic screen capture loop (Alt+P)")

        self.btn_solve = HoverButton(
            controls_row,
            text="⚡ Solve Now (Alt+S)",
            bg_normal=p["accent"],
            bg_hover=p["accent_hover"],
            fg_normal=p["accent_fg"],
            font=("Segoe UI", 9, "bold"),
            pady=6,
            command=self.trigger_solve_now,
        )
        self.btn_solve.pack(side="left", expand=True, fill="x", padx=4)
        Tooltip(self.btn_solve, "Capture screen and solve immediately (Alt+S)")

        self.region_frame = tk.Frame(controls_row, bg=p["bg_panel"])
        self.region_frame.pack(side="right", padx=(4, 0))

        self.btn_region = HoverButton(
            self.region_frame,
            text="✂ Region",
            bg_normal=p["bg_input"],
            bg_hover=p["bg_hover"],
            fg_normal=p["fg_primary"],
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
            command=self.open_region_selector,
        )
        self.btn_region.pack(side="left")
        Tooltip(self.btn_region, "Select a specific screen area to capture (Alt+R)")

        self.btn_reset_region = HoverButton(
            self.region_frame,
            text="↺",
            bg_normal=p["bg_input"],
            bg_hover=p["danger"],
            fg_normal=p["warning"],
            fg_hover="#11111b",
            font=("Segoe UI", 9, "bold"),
            padx=6,
            pady=6,
            command=self.reset_capture_region,
        )
        Tooltip(self.btn_reset_region, "Reset to full monitor capture")

        # 4. Middle Explanation & Reasoning Area
        text_card = tk.Frame(
            frame,
            bg=p["bg_card"],
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        text_card.pack(fill="both", expand=True, side="top", pady=(0, 8))

        self.scrollbar = tk.Scrollbar(
            text_card,
            bg=p["bg_card"],
            troughcolor=p["bg_card"],
            bd=0,
            highlightthickness=0,
            width=10,
        )
        self.scrollbar.pack(side="right", fill="y")

        self.text_area = tk.Text(
            text_card,
            bg=p["bg_card"],
            fg=p["fg_primary"],
            insertbackground=p["fg_primary"],
            selectbackground=p["bg_hover"],
            selectforeground=p["fg_primary"],
            font=("Segoe UI", 10),
            wrap="word",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            spacing1=2,
            spacing3=4,
            yscrollcommand=self.scrollbar.set,
        )
        self.text_area.pack(fill="both", expand=True)
        self.scrollbar.config(command=self.text_area.yview)

        # Configure rich text tags
        self.text_area.tag_configure("heading", foreground=p["accent"], font=("Segoe UI", 10, "bold"))
        self.text_area.tag_configure("bold", foreground=p["fg_primary"], font=("Segoe UI", 10, "bold"))
        self.text_area.tag_configure("answer_hl", foreground=p["success"], font=("Segoe UI", 10, "bold"))
        self.text_area.tag_configure("muted", foreground=p["fg_secondary"], font=("Segoe UI", 9))
        self.text_area.tag_configure("error", foreground=p["danger"], font=("Segoe UI", 10, "bold"))

        self._render_formatted_text(
            "Welcome to OmniSolve AI!\n\n"
            "• Press ⚡ Solve Now (or Alt+S) to analyze the question on screen.\n"
            "• Use ✂ Region (or Alt+R) to snip only the question area for faster & cleaner results.\n"
            "• Switch between Google Gemini, OpenAI, Claude, OpenRouter, Groq, DeepSeek, or Local Ollama anytime."
        )

    # ========================================================================
    # TAB 2: History
    # ========================================================================
    def _build_history_tab(self) -> None:
        p = self.palette
        frame = tk.Frame(self.content_container, bg=p["bg_panel"])
        self.tab_frames["history"] = frame

        toolbar = tk.Frame(frame, bg=p["bg_panel"])
        toolbar.pack(fill="x", pady=(2, 6))

        self.history_count_lbl = tk.Label(
            toolbar,
            text="Solved Questions (0)",
            fg=p["fg_primary"],
            bg=p["bg_panel"],
            font=("Segoe UI", 9, "bold"),
        )
        self.history_count_lbl.pack(side="left")

        btn_clear = HoverButton(
            toolbar,
            text="🗑 Clear",
            bg_normal=p["bg_input"],
            bg_hover=p["danger"],
            fg_normal=p["fg_secondary"],
            fg_hover="#11111b",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
            command=self.clear_history,
        )
        btn_clear.pack(side="right", padx=(4, 0))

        btn_export = HoverButton(
            toolbar,
            text="💾 Export .md",
            bg_normal=p["bg_input"],
            bg_hover=p["accent"],
            fg_normal=p["fg_primary"],
            fg_hover=p["accent_fg"],
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
            command=self.export_history_markdown,
        )
        btn_export.pack(side="right", padx=4)

        # Listbox of history entries
        list_frame = tk.Frame(
            frame, bg=p["bg_card"], highlightbackground=p["border"], highlightthickness=1
        )
        list_frame.pack(fill="x", pady=(0, 8))

        self.history_listbox = tk.Listbox(
            list_frame,
            bg=p["bg_card"],
            fg=p["fg_primary"],
            selectbackground=p["accent"],
            selectforeground=p["accent_fg"],
            font=("Segoe UI", 9),
            height=7,
            bd=0,
            highlightthickness=0,
            activestyle="none",
        )
        self.history_listbox.pack(fill="x", padx=6, pady=6)
        self.history_listbox.bind("<<ListboxSelect>>", self._on_history_select)

        # History detail viewer
        detail_frame = tk.Frame(
            frame, bg=p["bg_card"], highlightbackground=p["border"], highlightthickness=1
        )
        detail_frame.pack(fill="both", expand=True, pady=(0, 4))

        self.history_detail_text = tk.Text(
            detail_frame,
            bg=p["bg_card"],
            fg=p["fg_primary"],
            font=("Segoe UI", 9),
            wrap="word",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            state="disabled",
        )
        self.history_detail_text.pack(fill="both", expand=True)

    # ========================================================================
    # TAB 3: Settings & Multi-Model Manager
    # ========================================================================
    def _build_settings_tab(self) -> None:
        p = self.palette
        frame = tk.Frame(self.content_container, bg=p["bg_panel"])
        self.tab_frames["settings"] = frame

        # Section 1: AI Provider & Model Card
        ai_card = tk.Frame(
            frame, bg=p["bg_card"], highlightbackground=p["border"], highlightthickness=1, padx=10, pady=8
        )
        ai_card.pack(fill="x", pady=(2, 7))

        tk.Label(
            ai_card,
            text="🤖 AI Provider & Language Model",
            fg=p["accent"],
            bg=p["bg_card"],
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        # Provider Row
        tk.Label(ai_card, text="Provider:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).grid(
            row=1, column=0, sticky="w", pady=3
        )
        self.set_prov_var = tk.StringVar(value=PROVIDERS[self.config.provider]["name"])
        self.set_prov_cb = ttk.Combobox(
            ai_card,
            textvariable=self.set_prov_var,
            values=self.provider_names,
            state="readonly",
            style="Dark.TCombobox",
            width=26,
        )
        self.set_prov_cb.grid(row=1, column=1, sticky="ew", padx=6, pady=3)
        self.set_prov_cb.bind("<<ComboboxSelected>>", self._on_settings_provider_change)

        self.btn_get_key = HoverButton(
            ai_card,
            text="🔗 Get Key",
            bg_normal=p["bg_input"],
            bg_hover=p["bg_hover"],
            fg_normal=p["cyan"],
            font=("Segoe UI", 8),
            padx=6,
            pady=2,
            command=self._open_provider_key_url,
        )
        self.btn_get_key.grid(row=1, column=2, sticky="ew", pady=3)

        # Model Row
        tk.Label(ai_card, text="Model ID:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).grid(
            row=2, column=0, sticky="w", pady=3
        )
        self.set_model_var = tk.StringVar(value=self.config.model)
        self.set_model_cb = ttk.Combobox(
            ai_card,
            textvariable=self.set_model_var,
            values=PROVIDERS[self.config.provider]["models"],
            style="Dark.TCombobox",
            width=26,
        )
        self.set_model_cb.grid(row=2, column=1, sticky="ew", padx=6, pady=3)

        self.btn_fetch_models = HoverButton(
            ai_card,
            text="🔄 Fetch",
            bg_normal=p["bg_input"],
            bg_hover=p["bg_hover"],
            fg_normal=p["fg_primary"],
            font=("Segoe UI", 8),
            padx=6,
            pady=2,
            command=self._fetch_models_async,
        )
        self.btn_fetch_models.grid(row=2, column=2, sticky="ew", pady=3)
        Tooltip(self.btn_fetch_models, "Fetch available models from API / Local Ollama")

        # API Key Row
        tk.Label(ai_card, text="API Key:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).grid(
            row=3, column=0, sticky="w", pady=3
        )
        self.set_key_var = tk.StringVar(value=self.config.get_api_key(self.config.provider))
        self.set_key_entry = tk.Entry(
            ai_card,
            textvariable=self.set_key_var,
            bg=p["bg_input"],
            fg=p["fg_primary"],
            insertbackground=p["fg_primary"],
            relief="flat",
            font=("Consolas", 9),
            show="•",
        )
        self.set_key_entry.grid(row=3, column=1, sticky="ew", padx=6, pady=3, ipady=3)

        self.key_visible = False
        self.btn_toggle_key = HoverButton(
            ai_card,
            text="👁 Show",
            bg_normal=p["bg_input"],
            bg_hover=p["bg_hover"],
            fg_normal=p["fg_secondary"],
            font=("Segoe UI", 8),
            padx=6,
            pady=2,
            command=self._toggle_api_key_visibility,
        )
        self.btn_toggle_key.grid(row=3, column=2, sticky="ew", pady=3)

        # Base URL Row
        tk.Label(ai_card, text="Base URL:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).grid(
            row=4, column=0, sticky="w", pady=3
        )
        self.set_url_var = tk.StringVar(value=self.config.get_base_url(self.config.provider))
        self.set_url_entry = tk.Entry(
            ai_card,
            textvariable=self.set_url_var,
            bg=p["bg_input"],
            fg=p["fg_secondary"],
            insertbackground=p["fg_primary"],
            relief="flat",
            font=("Consolas", 8),
        )
        self.set_url_entry.grid(row=4, column=1, sticky="ew", padx=6, pady=3, ipady=3)

        self.btn_test_api = HoverButton(
            ai_card,
            text="🔌 Test",
            bg_normal=p["bg_input"],
            bg_hover=p["accent"],
            fg_normal=p["success"],
            fg_hover=p["accent_fg"],
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            command=self._test_api_connection_async,
        )
        self.btn_test_api.grid(row=4, column=2, sticky="ew", pady=3)

        ai_card.columnconfigure(1, weight=1)

        # Section 2: Subject Profile & Language Card
        prompt_card = tk.Frame(
            frame, bg=p["bg_card"], highlightbackground=p["border"], highlightthickness=1, padx=10, pady=8
        )
        prompt_card.pack(fill="x", pady=(0, 7))

        tk.Label(
            prompt_card,
            text="🎓 Exam Profile & Explanation Language",
            fg=p["accent"],
            bg=p["bg_card"],
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        tk.Label(prompt_card, text="Profile:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.profile_keys = list(PROMPT_PROFILES.keys())
        self.profile_names = [PROMPT_PROFILES[k]["name"] for k in self.profile_keys]
        curr_prof_name = PROMPT_PROFILES.get(self.config.prompt_profile, PROMPT_PROFILES["english_exam"])["name"]
        self.set_profile_var = tk.StringVar(value=curr_prof_name)
        self.set_profile_cb = ttk.Combobox(
            prompt_card,
            textvariable=self.set_profile_var,
            values=self.profile_names,
            state="readonly",
            style="Dark.TCombobox",
        )
        self.set_profile_cb.grid(row=1, column=1, sticky="ew", padx=6, pady=2)

        tk.Label(prompt_card, text="Language:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).grid(
            row=2, column=0, sticky="w", pady=2
        )
        self.lang_keys = list(LANGUAGE_MODES.keys())
        self.lang_names = [LANGUAGE_MODES[k] for k in self.lang_keys]
        curr_lang_name = LANGUAGE_MODES.get(self.config.answer_language, LANGUAGE_MODES["en"])
        self.set_lang_var = tk.StringVar(value=curr_lang_name)
        self.set_lang_cb = ttk.Combobox(
            prompt_card,
            textvariable=self.set_lang_var,
            values=self.lang_names,
            state="readonly",
            style="Dark.TCombobox",
        )
        self.set_lang_cb.grid(row=2, column=1, sticky="ew", padx=6, pady=2)
        prompt_card.columnconfigure(1, weight=1)

        # Section 3: Capture & UX Options Card
        ux_card = tk.Frame(
            frame, bg=p["bg_card"], highlightbackground=p["border"], highlightthickness=1, padx=10, pady=8
        )
        ux_card.pack(fill="x", pady=(0, 7))

        row_top = tk.Frame(ux_card, bg=p["bg_card"])
        row_top.pack(fill="x", pady=(0, 4))

        # Monitor
        tk.Label(row_top, text="Monitor:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).pack(
            side="left"
        )
        monitors = self.capturer.list_monitors()
        mon_values = [str(i) for i in range(len(monitors))]
        self.set_mon_var = tk.StringVar(value=str(self.config.monitor_index))
        self.set_mon_cb = ttk.Combobox(
            row_top,
            textvariable=self.set_mon_var,
            values=mon_values,
            state="readonly",
            style="Dark.TCombobox",
            width=3,
        )
        self.set_mon_cb.pack(side="left", padx=(4, 12))

        # Mode
        tk.Label(row_top, text="Mode:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).pack(
            side="left"
        )
        self.set_mode_var = tk.StringVar(value=self.config.mode)
        self.set_mode_cb = ttk.Combobox(
            row_top,
            textvariable=self.set_mode_var,
            values=["vision", "ocr"],
            state="readonly",
            style="Dark.TCombobox",
            width=7,
        )
        self.set_mode_cb.pack(side="left", padx=(4, 12))

        # Opacity
        tk.Label(row_top, text="Opacity:", fg=p["fg_secondary"], bg=p["bg_card"], font=("Segoe UI", 8)).pack(
            side="left"
        )
        self.set_opacity_var = tk.DoubleVar(value=self.config.window_opacity * 100)
        opacity_scale = tk.Scale(
            row_top,
            from_=35,
            to=100,
            orient="horizontal",
            variable=self.set_opacity_var,
            bg=p["bg_card"],
            fg=p["fg_primary"],
            highlightthickness=0,
            troughcolor=p["bg_input"],
            activebackground=p["accent"],
            bd=0,
            showvalue=False,
            length=90,
            command=self._on_opacity_slider,
        )
        opacity_scale.pack(side="left", padx=6)

        # Checkboxes Grid
        chk_frame = tk.Frame(ux_card, bg=p["bg_card"])
        chk_frame.pack(fill="x")

        self.var_skip_unchanged = tk.BooleanVar(value=self.config.skip_unchanged)
        self.var_hide_hud = tk.BooleanVar(value=self.config.hide_hud_on_capture)
        self.var_notify = tk.BooleanVar(value=self.config.notify)
        self.var_autocopy = tk.BooleanVar(value=self.config.auto_copy_answer)

        chk_opts = {
            "bg": p["bg_card"],
            "fg": p["fg_primary"],
            "selectcolor": p["bg_input"],
            "activebackground": p["bg_card"],
            "activeforeground": p["fg_primary"],
            "font": ("Segoe UI", 8),
        }

        tk.Checkbutton(
            chk_frame, text="Skip unchanged screen", variable=self.var_skip_unchanged, **chk_opts
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Checkbutton(
            chk_frame, text="Hide HUD on screenshot", variable=self.var_hide_hud, **chk_opts
        ).grid(row=0, column=1, sticky="w")
        tk.Checkbutton(
            chk_frame, text="Toast notifications", variable=self.var_notify, **chk_opts
        ).grid(row=1, column=0, sticky="w", padx=(0, 12))
        tk.Checkbutton(
            chk_frame, text="Auto-copy answer", variable=self.var_autocopy, **chk_opts
        ).grid(row=1, column=1, sticky="w")

        # Bottom Save Row
        save_row = tk.Frame(frame, bg=p["bg_panel"])
        save_row.pack(fill="x", pady=(2, 0))

        self.settings_status_lbl = tk.Label(
            save_row,
            text="Settings are saved locally to config.json",
            fg=p["fg_muted"],
            bg=p["bg_panel"],
            font=("Segoe UI", 8),
        )
        self.settings_status_lbl.pack(side="left")

        self.btn_save_settings = HoverButton(
            save_row,
            text="💾 Save & Apply",
            bg_normal=p["success"],
            bg_hover=p["accent"],
            fg_normal="#11111b",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=4,
            command=self.save_settings_from_ui,
        )
        self.btn_save_settings.pack(side="right")

    # ========================================================================
    # Footer & Resize Grip
    # ========================================================================
    def _build_footer_bar(self) -> None:
        p = self.palette
        self.footer = tk.Frame(self.root, bg=p["bg_root"], height=22)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)

        hk_lbl = tk.Label(
            self.footer,
            text="Alt+S Solve  •  Alt+P Pause  •  Alt+R Region  •  Alt+H Boss Key",
            fg=p["fg_muted"],
            bg=p["bg_root"],
            font=("Segoe UI", 7),
        )
        hk_lbl.pack(side="left", padx=10)

        self.resize_grip = tk.Label(
            self.footer,
            text="◢",
            fg=p["fg_muted"],
            bg=p["bg_root"],
            font=("Segoe UI", 9),
            cursor="size_nw_se",
        )
        self.resize_grip.pack(side="right", padx=4)
        self.resize_grip.bind("<ButtonPress-1>", self._start_resize)
        self.resize_grip.bind("<B1-Motion>", self._on_resize)

    # ========================================================================
    # Window Drag, Resize, Collapse, Pin & Stealth Actions
    # ========================================================================
    def _start_drag(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event) -> None:
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def _start_resize(self, event) -> None:
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.root.winfo_width()
        self._resize_start_h = self.root.winfo_height()

    def _on_resize(self, event) -> None:
        if self.is_collapsed:
            return
        dw = event.x_root - self._resize_start_x
        dh = event.y_root - self._resize_start_y
        new_w = max(430, self._resize_start_w + dw)
        new_h = max(380, self._resize_start_h + dh)
        self.expanded_width = new_w
        self.expanded_height = new_h
        self.root.geometry(f"{new_w}x{new_h}")
        self.short_answer_label.configure(wraplength=new_w - 60)

    def toggle_collapse(self) -> None:
        curr_x = self.root.winfo_x()
        curr_y = self.root.winfo_y()
        if self.is_collapsed:
            self.mini_strip.pack_forget()
            self.tab_bar.pack(fill="x", side="top")
            self.content_container.pack(fill="both", expand=True, padx=10, pady=(4, 0))
            self.footer.pack(fill="x", side="bottom")
            self.root.geometry(f"{self.expanded_width}x{self.expanded_height}+{curr_x}+{curr_y}")
            self.btn_collapse.configure(text="➖")
            self.is_collapsed = False
        else:
            self.expanded_width = self.root.winfo_width()
            self.expanded_height = self.root.winfo_height()
            self.tab_bar.pack_forget()
            self.content_container.pack_forget()
            self.footer.pack_forget()
            self.mini_strip.pack(fill="x", side="top")
            self.root.geometry(f"{self.expanded_width}x76+{curr_x}+{curr_y}")
            self.btn_collapse.configure(text="➕")
            self.is_collapsed = True

    def toggle_pin(self) -> None:
        self.config.always_on_top = not self.config.always_on_top
        self.root.attributes("-topmost", self.config.always_on_top)
        pin_fg = self.palette["success"] if self.config.always_on_top else self.palette["fg_muted"]
        self.btn_pin.set_colors(self.palette["bg_title"], self.palette["bg_hover"], pin_fg)

    def toggle_stealth_opacity(self) -> None:
        self.is_stealth_opacity = not self.is_stealth_opacity
        target_alpha = 0.45 if self.is_stealth_opacity else self.config.window_opacity
        self.root.attributes("-alpha", target_alpha)
        fg = self.palette["cyan"] if self.is_stealth_opacity else self.palette["fg_secondary"]
        self.btn_stealth.set_colors(self.palette["bg_title"], self.palette["bg_hover"], fg)

    def toggle_boss_key(self) -> None:
        """Instantly hides or restores the HUD window when Alt+H is pressed."""
        if self.is_hidden_boss:
            self.root.deiconify()
            self.root.attributes("-topmost", self.config.always_on_top)
            self.is_hidden_boss = False
        else:
            self.root.withdraw()
            self.is_hidden_boss = True

    # ========================================================================
    # Solver Controls & Region Snipping
    # ========================================================================
    def toggle_pause(self) -> None:
        if self.pause_event.is_set():
            self.pause_event.clear()
        else:
            self.pause_event.set()
        self._sync_pause_button()

    def _sync_pause_button(self) -> None:
        p = self.palette
        if self.pause_event.is_set():
            self.btn_pause.configure(text="▶ Resume (Alt+P)")
            self.btn_pause.set_colors(p["success"], p["accent"], "#11111b")
        else:
            self.btn_pause.configure(text="⏸ Pause (Alt+P)")
            self.btn_pause.set_colors(p["bg_input"], p["bg_hover"], p["fg_primary"])

    def trigger_solve_now(self) -> None:
        self.capturer.reset_change_detector()
        self.trigger_event.set()

    def open_region_selector(self) -> None:
        # Temporarily hide main window while snipping
        was_visible = not self.is_hidden_boss
        if was_visible:
            self.root.withdraw()
            self.root.update_idletasks()
            time.sleep(0.08)

        def _on_done(region: Optional[List[int]]) -> None:
            if was_visible:
                self.root.deiconify()
                self.root.attributes("-topmost", self.config.always_on_top)
            if region:
                self.config.capture_region = region
                self.capturer.reset_change_detector()
                self._update_region_button_ui()
                self.config.save()
                # Trigger an immediate solve of the newly selected region
                self.trigger_event.set()

        RegionSelectorOverlay(self.root, _on_done, self.palette)

    def reset_capture_region(self) -> None:
        self.config.capture_region = None
        self.capturer.reset_change_detector()
        self._update_region_button_ui()
        self.config.save()

    def _update_region_button_ui(self) -> None:
        p = self.palette
        reg = self.config.capture_region
        if reg and len(reg) == 4:
            self.btn_region.configure(text=f"✂ {reg[2]}×{reg[3]}")
            self.btn_region.set_colors(p["success_bg"], p["bg_hover"], p["success"])
            self.btn_reset_region.pack(side="left", padx=(2, 0))
        else:
            self.btn_region.configure(text="✂ Region")
            self.btn_region.set_colors(p["bg_input"], p["bg_hover"], p["fg_primary"])
            self.btn_reset_region.pack_forget()

    def copy_current_answer(self) -> None:
        text_to_copy = self.current_short_answer or self.short_answer_label.cget("text")
        if copy_to_clipboard(text_to_copy, self.root):
            self.btn_copy_ans.configure(text="✓ Copied!")
            self.root.after(1400, lambda: self.btn_copy_ans.configure(text="📋 Copy"))

    # ========================================================================
    # Quick Bar & Settings Synchronization
    # ========================================================================
    def _format_badge_text(self) -> str:
        short_prov = PROVIDERS.get(self.config.provider, {}).get("short", self.config.provider)
        model_short = self.config.model.split("/")[-1][:22]
        return f"{short_prov} • {model_short}"

    def _on_quick_provider_change(self, _event=None) -> None:
        short_val = self.quick_prov_var.get()
        for pid, meta in PROVIDERS.items():
            if meta["short"] == short_val:
                self._apply_provider_selection(pid)
                break

    def _on_quick_model_change(self, _event=None) -> None:
        new_model = self.quick_model_var.get().strip()
        if new_model:
            self.config.model = new_model
            self.config.provider_models[self.config.provider] = new_model
            self.set_model_var.set(new_model)
            self.model_badge.configure(text=self._format_badge_text())
            self.config.save()

    def _on_quick_delay_change(self, _event=None) -> None:
        raw = self.quick_delay_var.get().rstrip("s")
        try:
            self.config.cooldown_delay = int(raw)
            self.config.save()
        except ValueError:
            pass

    def _on_settings_provider_change(self, _event=None) -> None:
        full_name = self.set_prov_var.get()
        for pid, meta in PROVIDERS.items():
            if meta["name"] == full_name:
                self._apply_provider_selection(pid)
                break

    def _apply_provider_selection(self, provider_id: str) -> None:
        # Save current key before switching
        self.config.provider = provider_id
        meta = PROVIDERS[provider_id]
        model = self.config.get_model_for_provider(provider_id)
        self.config.model = model

        # Sync Quick Bar
        self.quick_prov_var.set(meta["short"])
        self.quick_model_cb.configure(values=meta["models"])
        self.quick_model_var.set(model)

        # Sync Settings Tab
        self.set_prov_var.set(meta["name"])
        self.set_model_cb.configure(values=meta["models"])
        self.set_model_var.set(model)
        self.set_key_var.set(self.config.get_api_key(provider_id))
        self.set_url_var.set(self.config.get_base_url(provider_id))

        self.model_badge.configure(text=self._format_badge_text())
        self.config.save()

    def _toggle_api_key_visibility(self) -> None:
        self.key_visible = not self.key_visible
        if self.key_visible:
            self.set_key_entry.configure(show="")
            self.btn_toggle_key.configure(text="🙈 Hide")
        else:
            self.set_key_entry.configure(show="•")
            self.btn_toggle_key.configure(text="👁 Show")

    def _open_provider_key_url(self) -> None:
        url = PROVIDERS.get(self.config.provider, {}).get("key_url", "")
        if url:
            webbrowser.open(url)

    def _on_opacity_slider(self, val: str) -> None:
        try:
            alpha = max(0.35, min(1.0, float(val) / 100.0))
            self.config.window_opacity = alpha
            if not self.is_stealth_opacity:
                self.root.attributes("-alpha", alpha)
        except ValueError:
            pass

    def _Sync_settings_to_config(self) -> None:
        # Provider
        full_name = self.set_prov_var.get()
        for pid, meta in PROVIDERS.items():
            if meta["name"] == full_name:
                self.config.provider = pid
                break

        # Model, Key, Base URL
        prov = self.config.provider
        model_val = self.set_model_var.get().strip() or self.config.get_model_for_provider(prov)
        self.config.model = model_val
        self.config.provider_models[prov] = model_val
        self.config.set_api_key(prov, self.set_key_var.get())

        url_val = self.set_url_var.get().strip()
        default_url = PROVIDERS.get(prov, {}).get("base_url", "")
        if url_val and url_val != default_url:
            self.config.custom_base_urls[prov] = url_val

        # Profile & Language
        prof_name = self.set_profile_var.get()
        for pk, pmeta in PROMPT_PROFILES.items():
            if pmeta["name"] == prof_name:
                self.config.prompt_profile = pk
                break

        lang_name = self.set_lang_var.get()
        for lk, lval in LANGUAGE_MODES.items():
            if lval == lang_name:
                self.config.answer_language = lk
                break

        # Capture & UX
        try:
            self.config.monitor_index = int(self.set_mon_var.get())
        except ValueError:
            pass
        self.config.mode = self.set_mode_var.get()
        self.config.skip_unchanged = bool(self.var_skip_unchanged.get())
        self.config.hide_hud_on_capture = bool(self.var_hide_hud.get())
        self.config.notify = bool(self.var_notify.get())
        self.config.auto_copy_answer = bool(self.var_autocopy.get())

        # Update quick bar & badges
        self.quick_prov_var.set(PROVIDERS[prov]["short"])
        self.quick_model_var.set(self.config.model)
        self.model_badge.configure(text=self._format_badge_text())
        self.meta_label.configure(text=f"{self.config.mode.upper()} MODE")

    def save_settings_from_ui(self) -> None:
        self._Sync_settings_to_config()
        self.config.save()
        self.settings_status_lbl.configure(
            text="✓ Configuration saved & applied!", fg=self.palette["success"]
        )
        self.root.after(
            2500,
            lambda: self.settings_status_lbl.configure(
                text="Settings are saved locally to config.json", fg=self.palette["fg_muted"]
            ),
        )

    def _fetch_models_async(self) -> None:
        self._Sync_settings_to_config()
        prov = self.config.provider
        base_url = self.config.get_base_url(prov)
        api_key = self.config.get_api_key(prov)
        self.settings_status_lbl.configure(
            text=f"Fetching models from {PROVIDERS[prov]['short']}...", fg=self.palette["warning"]
        )

        def _worker():
            models = fetch_provider_models(prov, base_url, api_key)
            self.root.after(0, lambda: self._on_models_fetched(models))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_models_fetched(self, models: List[str]) -> None:
        if models:
            self.set_model_cb.configure(values=models)
            self.quick_model_cb.configure(values=models)
            if self.set_model_var.get() not in models:
                self.set_model_var.set(models[0])
            self.settings_status_lbl.configure(
                text=f"✓ Loaded {len(models)} models!", fg=self.palette["success"]
            )
        else:
            self.settings_status_lbl.configure(
                text="Could not fetch remote models; using presets.", fg=self.palette["danger"]
            )

    def _test_api_connection_async(self) -> None:
        self._Sync_settings_to_config()
        self.btn_test_api.configure(text="⏳...")
        self.settings_status_lbl.configure(
            text=f"Testing {PROVIDERS[self.config.provider]['short']} ({self.config.model})...",
            fg=self.palette["warning"],
        )

        def _worker():
            ok, msg, _ms = self.llm_client.test_connection()
            self.root.after(0, lambda: self._on_test_api_done(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_api_done(self, ok: bool, msg: str) -> None:
        self.btn_test_api.configure(text="🔌 Test")
        color = self.palette["success"] if ok else self.palette["danger"]
        prefix = "✓ " if ok else "✕ "
        self.settings_status_lbl.configure(text=f"{prefix}{msg[:68]}", fg=color)

    # ========================================================================
    # Rich Text Formatting & History Management
    # ========================================================================
    def _render_formatted_text(self, text: str, is_error: bool = False) -> None:
        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", tk.END)

        if is_error:
            self.text_area.insert(tk.END, "⚠️ Error Encountered\n\n", "error")
            self.text_area.insert(tk.END, text, "muted")
            self.text_area.configure(state="disabled")
            return

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                self.text_area.insert(tk.END, "\n")
                continue

            # Clean markdown headers or **Label:**
            if line.lower().startswith(("**correct answer", "correct answer:")):
                clean = re.sub(r"\*\*", "", line)
                self.text_area.insert(tk.END, f"{clean}\n", "answer_hl")
            elif line.lower().startswith(("**explanation", "explanation:", "**пояснення", "пояснення:")):
                clean = re.sub(r"\*\*", "", line)
                self.text_area.insert(tk.END, f"{clean}\n", "heading")
            else:
                # Parse inline **bold** segments
                parts = re.split(r"(\*\*.*?\*\*)", raw_line)
                for part in parts:
                    if part.startswith("**") and part.endswith("**") and len(part) > 4:
                        self.text_area.insert(tk.END, part[2:-2], "bold")
                    else:
                        self.text_area.insert(tk.END, part)
                self.text_area.insert(tk.END, "\n")

        self.text_area.configure(state="disabled")
        self.text_area.see("1.0")

    def _add_history_entry(self, result: SolveResult) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        prov_short = PROVIDERS.get(result.provider, {}).get("short", result.provider)
        entry = {
            "time": timestamp,
            "short_answer": result.short_answer,
            "explanation": result.explanation,
            "raw_text": result.raw_text,
            "provider": prov_short,
            "model": result.model,
            "latency_ms": result.latency_ms,
        }
        self.history_items.insert(0, entry)
        display_line = f"[{timestamp}] {result.short_answer[:42]}  ({prov_short} • {result.latency_ms/1000:.1f}s)"
        self.history_listbox.insert(0, display_line)

        count = len(self.history_items)
        self.tab_buttons["history"].configure(text=f"📜 History ({count})")
        self.history_count_lbl.configure(text=f"Solved Questions ({count})")

    def _on_history_select(self, _event=None) -> None:
        sel = self.history_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.history_items):
            item = self.history_items[idx]
            detail = (
                f"Time: {item['time']}  |  Model: {item['provider']} ({item['model']})  |  {item['latency_ms']} ms\n"
                f"{'─' * 56}\n"
                f"Correct Answer: {item['short_answer']}\n\n"
                f"Explanation:\n{item['explanation'] or item['raw_text']}"
            )
            self.history_detail_text.configure(state="normal")
            self.history_detail_text.delete("1.0", tk.END)
            self.history_detail_text.insert("1.0", detail)
            self.history_detail_text.configure(state="disabled")

    def clear_history(self) -> None:
        self.history_items.clear()
        self.history_listbox.delete(0, tk.END)
        self.history_detail_text.configure(state="normal")
        self.history_detail_text.delete("1.0", tk.END)
        self.history_detail_text.configure(state="disabled")
        self.tab_buttons["history"].configure(text="📜 History (0)")
        self.history_count_lbl.configure(text="Solved Questions (0)")

    def export_history_markdown(self) -> None:
        if not self.history_items:
            return
        filepath = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export Solved History to Markdown",
            defaultextension=".md",
            initialfile=f"exam_solutions_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            filetypes=[("Markdown Files", "*.md"), ("All Files", "*.*")],
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("# ✨ OmniSolve AI — Session Solutions\n\n")
                for i, item in enumerate(reversed(self.history_items), 1):
                    f.write(f"## #{i} [{item['time']}] — `{item['provider']} / {item['model']}`\n\n")
                    f.write(f"- **Correct Answer:** {item['short_answer']}\n")
                    if item["explanation"]:
                        f.write(f"- **Explanation:** {item['explanation']}\n\n")
                    else:
                        f.write(f"\n{item['raw_text']}\n\n")
                    f.write("---\n\n")
        except Exception as e:
            print(f"[!] Failed to export history: {e}")

    # ========================================================================
    # Queue Polling from Background Worker
    # ========================================================================
    def _set_progress(self, fraction: float, color: Optional[str] = None) -> None:
        w = max(10, self.progress_canvas.winfo_width())
        fill_w = int(w * max(0.0, min(1.0, fraction)))
        self.progress_canvas.coords(self.progress_rect, 0, 0, fill_w, 3)
        if color:
            self.progress_canvas.itemconfig(self.progress_rect, fill=color)

    def _poll_queue(self) -> None:
        p = self.palette
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                mtype = msg.get("type")

                if mtype == "status":
                    text = msg.get("text", "")
                    color = msg.get("color", p["accent"])
                    progress = msg.get("progress", None)
                    self.status_label.configure(text=text)
                    self.status_dot.configure(fg=color)
                    self.mini_status_dot.configure(fg=color)
                    if progress is not None:
                        self._set_progress(progress, color)
                    self._sync_pause_button()

                elif mtype == "result":
                    res: SolveResult = msg["result"]
                    prov_short = PROVIDERS.get(res.provider, {}).get("short", res.provider)
                    self.meta_label.configure(
                        text=f"{res.latency_ms / 1000:.2f}s • {prov_short}"
                    )
                    if res.success:
                        self.current_short_answer = res.short_answer
                        self.short_answer_label.configure(
                            text=res.short_answer, fg=p["success"]
                        )
                        self.answer_card.configure(highlightbackground=p["success"])
                        self.mini_answer_lbl.configure(
                            text=f"✅ {res.short_answer}", fg=p["success"]
                        )
                        body = res.explanation if res.explanation else res.raw_text
                        self._render_formatted_text(body, is_error=False)
                        self._add_history_entry(res)
                        self._set_progress(1.0, p["success"])

                        if self.config.auto_copy_answer:
                            copy_to_clipboard(res.short_answer, self.root)
                    else:
                        self.short_answer_label.configure(
                            text="⚠️ Could not solve — Check Settings / API Key",
                            fg=p["danger"],
                        )
                        self.answer_card.configure(highlightbackground=p["danger"])
                        self.mini_answer_lbl.configure(text="⚠️ API Error", fg=p["danger"])
                        self._render_formatted_text(res.error or "Unknown API error", is_error=True)
                        self._set_progress(1.0, p["danger"])

                self.ui_queue.task_done()
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def on_close(self) -> None:
        self.exit_event.set()
        self.hotkeys.stop()
        try:
            self.config.save()
        except Exception:
            pass
        self.root.destroy()
        os._exit(0)
