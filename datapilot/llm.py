# -*- coding: utf-8 -*-
"""Minimal LLM clients: Ollama (local) and OpenAI-compatible APIs (DeepSeek/Qwen)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    """Raised when the model call fails."""


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: float | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout or config.LLM_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise LLMError(f"模型接口返回 HTTP {exc.code}：{body}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"连不上模型服务：{exc.reason}") from exc
    except TimeoutError as exc:
        raise LLMError("模型调用超时") from exc


class OllamaClient:
    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or config.OLLAMA_MODEL
        self.host = (host or config.OLLAMA_HOST).rstrip("/")

    def chat(self, messages: list[dict], json_mode: bool = True) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 512, "top_p": 0.9},
        }
        if json_mode:
            payload["format"] = "json"
        data = _post_json(f"{self.host}/api/chat", payload)
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Ollama 返回格式异常：{str(data)[:200]}") from exc


class OpenAICompatClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.base_url = (base_url or config.OPENAI_BASE_URL).rstrip("/")
        self.api_key = api_key or config.OPENAI_API_KEY
        self.model = model or config.OPENAI_MODEL
        if not self.api_key:
            raise LLMError("LLM_PROVIDER=openai 时需要设置 OPENAI_API_KEY")

    def chat(self, messages: list[dict], json_mode: bool = True) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 512,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            data = _post_json(f"{self.base_url}/chat/completions", payload, headers)
        except LLMError as exc:
            # Some providers reject response_format; retry once without it.
            if json_mode and "HTTP 400" in str(exc):
                payload.pop("response_format", None)
                data = _post_json(f"{self.base_url}/chat/completions", payload, headers)
            else:
                raise
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"模型返回格式异常：{str(data)[:200]}") from exc


def get_client():
    if config.LLM_PROVIDER == "openai":
        return OpenAICompatClient()
    return OllamaClient()
