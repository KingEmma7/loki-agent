"""Browser launch from the standalone binary (#22): shared browser cache and driver-based install."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from playwright.sync_api import Error

from loki.engine import browser
from loki.engine.browser import default_browsers_path, ensure_browsers_path, launch_browser


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)


@pytest.fixture
def not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)


@pytest.mark.parametrize(
    ("platform", "env", "expected"),
    [
        ("win32", {"LOCALAPPDATA": "C:/Users/u/AppData/Local"}, Path("C:/Users/u/AppData/Local/ms-playwright")),
        ("darwin", {}, Path.home() / "Library" / "Caches" / "ms-playwright"),
        ("linux", {"XDG_CACHE_HOME": "/tmp/cache"}, Path("/tmp/cache/ms-playwright")),
        ("linux", {}, Path.home() / ".cache" / "ms-playwright"),
    ],
)
def test_default_browsers_path_per_platform(monkeypatch, platform, env, expected):
    monkeypatch.setattr(sys, "platform", platform)
    for key in ("LOCALAPPDATA", "XDG_CACHE_HOME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert default_browsers_path() == expected


def test_frozen_points_at_shared_browser_cache(frozen):
    ensure_browsers_path()
    assert browser.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(default_browsers_path())


def test_frozen_respects_user_browsers_path(frozen, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/browsers")
    ensure_browsers_path()
    assert browser.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "/opt/browsers"


def test_not_frozen_leaves_browsers_path_alone(not_frozen):
    ensure_browsers_path()
    assert "PLAYWRIGHT_BROWSERS_PATH" not in browser.os.environ


def _missing_then_launched(engine: str) -> MagicMock:
    playwright = MagicMock()
    getattr(playwright, engine).launch.side_effect = [Error("Executable doesn't exist at /ms-playwright"), "browser"]
    return playwright


def test_frozen_install_uses_bundled_driver_not_loki_exe(frozen):
    with patch("loki.engine.browser.subprocess.run") as run, patch(
        "playwright._impl._driver.compute_driver_executable", return_value=("node.exe", "cli.js")
    ):
        assert launch_browser(_missing_then_launched("chromium"), "chromium") == "browser"
    cmd = run.call_args.args[0]
    assert cmd == ["node.exe", "cli.js", "install", "chromium"]
    assert sys.executable not in cmd
    assert run.call_args.kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"] == str(default_browsers_path())


def test_not_frozen_install_uses_python_module(not_frozen):
    with patch("loki.engine.browser.subprocess.run") as run:
        assert launch_browser(_missing_then_launched("webkit"), "webkit") == "browser"
    assert run.call_args.args[0] == [sys.executable, "-m", "playwright", "install", "webkit"]
    assert "PLAYWRIGHT_BROWSERS_PATH" not in run.call_args.kwargs["env"]
