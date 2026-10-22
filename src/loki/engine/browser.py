"""Browser engine selection and launch, shared by chaos sessions, concurrency lanes and the recorder."""
import logging
import subprocess
import sys
from playwright.sync_api import Browser, Error, Playwright

SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")
logger = logging.getLogger("loki")


def normalize_browser_name(browser_name: str | None) -> str:
    """Lower-cases and validates an engine name, falling back to chromium."""
    name = (browser_name or "chromium").lower().strip()
    return name if name in SUPPORTED_BROWSERS else "chromium"


def launch_browser(playwright: Playwright, browser_name: str, headless: bool = True) -> Browser:
    """Launches the engine, installing it through Playwright on first use if it is missing."""
    browser_type = getattr(playwright, browser_name)
    try:
        return browser_type.launch(headless=headless)
    except Error as e:
        err_msg = str(e).lower()
        if "executable doesn't exist" not in err_msg and "playwright install" not in err_msg:
            raise
    logger.warning(f"⚡ {browser_name.capitalize()} browser not found. Installing automatically via Playwright...")
    subprocess.run([sys.executable, "-m", "playwright", "install", browser_name], check=True)
    return browser_type.launch(headless=headless)
