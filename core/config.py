import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


# ============================================================================
# AI Provider Definitions & Model Presets
# ============================================================================
PROVIDERS: Dict[str, Dict] = {
    "gemini": {
        "name": "Google Gemini",
        "short": "Gemini",
        "env_key": "GEMINI_API_KEY",
        "requires_key": True,
        "supports_vision": True,
        "default_model": "gemini-3.1-flash-lite",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
        ],
        "key_url": "https://aistudio.google.com/app/apikey",
    },
    "openai": {
        "name": "OpenAI (GPT)",
        "short": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "requires_key": True,
        "supports_vision": True,
        "default_model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-4.1-nano",
            "o3-mini",
        ],
        "key_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "short": "Claude",
        "env_key": "ANTHROPIC_API_KEY",
        "requires_key": True,
        "supports_vision": True,
        "default_model": "claude-3-7-sonnet-latest",
        "base_url": "https://api.anthropic.com/v1",
        "models": [
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-sonnet-4-20250514",
        ],
        "key_url": "https://console.anthropic.com/",
    },
    "openrouter": {
        "name": "OpenRouter (200+ Models)",
        "short": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "requires_key": True,
        "supports_vision": True,
        "default_model": "google/gemini-2.5-flash",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "google/gemini-2.5-flash",
            "openai/gpt-4o-mini",
            "anthropic/claude-3.7-sonnet",
            "qwen/qwen-2.5-vl-72b-instruct:free",
            "meta-llama/llama-4-maverick:free",
            "meta-llama/llama-3.2-90b-vision-instruct",
            "deepseek/deepseek-chat-v3-0324:free",
        ],
        "key_url": "https://openrouter.ai/keys",
    },
    "groq": {
        "name": "Groq Cloud (Ultra-Fast)",
        "short": "Groq",
        "env_key": "GROQ_API_KEY",
        "requires_key": True,
        "supports_vision": True,
        "default_model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "llama-3.2-90b-vision-preview",
            "llama-3.2-11b-vision-preview",
            "llama-3.3-70b-versatile",
        ],
        "key_url": "https://console.groq.com/keys",
    },
    "deepseek": {
        "name": "DeepSeek",
        "short": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "requires_key": True,
        "supports_vision": False,
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "key_url": "https://platform.deepseek.com/",
    },
    "ollama": {
        "name": "Ollama (Local / Free)",
        "short": "Ollama",
        "env_key": "",
        "requires_key": False,
        "supports_vision": True,
        "default_model": "llama3.2-vision",
        "base_url": "http://localhost:11434",
        "models": [
            "llama3.2-vision",
            "qwen2.5vl",
            "gemma3:12b",
            "gemma3:4b",
            "llava",
            "qwen2.5:7b",
            "llama3.1:8b",
        ],
        "key_url": "https://ollama.com/",
    },
    "custom": {
        "name": "Custom OpenAI-Compatible",
        "short": "Custom",
        "env_key": "CUSTOM_API_KEY",
        "requires_key": False,
        "supports_vision": True,
        "default_model": "local-model",
        "base_url": "http://localhost:1234/v1",
        "models": [
            "local-model",
            "gpt-4o-mini",
        ],
        "key_url": "",
    },
}


# ============================================================================
# Prompt Profiles & Answer Languages
# ============================================================================
PROMPT_PROFILES: Dict[str, Dict[str, str]] = {
    "english_exam": {
        "name": "🇬🇧 English Exam (Grammar & Reading)",
        "instruction": (
            "You are an expert English grammar, vocabulary, and reading comprehension professor "
            "solving an online certification exam from a screen capture.\n"
            "1. Carefully identify the question, fill-in-the-blank sentence, or reading passage.\n"
            "2. Identify all available multiple-choice options (A, B, C, D, etc.) or required input.\n"
            "3. Determine the single most accurate answer."
        ),
    },
    "general_quiz": {
        "name": "🎓 General Quiz / Multiple-Choice Test",
        "instruction": (
            "You are an encyclopedic academic assistant solving a test or quiz shown on screen.\n"
            "1. Identify the active question and all answer choices on the screen.\n"
            "2. Select the exact correct option or state the exact answer required.\n"
            "3. Provide a clear, concise justification."
        ),
    },
    "programming": {
        "name": "💻 Programming & Computer Science",
        "instruction": (
            "You are a Principal Software Engineer and Computer Science expert solving a technical assessment.\n"
            "1. Analyze the code snippet, algorithm question, or multiple-choice CS question on screen.\n"
            "2. Identify the exact output, bug fix, time/space complexity, or correct option.\n"
            "3. Keep explanations crisp and technically accurate."
        ),
    },
    "math_science": {
        "name": "📐 Math, Physics & Engineering",
        "instruction": (
            "You are an expert STEM problem solver analyzing a math, physics, or science question on screen.\n"
            "1. Extract the exact formula, numbers, and question asked.\n"
            "2. Compute the final result step-by-step and match it to the correct option.\n"
            "3. State the final answer first, followed by key calculation steps."
        ),
    },
    "translate_ua": {
        "name": "🇺🇦 Переклад + Пояснення (EN → UA)",
        "instruction": (
            "Ти експерт з англійської мови та перекладач. Проаналізуй завдання або текст на екрані:\n"
            "1. Якщо на екрані тестове питання — вкажи правильну відповідь та поясни правило українською мовою.\n"
            "2. Також додай точний переклад речення/питання українською мовою."
        ),
    },
    "custom": {
        "name": "✏️ Custom Prompt",
        "instruction": (
            "Analyze the question visible on the screen, find the exact correct answer, "
            "and explain briefly why it is correct."
        ),
    },
}

LANGUAGE_MODES: Dict[str, str] = {
    "en": "English Only",
    "uk": "Українська (пояснення українською)",
    "bilingual": "Bilingual (English + Українська)",
}


def load_dotenv_file(filepath: str = ENV_PATH) -> Dict[str, str]:
    """Lightweight .env parser with zero external dependency requirements."""
    env_vars: Dict[str, str] = {}
    if not os.path.exists(filepath):
        return env_vars
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    env_vars[key] = val
                    if key not in os.environ and val:
                        os.environ[key] = val
    except Exception:
        pass
    return env_vars


@dataclass
class AppConfig:
    # Provider & Model settings
    provider: str = "gemini"
    model: str = "gemini-3.1-flash-lite"
    provider_models: Dict[str, str] = field(default_factory=dict)
    api_keys: Dict[str, str] = field(default_factory=dict)
    custom_base_urls: Dict[str, str] = field(default_factory=dict)

    # Solver Mode & Prompt settings
    mode: str = "vision"  # "vision" or "ocr"
    prompt_profile: str = "english_exam"
    answer_language: str = "en"  # "en", "uk", "bilingual"
    custom_prompt: str = (
        "Analyze the question visible on the screen, find the exact correct answer, "
        "and explain briefly why it is correct."
    )
    temperature: float = 0.1

    # Capture settings
    monitor_index: int = 1
    capture_region: Optional[List[int]] = None  # [left, top, width, height] or None for full monitor
    cooldown_delay: int = 10
    skip_unchanged: bool = True
    hide_hud_on_capture: bool = False

    # UI & Notification settings
    notify: bool = True
    auto_copy_answer: bool = False
    always_on_top: bool = True
    window_opacity: float = 0.96
    theme: str = "mocha"  # "mocha", "cyber", "nord"
    start_paused: bool = False

    def get_api_key(self, provider_id: Optional[str] = None) -> str:
        prov = provider_id or self.provider
        # 1. Check user-configured keys in config
        key = self.api_keys.get(prov, "").strip()
        if key and not key.startswith("your_"):
            return key
        # 2. Check environment variable
        env_name = PROVIDERS.get(prov, {}).get("env_key", "")
        if env_name:
            env_val = os.environ.get(env_name, "").strip()
            if env_val and not env_val.startswith("your_"):
                return env_val
        return ""

    def set_api_key(self, provider_id: str, key: str) -> None:
        self.api_keys[provider_id] = key.strip()

    def get_base_url(self, provider_id: Optional[str] = None) -> str:
        prov = provider_id or self.provider
        custom_url = self.custom_base_urls.get(prov, "").strip()
        if custom_url:
            return custom_url.rstrip("/")
        if prov == "ollama":
            env_url = os.environ.get("OLLAMA_BASE_URL", "").strip()
            if env_url:
                return env_url.rstrip("/")
        if prov == "custom":
            env_url = os.environ.get("CUSTOM_BASE_URL", "").strip()
            if env_url:
                return env_url.rstrip("/")
        return PROVIDERS.get(prov, {}).get("base_url", "").rstrip("/")

    def get_model_for_provider(self, provider_id: str) -> str:
        if provider_id in self.provider_models and self.provider_models[provider_id].strip():
            return self.provider_models[provider_id].strip()
        return PROVIDERS.get(provider_id, {}).get("default_model", "gpt-4o-mini")

    def build_system_prompt(self) -> str:
        profile_data = PROMPT_PROFILES.get(self.prompt_profile, PROMPT_PROFILES["english_exam"])
        if self.prompt_profile == "custom" and self.custom_prompt.strip():
            base_instruction = self.custom_prompt.strip()
        else:
            base_instruction = profile_data["instruction"]

        lang_instruction = ""
        if self.answer_language == "uk":
            lang_instruction = (
                "\nIMPORTANT LANGUAGE RULE: Keep the exact option text in its original language in "
                "**Correct Answer:**, but write the **Explanation:** in Ukrainian (українською мовою)."
            )
        elif self.answer_language == "bilingual":
            lang_instruction = (
                "\nIMPORTANT LANGUAGE RULE: Provide the **Explanation:** first in concise English "
                "and then in Ukrainian (українською мовою)."
            )

        return (
            f"{base_instruction}\n"
            f"{lang_instruction}\n\n"
            "Format your response EXACTLY using these labels:\n\n"
            "**Correct Answer:** [State the exact option letter/number and full answer text, e.g., \"B) have been working\"]\n\n"
            "**Explanation:** [Provide a clear, concise 1-3 sentence explanation of why this answer is correct and why the other choices are incorrect.]"
        )

    def save(self, filepath: str = CONFIG_PATH) -> None:
        try:
            self.provider_models[self.provider] = self.model
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Could not save config: {e}")

    @classmethod
    def load(cls, filepath: str = CONFIG_PATH) -> "AppConfig":
        load_dotenv_file(ENV_PATH)
        cfg = cls()
        # Pre-populate keys from environment variables
        for prov_id, prov_meta in PROVIDERS.items():
            env_name = prov_meta.get("env_key")
            if env_name:
                val = os.environ.get(env_name, "").strip()
                if val and not val.startswith("your_"):
                    cfg.api_keys[prov_id] = val

        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(cfg, k):
                        if k == "api_keys" and isinstance(v, dict):
                            # Merge env keys with saved keys (saved keys take priority if non-empty)
                            for pk, pv in v.items():
                                if pv and str(pv).strip():
                                    cfg.api_keys[pk] = str(pv).strip()
                        else:
                            setattr(cfg, k, v)
            except Exception as e:
                print(f"[!] Error loading config.json, using defaults: {e}")

        # Ensure provider is valid
        if cfg.provider not in PROVIDERS:
            cfg.provider = "gemini"
        if not cfg.model:
            cfg.model = cfg.get_model_for_provider(cfg.provider)
        cfg.provider_models[cfg.provider] = cfg.model
        return cfg
