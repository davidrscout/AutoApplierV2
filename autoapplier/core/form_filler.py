from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class FormField:
    element: Any
    tag: str
    input_type: str
    label: str
    name: str
    placeholder: str
    options: list[str]


def _label_for_element(page: Page, element: Any) -> str:
    label_text = ""
    element_id = element.get_attribute("id") or ""
    if element_id:
        label = page.query_selector(f'label[for="{element_id}"]')
        if label:
            label_text = label.inner_text().strip()
    if not label_text:
        label_text = (
            element.evaluate(
                """(el) => {
                    const parent = el.closest('label');
                    return parent ? parent.innerText : '';
                }"""
            )
            or ""
        ).strip()
    return label_text


def extract_form_fields(page: Page) -> list[FormField]:
    fields: list[FormField] = []
    elements = page.query_selector_all("input, textarea, select")
    for element in elements:
        if not element.is_visible():
            continue
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        input_type = (element.get_attribute("type") or "").lower()
        if input_type in {"hidden", "submit", "button", "reset"}:
            continue
        name = (element.get_attribute("name") or "").strip()
        placeholder = (element.get_attribute("placeholder") or "").strip()
        aria = (element.get_attribute("aria-label") or "").strip()
        label_text = _label_for_element(page, element)
        label = label_text or aria or placeholder or name or input_type or tag
        options = []
        if tag == "select":
            option_elements = element.query_selector_all("option")
            options = [(opt.inner_text() or "").strip() for opt in option_elements]
        fields.append(
            FormField(
                element=element,
                tag=tag,
                input_type=input_type,
                label=label.strip(),
                name=name,
                placeholder=placeholder,
                options=options,
            )
        )
    return fields


def _match_option(options: list[str], answer: str) -> str | None:
    answer_l = answer.lower()
    for opt in options:
        if opt and answer_l == opt.lower():
            return opt
    for opt in options:
        if opt and answer_l in opt.lower():
            return opt
    return None


def fill_field(
    page: Page,
    field: FormField,
    answer: str,
    cv_path: str | None,
    cover_letter_path: str | None,
) -> bool:
    if field.tag == "input":
        if field.input_type == "file":
            if "cover" in field.label.lower():
                if cover_letter_path:
                    field.element.set_input_files(cover_letter_path)
                    return True
                return False
            if "cv" in field.label.lower() or "resume" in field.label.lower():
                if cv_path:
                    field.element.set_input_files(cv_path)
                    return True
                return False
            if cv_path:
                field.element.set_input_files(cv_path)
                return True
            return False
        if field.input_type in {"checkbox", "radio"}:
            answer_l = answer.strip().lower()
            should_check = answer_l in {"yes", "true", "1", "y", "checked"}
            if should_check:
                if not field.element.is_checked():
                    field.element.check()
            else:
                if field.element.is_checked():
                    field.element.uncheck()
            return True
        field.element.fill(answer)
        return True
    if field.tag == "textarea":
        field.element.fill(answer)
        return True
    if field.tag == "select":
        match = _match_option(field.options, answer)
        if match:
            field.element.select_option(label=match)
            return True
        return False
    return False


def find_required_unfilled(page: Page) -> list[str]:
    missing = []
    selectors = [
        "input[required]",
        "textarea[required]",
        "select[required]",
    ]
    for selector in selectors:
        for element in page.query_selector_all(selector):
            if not element.is_visible():
                continue
            tag = element.evaluate("el => el.tagName.toLowerCase()")
            input_type = (element.get_attribute("type") or "").lower()
            if input_type in {"hidden", "submit", "button", "reset"}:
                continue
            value = (element.input_value() or "").strip()
            if value:
                continue
            label = ""
            element_id = element.get_attribute("id") or ""
            if element_id:
                label_el = page.query_selector(f'label[for="{element_id}"]')
                if label_el:
                    label = (label_el.inner_text() or "").strip()
            if not label:
                label = (element.get_attribute("aria-label") or "").strip()
            if not label:
                label = (element.get_attribute("name") or "").strip()
            missing.append(label or "required field")
    return missing


def submit_application(page: Page, log_cb=None) -> bool:
    selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button",
        "input[type='button']",
    ]
    for selector in selectors:
        buttons = page.query_selector_all(selector)
        for button in buttons:
            if not button.is_visible():
                continue
            text = (button.inner_text() or "").strip().lower()
            value = (button.get_attribute("value") or "").strip().lower()
            combined = f"{text} {value}".strip()
            if selector in {"button[type='submit']", "input[type='submit']"}:
                button.click()
                if log_cb:
                    log_cb("Submit button clicked.")
                return True
            if any(keyword in combined for keyword in ["submit", "apply", "send", "finish"]):
                button.click()
                if log_cb:
                    log_cb(f"Clicked button: {combined}")
                return True
    try:
        page.evaluate("document.querySelector('form')?.submit()")
        if log_cb:
            log_cb("Form submitted via JS.")
        return True
    except Exception:
        if log_cb:
            log_cb("No submit action found.")
        return False
