import json
import re
from dataclasses import dataclass

import requests


@dataclass
class OllamaConfig:
    base_url: str
    model: str


class OllamaClient:
    def __init__(self, config: OllamaConfig, timeout: int = 120) -> None:
        self.config = config
        self.timeout = timeout

    def ensure_model_available(self) -> str | None:
        tags_url = f"{self.config.base_url.rstrip('/')}/api/tags"
        try:
            resp = requests.get(tags_url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            if not models:
                return None
            names = [m.get("name") for m in models if m.get("name")]
            if self.config.model not in names:
                self.config.model = names[0]
            return self.config.model
        except Exception:
            return None

    def _post(self, prompt: str) -> str:
        base = self.config.base_url.rstrip("/")
        url = f"{base}/api/generate"
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "top_p": 1, "top_k": 1},
        }
        resp = requests.post(url, json=payload, timeout=self.timeout)
        if resp.status_code == 404:
            # Fallback for servers that only expose the chat endpoint.
            chat_url = f"{base}/api/chat"
            chat_payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0, "top_p": 1, "top_k": 1},
            }
            chat_resp = requests.post(chat_url, json=chat_payload, timeout=self.timeout)
            if chat_resp.status_code == 404:
                # OpenAI-compatible fallback
                oa_url = f"{base}/v1/chat/completions"
                oa_payload = {
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                }
                oa_resp = requests.post(oa_url, json=oa_payload, timeout=self.timeout)
                oa_resp.raise_for_status()
                data = oa_resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                return (content or "").strip()
            chat_resp.raise_for_status()
            data = chat_resp.json()
            message = data.get("message", {})
            return (message.get("content") or "").strip()
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    def generate_text(self, prompt: str) -> str:
        return self._post(prompt).strip()

    def generate_json(self, prompt: str) -> dict:
        text = self._post(prompt)
        extracted = self._extract_json(text)
        if extracted is None:
            raise ValueError("LLM did not return JSON")
        return extracted

    def _extract_json(self, text: str) -> dict | None:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
