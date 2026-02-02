# AutoApplier V2 🚀

**Autonomous Job Application Agent** powered by Playwright and LLM integration.

AutoApplier V2 automates the tedious process of finding and applying for jobs on platforms like LinkedIn. It uses an LLM (Large Language Model) to intelligently parse job descriptions, match them against your CV, generate cover letters, and fill out application forms autonomously.

## ⚠️ DISCLAIMER & WARNING

**This software is for EDUCATIONAL PURPOSES ONLY.**

Automated scraping and botting may violate the Terms of Service (ToS) of platforms like LinkedIn. Using this tool may result in:
-   Temporary or permanent account suspension.
-   IP bans.
-   Legal action in some jurisdictions.

**Use at your own risk.** The authors are not responsible for any consequences resulting from the use of this tool. We strongly recommend **not** using your primary professional account for testing.

---

## ✨ Features

-   **Autonomous Job Search:** Scrapes job listings based on your profile and preferences.
-   **Smart Matching:** Uses LLM to evaluate if a job matches your skills before applying.
-   **Intelligent Form Filling:** Answers application questions contextually based on your CV/Bio data.
-   **Cover Letter Generation:** Generates tailored cover letters on the fly.
-   **OpenClaw Gateway Support:** Connects to a remote OpenClaw gateway for secure, keyless LLM access.
-   **Stealth Mode:** Uses local browser profiles to mimic human behavior.

## 🛠️ Setup

### Prerequisites

-   Python 3.11+
-   Chrome / Chromium browser

### 1. Environment Setup (Recommended)

We strongly recommend using a virtual environment (`venv`) or `uv` to keep dependencies isolated.

#### Option A: Using `venv` (Standard)

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\Activate

# Activate (Mac/Linux)
source venv/bin/activate
```

#### Option B: Using `uv` (Faster)

```bash
# Install uv
pip install uv

# Create and sync venv
uv venv
uv pip sync requirements.txt
```

### 2. Install Dependencies

Once your environment is active:

```bash
pip install -r requirements.txt
python -m playwright install
```

### 3. Prepare your CVs

-   Place your PDF resumes in the `cv/` folder.
-   The bot will read these to understand your profile.

## ⚙️ Configuration

### LLM Gateway (OpenClaw)

This tool is designed to work with an OpenClaw Gateway to avoid exposing API keys locally. Set these environment variables:

```powershell
# Windows PowerShell
$env:OPENCLAW_GATEWAY_TOKEN="your_token_here"
$env:CLAW_URL="http://127.0.0.1:18789/v1/chat/completions"
$env:CLAW_MODEL="openclaw"
$env:CLAW_TIMEOUT_SECONDS="60"
```

### Local Config

-   **`config/keywords.txt`**: Add search keywords (one per line).
-   **`auto_applier_v2/data/settings.json`**: Application stores preferences here.

## 🚀 Usage

**Important:** Run the application from the repository root directory.

```bash
python auto_applier_v2/main.py
```

---
*Created by [DavidRScout](https://github.com/davidrscout)*
