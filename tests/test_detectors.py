from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from playwright.sync_api import Error
from loki.engine.browser import launch_browser, normalize_browser_name
from loki.engine.detectors import (
    DialogDetector,
    JavaScriptErrorDetector,
    MobileLayoutDetector,
    NavigationDetector,
    NetworkDetector,
    ResourceDetector,
    UiFreezeDetector,
    default_detectors,
)
from loki.engine.devices import resolve_device
from loki.models import IncidentReport


class FakePage:
    """Minimal Page stand-in: records listeners/bindings so tests can fire events."""

    def __init__(self):
        self.handlers = {}
        self.bindings = {}
        self.init_scripts = []
        self.main_frame = object()
        self.evaluate = MagicMock(return_value=[])

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event, payload):
        for handler in self.handlers.get(event, []):
            handler(payload)

    def expose_binding(self, name, fn):
        self.bindings[name] = fn

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def is_closed(self):
        return False

    viewport_size = {"width": 390, "height": 844}


@pytest.fixture
def report():
    return IncidentReport(target_url="http://localhost:8000")


def test_javascript_errors_and_rejections(report):
    page = FakePage()
    JavaScriptErrorDetector().attach(page, report)
    page.emit("pageerror", "TypeError: x is undefined")
    page.emit("console", SimpleNamespace(type="error", text="boom"))
    page.emit("console", SimpleNamespace(type="log", text="ignored"))
    page.bindings["__loki_record_rejection"](None, "fetch failed")
    page.bindings["__loki_record_rejection"](None, "fetch failed")

    assert report.crashes == ["TypeError: x is undefined"]
    assert report.console_errors == ["boom"]
    assert report.unhandled_rejections == ["Unhandled Promise Rejection: fetch failed"]
    assert any("unhandledrejection" in s for s in page.init_scripts)


def test_network_errors(report):
    page = FakePage()
    NetworkDetector().attach(page, report)
    page.emit("response", SimpleNamespace(status=200, status_text="OK", url="/ok"))
    page.emit("response", SimpleNamespace(status=503, status_text="Service Unavailable", url="/api"))
    failed = SimpleNamespace(failure="net::ERR_FAILED", method="GET", url="/x", resource_type="xhr")
    page.emit("requestfailed", failed)
    page.emit("requestfailed", failed)

    assert report.http_errors == ["HTTP 503 (Service Unavailable) on /api"]
    assert report.failed_requests == ["[GET] /x (xhr) - net::ERR_FAILED"]


def test_dialogs_are_recorded_and_dismissed(report):
    page = FakePage()
    DialogDetector().attach(page, report)
    dialog = MagicMock(type="alert", message="Session expired")
    page.emit("dialog", dialog)

    assert report.unexpected_dialogs == ["Unexpected alert dialog: 'Session expired'"]
    dialog.dismiss.assert_called_once()


def test_navigation_to_browser_error_page(report):
    page = FakePage()
    page.main_frame = SimpleNamespace(url="http://localhost:8000/")
    NavigationDetector().attach(page, report)
    page.emit("framenavigated", SimpleNamespace(url="chrome-error://chromewebdata/"))  # an iframe, not main
    page.emit("framenavigated", page.main_frame)  # main frame on a normal page
    assert report.navigation_errors == []

    page.main_frame = SimpleNamespace(url="chrome-error://chromewebdata/")
    page.emit("framenavigated", page.main_frame)
    assert report.navigation_errors == ["Navigated to browser error page: chrome-error://chromewebdata/"]


def test_resource_failures_live_and_final(report):
    page = FakePage()
    detector = ResourceDetector()
    detector.attach(page, report)
    page.bindings["__loki_record_resource_failure"](None, "img", "/missing.png")
    page.evaluate.return_value = ["/broken.jpg"]
    detector.inspect(page, report)

    assert report.resource_failures == [
        "Failed to load <IMG> resource: /missing.png",
        "Broken image in DOM (0px natural width): /broken.jpg",
    ]


def test_mobile_layout_only_under_device_emulation(report):
    page = FakePage()
    page.evaluate.return_value = ["Horizontal scroll overflow detected"]
    detector = MobileLayoutDetector()

    detector.after_navigation(page, report)
    assert report.layout_issues == []

    report.device_name = "iPhone 15"
    detector.after_navigation(page, report)
    detector.inspect(page, report)
    assert report.layout_issues == ["Horizontal scroll overflow detected"]


def test_ui_freeze_requires_api_chaos(report):
    page = FakePage()
    UiFreezeDetector(persona=None).inspect(page, report)
    assert report.layout_issues == []

    persona = SimpleNamespace(api_chaos=MagicMock())
    persona.api_chaos.sniff_white_screen_or_freeze.return_value = {"reason": "blank body"}
    UiFreezeDetector(persona).inspect(page, report)
    assert report.layout_issues == ["[UI Freeze / Blank Screen] blank body"]


def test_default_detectors_cover_every_vector():
    kinds = {type(d) for d in default_detectors()}
    assert kinds == {
        JavaScriptErrorDetector, NetworkDetector, DialogDetector, NavigationDetector,
        ResourceDetector, MobileLayoutDetector, UiFreezeDetector,
    }


def test_normalize_browser_name():
    assert normalize_browser_name(None) == "chromium"
    assert normalize_browser_name(" WebKit ") == "webkit"
    assert normalize_browser_name("opera") == "chromium"


def test_launch_browser_installs_missing_engine():
    playwright = MagicMock()
    playwright.firefox.launch.side_effect = [Error("Executable doesn't exist at /ms-playwright"), "browser"]
    with patch("loki.engine.browser.subprocess.run") as run:
        assert launch_browser(playwright, "firefox", headless=True) == "browser"
    assert run.call_args.args[0][-2:] == ["install", "firefox"]


def test_launch_browser_reraises_other_errors():
    playwright = MagicMock()
    playwright.chromium.launch.side_effect = Error("Target closed")
    with patch("loki.engine.browser.subprocess.run") as run, pytest.raises(Error):
        launch_browser(playwright, "chromium")
    run.assert_not_called()


def test_resolve_device_alias_and_landscape():
    devices = {"iPhone 15": {"viewport": {"width": 393, "height": 852}}}
    name, desc = resolve_device("iphone-15", "landscape", devices)
    assert name == "iPhone 15"
    assert desc["viewport"] == {"width": 852, "height": 393}
    assert resolve_device("nokia-3310", "portrait", devices) == (None, None)
