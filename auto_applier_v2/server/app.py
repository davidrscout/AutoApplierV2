import json
import logging
import os
import time
from typing import Any, Dict

import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from openai import OpenAI
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

APP_NAME = "AutoApplier LLM API"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-session-secret-change")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-secret-change")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
RATE_LIMIT_PER_MIN = int(os.getenv("LLM_RATE_LIMIT_PER_MIN", "60"))
LOG_PATH = os.getenv("LLM_API_LOG_PATH", os.path.join(os.getcwd(), "logs", "llm_api.log"))

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

oauth = OAuth()
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

openai_client = OpenAI()

_rate_state: Dict[str, list[float]] = {}


class LLMRequest(BaseModel):
    task: str
    payload: Dict[str, Any]


def _issue_token(user: Dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "sub": user.get("sub") or user.get("id") or user.get("email"),
        "email": user.get("email"),
        "name": user.get("name"),
        "iat": now,
        "exp": now + 60 * 60 * 24 * 7,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _get_user_from_token(auth_header: str) -> Dict[str, Any]:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _enforce_rate_limit(user_id: str) -> None:
    now = time.time()
    window = 60
    bucket = _rate_state.setdefault(user_id, [])
    bucket[:] = [ts for ts in bucket if now - ts < window]
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)


def _extract_json(text: str) -> Dict[str, Any]:
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
    return {}


def _call_openai(prompt: str, json_mode: bool = False) -> str:
    kwargs: Dict[str, Any] = {"model": OPENAI_MODEL, "input": prompt}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = openai_client.responses.create(**kwargs)
    output_text = getattr(response, "output_text", "") or ""
    return output_text


@app.get("/auth/login")
async def auth_login(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    if not user:
        user = await oauth.google.parse_id_token(request, token)
    if not user:
        raise HTTPException(status_code=400, detail="Unable to fetch user profile")

    jwt_token = _issue_token(user)
    html = f"""
    <html>
      <head><title>AutoApplier OAuth</title></head>
      <body style="font-family: sans-serif; padding: 24px;">
        <h2>Login correcto ✅</h2>
        <p>Copia este token y pégalo en la app (campo Auth Token):</p>
        <textarea rows="6" style="width: 100%;">{jwt_token}</textarea>
        <p>Usuario: {user.get('email')}</p>
      </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/auth/me")
def auth_me(request: Request):
    user = _get_user_from_token(request.headers.get("Authorization", ""))
    return {"user": user}


@app.post("/api/llm")
def llm_api(req: LLMRequest, request: Request):
    user = _get_user_from_token(request.headers.get("Authorization", ""))
    user_id = str(user.get("sub"))
    _enforce_rate_limit(user_id)

    start = time.time()
    task = req.task
    payload = req.payload or {}

    if task == "analyze_html":
        html_snippet = str(payload.get("html_snippet", ""))
        user_data = payload.get("user_data", {})
        prompt = (
            "You are an expert form-filling AI agent. "
            "Your goal is to map the User Profile Data to the HTML Form Fields provided.\n"
            "INSTRUCTIONS:\n"
            "1. Output MUST be strictly valid JSON: {\"field_id_or_name\": \"value\"}.\n"
            "2. For <select> fields: You MUST pick one of the options listed in the HTML. "
            "Pick the closest semantic match (e.g., if User is 'Spain' and options are 'ES', 'Espana', select that).\n"
            "3. For Phone Code: If the select has country codes (e.g., 'Spain (+34)'), match the user's country.\n"
            "4. For Experience/Years: Calculate from the CV data if possible, otherwise use a sensible default based on seniority.\n"
            "5. NO Markdown, NO explanation text. Just the raw JSON string.\n\n"
            f"--- USER PROFILE ---\n{json.dumps(user_data, ensure_ascii=False)}\n\n"
            f"--- HTML FORM FIELDS ---\n{html_snippet}\n"
        )
        text = _call_openai(prompt, json_mode=True)
        result = _extract_json(text)
    elif task == "evaluate_match_bool":
        job_description = str(payload.get("job_description", ""))
        cv_text = str(payload.get("cv_text", ""))
        if not cv_text:
            result = True
        else:
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
            text = _call_openai(prompt)
            result = "YES" in text.strip().upper()
    elif task == "generate_keywords":
        cv_text = str(payload.get("cv_text", ""))
        prompt = (
            "Analyze this CV and extract the 5 BEST job search keywords for LinkedIn.\n"
            "Focus on job titles (e.g. 'Pentester') and high-value skills (e.g. 'DevSecOps').\n"
            "Format: Comma separated list. Example: Python, Django, React\n\n"
            f"CV TEXT: {cv_text[:4000]}"
        )
        text = _call_openai(prompt)
        result = [k.strip() for k in text.split(",") if k.strip()][:5]
    else:
        raise HTTPException(status_code=400, detail="Unknown task")

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info("user_id=%s task=%s duration_ms=%s", user_id, task, elapsed_ms)
    return JSONResponse({"result": result, "duration_ms": elapsed_ms})
