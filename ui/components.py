import tkinter as tk
from typing import Callable, Dict, List, Optional


class HoverButton(tk.Button):
    """Flat modern button with smooth hover color feedback."""

    def __init__(self, master, bg_normal: str, bg_hover: str, fg_normal: str, fg_hover: Optional[str] = None, **kwargs):
        self.bg_normal = bg_normal
        self.bg_hover = bg_hover
        self.fg_normal = fg_normal
        self.fg_hover = fg_hover or fg_normal
        super().__init__(
            master,
            bg=bg_normal,
            fg=fg_normal,
            activebackground=bg_hover,
            activeforeground=self.fg_hover,
            bd=0,
            relief="flat",
            highlightthickness=0,
            cursor="hand2",
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def set_colors(self, bg_normal: str, bg_hover: str, fg_normal: str, fg_hover: Optional[str] = None) -> None:
        self.bg_normal = bg_normal
        self.bg_hover = bg_hover
        self.fg_normal = fg_normal
        self.fg_hover = fg_hover or fg_normal
        self.configure(
            bg=bg_normal,
            fg=fg_normal,
            activebackground=bg_hover,
            activeforeground=self.fg_hover,
        )

    def _on_enter(self, _event) -> None:
        if str(self["state"]) != "disabled":
            self.configure(bg=self.bg_hover, fg=self.fg_hover)

    def _on_leave(self, _event) -> None:
        if str(self["state"]) != "disabled":
            self.configure(bg=self.bg_normal, fg=self.fg_normal)


class Tooltip:
    """Clean floating tooltip for buttons and badges."""

    def __init__(self, widget: tk.Widget, text: str, bg: str = "#11111b", fg: str = "#cdd6f4"):
        self.widget = widget
        self.text = text
        self.bg = bg
        self.fg = fg
        self.tip_win: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self.tip_win or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip_win = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.wm_geometry(f"+{x}+{y}")
        frame = tk.Frame(tw, bg=self.bg, highlightbackground="#45475a", highlightthickness=1)
        frame.pack()
        lbl = tk.Label(
            frame,
            text=self.text,
            justify="left",
            bg=self.bg,
            fg=self.fg,
            font=("Segoe UI", 8),
            padx=7,
            pady=3,
        )
        lbl.pack()

    def _hide(self, _event=None) -> None:
        if self.tip_win:
            try:
                self.tip_win.destroy()
            except Exception:
                pass
            self.tip_win = None


class RegionSelectorOverlay:
    """
    Fullscreen interactive screen-snipping overlay.
    Allows dragging a rectangle over the exam question area and returns [left, top, width, height].
    """

    def __init__(self, parent_root: tk.Tk, on_selected: Callable[[Optional[List[int]]], None], palette: Dict[str, str]):
        self.parent = parent_root
        self.on_selected = on_selected
        self.palette = palette

        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.dim_label_id = None

        self.overlay = tk.Toplevel(self.parent)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-alpha", 0.32)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="#09090f", cursor="crosshair")

        self.canvas = tk.Canvas(self.overlay, bg="#09090f", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        # Instruction banner at top center
        sw = self.overlay.winfo_screenwidth()
        self.canvas.create_rectangle(
            sw // 2 - 240,
            24,
            sw // 2 + 240,
            66,
            fill="#11111b",
            outline=palette["accent"],
            width=2,
        )
        self.canvas.create_text(
            sw // 2,
            45,
            text="✂ Drag to select capture area  •  Right-Click or ESC to cancel",
            fill="#cdd6f4",
            font=("Segoe UI", 10, "bold"),
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", self._cancel)
        self.overlay.bind("<Escape>", self._cancel)
        self.overlay.focus_force()

    def _on_press(self, event) -> None:
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.dim_label_id:
            self.canvas.delete(self.dim_label_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline=self.palette["accent"],
            width=3,
            fill="#1e1e2e",
            stipple="gray25",
        )
        self.dim_label_id = self.canvas.create_text(
            self.start_x + 6,
            self.start_y - 12,
            text="0 × 0 px",
            anchor="sw",
            fill=self.palette["success"],
            font=("Segoe UI", 9, "bold"),
        )

    def _on_drag(self, event) -> None:
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)
        w = int(abs(cur_x - self.start_x))
        h = int(abs(cur_y - self.start_y))
        if self.dim_label_id:
            lx = min(self.start_x, cur_x)
            ly = max(18, min(self.start_y, cur_y) - 6)
            self.canvas.coords(self.dim_label_id, lx, ly)
            self.canvas.itemconfig(self.dim_label_id, text=f"{w} × {h} px")

    def _on_release(self, event) -> None:
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)
        left = int(min(self.start_x, end_x))
        top = int(min(self.start_y, end_y))
        width = int(abs(end_x - self.start_x))
        height = int(abs(end_y - self.start_y))

        self.overlay.destroy()
        if width >= 25 and height >= 25:
            self.on_selected([left, top, width, height])
        else:
            self.on_selected(None)

    def _cancel(self, _event=None) -> None:
        try:
            self.overlay.destroy()
        except Exception:
            pass
        self.on_selected(None)
