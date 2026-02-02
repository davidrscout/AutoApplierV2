import json
import os
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def normalize_question(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s\-_/]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:200]


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\-_. ]+", "", text).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:80] if cleaned else "file"


def hash_files(paths: list[Path]) -> str:
    import hashlib

    h = hashlib.sha256()
    for p in sorted(paths):
        try:
            h.update(p.name.encode("utf-8", errors="ignore"))
            stat = p.stat()
            h.update(str(stat.st_mtime_ns).encode())
            h.update(str(stat.st_size).encode())
        except Exception:
            continue
    return h.hexdigest()


def load_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def clamp_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))
