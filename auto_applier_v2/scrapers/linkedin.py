from __future__ import annotations

import asyncio
import random
from urllib.parse import quote_plus

from playwright.async_api import Page


class LinkedInScraper:
    async def scrape_jobs(self, page: Page, keywords: str, location: str) -> list[dict]:
        kw = quote_plus(keywords or "")
        loc = quote_plus(location or "")

        url = f"https://www.linkedin.com/jobs/search?keywords={kw}&location={loc}"

        print(f"[SCRAPER] Navegando a: {url}")
        await page.goto(url, wait_until="domcontentloaded")

        await asyncio.sleep(random.uniform(3, 5))

        await page.mouse.wheel(0, 1000)
        await asyncio.sleep(1)

        print("[SCRAPER] Buscando tarjetas de trabajo...")

        possible_cards = await page.query_selector_all(
            "li, div.job-card-container, div.base-card, div.job-search-card"
        )

        results: list[dict] = []
        seen_urls = set()

        print(f"[SCRAPER] Analizando {len(possible_cards)} elementos...")

        for card in possible_cards:
            try:
                link_el = await card.query_selector("a[href*='/jobs/view/'], a[href*='currentJobId']")

                if not link_el:
                    continue

                raw_url = await link_el.get_attribute("href")
                if not raw_url:
                    continue

                job_url = raw_url.split("?")[0]
                if not job_url.startswith("http"):
                    job_url = f"https://www.linkedin.com{job_url}"

                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = "Unknown Title"
                title_el = await card.query_selector(
                    "strong, h3, .job-card-list__title, .base-search-card__title"
                )
                if title_el:
                    title = (await title_el.inner_text()).strip()

                company = "Unknown Company"
                company_el = await card.query_selector(
                    ".job-card-container__company-name, h4, .base-search-card__subtitle"
                )
                if company_el:
                    company = (await company_el.inner_text()).strip()

                text_content = (await card.inner_text()).lower()
                is_easy_apply = (
                    "easy apply" in text_content
                    or "sencilla" in text_content
                    or "facilmente" in text_content
                )

                print(f"   -> [ENCONTRADO] {title}")
                results.append(
                    {
                        "title": title,
                        "company": company,
                        "url": job_url,
                        "easy_apply": is_easy_apply,
                    }
                )

            except Exception:
                continue

        print(f"[SCRAPER] Total ofertas encontradas: {len(results)}")
        return results

    async def _lazy_scroll(self, page: Page) -> None:
        pass
