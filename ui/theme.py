import sys
from typing import Dict

THEMES: Dict[str, Dict[str, str]] = {
    "mocha": {
        "name": "Catppuccin Mocha",
        "bg_root": "#181825",
        "bg_title": "#11111b",
        "bg_panel": "#1e1e2e",
        "bg_card": "#262639",
        "bg_input": "#313244",
        "bg_hover": "#45475a",
        "border": "#313244",
        "border_focus": "#89b4fa",
        "fg_primary": "#cdd6f4",
        "fg_secondary": "#a6adc8",
        "fg_muted": "#6c7086",
        "accent": "#89b4fa",
        "accent_hover": "#b4befe",
        "accent_fg": "#11111b",
        "success": "#a6e3a1",
        "success_bg": "#1e3329",
        "warning": "#f9e2af",
        "danger": "#f38ba8",
        "cyan": "#94e2d5",
        "purple": "#cba6f7",
    },
    "cyber": {
        "name": "Midnight Cyber",
        "bg_root": "#0b0f19",
        "bg_title": "#060911",
        "bg_panel": "#111827",
        "bg_card": "#1e293b",
        "bg_input": "#1f2937",
        "bg_hover": "#334155",
        "border": "#1e293b",
        "border_focus": "#38bdf8",
        "fg_primary": "#f1f5f9",
        "fg_secondary": "#94a3b8",
        "fg_muted": "#64748b",
        "accent": "#38bdf8",
        "accent_hover": "#7dd3fc",
        "accent_fg": "#060911",
        "success": "#34d399",
        "success_bg": "#06362d",
        "warning": "#fbbf24",
        "danger": "#fb7185",
        "cyan": "#22d3ee",
        "purple": "#a78bfa",
    },
    "nord": {
        "name": "Nordic Slate",
        "bg_root": "#242933",
        "bg_title": "#1e222a",
        "bg_panel": "#2e3440",
        "bg_card": "#3b4252",
        "bg_input": "#434c5e",
        "bg_hover": "#4c566a",
        "border": "#434c5e",
        "border_focus": "#88c0d0",
        "fg_primary": "#eceff4",
        "fg_secondary": "#d8dee9",
        "fg_muted": "#9099ab",
        "accent": "#88c0d0",
        "accent_hover": "#8fbcbb",
        "accent_fg": "#1e222a",
        "success": "#a3be8c",
        "success_bg": "#2b382c",
        "warning": "#ebcb8b",
        "danger": "#bf616a",
        "cyan": "#8fbcbb",
        "purple": "#b48ead",
    },
}


def enable_high_dpi() -> None:
    """Enables crisp High-DPI font & window rendering on Windows."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
