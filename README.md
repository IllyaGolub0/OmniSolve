<div align="center">

#  OmniSolve AI — Multi-Model Exam & Screen Assistant

**An intelligent, non-intrusive floating HUD that captures screen questions and solves them in real time using any Vision or Text LLM.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-a6e3a1?style=for-the-badge)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](#)
[![Multi-LLM](https://img.shields.io/badge/Models-Gemini%20%7C%20OpenAI%20%7C%20Claude%20%7C%20Groq%20%7C%20Ollama-89b4fa?style=for-the-badge)](#-supported-ai-providers)

</div>

---

##  Overview

**OmniSolve AI** is a modern desktop assistant designed for analyzing online quizzes, English certification tests, programming assessments, and STEM problems directly from your screen.

Unlike basic single-model scripts, **OmniSolve AI** features a **multi-provider AI engine**, an **interactive screen-region snipping tool**, **smart screen-change detection** (to save API tokens), **global hotkeys**, and a **customizable Catppuccin Mocha floating HUD**.

---

##  Key Features

-  **Multi-Provider AI Engine** — Switch seamlessly between **Google Gemini**, **OpenAI (GPT-4o / GPT-4.1)**, **Anthropic Claude**, **OpenRouter (200+ models)**, **Groq Cloud (Llama 4 Vision)**, **DeepSeek**, **Local Ollama** (100% free & offline), or any **Custom OpenAI-Compatible API**.
-  **Interactive Screen Region Snipping (`Alt+R`)** — Drag a crosshair rectangle over the exact question area instead of capturing your entire monitor. Faster uploads, lower token usage, and cleaner accuracy.
-  **Smart Duplicate Detection** — Automatically detects whether the screen has changed since the last scan so you never waste API calls while reading the same question.
-  **Modern High-DPI Floating HUD** —
  - Highlighted **Correct Answer** card with one-click **` Copy`** button.
  - Rich formatted explanation viewer.
  - **Mini-HUD Mode** — Collapses into a tiny 76px status strip that still displays live answers.
  - **Ghost Opacity  & Boss Key (`Alt+H`)** — Adjustable window transparency (35%–100%) and instant hide/restore shortcut.
-  **Session History & Markdown Export** — Review all solved questions from your session with latency stats and export them to a clean `.md` study guide.
-  **Multi-Subject Profiles & Bilingual Explanations** — Built-in profiles for *English Grammar & Reading*, *General Quizzes*, *Programming & CS*, *Math & Science*, and *EN → UA Translation*, with explanations in **English**, **Ukrainian**, or **Bilingual**.

---

## Supported AI Providers

| Provider | Vision Mode | OCR / Text Mode | Default Model | Highlights |
| :--- | :---: | :---: | :--- | :--- |
| **Google Gemini** | ✅ | ✅ | `gemini-3.1-flash-lite` | Fast multimodal vision & generous free tier |
| **OpenAI** | ✅ | ✅ | `gpt-4o-mini` | Supports `gpt-4o`, `gpt-4.1`, `o3-mini` |
| **Anthropic Claude** | ✅ | ✅ | `claude-3-7-sonnet-latest` | Top-tier reasoning & reading comprehension |
| **OpenRouter** | ✅ | ✅ | `google/gemini-2.5-flash` | Single key for 200+ models (including `:free` models) |
| **Groq Cloud** | ✅ | ✅ | `meta-llama/llama-4-scout-17b-16e-instruct` | Sub-second ultra-fast inference |
| **DeepSeek** | — | ✅ | `deepseek-chat` | Low-cost reasoning (`deepseek-chat`, `deepseek-reasoner`) |
| **Ollama (Local)** | ✅ | ✅ | `llama3.2-vision` | 100% offline & free (`qwen2.5vl`, `gemma3`, `llava`) |
| **Custom API** | ✅ | ✅ | Custom | Works with LM Studio, vLLM, LocalAI, Together AI |

---

## Global Hotkeys

Works anywhere on Windows without requiring administrator privileges:

| Shortcut | Action | Description |
| :--- | :--- | :--- |
| **`Alt + S`** |  **Solve Now** | Immediately captures the screen/region and queries the active AI model |
| **`Alt + P`** |  **Pause / Resume** | Pauses or resumes the automatic periodic scanning loop |
| **`Alt + R`** |  **Select Region** | Opens the fullscreen crosshair snipping tool to select a capture area |
| **`Alt + H`** |  **Boss Key (Hide/Show)** | Instantly hides or restores the floating HUD window |

---

## Installation & Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/your-username/omnisolve-ai.git
cd omnisolve-ai
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure API Keys (Optional — can also be done in GUI!)
Copy `.env.example` to `.env` and add the API key for your preferred provider, **or** simply launch the app and enter your key in the **⚙ Settings** tab:
```bash
copy .env.example .env
```

### 4. Run the application
```bash
python English.py
```

#### Optional CLI Arguments
```bash
# Launch directly with OpenAI GPT-4o and a 15-second cooldown
python English.py --provider openai --model gpt-4o --delay 15

# Launch with local Ollama vision model, starting paused (manual trigger via Alt+S)
python English.py --provider ollama --model llama3.2-vision --paused

# Run in headless terminal-only mode (Toast notifications + console output)
python English.py --no-gui
```

---

## Project Structure

```text
├── English.py             # Main application entry point & worker orchestrator
├── core/
│   ├── config.py          # Persistent configuration (config.json & .env loader)
│   ├── providers.py       # Unified Multi-LLM client (Gemini, OpenAI, Claude, Groq, OpenRouter, Ollama)
│   ├── capture.py         # Screen/region capture, perceptual diff detector, OCR & Toast helpers
│   └── hotkeys.py         # Native Win32 global hotkey listener (zero external dependencies)
├── ui/
│   ├── theme.py           # High-DPI scaling & color palettes (Mocha, Midnight Cyber, Nord)
│   ├── components.py      # Custom widgets, tooltips & interactive RegionSelectorOverlay
│   └── app.py             # Main floating HUD interface (Solver, History & Settings tabs)
├── .env.example           # Environment variables template
├── requirements.txt       # Python dependencies
└── LICENSE                # MIT License
```

---

##  License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.
