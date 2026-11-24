"""Unit and integration tests for PlaywrightManager and FormAutomator."""

from __future__ import annotations

import os
import pytest
from backend.app.automation.manager import PlaywrightManager, is_allowed_origin
from backend.app.automation.automator import FormAutomator, DISALLOWED_SUBMIT_SELECTORS

PLAYWRIGHT_DISABLED = os.environ.get("CARRYFLOW_PLAYWRIGHT_DISABLED", "").lower() in {
    "1", "true", "yes"
}


def test_origin_allowlist_enforcement():
    """Verify that only approved local origins are allowed."""
    assert is_allowed_origin("http://127.0.0.1:8000/portal/a") is True
    assert is_allowed_origin("http://localhost:8000/portal/b") is True
    assert is_allowed_origin("http://127.0.0.1:8000/portal/source") is True
    assert is_allowed_origin("http://127.0.0.1:8000/api/state") is True

    # External, spoofed, or unexpected origins must be rejected
    assert is_allowed_origin("https://google.com") is False
    assert is_allowed_origin("https://evil.com/portal/a") is False
    assert is_allowed_origin("http://192.168.1.1:8000/portal/a") is False
    assert is_allowed_origin("javascript:alert(1)") is False
    assert is_allowed_origin("file:///etc/passwd") is False


def test_submit_button_safety_guards():
    """Verify that FormAutomator safety guards strictly prevent submission attempts."""
    assert "#submit-application" in DISALLOWED_SUBMIT_SELECTORS
    assert "button[type='submit']" in DISALLOWED_SUBMIT_SELECTORS
    assert "input[type='submit']" in DISALLOWED_SUBMIT_SELECTORS


@pytest.mark.skipif(PLAYWRIGHT_DISABLED, reason="Playwright browser launch disabled in sandbox environment")
def test_form_automator_with_live_browser():
    """Test FormAutomator with live Chromium when not in restricted sandbox."""
    import asyncio

    async def _test():
        mgr = PlaywrightManager()
        started = await mgr.start(headless=True)
        if not started:
            pytest.skip("Chromium could not be launched in this environment")

        try:
            page = await mgr.get_page()
            html = """
            <!doctype html>
            <html>
            <body>
                <input id="candidate_name" name="candidate_name" value="">
                <button id="submit-application">Submit</button>
            </body>
            </html>
            """
            await page.set_content(html)
            res = await FormAutomator.fill_fields(page, {
                "candidate_name": "Aarav Mehta",
                "submit-application": "click",
            })
            assert "candidate_name" in res["filled"]
            assert "submit-application" not in res["filled"]
            assert res["observed"]["candidate_name"] == "Aarav Mehta"
        finally:
            await mgr.stop()

    asyncio.run(_test())
