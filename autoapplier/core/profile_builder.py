from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pdfplumber


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
LINKEDIN_RE = re.compile(r"(https?://)?(www\.)?linkedin\.com/[A-Za-z0-9_/-]+", re.IGNORECASE)
GITHUB_RE = re.compile(r"(https?://)?(www\.)?github\.com/[A-Za-z0-9_-]+", re.IGNORECASE)

LANGUAGE_HINTS = [
    "english",
    "spanish",
    "french",
    "german",
    "italian",
    "portuguese",
    "catalan",
    "galician",
    "basque",
    "chinese",
    "japanese",
    "korean",
    "arabic",
    "hindi",
    "bengali",
    "russian",
    "polish",
    "dutch",
    "swedish",
    "norwegian",
    "danish",
    "finnish",
]


@dataclass
class ProfileBuildResult:
    profile_updates: dict
    summary: str


@dataclass
class ProfileLLMResult:
    profile_updates: dict
    extra_fields: dict
    summary: str
    roles: list[str]
    search_queries: list[str]
    questions: list[str]


def _extract_text(path: Path) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except Exception:
        return ""


def _is_cover_letter_text(text: str) -> bool:
    text_l = text.lower()
    hints = [
        "dear hiring",
        "hiring manager",
        "talent acquisition",
        "cover letter",
        "sincerely",
        "to whom it may concern",
        "subject:",
    ]
    return any(hint in text_l for hint in hints)


def _is_cover_path(path: Path) -> bool:
    parts = " ".join([p.lower() for p in path.parts])
    if any(word in parts for word in ["coverletter", "cover letter", "motivation"]):
        return True
    name = path.name.lower()
    if any(word in name for word in ["coverletter", "cover letter", "motivation"]):
        return True
    return False


def _should_use_pdf(path: Path) -> bool:
    if path.suffix.lower() != ".pdf":
        return False
    if _is_cover_path(path):
        return False
    return True


def _extract_name(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates: list[str] = []
    for line in lines[:30]:
        if len(line) > 60:
            continue
        lower = line.lower()
        if any(word in lower for word in ["resume", "curriculum", "cv"]):
            continue
        if any(word in lower for word in ["dear", "to whom", "hiring manager", "sincerely"]):
            continue
        if any(word in lower for word in ["email", "phone", "mobile", "address"]):
            continue
        if "@" in line or "," in line:
            continue
        words = line.split()
        if 2 <= len(words) <= 4:
            cap_words = [w for w in words if w[:1].isalpha() and w[:1].isupper()]
            if len(cap_words) >= 2:
                candidates.append(" ".join(words))
    if not candidates:
        return ""
    # Prefer the earliest candidate that is not all-caps but title-ish.
    for cand in candidates:
        if cand.isupper():
            continue
        return cand
    return candidates[0]


def _extract_single(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    value = match.group(0).strip()
    if value.startswith("http"):
        return value
    if "linkedin.com" in value.lower():
        return f"https://{value.lstrip('/')}"
    if "github.com" in value.lower():
        return f"https://{value.lstrip('/')}"
    return value


def _extract_languages(text: str) -> str:
    text_l = text.lower()
    found = []
    for lang in LANGUAGE_HINTS:
        if re.search(rf"\\b{re.escape(lang)}\\b", text_l):
            found.append(lang.title())
    return ", ".join(sorted(set(found)))


def _extract_skills(text: str) -> list[str]:
    skills = []
    for line in text.splitlines():
        if "skills" in line.lower():
            parts = re.split(r"[:\-•]", line, maxsplit=1)
            if len(parts) > 1:
                skills.extend([p.strip() for p in parts[1].split(",") if p.strip()])
    if not skills:
        tokens = re.findall(r"[A-Za-z][A-Za-z+.#-]{2,}", text)
        common = {}
        for token in tokens:
            t = token.lower()
            if t in {"experience", "project", "projects", "education", "university", "summary"}:
                continue
            common[t] = common.get(t, 0) + 1
        ranked = sorted(common.items(), key=lambda x: x[1], reverse=True)
        skills = [k for k, _ in ranked[:20]]
    clean = []
    for skill in skills:
        s = skill.strip()
        if s and len(s) <= 40:
            clean.append(s)
    return clean


def build_profile_from_cvs(root: str) -> ProfileBuildResult:
    root_path = Path(root) if root else None
    if not root_path or not root_path.exists():
        return ProfileBuildResult(profile_updates={}, summary="")

    texts = []
    for path in root_path.rglob("*"):
        if not _should_use_pdf(path):
            continue
        text = _extract_text(path)
        if text and _is_cover_letter_text(text[:2000]):
            continue
        if text:
            texts.append(text)

    if not texts:
        return ProfileBuildResult(profile_updates={}, summary="")

    combined = "\n".join(texts)
    name = _extract_name(combined)
    email = _extract_single(EMAIL_RE, combined)
    phone = _extract_single(PHONE_RE, combined)
    linkedin = _extract_single(LINKEDIN_RE, combined)
    github = _extract_single(GITHUB_RE, combined)
    languages = _extract_languages(combined)
    skills = _extract_skills(combined)

    updates = {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "languages": languages,
    }
    summary_parts = []
    if skills:
        summary_parts.append(f"Skills: {', '.join(skills[:20])}")
    if languages:
        summary_parts.append(f"Languages: {languages}")
    summary = "\n".join(summary_parts)
    return ProfileBuildResult(profile_updates=updates, summary=summary)


def collect_cv_texts(root: str, max_chars: int | None = 20000) -> str:
    root_path = Path(root) if root else None
    if not root_path or not root_path.exists():
        return ""
    texts = []
    for path in root_path.rglob("*"):
        if not _should_use_pdf(path):
            continue
        text = _extract_text(path)
        if text and _is_cover_letter_text(text[:2000]):
            continue
        if text:
            texts.append(text)
        if max_chars is not None and sum(len(t) for t in texts) >= max_chars:
            break
    combined = "\n".join(texts)
    if max_chars is None:
        return combined
    return combined[:max_chars]


def build_profile_with_ollama(
    root: str,
    ollama_client,
    existing_profile: dict,
) -> ProfileLLMResult:
    cv_text = collect_cv_texts(root)
    if not cv_text:
        return ProfileLLMResult(
            profile_updates={},
            extra_fields={},
            summary="",
            roles=[],
            search_queries=[],
            questions=[],
        )
    prompt = (
        "Extract all possible profile information from the CV text. "
        "Return JSON only with keys: profile_updates, extra_fields, summary, search_queries, questions, roles. "
        "profile_updates must include only these keys if present: "
        "name, email, phone, location, linkedin, github, languages, salary_expectations, remote_preference. "
        "extra_fields must include EVERYTHING else you can extract from the CV. "
        "Use short, stable keys and keep values concise. "
        "You may include arrays and nested objects in extra_fields if needed. "
        "summary is a short skills summary. "
        "roles is a list of likely job titles based on the CV (3-6 items). "
        "search_queries is a list of 3-6 Google search queries for relevant jobs, using only role titles and locations. "
        "Do NOT include domains, URLs, or random words from the CV in search queries. "
        "questions is a list of clarification questions ONLY if the CV lacks needed info. "
        "Do not invent personal data; only extract from the CV text.\n\n"
        f"EXISTING PROFILE:\n{existing_profile}\n\n"
        f"CV TEXT:\n{cv_text}"
    )
    try:
        data = ollama_client.generate_json(prompt)
    except Exception:
        fallback = build_profile_from_cvs(root)
        return ProfileLLMResult(
            profile_updates=fallback.profile_updates,
            extra_fields={},
            summary=fallback.summary,
            roles=[],
            search_queries=[],
            questions=[],
        )
    profile_updates = data.get("profile_updates", {}) if isinstance(data.get("profile_updates"), dict) else {}
    raw_extra = data.get("extra_fields", {})
    extra_fields = _flatten_extra_fields(raw_extra)
    summary = str(data.get("summary", "")).strip()
    raw_roles = data.get("roles", [])
    roles = [str(r).strip() for r in raw_roles if str(r).strip()] if isinstance(raw_roles, list) else []
    raw_queries = data.get("search_queries", [])
    search_queries = [str(q).strip() for q in raw_queries if str(q).strip()] if isinstance(raw_queries, list) else []
    raw_questions = data.get("questions", [])
    questions = [str(q).strip() for q in raw_questions if str(q).strip()] if isinstance(raw_questions, list) else []
    return ProfileLLMResult(
        profile_updates=profile_updates,
        extra_fields=extra_fields,
        summary=summary,
        roles=roles,
        search_queries=search_queries,
        questions=questions,
    )


def _flatten_extra_fields(data, prefix: str = "") -> dict:
    flat = {}
    if isinstance(data, dict):
        for key, value in data.items():
            key_str = str(key).strip()
            if not key_str:
                continue
            new_prefix = f"{prefix}{key_str}" if not prefix else f"{prefix}.{key_str}"
            flat.update(_flatten_extra_fields(value, new_prefix))
        if not data and prefix:
            flat[prefix] = ""
    elif isinstance(data, list):
        if not data and prefix:
            flat[prefix] = ""
        for idx, item in enumerate(data, start=1):
            item_prefix = f"{prefix}_{idx}" if prefix else f"item_{idx}"
            flat.update(_flatten_extra_fields(item, item_prefix))
    else:
        if prefix:
            flat[prefix] = str(data)
    return flat


def infer_roles_from_paths(root: str) -> list[str]:
    root_path = Path(root) if root else None
    if not root_path or not root_path.exists():
        return []
    roles = set()
    for path in root_path.rglob("*"):
        if not _should_use_pdf(path):
            continue
        name = " ".join(path.parts).lower()
        if "cyber" in name:
            roles.update(["Cybersecurity Analyst", "SOC Analyst", "Penetration Tester"])
        if "red team" in name:
            roles.add("Red Team Analyst")
        if "purple team" in name:
            roles.add("Purple Team Analyst")
        if "futbol" in name or "football" in name:
            roles.update(["Football Scout", "Football Analyst"])
        if "data" in name:
            roles.add("Data Analyst")
        if "devops" in name:
            roles.add("DevOps Engineer")
        if "web" in name:
            roles.add("Web Developer")
    return sorted(roles)
