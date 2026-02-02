import asyncio
import threading
import time
import traceback

from playwright.async_api import Page

from .browser import BrowserManager
from .semantic_filler import SemanticFormFiller
from .llm_client import LLMClient
from .tracker import JobTracker
from scrapers.linkedin import LinkedInScraper


class AutomationEngine(threading.Thread):
    def __init__(self, ui_log_queue, user_data: dict) -> None:
        super().__init__(daemon=True)
        self.ui_log_queue = ui_log_queue
        self.user_data = user_data
        self.paused = False
        self._stop_requested = False

    def log(self, message: str) -> None:
        print(f"[DEBUG TERMINAL] {message}")
        try:
            self.ui_log_queue.put(message)
        except Exception:
            pass

    def pause(self) -> None:
        self.paused = True
        self.log("[ENGINE] Paused")

    def resume(self) -> None:
        self.paused = False
        self.log("[ENGINE] Resumed")

    def stop(self) -> None:
        self._stop_requested = True
        self.log("[ENGINE] Stop requested")

    def run(self) -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_async())
            loop.close()
        except Exception:
            traceback.print_exc()

    async def _run_async(self) -> None:
        try:
            self.log("[ENGINE] Iniciando componentes...")
            scraper = LinkedInScraper()
            browser = await BrowserManager.get_instance()
            llm_client = LLMClient()
            filler = SemanticFormFiller(llm=llm_client)
            tracker = JobTracker()

            self.log("[ENGINE] Lanzando navegador...")
            page = await browser.launch_browser(
                user_data_dir=self.user_data.get("user_data_dir", "./config/browser_profile"),
                headless=False,
                executable_path=self.user_data.get("browser_path"),
                channel=self.user_data.get("browser_channel"),
            )

            raw_keywords = self.user_data.get("keywords", "")
            cv_context = self.user_data.get("cv_context", "")

            # --- GENERACIÓN DE KEYWORDS ---
            # FORZAMOS MODO MANUAL HOY PARA EVITAR ERROR 429
            if not raw_keywords or raw_keywords.upper() == "AUTO":
                keyword_list = [
                    "Football Scout, Performance Analyst, Data Scout, Sports Analyst Python Developer, Backend Developer, AI Engineer, Full Stack Developer, Cloud Engineer, Google Cloud Platform, API Developer, Software Engineer Junior Cybersecurity Analyst, Junior Pentester, SOC Analyst, Offensive Security, Red Team, Ethical Hacker, Vulnerability Researcher, Security Consultant, Incident Response, Threat Hunting"
                ]
                self.log(f"Usando lista manual de emergencia: {keyword_list}")
            else:
                keyword_list = [k.strip() for k in raw_keywords.split(",") if k.strip()]

            if not keyword_list:
                self.log("ERROR: No hay keywords definidas.")
                return

            location = self.user_data.get("location", "Spain")

            for current_keyword in keyword_list:
                if self._stop_requested:
                    break
                self.log(f"--- NUEVA BUSQUEDA: {current_keyword} ---")

                try:
                    jobs = await scraper.scrape_jobs(page, current_keyword, location)
                    self.log(f"Ofertas para '{current_keyword}': {len(jobs)}")

                    for job in jobs:
                        if self._stop_requested:
                            break
                        while self.paused:
                            time.sleep(1)

                        try:
                            self.log(f"Procesando: {job.get('title')}")
                            await page.goto(job.get("url"), wait_until="domcontentloaded")
                            await asyncio.sleep(3)

                            desc_el = await page.query_selector(
                                "#job-details, .jobs-description__content, article"
                            )
                            if desc_el:
                                text = await desc_el.inner_text()
                                if not llm_client.evaluate_match_bool(text, cv_context):
                                    self.log("SKIPPED: Perfil no encaja.")
                                    tracker.track_job(job, "SKIPPED", "No Match")
                                    continue

                            apply_btn = await page.query_selector(".jobs-apply-button--top-card button")
                            if not apply_btn:
                                apply_btn = await page.query_selector(".jobs-apply-button")

                            if apply_btn:
                                await apply_btn.scroll_into_view_if_needed()
                                await apply_btn.click(force=True)
                                await asyncio.sleep(2)

                                if "linkedin.com/jobs/view" not in page.url:
                                    self.log("EXTERNO: Web externa.")
                                    tracker.track_job(job, "EXTERNO", "Web externa")
                                    await page.go_back()
                                    continue

                                modal = await page.query_selector(".jobs-easy-apply-modal")
                                if modal:
                                    self.log("Rellenando formulario...")
                                    await filler.fill_page(page, self.user_data)
                                    tracker.track_job(job, "APLICADO")
                                else:
                                    tracker.track_job(job, "FALLIDO", "No modal")
                            else:
                                tracker.track_job(job, "SALTADO", "No button")

                        except Exception as e:
                            self.log(f"Error oferta: {e}")
                            tracker.track_job(job, "ERROR", str(e))

                except Exception as e:
                    self.log(f"Error busqueda: {e}")

            self.log("[ENGINE] Finalizado.")
        except Exception:
            traceback.print_exc()
        finally:
            try:
                await browser.close()
            except Exception:
                pass
