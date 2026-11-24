"""Playwright browser lifecycle and execution manager for CarryFlow."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

logger = logging.getLogger("carryflow.automation.manager")

ALLOWED_AUTOMATION_ORIGINS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
}


def is_allowed_origin(url: str) -> bool:
    try:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return origin in ALLOWED_AUTOMATION_ORIGINS
    except Exception:
        return False


class PlaywrightManager:
    """Manages the lifecycle of an async Playwright browser instance."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()
        self._latest_screenshot: bytes | None = None
        self._current_url: str = "about:blank"
        self._is_ready: bool = False
        self._error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    @property
    def is_ready(self) -> bool:
        return self._is_ready and self.is_running

    @property
    def current_url(self) -> str:
        return self._current_url

    @property
    def latest_screenshot(self) -> bytes | None:
        return self._latest_screenshot

    async def start(
        self,
        headless: bool | None = None,
        slow_mo: int | None = None,
    ) -> bool:
        """Start Playwright and launch Chromium."""
        async with self._lock:
            if self.is_running and self._page:
                return True

            if headless is None:
                headless_env = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower()
                headless = headless_env not in {"false", "0", "no"}

            if slow_mo is None:
                try:
                    slow_mo = int(os.getenv("PLAYWRIGHT_SLOWMO", "50"))
                except ValueError:
                    slow_mo = 50

            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=headless,
                    slow_mo=slow_mo,
                )
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="CarryFlow-BrowserTaskAssistant/0.1.0",
                )
                self._page = await self._context.new_page()
                self._current_url = self._page.url or "about:blank"
                self._is_ready = True
                self._error = None
                logger.info("PlaywrightManager started successfully")
                return True
            except Exception as e:
                self._error = str(e)
                self._is_ready = False
                logger.exception("Failed to start Playwright: %s", e)
                await self._cleanup()
                return False

    async def stop(self) -> None:
        """Stop and cleanup Playwright browser instance."""
        async with self._lock:
            await self._cleanup()

    async def _cleanup(self) -> None:
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._is_ready = False

    async def get_page(self) -> Page:
        """Get active page or ensure one exists."""
        if not self.is_running or not self._page or self._page.is_closed():
            started = await self.start()
            if not started or not self._page:
                raise RuntimeError(f"Playwright browser is not running: {self._error or 'Unknown error'}")
        return self._page

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navigate active page to URL with strict origin enforcement."""
        if not is_allowed_origin(url):
            raise ValueError(f"Origin of URL '{url}' is outside approved local demo scope")

        page = await self.get_page()
        async with self._lock:
            response = await page.goto(url, wait_until="domcontentloaded")
            self._current_url = page.url
            try:
                self._latest_screenshot = await page.screenshot(type="png", full_page=False)
            except Exception as err:
                logger.warning("Could not capture screenshot on navigate: %s", err)

            status_code = response.status if response else 200
            return {
                "ok": True,
                "url": self._current_url,
                "status_code": status_code,
            }

    async def capture_screenshot(self) -> bytes:
        """Capture screenshot of the current page."""
        page = await self.get_page()
        async with self._lock:
            screenshot = await page.screenshot(type="png", full_page=False)
            self._latest_screenshot = screenshot
            return screenshot

    def get_status(self) -> dict[str, Any]:
        """Return current status of Playwright automation."""
        return {
            "running": self.is_running,
            "ready": self.is_ready,
            "current_url": self._current_url,
            "has_screenshot": self._latest_screenshot is not None,
            "error": self._error,
        }


# Global singleton instance
_manager_instance: PlaywrightManager | None = None


def get_playwright_manager() -> PlaywrightManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PlaywrightManager()
    return _manager_instance
