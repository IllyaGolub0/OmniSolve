import sys
import threading
from typing import Callable, Dict

if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes


class GlobalHotkeyManager:
    """
    Lightweight native Windows Global Hotkey listener using Win32 RegisterHotKey.
    Requires zero third-party packages and runs without administrator privileges.
    """

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    # Virtual-Key Codes
    VK_S = 0x53  # Alt+S -> Solve Now
    VK_P = 0x50  # Alt+P -> Pause / Resume
    VK_R = 0x52  # Alt+R -> Select Region
    VK_H = 0x48  # Alt+H -> Hide / Show HUD (Boss Key)

    def __init__(self, callbacks: Dict[str, Callable[[], None]]):
        self.callbacks = callbacks
        self._thread = None
        self._thread_id = None
        self._running = False

    def start(self) -> None:
        if not sys.platform.startswith("win") or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if sys.platform.startswith("win") and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
            except Exception:
                pass

    def _loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        bindings = {
            1: (self.MOD_ALT | self.MOD_NOREPEAT, self.VK_S, "solve"),
            2: (self.MOD_ALT | self.MOD_NOREPEAT, self.VK_P, "pause"),
            3: (self.MOD_ALT | self.MOD_NOREPEAT, self.VK_R, "region"),
            4: (self.MOD_ALT | self.MOD_NOREPEAT, self.VK_H, "boss_key"),
        }

        registered_ids = []
        for hk_id, (mods, vk, _) in bindings.items():
            if user32.RegisterHotKey(None, hk_id, mods, vk):
                registered_ids.append(hk_id)

        msg = wintypes.MSG()
        try:
            while self._running:
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res <= 0:
                    break
                if msg.message == self.WM_HOTKEY:
                    hk_id = msg.wParam
                    if hk_id in bindings:
                        action_name = bindings[hk_id][2]
                        cb = self.callbacks.get(action_name)
                        if cb:
                            try:
                                cb()
                            except Exception:
                                pass
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hk_id in registered_ids:
                try:
                    user32.UnregisterHotKey(None, hk_id)
                except Exception:
                    pass
