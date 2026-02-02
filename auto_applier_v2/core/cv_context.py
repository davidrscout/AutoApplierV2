import json
import os
from typing import Callable

try:
    import pypdf
except ImportError:
    pypdf = None


class CVContextManager:
    def __init__(self, cache_path: str, llm=None) -> None:
        self.cache_path = cache_path
        self.llm = llm
        self.context_text = ""
        self.cv_folder = ""

    def build_context(self, cv_root: str, log: Callable[[str], None]) -> str:
        self.cv_folder = cv_root
        if self.context_text:
            return self.context_text

        cached = self._load_cache() or {}
        if cached.get("folder_path") == self.cv_folder and cached.get("text"):
            self.context_text = str(cached.get("text", ""))
            log("[CV] Cached context found. Skipping rebuild.")
            return self.context_text

        self.context_text = self._read_cv_files(log)
        self._save_cache()
        return self.context_text

    def build_keywords_file(
        self,
        cv_root: str,
        log: Callable[[str], None],
        output_path: str,
    ) -> list[str]:
        self.cv_folder = cv_root
        keywords = self.generate_keywords()
        if not keywords:
            log("[CV] No keywords generated.")
            return []

        self._write_keywords_file(output_path, keywords)
        cached = self._load_cache() or {}
        cached.update(
            {
                "folder_path": self.cv_folder,
                "keywords": keywords,
            }
        )
        self._save_cache(cached)
        log(f"[CV] Keywords saved: {output_path}")
        return keywords

    def generate_keywords(self) -> list[str]:
        print("[CV] MODO MANUAL: Usando keywords maestras (sin llamar a API).")
        return [
            # Cybersecurity
            "Cybersecurity Analyst",
            "Junior Pentester",
            "SOC Analyst",
            "Offensive Security",
            "Red Team",
            "Ethical Hacker",
            "Vulnerability Researcher",
            "Security Consultant",
            # Development & AI
            "Python Developer",
            "Backend Developer",
            "AI Engineer",
            "Full Stack Developer",
            "Cloud Engineer",
            "API Developer",
            "Software Engineer",
            # Scouting
            "Football Scout",
            "Performance Analyst",
            "Data Scout",
            "Sports Analyst",
        ]

    def _read_cv_files(self, log: Callable[[str], None]) -> str:
        if not self.cv_folder or not os.path.exists(self.cv_folder):
            return ""

        files = [f for f in os.listdir(self.cv_folder) if f.lower().endswith(".pdf")]
        if not pypdf:
            log("[CV] Missing pypdf. Install with: pip install pypdf")
            return ""

        log(f"[CV] Reading {len(files)} PDF files...")
        full_text: list[str] = []
        for filename in files:
            path = os.path.join(self.cv_folder, filename)
            try:
                text = ""
                with open(path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages[:2]:
                        text += (page.extract_text() or "") + "\n"
                full_text.append(f"--- CV: {filename} ---\n{text}")
            except Exception:
                pass

        return "\n".join(full_text)

    def _write_keywords_file(self, path: str, keywords: list[str]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(", ".join(keywords))
                f.write("\n")
        except Exception:
            pass

    def _load_cache(self) -> dict | None:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_cache(self, data: dict | None = None) -> None:
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data or {"folder_path": self.cv_folder, "text": self.context_text}, f)
        except Exception:
            pass
