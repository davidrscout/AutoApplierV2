from __future__ import annotations

from urllib.parse import quote_plus

from playwright.sync_api import Page


def collect_job_urls_duckduckgo(
    page: Page,
    queries: list[str],
    max_pages: int,
    max_jobs: int,
    log_cb,
    pause_cb=None,
) -> list[str]:
    results: list[str] = []
    seen = set()
    for query in queries:
        if len(results) >= max_jobs:
            break
        log_cb(f"DuckDuckGo query: {query}")
        for page_idx in range(max_pages):
            if len(results) >= max_jobs:
                break
            start = page_idx * 50
            # Use the HTML-only endpoint to avoid JS blocks.
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={start}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                log_cb(f"DuckDuckGo search error: {exc}")
                break
            if _is_ddg_captcha(page):
                log_cb("DuckDuckGo CAPTCHA detected. Waiting for manual solve...")
                if pause_cb:
                    pause_cb("Resuelve el CAPTCHA en Chrome y pulsa Continuar.")
                if _is_ddg_captcha(page):
                    log_cb("CAPTCHA still present; skipping this query page.")
                    continue
            links = page.query_selector_all("a.result__a, a[data-testid='result-title-a']")
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
        log_cb(f"DuckDuckGo results so far: {len(results)}")
    return results


def collect_job_urls_bing(
    page: Page,
    queries: list[str],
    max_pages: int,
    max_jobs: int,
    log_cb,
    pause_cb=None,
    site_filter: str | None = None,
) -> list[str]:
    results: list[str] = []
    seen = set()
    for query in queries:
        if len(results) >= max_jobs:
            break
        q = f"site:{site_filter} {query}" if site_filter else query
        log_cb(f"Bing query: {q}")
        for page_idx in range(max_pages):
            if len(results) >= max_jobs:
                break
            first = page_idx * 10 + 1
            url = f"https://www.bing.com/search?q={quote_plus(q)}&first={first}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                log_cb(f"Bing search error: {exc}")
                break
            if _is_ddg_captcha(page):
                log_cb("Bing CAPTCHA detected. Waiting for manual solve...")
                if pause_cb:
                    pause_cb("Resuelve el CAPTCHA en el navegador y pulsa Continuar.")
                if _is_ddg_captcha(page):
                    log_cb("CAPTCHA still present; skipping this query page.")
                    continue
            links = page.query_selector_all("li.b_algo h2 a")
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
        log_cb(f"Bing results so far: {len(results)}")
    return results


def _is_ddg_captcha(page: Page) -> bool:
    try:
        url = page.url.lower()
        if "captcha" in url:
            return True
        if page.query_selector("input[name='captcha']"):
            return True
        if page.query_selector("iframe[src*='recaptcha']"):
            return True
        body_text = page.inner_text("body").lower()
        if "captcha" in body_text or "unusual traffic" in body_text:
            return True
    except Exception:
        return False
    return False


def is_login_or_captcha(page: Page) -> bool:
    try:
        url = page.url.lower()
        if "login" in url or "signin" in url:
            return True
        if "linkedin.com/login" in url or "linkedin.com/uas/login" in url:
            return True
        if "linkedin.com/checkpoint" in url or "linkedin.com/authwall" in url:
            return True
        if _is_ddg_captcha(page):
            return True
        body_text = page.inner_text("body").lower()
        if "sign in" in body_text or "log in" in body_text:
            return True
        if "inicia sesión" in body_text or "iniciar sesión" in body_text:
            return True
        if "registrarte" in body_text or "crear cuenta" in body_text:
            if "linkedin" in url:
                return True
        if "captcha" in body_text:
            return True
        # LinkedIn login form fields
        if page.query_selector("input[name='session_key']") or page.query_selector("input[name='session_password']"):
            return True
    except Exception:
        return False
    return False
