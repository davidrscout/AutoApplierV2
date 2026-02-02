import os
from typing import Any, Dict, List

import httpx

DEFAULT_URL = "http://127.0.0.1:18789/v1/chat/completions"
DEFAULT_MODEL = "openclaw"
DEFAULT_TIMEOUT = 60


def _require_token() -> str:
    token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if not token:
        raise ValueError("OPENCLAW_GATEWAY_TOKEN no seteada")
    return token


def claw_chat(messages: List[Dict[str, Any]], temperature: float = 0.2) -> str:
    token = _require_token()
    url = os.getenv("CLAW_URL", DEFAULT_URL).strip() or DEFAULT_URL
    model = os.getenv("CLAW_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    timeout_seconds = float(os.getenv("CLAW_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)))

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise RuntimeError("Is the SSH tunnel up?") from exc
    except httpx.ConnectError as exc:
        raise RuntimeError("Is the SSH tunnel up?") from exc
    except httpx.RequestError as exc:
        raise RuntimeError("Is the SSH tunnel up?") from exc

    if response.status_code == 401:
        raise RuntimeError("Token incorrecto")
    if response.status_code >= 400:
        short = response.text[:200].replace("\n", " ")
        raise RuntimeError(f"OpenClaw Gateway error {response.status_code}: {short}")

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("OpenClaw Gateway devolvio JSON invalido") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(
            "OpenClaw Gateway respuesta invalida: falta choices[0].message.content"
        ) from exc

    return (content or "").strip()
