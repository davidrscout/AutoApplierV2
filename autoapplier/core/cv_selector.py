from dataclasses import dataclass
from pathlib import Path
import re

import pdfplumber

from .profile_builder import _is_cover_letter_text, _should_use_pdf


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return set(words)


def _score_text(job_text: str, cv_text: str) -> float:
    job_tokens = _tokenize(job_text)
    cv_tokens = _tokenize(cv_text)
    if not job_tokens or not cv_tokens:
        return 0.0
    overlap = job_tokens.intersection(cv_tokens)
    return len(overlap) / len(job_tokens)


@dataclass
class CVMatch:
    path: Path
    score: float


class CVSelector:
    def __init__(self, root: str) -> None:
        self.root = Path(root) if root else None
        self.index: list[CVMatch] = []

    def index_cvs(self) -> None:
        self.index = []
        if not self.root or not self.root.exists():
            return
        for path in self.root.rglob("*"):
            if not _should_use_pdf(path):
                continue
            text = self._extract_text(path)
            if text and _is_cover_letter_text(text[:2000]):
                continue
            if not text:
                continue
            self.index.append(CVMatch(path=path, score=0.0))

    def select_best(self, job_text: str) -> Path | None:
        if not self.index:
            return None
        best_path = None
        best_score = -1.0
        for entry in self.index:
            text = self._extract_text(entry.path)
            score = _score_text(job_text, text)
            if score > best_score:
                best_score = score
                best_path = entry.path
        return best_path

    def _extract_text(self, path: Path) -> str:
        try:
            with pdfplumber.open(path) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            return "\n".join(pages)
        except Exception:
            return ""
