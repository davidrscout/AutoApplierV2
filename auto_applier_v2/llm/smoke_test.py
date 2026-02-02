import os
import sys

from .claw_gateway import claw_chat


def _print_config() -> None:
    url = os.getenv("CLAW_URL", "http://127.0.0.1:18789/v1/chat/completions").strip()
    model = os.getenv("CLAW_MODEL", "openclaw").strip()
    timeout = os.getenv("CLAW_TIMEOUT_SECONDS", "60").strip()
    token_set = bool(os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip())

    print("[SMOKE] CLAW_URL=", url)
    print("[SMOKE] CLAW_MODEL=", model)
    print("[SMOKE] CLAW_TIMEOUT_SECONDS=", timeout)
    print("[SMOKE] OPENCLAW_GATEWAY_TOKEN set=", token_set)


def main() -> int:
    _print_config()

    try:
        text = claw_chat(
            [{"role": "user", "content": "di OK"}],
            temperature=0.2,
        )
    except Exception as exc:
        print("[SMOKE] Error:", exc)
        return 3

    print("[SMOKE] Response:", text)
    if text.strip() == "OK":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
