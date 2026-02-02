from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
from datetime import datetime
import hashlib
import csv

from playwright.sync_api import sync_playwright

from .cv_selector import CVSelector
from .form_filler import extract_form_fields, fill_field, submit_application, find_required_unfilled
from .llm import OllamaClient, OllamaConfig
from .job_search import is_login_or_captcha
from .profile_builder import build_profile_with_ollama, infer_roles_from_paths
from .storage import load_autoprofile, save_autoprofile, load_personal_answers, save_personal_answers, save_settings
from .tracking import log_application
from .utils import (
    OUTPUT_DIR,
    TEMPLATES_DIR,
    DATA_DIR,
    load_text_file,
    normalize_question,
    safe_filename,
    hash_files,
)


PERSONAL_KEYWORDS = {
    "ssn",
    "social security",
    "social-security",
    "passport",
    "visa",
    "citizenship",
    "work authorization",
    "dob",
    "date of birth",
    "age",
    "gender",
    "race",
    "ethnicity",
    "religion",
    "disability",
    "criminal",
    "conviction",
    "medical",
    "health",
    "salary history",
    "background check",
    "driver license",
    "ssn last 4",
    "legal name",
}


@dataclass
class PopupRequest:
    question: str
    kind: str = "personal"
    answer: str | None = None
    remember: bool = False
    event: threading.Event | None = None


class AutomationRunner:
    def __init__(self, settings: dict, log_cb, status_cb, popup_cb) -> None:
        self.settings = settings
        self.autoprofile = load_autoprofile()
        self.profile_summary = self.autoprofile.get("summary", "")
        self.cv_hash = None
        # Wrap log to also print to stdout with timestamp.
        self.log_path = DATA_DIR / "run_logs.csv"
        self._ensure_log_file()
        def _log(msg: str) -> None:
            stamped = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
            log_cb(stamped)
            print(stamped, flush=True)
            try:
                with self.log_path.open("a", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.now().isoformat(timespec="seconds"), msg])
            except Exception:
                pass

        self.log = _log
        self.set_status = status_cb
        self.popup_cb = popup_cb
        self.stop_requested = threading.Event()
        self.personal_answers = load_personal_answers()
        self.cv_selector = CVSelector(settings.get("cv_root", ""))
        self.cv_selector.index_cvs()
        if self.cv_selector.index:
            self.log(f"Indexed {len(self.cv_selector.index)} CV PDFs.")
        else:
            self.log("No CV PDFs found in the selected folder.")
        self.ollama = OllamaClient(
            OllamaConfig(
                base_url=settings.get("ollama_base_url", "http://localhost:11434"),
                model=settings.get("ollama_model", "llama3.1"),
            )
        )
        model = self.ollama.ensure_model_available()
        if not model:
            self.log("No Ollama models installed. Please run: ollama pull <model>")
        else:
            self.log(f"Ollama model: {model}")

    def request_stop(self) -> None:
        self.stop_requested.set()

    def run(self) -> None:
        daily_limit = int(self.settings.get("daily_limit", 10))
        applied = 0
        with sync_playwright() as p:
            browser, context = self._launch_browser_and_context(p)
            page = context.new_page()
            self._ensure_autoprofile(force=False)
            job_urls = self.search_jobs(page)
            if not job_urls:
                self.log("No job URLs provided or found.")
                browser.close()
                return
            for job_url in job_urls:
                if self.stop_requested.is_set():
                    break
                if applied >= daily_limit:
                    self.log("Daily limit reached.")
                    break
                self.set_status(f"Opening {job_url}")
                try:
                    page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(2)
                    if is_login_or_captcha(page):
                        self.log("Login/CAPTCHA detected. Waiting for manual interaction...")
                        if not self._pause_for_captcha(
                            "Completa el login/CAPTCHA en el navegador y pulsa Continuar."
                        ):
                            log_application(
                                role="",
                                company="",
                                job_title="",
                                job_url=job_url,
                                location="",
                                remote="",
                                cv_used="",
                                score=None,
                                status="POPUP_REQUIRED",
                                notes="Login/CAPTCHA required",
                            )
                            continue
                        # If still blocked, skip.
                        if is_login_or_captcha(page):
                            log_application(
                                role="",
                                company="",
                                job_title="",
                                job_url=job_url,
                                location="",
                                remote="",
                                cv_used="",
                                score=None,
                                status="POPUP_REQUIRED",
                                notes="Login/CAPTCHA still present",
                            )
                            continue
                    job_text = self._get_job_text(page)
                    if not job_text:
                        self.log("Could not read job description; skipping.")
                        log_application(
                            role="",
                            company="",
                            job_title="",
                            job_url=job_url,
                            location="",
                            remote="",
                            cv_used="",
                            score=None,
                            status="ERROR",
                            notes="Empty job description",
                        )
                        continue
                    analysis = self.analyze_job(job_text)
                    score = analysis.get("score", 0)
                    decision = self.should_apply(score, analysis)
                    if not decision:
                        self.log(f"Discarded {job_url} (score {score})")
                        log_application(
                            role=analysis.get("role", ""),
                            company=analysis.get("company_name", ""),
                            job_title=analysis.get("job_title", ""),
                            job_url=job_url,
                            location=analysis.get("location", ""),
                            remote=analysis.get("work_mode", ""),
                            cv_used="",
                            score=score,
                            status="DISCARDED",
                            notes=analysis.get("reason", ""),
                        )
                        continue
                    self.set_status(f"Applying {job_url}")
                    cover_path = self.generate_cover_letter(job_text, analysis)
                    cv_path = self.cv_selector.select_best(job_text)
                    ok = self.apply_to_job(page, job_text, cv_path, cover_path)
                    if ok:
                        applied += 1
                        log_application(
                            role=analysis.get("role", ""),
                            company=analysis.get("company_name", ""),
                            job_title=analysis.get("job_title", ""),
                            job_url=job_url,
                            location=analysis.get("location", ""),
                            remote=analysis.get("work_mode", ""),
                            cv_used=str(cv_path) if cv_path else "",
                            score=score,
                            status="APPLIED",
                            notes="Submitted",
                        )
                    else:
                        log_application(
                            role=analysis.get("role", ""),
                            company=analysis.get("company_name", ""),
                            job_title=analysis.get("job_title", ""),
                            job_url=job_url,
                            location=analysis.get("location", ""),
                            remote=analysis.get("work_mode", ""),
                            cv_used=str(cv_path) if cv_path else "",
                            score=score,
                            status="ERROR",
                            notes="Form submission failed",
                        )
                except Exception as exc:
                    self.log(f"Error for {job_url}: {exc}")
                    log_application(
                        role="",
                        company="",
                        job_title="",
                        job_url=job_url,
                        location="",
                        remote="",
                        cv_used="",
                        score=None,
                        status="ERROR",
                        notes=str(exc),
                    )
            browser.close()
        self.set_status("Idle")

    def scan_only(self) -> None:
        with sync_playwright() as p:
            browser, context = self._launch_browser_and_context(p)
            context.new_page()
            self._ensure_autoprofile(force=True)
            browser.close()
        self.set_status("Idle")

    def _launch_browser_and_context(self, p):
        headless = bool(self.settings.get("headless", False))
        channel = str(self.settings.get("browser_channel", "chrome")).strip().lower()
        executable_path = str(self.settings.get("browser_executable_path", "")).strip()
        user_data_dir = str(self.settings.get("browser_user_data_dir", "")).strip()
        use_persistent = bool(self.settings.get("use_persistent_context", False))

        if use_persistent and user_data_dir:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=headless,
                    channel=None if executable_path else (channel if channel in {"chrome", "msedge"} else None),
                    executable_path=executable_path or None,
                )
                if executable_path:
                    self.log(f"Using browser executable: {executable_path}")
                elif channel:
                    self.log(f"Using browser channel: {channel}")
                return context.browser, context
            except Exception as exc:
                self.log(f"Persistent context failed: {exc}")

        try:
            if executable_path:
                browser = p.chromium.launch(headless=headless, executable_path=executable_path)
                self.log(f"Using browser executable: {executable_path}")
            elif channel in {"chrome", "msedge"}:
                browser = p.chromium.launch(headless=headless, channel=channel)
                self.log(f"Using browser channel: {channel}")
            else:
                browser = p.chromium.launch(headless=headless)
        except Exception as exc:
            self.log(f"Browser launch failed: {exc}")
            browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        return browser, context

    def _ensure_log_file(self) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            # reset on each run
            with self.log_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "message"])
        except Exception:
            pass

    def _ensure_autoprofile(self, force: bool = False) -> None:
        cv_root = self.settings.get("cv_root", "")
        if not cv_root:
            return
        current_hash = self._hash_cv_folder(cv_root)
        self.cv_hash = current_hash
        cached_hash = self.autoprofile.get("cv_hash", "")
        if not force and cached_hash == current_hash:
            self.log("CVs unchanged; skipping AutoProfile rebuild.")
            return
        rebuild = bool(self.settings.get("rebuild_autoprofile", True)) or force
        if rebuild or not (self.autoprofile.get("profile") or self.autoprofile.get("extra_fields")):
            self.log("Building AutoProfile from CVs with Ollama...")
            try:
                result = build_profile_with_ollama(cv_root, self.ollama, {})
            except Exception as exc:
                self.log(f"AutoProfile build failed: {exc}")
                return
            profile = result.profile_updates or {}
            extras = result.extra_fields or {}
            roles_from_paths = infer_roles_from_paths(cv_root)
            merged_roles = list(dict.fromkeys((result.roles or []) + roles_from_paths))
            self.autoprofile = {
                "profile": profile,
                "extra_fields": extras,
                "summary": result.summary,
                "roles": merged_roles,
                "search_queries": [],
            }
            try:
                from .profile_builder import collect_cv_texts

                self.autoprofile["cv_text_full"] = collect_cv_texts(cv_root, max_chars=None)
            except Exception:
                self.autoprofile["cv_text_full"] = ""
            self.autoprofile["cv_hash"] = current_hash
            save_autoprofile(self.autoprofile)
        if self.autoprofile.get("roles"):
            self.log(f"Inferred roles: {', '.join(self.autoprofile.get('roles'))}")
        if self.autoprofile.get("search_queries"):
            self.log(f"Inferred search queries: {len(self.autoprofile.get('search_queries'))}")

    def analyze_job(self, job_text: str) -> dict:
        target_role = self.settings.get("selected_role", "")
        prompt = (
            "You are analyzing a job description to decide if it is a good match. "
            "Return JSON only with keys: score (0-100), reason (short), job_title, company_name, key_skills, work_mode, location, role, role_match. "
            "work_mode must be one of: remote, hybrid, onsite, unknown. "
            "role_match must be true/false if the job matches the target role.\n\n"
            f"TARGET ROLE:\n{target_role}\n\n"
            "Be deterministic. Do not include personal data.\n\n"
            f"PROFILE SUMMARY:\n{self.profile_summary}\n\n"
            f"JOB TEXT:\n{job_text[:6000]}"
        )
        try:
            data = self.ollama.generate_json(prompt)
            return {
                "score": int(data.get("score", 0)),
                "reason": str(data.get("reason", "")),
                "job_title": str(data.get("job_title", "")),
                "company_name": str(data.get("company_name", "")),
                "key_skills": str(data.get("key_skills", "")),
                "work_mode": str(data.get("work_mode", "unknown")).lower(),
                "location": str(data.get("location", "")),
                "role": str(data.get("role", "")),
                "role_match": bool(data.get("role_match", False)),
            }
        except Exception:
            return {
                "score": 50,
                "reason": "LLM fallback",
                "job_title": "",
                "company_name": "",
                "key_skills": "",
                "work_mode": "unknown",
                "location": "",
                "role": "",
                "role_match": False,
            }

    def should_apply(self, score: int, analysis: dict) -> bool:
        threshold = int(self.settings.get("min_score_threshold", 60))
        target_role = self.settings.get("selected_role", "")
        if target_role:
            role_match = bool(analysis.get("role_match", False))
            if not role_match:
                score = max(0, score - 20)
        if score < threshold:
            return False
        work_mode = analysis.get("work_mode", "unknown")
        if work_mode == "remote" and not self.settings.get("allow_remote", True):
            return False
        if work_mode == "hybrid" and not self.settings.get("allow_hybrid", True):
            return False
        if work_mode == "onsite" and int(self.settings.get("max_distance_km", 50)) <= 0:
            return False
        return True

    def classify_question(self, question: str) -> str:
        if not question:
            return "AUTO"
        normalized = normalize_question(question)
        if normalized in self.personal_answers:
            return "PERSONAL"
        q_lower = normalized
        for keyword in PERSONAL_KEYWORDS:
            if keyword in q_lower:
                return "PERSONAL"
        profile = self.autoprofile.get("profile", {})
        for key, value in profile.items():
            if not value:
                continue
            if key.replace("_", " ") in q_lower:
                return "PROFILE"
        extra_fields = self.autoprofile.get("extra_fields", {})
        if isinstance(extra_fields, dict):
            for key in extra_fields.keys():
                if normalize_question(str(key)) in q_lower:
                    return "PROFILE"
        prompt = (
            "Classify the question into one of AUTO, PROFILE, or PERSONAL. "
            "Return JSON only with key 'category'. "
            "Rules: PERSONAL if it asks for legal, sensitive, or private data. "
            "PROFILE if it is present in the user profile. Otherwise AUTO.\n\n"
            f"QUESTION:\n{question}\n"
            f"PROFILE KEYS: {', '.join((self.autoprofile.get('profile', {}) or {}).keys())}"
        )
        try:
            data = self.ollama.generate_json(prompt)
            category = str(data.get("category", "AUTO")).upper().strip()
            if category in {"AUTO", "PROFILE", "PERSONAL"}:
                return category
        except Exception:
            pass
        return "AUTO"

    def answer_auto(self, question: str, job_text: str) -> str:
        prompt = (
            "Answer the application question professionally using only job context and general professional language. "
            "Do NOT fabricate personal, legal, or ethical data. "
            "If the question requires personal data, respond exactly with: <<NEEDS_PERSONAL>>. "
            "Return a concise answer.\n\n"
            f"QUESTION:\n{question}\n\n"
            f"PROFILE SUMMARY:\n{self.profile_summary}\n\n"
            f"JOB TEXT:\n{job_text[:6000]}"
        )
        answer = self.ollama.generate_text(prompt)
        return answer.strip()

    def answer_profile(self, question: str) -> str | None:
        q = question.lower()
        profile = self.autoprofile.get("profile", {})
        mapping = {
            "name": profile.get("name", ""),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "location": profile.get("location", ""),
            "linkedin": profile.get("linkedin", ""),
            "github": profile.get("github", ""),
            "language": profile.get("languages", ""),
            "salary": profile.get("salary_expectations", ""),
            "remote": profile.get("remote_preference", ""),
        }
        for key, value in mapping.items():
            if key in q and value:
                return str(value)
        extra_fields = self.autoprofile.get("extra_fields", {})
        if isinstance(extra_fields, dict):
            q_norm = normalize_question(question)
            for key, value in extra_fields.items():
                key_norm = normalize_question(str(key))
                if key_norm and key_norm in q_norm:
                    return str(value)
        return None

    def get_personal_answer(self, question: str) -> str | None:
        key = normalize_question(question)
        if key in self.personal_answers:
            return self.personal_answers[key]
        request = PopupRequest(question=question, kind="personal", event=threading.Event())
        self.popup_cb(request)
        request.event.wait()
        if request.answer is None:
            return None
        if request.remember:
            self.personal_answers[key] = request.answer
            save_personal_answers(self.personal_answers)
        return request.answer

    def _pause_for_captcha(self, message: str) -> bool:
        request = PopupRequest(question=message, kind="captcha", event=threading.Event())
        self.popup_cb(request)
        request.event.wait()
        return request.answer is not None

    def apply_to_job(self, page, job_text: str, cv_path: Path | None, cover_path: Path | None) -> bool:
        self.click_easy_apply(page)
        fields = extract_form_fields(page)
        if not fields:
            self.log("No form fields found.")
            return False
        for field in fields:
            question = field.label or field.name or field.placeholder
            category = self.classify_question(question)
            answer = None
            if category == "PROFILE":
                answer = self.answer_profile(question)
                if not answer:
                    category = "PERSONAL"
            if category == "PERSONAL":
                answer = self.get_personal_answer(question)
                if answer is None:
                    self.log("Personal answer not provided.")
                    return False
            if category == "AUTO":
                answer = self.answer_auto(question, job_text)
                if answer.strip() == "<<NEEDS_PERSONAL>>":
                    answer = self.get_personal_answer(question)
                    if answer is None:
                        return False
            if answer is None:
                continue
            filled = fill_field(
                page,
                field,
                answer,
                str(cv_path) if cv_path else None,
                str(cover_path) if cover_path else None,
            )
            if not filled:
                self.log(f"Could not fill field: {question}")
        missing = find_required_unfilled(page)
        if missing:
            self.log(f"Required fields missing: {', '.join(missing[:6])}")
            return False
        return submit_application(page, self.log)

    def click_easy_apply(self, page) -> None:
        selectors = [
            "button.jobs-apply-button",
            "button.jobs-apply-button--top-card",
            "button[aria-label*='Easy Apply']",
            "button[data-control-name='jobdetails_topcard_inapply']",
            "a[href*='apply']",
        ]
        for sel in selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                try:
                    btn.click()
                    page.wait_for_timeout(1200)
                    self.log(f"Clicked apply button: {sel}")
                    return
                except Exception:
                    continue

    def _get_job_text(self, page) -> str:
        selectors = [
            "section.jobs-description__container",
            "div.show-more-less-html__markup",
            "div.jobs-description__content",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    txt = el.inner_text(timeout=5000)
                    if txt and len(txt.strip()) > 50:
                        return txt
            except Exception:
                continue
        try:
            return page.inner_text("body", timeout=8000)
        except Exception:
            return ""

    def generate_cover_letter(self, job_text: str, analysis: dict) -> Path:
        template_path = TEMPLATES_DIR / "cover_letter.txt"
        template = load_text_file(template_path)
        job_title = analysis.get("job_title") or "the role"
        company_name = analysis.get("company_name") or "your company"
        key_skills = analysis.get("key_skills") or "relevant skills"
        prompt = (
            "Write a concise cover letter (under 200 words) using the template variables. "
            "Do not invent personal data. "
            "Return plain text only.\n\n"
            f"JOB TITLE: {job_title}\n"
            f"COMPANY: {company_name}\n"
            f"KEY SKILLS: {key_skills}\n"
            f"PROFILE SUMMARY:\n{self.profile_summary}\n"
            f"PROFILE NAME: {self.autoprofile.get('profile', {}).get('name','')}\n"
            f"TEMPLATE:\n{template}"
        )
        try:
            letter = self.ollama.generate_text(prompt)
        except Exception:
            letter = template.format(
                job_title=job_title,
                company_name=company_name,
                key_skills=key_skills,
                relevant_experience="relevant experience",
                name=self.autoprofile.get("profile", {}).get("name", ""),
            )
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = safe_filename(f"cover_letter_{company_name}_{job_title}.txt")
        path = OUTPUT_DIR / filename
        path.write_text(letter.strip(), encoding="utf-8")
        return path

    def search_jobs(self, page) -> list[str]:
        return self.search_jobs_linkedin(page)

    def search_jobs_linkedin(self, page) -> list[str]:
        queries = self.autoprofile.get("search_queries", [])
        if not queries:
            queries = self._generate_search_queries()
            if queries:
                self.autoprofile["search_queries"] = queries
                save_autoprofile(self.autoprofile)
            else:
                self.log("No search queries available for LinkedIn search.")
        else:
            queries = self._clean_search_queries(queries)
            if not queries:
                self.log("Saved search queries are invalid; regenerating.")
                queries = self._generate_search_queries()
                if queries:
                    self.autoprofile["search_queries"] = queries
                    save_autoprofile(self.autoprofile)
        if not queries:
            return []
        max_pages = int(self.settings.get("max_search_pages", 2))
        max_jobs = int(self.settings.get("max_jobs", 20))
        self.log("Searching LinkedIn directly with Playwright...")
        results = self._collect_linkedin_jobs(
            page=page,
            queries=queries,
            max_pages=max_pages,
            max_jobs=max_jobs,
        )
        return results

    def _generate_search_queries(self) -> list[str]:
        cv_root = self.settings.get("cv_root", "")
        if not cv_root:
            return []
        try:
            result = build_profile_with_ollama(cv_root, self.ollama, self.autoprofile.get("profile", {}))
        except Exception:
            return []
        profile = self.autoprofile.get("profile", {})
        updates = result.profile_updates
        if updates:
            profile.update(updates)
        extras = result.extra_fields if isinstance(result.extra_fields, dict) else {}
        if extras:
            existing = self.autoprofile.get("extra_fields", {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update(extras)
            self.autoprofile["extra_fields"] = existing
        if updates:
            self.autoprofile["profile"] = profile
        if result.summary:
            self.profile_summary = result.summary
            self.autoprofile["summary"] = result.summary
        if result.roles:
            self.autoprofile["roles"] = result.roles
        save_autoprofile(self.autoprofile)
        target_role = self.settings.get("selected_role", "")
        if target_role:
            location = self._preferred_location()
            queries = self._clean_search_queries(self._role_queries(target_role, location))
        else:
            queries = self._clean_search_queries(result.search_queries)
        if not queries:
            self.log("Ollama did not return search queries. Trying focused query generation...")
            queries = self._generate_search_queries_focused()
        if not queries and result.roles:
            built = []
            location = self._preferred_location()
            for role in result.roles:
                built.append(self._build_query(role, location))
            queries = self._clean_search_queries(built)
        if not queries:
            fallback = self._fallback_search_queries()
            if fallback:
                return fallback
        return queries

    def _generate_search_queries_focused(self) -> list[str]:
        cv_text = self.autoprofile.get("cv_text_full", "")
        if not cv_text:
            return []
        prompt = (
            "From the CV text, infer 3-6 job roles and 3-6 Google search queries. "
            "Return JSON only with keys: roles, search_queries. "
            "search_queries must ONLY include role titles and (optional) location, no domains, no URLs, no random words. "
            "Example: 'backend python developer jobs Madrid', 'data engineer jobs remote'. "
            "Do not invent personal data.\n\n"
            f"CV TEXT:\n{cv_text[:8000]}"
        )
        try:
            data = self.ollama.generate_json(prompt)
        except Exception as exc:
            self.log(f"Focused query generation failed: {exc}")
            return []
        roles = data.get("roles", []) if isinstance(data.get("roles"), list) else []
        queries = data.get("search_queries", []) if isinstance(data.get("search_queries"), list) else []
        roles = [str(r).strip() for r in roles if str(r).strip()]
        queries = [str(q).strip() for q in queries if str(q).strip()]
        if roles:
            self.autoprofile["roles"] = roles
        # Prefer building queries from roles + preferred location to avoid noisy outputs.
        built = []
        location = self._preferred_location()
        for role in roles:
            built.append(self._build_query(role, location))
        queries = built or queries
        self.autoprofile["search_queries"] = queries
        save_autoprofile(self.autoprofile)
        return self._clean_search_queries(queries)

    def _fallback_search_queries(self) -> list[str]:
        skills = []
        if self.profile_summary:
            for token in self.profile_summary.replace("Skills:", "").split(","):
                t = token.strip()
                if t:
                    skills.append(t)
        roles = self.autoprofile.get("roles", [])
        role = roles[0] if roles else ""
        location = self._preferred_location()
        return self._build_queries_from_inputs(role, location, skills)

    def _preferred_location(self) -> str:
        locations = self.settings.get("preferred_locations", [])
        if isinstance(locations, list) and locations:
            return str(locations[0])
        return self.autoprofile.get("profile", {}).get("location", "")

    def _build_query(self, role: str, location: str) -> str:
        prefer_remote = bool(self.settings.get("prefer_remote", True))
        role = role.strip()
        if prefer_remote and location:
            return f"{role} jobs remote or {location}".strip()
        if prefer_remote:
            return f"{role} jobs remote".strip()
        if location:
            return f"{role} jobs {location}".strip()
        return f"{role} jobs".strip()

    def _role_queries(self, role: str, location: str) -> list[str]:
        role_l = role.lower()
        base = [role]
        if "cyber" in role_l:
            base += [
                "Cybersecurity analyst",
                "SOC analyst",
                "Penetration tester",
                "Analista de ciberseguridad",
                "Analista SOC",
                "Pentester",
            ]
        if "data" in role_l:
            base += ["Data analyst", "Data engineer", "Analista de datos", "Ingeniero de datos"]
        if "devops" in role_l:
            base += ["DevOps engineer", "Site reliability engineer", "Ingeniero DevOps", "SRE"]
        if "football" in role_l or "futbol" in role_l:
            base += ["Football scout", "Football analyst", "Ojeador de fútbol", "Analista de fútbol"]
        queries = []
        for term in base:
            queries.append(self._build_query(term, location))
        return list(dict.fromkeys(queries))

    def _collect_linkedin_jobs(self, page, queries: list[str], max_pages: int, max_jobs: int) -> list[str]:
        results: list[str] = []
        seen = set()
        location = self.settings.get("linkedin_location", "")
        remote_only = bool(self.settings.get("linkedin_remote_only", False))
        wt = "&f_WT=2" if remote_only else ""
        for query in queries:
            if len(results) >= max_jobs:
                break
            loc_param = f"&location={location.replace(' ', '%20')}" if location else ""
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={query.replace(' ', '%20')}{loc_param}{wt}"
            if not self._navigate_and_wait(page, search_url):
                continue
            if is_login_or_captcha(page):
                self.log("LinkedIn login required. Waiting for manual interaction...")
                if not self._pause_for_captcha("Inicia sesión en LinkedIn y pulsa Continuar."):
                    break
                if not self._navigate_and_wait(page, search_url):
                    continue
            for page_idx in range(max_pages):
                try:
                    links = page.query_selector_all("a.job-card-list__title, a.base-card__full-link")
                except Exception as exc:
                    self.log(f"LinkedIn select error: {exc}")
                    break
                for link in links:
                    href = link.get_attribute("href") or ""
                    if not href or not href.startswith("http"):
                        continue
                    if href in seen:
                        continue
                    seen.add(href)
                    results.append(href)
                    if len(results) >= max_jobs:
                        break
                if len(results) >= max_jobs:
                    break
                # Try to scroll a bit to load more cards quickly
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
                # Navigate next page if available
                next_btn = page.query_selector("button[aria-label='Next'], button[aria-label='Siguiente']")
                if next_btn and next_btn.is_visible():
                    try:
                        next_btn.click()
                        page.wait_for_load_state("domcontentloaded", timeout=15000)
                        continue
                    except Exception:
                        break
                break
        return results

    def _navigate_and_wait(self, page, url: str) -> bool:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=15000)
            return True
        except Exception as exc:
            self.log(f"Navigation failed: {exc}")
            return False

    def _build_queries_from_inputs(self, role: str, location: str, skills: list[str] | None = None) -> list[str]:
        role = role.strip()
        location = location.strip()
        skills = skills or []
        base_terms = []
        if role:
            base_terms.append(role)
        if skills:
            base_terms.append(" ".join(skills[:5]))
        if not base_terms:
            return []
        queries = []
        for term in base_terms:
            queries.append(self._build_query(term, location))
        return self._clean_search_queries(queries)[:6]

    def _clean_search_queries(self, queries: list[str]) -> list[str]:
        cleaned = []
        for q in queries:
            text = " ".join(q.replace("http", "").split())
            if any(token in text for token in [".com", ".es", ".net", ".org", "www."]):
                continue
            letters = sum(ch.isalpha() for ch in text)
            if letters < 8:
                continue
            cleaned.append(text)
        return cleaned

    def _hash_cv_folder(self, root: str) -> str:
        paths = list(Path(root).rglob("*.pdf"))
        return hash_files(paths)
