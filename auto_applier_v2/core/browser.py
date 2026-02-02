import asyncio
import os
from typing import Optional

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

try:
    from playwright_stealth import stealth_async as _stealth_async  # type: ignore

    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False

    async def _stealth_async(page: Page) -> None:  # type: ignore[override]
        return None


class BrowserManager:
    _instance = None
    _instance_lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._restart_lock = asyncio.Lock()
        self._is_crashed = False
        self._last_launch_args = {}

    @classmethod
    async def get_instance(cls) -> "BrowserManager":
        async with cls._instance_lock:
            return cls()

    async def launch_browser(
        self,
        user_data_dir: str,
        headless: bool = False,
        executable_path: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> Page:
        self._last_launch_args = {
            "user_data_dir": user_data_dir,
            "headless": headless,
            "executable_path": executable_path,
            "channel": channel,
        }
        await self._ensure_playwright()
        await self._ensure_context(user_data_dir, headless, executable_path, channel)
        return await self._ensure_page()

    async def _ensure_playwright(self) -> None:
        if self._playwright is None:
            print("[DEBUG TERMINAL] [BROWSER] Starting Playwright...")
            self._playwright = await async_playwright().start()
            print("[DEBUG TERMINAL] [BROWSER] Playwright ready.")

    async def _ensure_context(
        self,
        user_data_dir: str,
        headless: bool,
        executable_path: Optional[str],
        channel: Optional[str],
    ) -> None:
        if self._context is not None and not self._is_crashed:
            return
        await self._restart_if_needed()
        os.makedirs(user_data_dir, exist_ok=True)
        print("[DEBUG TERMINAL] [BROWSER] Launching persistent context...")
        try:
            self._context = await asyncio.wait_for(
                self._playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=headless,
                    executable_path=executable_path,
                    channel=channel,
                    args=["--disable-blink-features=AutomationControlled"],
                ),
                timeout=60,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Playwright launch_persistent_context timed out") from exc
        print("[DEBUG TERMINAL] [BROWSER] Context launched.")
        self._is_crashed = False

        browser = self._context.browser
        if browser:
            browser.on("disconnected", self._on_browser_disconnected)

    async def _ensure_page(self) -> Page:
        if self._page is not None and not self._is_crashed:
            return self._page
        if self._context is None:
            await self._restart_if_needed()
        pages = self._context.pages if self._context else []
        if pages:
            self._page = pages[0]
        else:
            self._page = await self._context.new_page()  # type: ignore[union-attr]

        if _STEALTH_AVAILABLE:
            try:
                await _stealth_async(self._page)
            except Exception:
                pass

        return self._page

    def _on_browser_disconnected(self) -> None:
        self._is_crashed = True

    async def _restart_if_needed(self) -> None:
        if not self._is_crashed and self._context is not None:
            return
        async with self._restart_lock:
            if not self._is_crashed and self._context is not None:
                return
            print("[DEBUG TERMINAL] [BROWSER] Restarting context (cleanup)...")
            await self._safe_close_context()
            self._context = None
            self._page = None
            self._is_crashed = False
            print("[DEBUG TERMINAL] [BROWSER] Restart cleanup done.")

    async def _safe_close_context(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
        except Exception:
            pass

    async def close(self) -> None:
        await self._safe_close_context()
        self._context = None
        self._page = None
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._is_crashed = False
