import json
from typing import Any, Dict, List

from llm.claw_gateway import claw_chat
from llm.errors import LLMParseError


class LLMClient:
    def __init__(self) -> None:
        pass

    def analyze_html(self, html_snippet: str, user_data: dict) -> dict:
        system = (
            "You are an expert form-filling AI agent. "
            "Your goal is to map the User Profile Data to the HTML Form Fields provided.\n"
            "INSTRUCTIONS:\n"
            "1. Output MUST be strictly valid JSON: {\"field_id_or_name\": \"value\"}.\n"
            "2. For <select> fields: You MUST pick one of the options listed in the HTML. "
            "Pick the closest semantic match (e.g., if User is 'Spain' and options are 'ES', 'Espana', select that).\n"
            "3. For Phone Code: If the select has country codes (e.g., 'Spain (+34)'), match the user's country.\n"
            "4. For Experience/Years: Calculate from the CV data if possible, otherwise use a sensible default based on seniority.\n"
            "5. NO Markdown, NO explanation text. Just the raw JSON string.\n"
        )
        prompt = (
            f"--- USER PROFILE ---\n{json.dumps(user_data, ensure_ascii=False)}\n\n"
            f"--- HTML FORM FIELDS ---\n{html_snippet}\n"
        )
        text = claw_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        result = self._extract_json(text)
        if result is None:
            raise LLMParseError("LLM did not return valid JSON for analyze_html")
        return result

    def evaluate_match_bool(self, job_description: str, cv_text: str) -> bool:
        if not cv_text:
            return True
        prompt = (
            "Role: Expert Tech Recruiter.\n"
            "Task: Evaluate if the Candidate is a RELEVANT match for the Job Description.\n"
            "Criteria:\n"
            "- If the job requires specific hard skills (e.g. Java) and CV only has Python -> NO.\n"
            "- If the roles are related (e.g. Job: 'SOC Analyst', CV: 'Cybersecurity Junior') -> YES.\n"
            "- Ignore 'years of experience' requirements if the skills are strong.\n"
            "- Be lenient with 'Junior' or 'Trainee' roles.\n"
            "Output: Reply ONLY with the word 'YES' or 'NO'.\n\n"
            f"--- JOB DESCRIPTION ---\n{job_description[:6000]}\n\n"
            f"--- CANDIDATE CV ---\n{cv_text[:6000]}\n"
        )
        text = claw_chat(
            [
                {"role": "system", "content": ""},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return "YES" in text.strip().upper()

    def generate_keywords(self, cv_text: str) -> List[str]:
        prompt = (
            "Analyze this CV and extract the 5 BEST job search keywords for LinkedIn.\n"
            "Focus on job titles (e.g. 'Pentester') and high-value skills (e.g. 'DevSecOps').\n"
            "Format: Comma separated list. Example: Python, Django, React\n\n"
            f"CV TEXT: {cv_text[:4000]}"
        )
        text = claw_chat(
            [
                {"role": "system", "content": ""},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return [k.strip() for k in text.split(",") if k.strip()][:5]

    def _extract_json(self, text: str) -> Dict[str, Any] | None:
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            pass
        return None
