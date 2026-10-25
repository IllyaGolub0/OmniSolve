from typing import Dict, List, Optional, Tuple
import mss
import numpy as np
from PIL import Image, ImageGrab

# Optional EasyOCR
easyocr_available = False
try:
    import easyocr
    easyocr_available = True
except ImportError:
    pass

# Optional Windows Toast Notification
notify_available = False
try:
    from winotify import Notification
    notify_available = True
except ImportError:
    pass

# Optional pyperclip
pyperclip_available = False
try:
    import pyperclip
    pyperclip_available = True
except ImportError:
    pass


class ScreenCapturer:
    """Handles full-monitor and custom-region screen captures, change detection, and local OCR."""

    def __init__(self):
        self._last_thumb: Optional[np.ndarray] = None
        self._ocr_reader = None

    @staticmethod
    def list_monitors() -> List[Dict]:
        """Returns list of monitor dicts from mss (index 0 = all combined, 1 = primary, etc.)."""
        try:
            with mss.mss() as sct:
                return list(sct.monitors)
        except Exception:
            return [{"left": 0, "top": 0, "width": 1920, "height": 1080}]

    def capture_pil(
        self,
        monitor_index: int = 1,
        region: Optional[List[int]] = None,
    ) -> Image.Image:
        """
        Captures either a custom region [left, top, width, height] or the specified monitor index.
        Returns a PIL RGB Image.
        """
        with mss.mss() as sct:
            if region and len(region) == 4 and region[2] > 10 and region[3] > 10:
                bbox = {
                    "left": int(region[0]),
                    "top": int(region[1]),
                    "width": int(region[2]),
                    "height": int(region[3]),
                }
            else:
                idx = monitor_index if 0 <= monitor_index < len(sct.monitors) else 1
                bbox = sct.monitors[idx]

            try:
                shot = sct.grab(bbox)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                return img
            except Exception:
                # Fallback to PIL ImageGrab if GDI BitBlt fails temporarily
                pil_bbox = (
                    bbox["left"],
                    bbox["top"],
                    bbox["left"] + bbox["width"],
                    bbox["top"] + bbox["height"],
                )
                return ImageGrab.grab(bbox=pil_bbox, all_screens=True).convert("RGB")

    def has_screen_changed(self, pil_img: Image.Image, threshold: float = 1.6) -> bool:
        """
        Computes mean absolute pixel difference on a downsampled 64x64 grayscale thumbnail
        to detect if the screen content has meaningfully changed since the last capture.
        """
        small = pil_img.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
        arr = np.asarray(small, dtype=np.float32)
        if self._last_thumb is None or self._last_thumb.shape != arr.shape:
            self._last_thumb = arr
            return True
        diff = float(np.mean(np.abs(arr - self._last_thumb)))
        if diff >= threshold:
            self._last_thumb = arr
            return True
        return False

    def reset_change_detector(self) -> None:
        self._last_thumb = None

    def extract_text_ocr(self, pil_img: Image.Image) -> Tuple[bool, str]:
        """Runs local EasyOCR on a PIL image if available."""
        if not easyocr_available:
            return (
                False,
                "EasyOCR is not installed. Run `pip install easyocr` or switch Mode to 'Vision'.",
            )
        try:
            if self._ocr_reader is None:
                self._ocr_reader = easyocr.Reader(["en"])
            np_img = np.array(pil_img)
            results = self._ocr_reader.readtext(np_img)
            text = "\n".join([r[1] for r in results if len(r) > 1])
            return True, text.strip()
        except Exception as e:
            return False, f"OCR Error: {e}"


def send_toast_notification(title: str, message: str, enabled: bool = True) -> None:
    """Sends a non-intrusive Windows Toast notification."""
    if not enabled or not notify_available:
        return
    try:
        toast = Notification(
            app_id="OmniSolve AI Assistant",
            title=title,
            msg=message[:240],
            duration="short",
        )
        toast.show()
    except Exception:
        pass


def copy_to_clipboard(text: str, root_tk=None) -> bool:
    """Copies text to clipboard using pyperclip or tkinter fallback."""
    if not text:
        return False
    if pyperclip_available:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            pass
    if root_tk is not None:
        try:
            root_tk.clipboard_clear()
            root_tk.clipboard_append(text)
            root_tk.update_idletasks()
            return True
        except Exception:
            pass
    return False
