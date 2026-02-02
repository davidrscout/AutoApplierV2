import asyncio
import re
from typing import Any, Dict

from playwright.async_api import Page

from .llm_client import LLMClient


class SemanticFormFiller:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def fill_page(self, page: Page, user_data: dict) -> None:
        max_steps = 15
        step = 0

        while step < max_steps:
            print(f"[FILLER] Paso {step + 1}: Analizando formulario...")
            await asyncio.sleep(2)

            modal = await page.query_selector(".jobs-easy-apply-modal")
            if not modal:
                print("[FILLER] No modal. Puede que hayamos terminado.")
                break

            await self._fill_visible_inputs(page, modal, user_data)

            if await self._handle_buttons(modal):
                print("[FILLER] Proceso finalizado con exito.")
                return

            step += 1

        print("[FILLER] Limite de pasos alcanzado.")

    async def _handle_buttons(self, modal) -> bool:
        submit_btn = await modal.query_selector(
            "button[aria-label*='Submit'], button[aria-label*='Enviar solicitud']"
        )
        if submit_btn and await submit_btn.is_visible():
            print("[FILLER] Click en ENVIAR SOLICITUD.")
            await submit_btn.click()
            await asyncio.sleep(3)
            return True

        review_btn = await modal.query_selector(
            "button[aria-label*='Review'], button[aria-label*='Revisar']"
        )
        if review_btn and await review_btn.is_visible():
            print("[FILLER] Click en REVISAR.")
            await review_btn.click()
            return False

        next_btn = await modal.query_selector(
            "button[aria-label*='Next'], button[aria-label*='Siguiente']"
        )
        if next_btn and await next_btn.is_visible():
            print("[FILLER] Click en SIGUIENTE.")
            await next_btn.click()
            return False

        return True

    async def _fill_visible_inputs(self, page: Page, container: Any, user_data: dict) -> None:
        elements = await container.query_selector_all(
            "input, textarea, select, fieldset div[role='radio']"
        )

        if not elements:
            return

        simplified = []
        element_handles = []

        for el in elements:
            if not await el.is_visible():
                continue

            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            input_type = (await el.get_attribute("type") or "").lower()

            if input_type in ["hidden", "submit", "button", "image"]:
                continue

            label_text = await el.evaluate(
                """(el) => {
                let label = null;
                if (el.id) label = document.querySelector(`label[for=\"${el.id}\"]`);
                if (!label) label = el.closest('label');
                if (!label && el.closest('fieldset')) label = el.closest('fieldset').querySelector('legend');
                return label ? label.innerText : '';
            }"""
            )

            label_text = (label_text or "").replace("\n", " ").strip()
            name = await el.get_attribute("name") or ""
            ident = await el.get_attribute("id") or name or f"elem_{len(simplified)}"

            options_text = ""
            if tag == "select":
                options_text = await self._get_optimized_options(el)

            simplified.append(
                {
                    "tag": tag,
                    "type": input_type,
                    "ident": ident,
                    "label": label_text,
                    "options": options_text,
                }
            )
            element_handles.append((el, ident, tag, input_type))

        if not simplified:
            return

        html_snippet = "\n".join([str(s) for s in simplified])
        print("[FILLER] Consultando a Ollama...")
        mapping = self.llm.analyze_html(html_snippet, user_data)

        if not mapping:
            return

        for el, ident, tag, input_type in element_handles:
            if ident not in mapping:
                continue

            value = str(mapping[ident])
            if not value or value.lower() == "none":
                continue

            print(f"   -> Intentando rellenar {ident} ({tag}) con '{value}'")

            try:
                if input_type == "radio":
                    await el.evaluate("el => el.click()")
                    continue

                if input_type == "checkbox":
                    should_check = value.lower() in ["true", "yes", "si", "1"]
                    if should_check != await el.is_checked():
                        await el.click(force=True)
                    continue

                if tag == "select":
                    try:
                        await el.select_option(label=value)
                    except Exception:
                        opts = await el.query_selector_all("option")
                        for o in opts:
                            txt = await o.inner_text()
                            if value.lower() in txt.lower():
                                await el.select_option(value=await o.get_attribute("value"))
                                break
                    continue

                if input_type == "file":
                    if user_data.get("cv_path"):
                        await el.set_input_files(user_data.get("cv_path"))
                    continue

                await el.fill(value)

            except Exception as e:
                print(f"   -> Error menor rellenando campo: {e}")

    async def _get_optimized_options(self, el) -> str:
        return await el.evaluate(
            """el => {
            const opts = Array.from(el.options);
            if (opts.length > 20) {
                return opts.slice(0, 10).map(o => o.text).join('|') + '|... (Choose closest match)';
            }
            return opts.map(o => o.text).join('|');
        }"""
        )
