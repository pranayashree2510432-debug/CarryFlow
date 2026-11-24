"""Tests for Playwright automation endpoints in FastAPI."""

from __future__ import annotations

import os
import pytest
from fastapi import HTTPException
from backend.app import main

PLAYWRIGHT_DISABLED = os.environ.get("CARRYFLOW_PLAYWRIGHT_DISABLED", "").lower() in {
    "1", "true", "yes"
}


@pytest.fixture(autouse=True)
def setup_app():
    main.init()
    main.reset()
    yield
    main.reset()


def test_automation_status_endpoint():
    """Verify GET /api/automation/status returns status structure."""
    st = main.automation_status()
    assert "running" in st
    assert "ready" in st
    assert "current_url" in st


@pytest.mark.skipif(PLAYWRIGHT_DISABLED, reason="Async test loop requires non-sandboxed environment")
def test_automation_navigate_rejects_external_origin():
    """Verify POST /api/automation/navigate enforces origin allowlist."""
    import asyncio
    async def _test():
        with pytest.raises(HTTPException) as exc:
            await main.automation_navigate(main.AutomationNavigateBody(url="https://external-malicious.com"))
        assert exc.value.status_code == 403
    asyncio.run(_test())


@pytest.mark.skipif(PLAYWRIGHT_DISABLED, reason="Async test loop requires non-sandboxed environment")
def test_automation_screenshot_returns_404_when_stopped():
    """Verify screenshot endpoint returns 404 when browser is inactive."""
    import asyncio
    async def _test():
        resp = await main.automation_screenshot()
        assert resp.status_code == 404
    asyncio.run(_test())
