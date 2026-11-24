"""Playwright form inspection and interaction automator for CarryFlow."""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger("carryflow.automation.automator")

DISALLOWED_SUBMIT_SELECTORS = {
    "#submit-application",
    "button[type='submit']",
    "input[type='submit']",
    ".submit-button",
}


class FormAutomator:
    """Inspects, fills, and observes form fields via Playwright with safety guarantees."""

    @staticmethod
    async def inspect_fields(page: Page) -> list[dict[str, Any]]:
        """Inspect all interactive form fields on the page."""
        script = """() => {
            const fields = [];
            const elements = document.querySelectorAll("input:not([type='hidden']):not([type='submit']), textarea, select");
            for (const el of elements) {
                const id = el.id || el.name || "";
                let label = "";
                if (el.id) {
                    const l = document.querySelector(`label[for="${el.id}"]`);
                    if (l) label = l.textContent.trim();
                }
                if (!label && el.closest("label")) {
                    label = el.closest("label").textContent.trim();
                }
                if (!label && el.placeholder) {
                    label = el.placeholder;
                }
                if (!label && el.getAttribute("aria-label")) {
                    label = el.getAttribute("aria-label");
                }
                fields.push({
                    id: id,
                    name: el.name || "",
                    tag: el.tagName.toLowerCase(),
                    type: el.type || "text",
                    label: label,
                    value: el.value || "",
                    checked: el.checked || false,
                });
            }
            return fields;
        }"""
        return await page.evaluate(script)

    @staticmethod
    async def observe_fields(page: Page) -> dict[str, str]:
        """Read actual current values from all form elements on the page."""
        script = """() => {
            const observed = {};
            const elements = document.querySelectorAll("input:not([type='hidden']):not([type='submit']), textarea, select");
            for (const el of elements) {
                const key = el.id || el.name;
                if (!key) continue;
                if (el.type === "checkbox") {
                    if (el.checked) {
                        observed[key] = el.value && el.value !== "on" ? el.value : "true";
                    } else {
                        observed[key] = "";
                    }
                } else if (el.type === "radio") {
                    if (el.checked) {
                        observed[key] = el.value || "true";
                    } else if (!(key in observed)) {
                        observed[key] = "";
                    }
                } else {
                    observed[key] = (el.value || "").trim();
                }
            }
            return observed;
        }"""
        res = await page.evaluate(script)
        return dict(res) if isinstance(res, dict) else {}

    @classmethod
    async def fill_fields(
        cls,
        page: Page,
        field_values: dict[str, str],
    ) -> dict[str, Any]:
        """Fill approved field values into the form.
        
        Guarantees:
        - NEVER clicks or triggers any submission button.
        - Fills only the explicitly provided field values.
        - Dispatches DOM events so page listeners recognize changes.
        - Returns actual observed DOM values after filling.
        """
        filled: list[str] = []
        errors: dict[str, str] = {}

        for field_id, value in field_values.items():
            # Strict safety guard: never target submit buttons
            if field_id in {"submit-application", "submit"}:
                logger.warning("Prevented attempt to automate submit button '%s'", field_id)
                continue

            selector_candidates = [
                f"#{field_id}",
                f"[name='{field_id}']",
                f"input[name='{field_id}']",
                f"textarea[name='{field_id}']",
                f"select[name='{field_id}']",
            ]

            target_locator = None
            for sel in selector_candidates:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    target_locator = loc
                    break

            if target_locator is None:
                errors[field_id] = "Field selector not found on page"
                continue

            try:
                tag = await target_locator.evaluate("el => el.tagName.toLowerCase()")
                el_type = await target_locator.evaluate("el => el.type || ''")

                if tag == "select":
                    await target_locator.select_option(value=value)
                elif el_type == "checkbox":
                    if str(value).lower() in {"true", "1", "yes", "on"}:
                        await target_locator.check()
                    else:
                        await target_locator.uncheck()
                elif el_type == "radio":
                    radio_loc = page.locator(f"input[type='radio'][name='{field_id}'][value='{value}']").first
                    if await radio_loc.count() > 0:
                        await radio_loc.check()
                    else:
                        await target_locator.check()
                else:
                    await target_locator.fill(value)

                # Dispatch change and input events to emulate natural user typing
                await target_locator.evaluate("""el => {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""")
                filled.append(field_id)
            except Exception as e:
                logger.warning("Error filling field '%s': %s", field_id, e)
                errors[field_id] = str(e)

        observed = await cls.observe_fields(page)
        return {
            "filled": filled,
            "errors": errors,
            "observed": observed,
        }
