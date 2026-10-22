"""Browser engine selection and launch, shared by chaos sessions, concurrency lanes and the recorder."""
import logging
import os
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import Browser, Error, Playwright

SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")
logger = logging.getLogger("loki")


def is_frozen() -> bool:
    """True inside the standalone PyInstaller binary."""
    return bool(getattr(sys, "frozen", False))


def default_browsers_path() -> Path:
    """Playwright's default per-user browser cache for the current OS."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"


def ensure_browsers_path() -> None:
    """Points a frozen binary at the shared browser cache. Call before starting Playwright.

    When frozen, Playwright defaults `PLAYWRIGHT_BROWSERS_PATH` to "0" (browsers bundled next
    to the package), but the binary ships none — and a onefile build's temp dir is deleted on
    exit, so an install there would never persist. A user-provided value is always respected.
    """
    if is_frozen() and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(default_browsers_path())


def _install_command(browser_name: str) -> list[str]:
    """`playwright install <engine>`, through the bundled driver when there's no Python interpreter."""
    if is_frozen():
        # In a frozen app sys.executable is loki.exe itself, not a Python interpreter.
        from playwright._impl._driver import compute_driver_executable

        driver_executable, driver_cli = compute_driver_executable()
        return [driver_executable, driver_cli, "install", browser_name]
    return [sys.executable, "-m", "playwright", "install", browser_name]


def install_browser(browser_name: str) -> None:
    """Downloads a Playwright browser engine into the active browsers path."""
    from playwright._impl._driver import get_driver_env

    ensure_browsers_path()
    subprocess.run(_install_command(browser_name), env=get_driver_env(), check=True)


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
    install_browser(browser_name)
    return browser_type.launch(headless=headless)
