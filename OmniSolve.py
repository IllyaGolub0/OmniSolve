import argparse
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

# If launched from an empty venv or MSYS2 python without 'mss', auto-relaunch with the Python installation that has dependencies
try:
    import mss  # noqa: F401
except ModuleNotFoundError:
    if sys.platform.startswith("win") and not os.environ.get("_OMNISOLVE_RELAUNCHED"):
        candidate_pythons = [
            os.path.expandvars(r"%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
        ]
        for py_exe in candidate_pythons:
            if os.path.exists(py_exe) and os.path.abspath(py_exe).lower() != os.path.abspath(sys.executable).lower():
                env = os.environ.copy()
                env["_OMNISOLVE_RELAUNCHED"] = "1"
                env.pop("VIRTUAL_ENV", None)
                env.pop("PYTHONHOME", None)
                sys.exit(subprocess.call([py_exe, *sys.argv], env=env))
    raise

# Ensure UTF-8 console output on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.config import AppConfig, PROVIDERS
from core.providers import MultiLLMClient
from core.capture import ScreenCapturer, send_toast_notification
from ui.theme import enable_high_dpi
from ui.app import OmniSolveApp


class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GRAY = "\033[90m"


def print_banner(config: AppConfig, gui_enabled: bool) -> None:
    os.system("cls" if os.name == "nt" else "clear")
    prov_name = PROVIDERS.get(config.provider, {}).get("name", config.provider)
    region_str = (
        f"Custom Region ({config.capture_region[2]}x{config.capture_region[3]})"
        if config.capture_region
        else f"Monitor {config.monitor_index} (Full)"
    )
    print(f"{Colors.CYAN}╔════════════════════════════════════════════════════════════════════╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}{Colors.BOLD}{Colors.MAGENTA}             ✨ OMNISOLVE AI — EXAM & SCREEN ASSISTANT              {Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠════════════════════════════════════════════════════════════════════╣{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}  • {Colors.BOLD}AI Provider:{Colors.RESET}  {Colors.GREEN}{prov_name:<50}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}  • {Colors.BOLD}Model:{Colors.RESET}        {Colors.BLUE}{config.model:<50}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}  • {Colors.BOLD}Solver Mode:{Colors.RESET}  {Colors.BLUE}{config.mode.upper():<50}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}  • {Colors.BOLD}Capture Area:{Colors.RESET} {Colors.BLUE}{region_str:<50}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}  • {Colors.BOLD}Cooldown:{Colors.RESET}     {Colors.YELLOW}{f'{config.cooldown_delay}s':<50}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}  • {Colors.BOLD}Hotkeys:{Colors.RESET}      {Colors.GRAY}{'Alt+S Solve | Alt+P Pause | Alt+R Region | Alt+H Hide':<50}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╚════════════════════════════════════════════════════════════════════╝{Colors.RESET}\n")


def solver_worker(
    config: AppConfig,
    llm_client: MultiLLMClient,
    capturer: ScreenCapturer,
    ui_queue: queue.Queue,
    trigger_event: threading.Event,
    pause_event: threading.Event,
    exit_event: threading.Event,
    root_ref: list,
) -> None:
    """Background worker thread handling periodic or manual screen capture and multi-LLM solving."""
    while not exit_event.is_set():
        forced_manual = False
        if trigger_event.is_set():
            trigger_event.clear()
            forced_manual = True
        elif pause_event.is_set():
            ui_queue.put({"type": "status", "text": "Paused (Press Alt+S to solve once)", "color": "#f9e2af", "progress": 0.0})
            time.sleep(0.15)
            continue

        prov_short = PROVIDERS.get(config.provider, {}).get("short", config.provider)
        ui_queue.put({"type": "status", "text": "Capturing screen...", "color": "#89b4fa", "progress": 0.25})

        try:
            # Optional stealth hide HUD during capture so it never captures itself
            tk_root = root_ref[0] if root_ref else None
            restored_alpha = config.window_opacity
            if config.hide_hud_on_capture and tk_root is not None:
                try:
                    tk_root.attributes("-alpha", 0.0)
                    tk_root.update_idletasks()
                    time.sleep(0.04)
                except Exception:
                    pass

            pil_img = capturer.capture_pil(
                monitor_index=config.monitor_index,
                region=config.capture_region,
            )

            if config.hide_hud_on_capture and tk_root is not None:
                try:
                    tk_root.attributes("-alpha", restored_alpha)
                except Exception:
                    pass

            # Check if screen changed (skip duplicate queries during automatic loop)
            if not forced_manual and config.skip_unchanged:
                if not capturer.has_screen_changed(pil_img):
                    ui_queue.put(
                        {
                            "type": "status",
                            "text": "Screen unchanged — waiting for new question...",
                            "color": "#94e2d5",
                            "progress": 1.0,
                        }
                    )
                    # Wait briefly or until triggered
                    for _ in range(15):
                        if exit_event.is_set() or trigger_event.is_set():
                            break
                        time.sleep(0.2)
                    continue
            else:
                # Update baseline thumbnail even when forced
                capturer.has_screen_changed(pil_img)

            # Query LLM in Vision or OCR mode
            if config.mode == "ocr":
                ui_queue.put({"type": "status", "text": "Running local OCR...", "color": "#f9e2af", "progress": 0.45})
                ok_ocr, text_or_err = capturer.extract_text_ocr(pil_img)
                if not ok_ocr:
                    from core.providers import SolveResult
                    res = SolveResult(
                        success=False,
                        raw_text="",
                        short_answer="OCR Error",
                        explanation=text_or_err,
                        provider=config.provider,
                        model=config.model,
                        latency_ms=0,
                        error=text_or_err,
                    )
                elif len(text_or_err) < 12:
                    ui_queue.put({"type": "status", "text": "No question text detected via OCR", "color": "#f9e2af", "progress": 0.0})
                    time.sleep(2.0)
                    continue
                else:
                    ui_queue.put(
                        {
                            "type": "status",
                            "text": f"Querying {prov_short} ({config.model})...",
                            "color": "#cba6f7",
                            "progress": 0.7,
                        }
                    )
                    res = llm_client.solve_text(text_or_err)
            else:
                ui_queue.put(
                    {
                        "type": "status",
                        "text": f"Solving with {prov_short} ({config.model})...",
                        "color": "#cba6f7",
                        "progress": 0.65,
                    }
                )
                print(f"{Colors.YELLOW}[*] Solving screen with {prov_short} ({config.model})...{Colors.RESET}")
                res = llm_client.solve_vision(pil_img)

            # Publish result to terminal & GUI
            ui_queue.put({"type": "result", "result": res})
            if res.success:
                print(f"\n{Colors.CYAN}══════════════════ {prov_short.upper()} ({res.model}) [{res.latency_ms}ms] ══════════════════{Colors.RESET}")
                print(f"{Colors.GREEN}✔ Answer: {res.short_answer}{Colors.RESET}")
                if res.explanation:
                    print(f"{Colors.RESET}{res.explanation}")
                print(f"{Colors.CYAN}════════════════════════════════════════════════════════════════════{Colors.RESET}\n")

                ui_queue.put({"type": "status", "text": "Solved!", "color": "#a6e3a1", "progress": 1.0})
                send_toast_notification("✅ Correct Answer", res.short_answer, enabled=config.notify)
            else:
                print(f"{Colors.RED}[!] {res.error}{Colors.RESET}\n")
                ui_queue.put({"type": "status", "text": "API Error — check Settings", "color": "#f38ba8", "progress": 1.0})

        except Exception as e:
            err_msg = f"Unexpected worker error: {e}"
            print(f"{Colors.RED}[!] {err_msg}{Colors.RESET}")
            ui_queue.put({"type": "status", "text": "Error encountered", "color": "#f38ba8", "progress": 1.0})

        # Cooldown loop with live progress bar countdown
        elapsed = 0.0
        while not exit_event.is_set():
            total_delay = max(1, float(config.cooldown_delay))
            if elapsed >= total_delay:
                break
            if trigger_event.is_set() or pause_event.is_set():
                break
            remaining = max(0.0, total_delay - elapsed)
            fraction = max(0.0, min(1.0, remaining / total_delay))
            ui_queue.put(
                {
                    "type": "status",
                    "text": f"Next scan in {remaining:.1f}s...",
                    "color": "#94e2d5",
                    "progress": fraction,
                }
            )
            time.sleep(0.15)
            elapsed += 0.15


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OmniSolve AI — Multi-Model Screen & Exam Assistant (Gemini, OpenAI, Claude, Groq, OpenRouter, DeepSeek, Ollama)"
    )
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), help="AI provider ID (e.g. gemini, openai, anthropic, groq, openrouter, ollama)")
    parser.add_argument("--model", type=str, help="Override model ID (e.g. gpt-4o, gemini-2.5-flash, llama3.2-vision)")
    parser.add_argument("--mode", choices=["vision", "ocr"], help="Capture mode: vision (multimodal) or ocr (local EasyOCR)")
    parser.add_argument("--delay", type=int, help="Cooldown delay in seconds between scans")
    parser.add_argument("--paused", action="store_true", help="Start with automatic scanning loop paused (manual trigger only)")
    parser.add_argument("--no-gui", action="store_true", help="Run in headless CLI-only mode without floating HUD")
    return parser.parse_args()


def main() -> None:
    args = parse_cli_args()
    config = AppConfig.load()

    # Apply optional CLI overrides
    if args.provider:
        config.provider = args.provider
        if not args.model:
            config.model = config.get_model_for_provider(args.provider)
    if args.model:
        config.model = args.model
    if args.mode:
        config.mode = args.mode
    if args.delay:
        config.cooldown_delay = max(1, args.delay)

    gui_enabled = not args.no_gui
    print_banner(config, gui_enabled)

    ui_queue: queue.Queue = queue.Queue()
    trigger_event = threading.Event()
    pause_event = threading.Event()
    exit_event = threading.Event()

    if args.paused or config.start_paused:
        pause_event.set()

    llm_client = MultiLLMClient(config)
    capturer = ScreenCapturer()
    root_ref = [None]

    worker = threading.Thread(
        target=solver_worker,
        args=(config, llm_client, capturer, ui_queue, trigger_event, pause_event, exit_event, root_ref),
        daemon=True,
    )
    worker.start()

    if gui_enabled:
        enable_high_dpi()
        try:
            root = tk.Tk()
            root_ref[0] = root
            _app = OmniSolveApp(
                root=root,
                config=config,
                llm_client=llm_client,
                capturer=capturer,
                ui_queue=ui_queue,
                trigger_event=trigger_event,
                pause_event=pause_event,
                exit_event=exit_event,
            )
            root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            exit_event.set()
    else:
        try:
            while not exit_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print(f"\n{Colors.MAGENTA}[*] Solver stopped by user. Goodbye!{Colors.RESET}")
        finally:
            exit_event.set()


if __name__ == "__main__":
    main()
