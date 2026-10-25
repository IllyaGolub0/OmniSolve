import base64
import io
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
from PIL import Image
import requests

from core.config import AppConfig, PROVIDERS

# Optional official Google GenAI SDK
genai_sdk = None
try:
    from google import genai as genai_sdk
except ImportError:
    pass


@dataclass
class SolveResult:
    success: bool
    raw_text: str
    short_answer: str
    explanation: str
    provider: str
    model: str
    latency_ms: int
    error: Optional[str] = None


def encode_pil_to_base64(pil_img: Image.Image, max_dim: int = 1600, quality: int = 88) -> Tuple[str, str]:
    """Resizes image if overly large and encodes to JPEG base64 string for fast multimodal upload."""
    img = pil_img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64, "image/jpeg"


def parse_ai_response(full_response: str) -> Tuple[str, str]:
    """
    Extracts (short_answer, explanation) from the LLM response.
    Also handles <think>...</think> blocks from reasoning models cleanly.
    """
    if not full_response:
        return "No answer returned", ""

    # Strip <think>...</think> tags if present from DeepSeek-R1 / QwQ models
    cleaned = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL).strip()
    if not cleaned:
        cleaned = full_response.strip()

    short_answer = ""
    explanation = ""

    # Match **Correct Answer:** or Correct Answer:
    ans_match = re.search(
        r"(?:\*\*|##\s*)?(?:Correct Answer|Правильна відповідь|Answer)\s*:?\s*(?:\*\*)?\s*(.+?)(?=\n\s*(?:\*\*|##\s*)?(?:Explanation|Пояснення)\b|\Z)",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    exp_match = re.search(
        r"(?:\*\*|##\s*)?(?:Explanation|Пояснення)\s*:?\s*(?:\*\*)?\s*(.+)",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if ans_match:
        first_chunk = ans_match.group(1).strip()
        # Take first non-empty line of the answer section
        lines = [ln.strip().strip("*").strip() for ln in first_chunk.splitlines() if ln.strip()]
        if lines:
            short_answer = lines[0]
            if len(lines) > 1 and not exp_match:
                explanation = "\n".join(lines[1:]).strip()

    if exp_match:
        explanation = exp_match.group(1).strip()

    # Fallback if model didn't follow strict headers
    if not short_answer:
        lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
        if lines:
            short_answer = re.sub(r"^\*\*|\*\*$", "", lines[0]).strip()
            explanation = "\n".join(lines[1:]).strip()
        else:
            short_answer = cleaned[:140]

    return short_answer, explanation


class MultiLLMClient:
    """Unified client supporting Google Gemini, OpenAI, Anthropic Claude, OpenRouter, Groq, DeepSeek, Ollama, and Custom APIs."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._gemini_client = None
        self._gemini_client_key = None

    def _get_gemini_sdk_client(self, api_key: str):
        if not genai_sdk or not api_key:
            return None
        if self._gemini_client is None or self._gemini_client_key != api_key:
            self._gemini_client = genai_sdk.Client(api_key=api_key)
            self._gemini_client_key = api_key
        return self._gemini_client

    def solve_vision(self, pil_img: Image.Image) -> SolveResult:
        """Sends image + system prompt to the selected multimodal LLM provider."""
        provider = self.config.provider
        model = self.config.model.strip() or self.config.get_model_for_provider(provider)
        prompt = self.config.build_system_prompt()
        t0 = time.perf_counter()

        try:
            raw_text = self._dispatch_request(
                provider=provider,
                model=model,
                prompt=prompt,
                pil_img=pil_img,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            short_ans, explanation = parse_ai_response(raw_text)
            return SolveResult(
                success=True,
                raw_text=raw_text,
                short_answer=short_ans,
                explanation=explanation,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            err_str = str(e)
            return SolveResult(
                success=False,
                raw_text="",
                short_answer="API Error",
                explanation=err_str,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                error=err_str,
            )

    def solve_text(self, extracted_text: str) -> SolveResult:
        """Sends OCR/recognized text + system prompt to the selected LLM provider."""
        provider = self.config.provider
        model = self.config.model.strip() or self.config.get_model_for_provider(provider)
        base_prompt = self.config.build_system_prompt()
        full_prompt = (
            f"{base_prompt}\n\n"
            f"--- RECOGNIZED SCREEN TEXT ---\n"
            f"{extracted_text}\n"
            f"------------------------------"
        )
        t0 = time.perf_counter()

        try:
            raw_text = self._dispatch_request(
                provider=provider,
                model=model,
                prompt=full_prompt,
                pil_img=None,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            short_ans, explanation = parse_ai_response(raw_text)
            return SolveResult(
                success=True,
                raw_text=raw_text,
                short_answer=short_ans,
                explanation=explanation,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            err_str = str(e)
            return SolveResult(
                success=False,
                raw_text="",
                short_answer="API Error",
                explanation=err_str,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                error=err_str,
            )

    def test_connection(self) -> Tuple[bool, str, int]:
        """Tests the currently configured provider, model, and API key with a fast ping prompt."""
        provider = self.config.provider
        model = self.config.model.strip() or self.config.get_model_for_provider(provider)
        t0 = time.perf_counter()
        try:
            reply = self._dispatch_request(
                provider=provider,
                model=model,
                prompt="Reply with the exact word: READY",
                pil_img=None,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            snippet = reply.strip().splitlines()[0][:60] if reply else "OK"
            return True, f"Connected ({latency} ms): {snippet}", latency
        except Exception as e:
            latency = int((time.perf_counter() - t0) * 1000)
            return False, str(e), latency

    def _dispatch_request(
        self,
        provider: str,
        model: str,
        prompt: str,
        pil_img: Optional[Image.Image] = None,
    ) -> str:
        api_key = self.config.get_api_key(provider)
        prov_meta = PROVIDERS.get(provider, {})

        if prov_meta.get("requires_key", True) and not api_key:
            prov_name = prov_meta.get("name", provider)
            raise ValueError(
                f"API Key for {prov_name} is missing.\n"
                f"Open the '⚙ Settings' tab and paste your {prov_name} API key (or add it to .env)."
            )

        if provider == "gemini":
            return self._call_gemini(api_key, model, prompt, pil_img)
        elif provider == "anthropic":
            return self._call_anthropic(api_key, model, prompt, pil_img)
        elif provider == "ollama":
            return self._call_ollama(model, prompt, pil_img)
        elif provider in ("openai", "openrouter", "groq", "deepseek", "custom"):
            return self._call_openai_compatible(provider, api_key, model, prompt, pil_img)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _call_gemini(
        self,
        api_key: str,
        model: str,
        prompt: str,
        pil_img: Optional[Image.Image],
    ) -> str:
        # 1. Use google-genai SDK if available
        sdk_client = self._get_gemini_sdk_client(api_key)
        if sdk_client is not None:
            contents = [pil_img, prompt] if pil_img is not None else prompt
            response = sdk_client.models.generate_content(
                model=model,
                contents=contents,
            )
            if response and response.text:
                return response.text
            raise RuntimeError("Empty response received from Gemini API.")

        # 2. Fallback to direct Gemini REST API
        base_url = self.config.get_base_url("gemini")
        url = f"{base_url}/models/{model}:generateContent?key={api_key}"
        parts = [{"text": prompt}]
        if pil_img is not None:
            b64_data, mime = encode_pil_to_base64(pil_img)
            parts.insert(0, {"inline_data": {"mime_type": mime, "data": b64_data}})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": self.config.temperature},
        }
        resp = requests.post(url, json=payload, timeout=45)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {data}")
        text_parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in text_parts)

    def _call_openai_compatible(
        self,
        provider: str,
        api_key: str,
        model: str,
        prompt: str,
        pil_img: Optional[Image.Image],
    ) -> str:
        base_url = self.config.get_base_url(provider)
        url = f"{base_url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/omnisolve-ai/english-exam-solver"
            headers["X-Title"] = "OmniSolve AI Exam Assistant"

        if pil_img is not None:
            if provider == "deepseek" and "vl" not in model.lower():
                raise ValueError(
                    f"Model '{model}' on DeepSeek is text-only and does not accept direct screenshots.\n"
                    f"Switch Mode to 'OCR' or choose a Vision provider (Gemini, OpenAI, Claude, Groq, OpenRouter)."
                )
            b64_data, mime = encode_pil_to_base64(pil_img)
            user_content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64_data}"},
                },
            ]
        else:
            user_content = prompt

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
        }
        # Reasoning models (o1, o3) don't accept temperature in some OpenAI endpoints
        if not model.startswith(("o1", "o3", "o4")):
            payload["temperature"] = self.config.temperature

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            try:
                err_json = resp.json()
                err_msg = err_json.get("error", {}).get("message", resp.text[:300])
            except Exception:
                err_msg = resp.text[:300]
            raise RuntimeError(f"{PROVIDERS.get(provider, {}).get('short', provider)} Error ({resp.status_code}): {err_msg}")

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("No response choices returned from API.")
        return choices[0].get("message", {}).get("content", "")

    def _call_anthropic(
        self,
        api_key: str,
        model: str,
        prompt: str,
        pil_img: Optional[Image.Image],
    ) -> str:
        base_url = self.config.get_base_url("anthropic")
        url = f"{base_url}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        content_blocks = []
        if pil_img is not None:
            b64_data, mime = encode_pil_to_base64(pil_img)
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": b64_data,
                    },
                }
            )
        content_blocks.append({"type": "text", "text": prompt})

        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": self.config.temperature,
            "messages": [{"role": "user", "content": content_blocks}],
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            try:
                err_msg = resp.json().get("error", {}).get("message", resp.text[:300])
            except Exception:
                err_msg = resp.text[:300]
            raise RuntimeError(f"Claude API Error ({resp.status_code}): {err_msg}")

        data = resp.json()
        blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    def _call_ollama(
        self,
        model: str,
        prompt: str,
        pil_img: Optional[Image.Image],
    ) -> str:
        base_url = self.config.get_base_url("ollama")
        url = f"{base_url}/api/chat"

        message = {"role": "user", "content": prompt}
        if pil_img is not None:
            b64_data, _ = encode_pil_to_base64(pil_img)
            message["images"] = [b64_data]

        payload = {
            "model": model,
            "messages": [message],
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }

        try:
            resp = requests.post(url, json=payload, timeout=90)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {base_url}.\n"
                "Make sure Ollama is running (`ollama serve`) and the model is pulled (`ollama pull llama3.2-vision`)."
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Ollama Error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        return data.get("message", {}).get("content", "")


def fetch_provider_models(provider: str, base_url: str, api_key: str = "") -> List[str]:
    """Dynamically fetches available models from Ollama or OpenAI-compatible endpoints."""
    try:
        if provider == "ollama":
            resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", []) if m.get("name")]
                if models:
                    return models
        elif provider == "gemini" and api_key:
            resp = requests.get(
                f"{base_url.rstrip('/')}/models?key={api_key}",
                timeout=8,
            )
            if resp.status_code == 200:
                models = []
                for m in resp.json().get("models", []):
                    name = m.get("name", "").replace("models/", "")
                    methods = m.get("supportedGenerationMethods", [])
                    if name and "generateContent" in methods and "gemini" in name:
                        models.append(name)
                if models:
                    return models
        elif provider in ("openai", "openrouter", "groq", "deepseek", "custom"):
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=8)
            if resp.status_code == 200:
                models = [m.get("id") for m in resp.json().get("data", []) if m.get("id")]
                if models:
                    return sorted(models)[:60]
    except Exception:
        pass
    return PROVIDERS.get(provider, {}).get("models", [])
