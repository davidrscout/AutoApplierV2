from pathlib import Path

from .utils import DATA_DIR, read_json, write_json


AUTOPROFILE_PATH = DATA_DIR / "autoprofile.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
PERSONAL_ANSWERS_PATH = DATA_DIR / "personal_answers.json"


def load_autoprofile() -> dict:
    return read_json(
        AUTOPROFILE_PATH,
        {
            "profile": {},
            "extra_fields": {},
            "summary": "",
            "roles": [],
            "search_queries": [],
            "cv_text_full": "",
        },
    )


def save_autoprofile(profile: dict) -> None:
    write_json(AUTOPROFILE_PATH, profile)


def load_settings() -> dict:
    return read_json(
        SETTINGS_PATH,
        {
            "daily_limit": 10,
            "min_score_threshold": 60,
            "max_distance_km": 50,
            "allow_remote": True,
            "allow_hybrid": True,
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3.1",
            "headless": False,
            "cv_root": "",
            "max_search_pages": 2,
            "max_jobs": 20,
            "browser_channel": "chrome",
            "rebuild_autoprofile": True,
            "preferred_locations": ["Murcia"],
            "prefer_remote": True,
            "selected_role": "",
            "browser_executable_path": "",
            "browser_user_data_dir": "",
            "use_persistent_context": False,
            "linkedin_location": "Murcia, Region of Murcia, Spain",
            "linkedin_remote_only": True,
        },
    )


def save_settings(settings: dict) -> None:
    write_json(SETTINGS_PATH, settings)


def load_personal_answers() -> dict:
    return read_json(PERSONAL_ANSWERS_PATH, {})


def save_personal_answers(answers: dict) -> None:
    write_json(PERSONAL_ANSWERS_PATH, answers)
