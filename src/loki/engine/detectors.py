"""Failure detectors for chaos sessions.

Each detector owns one failure vector and plugs into ChaosSandbox.run_session at three
points: `attach` (live page listeners, before the first navigation), `after_navigation`
(once the target has loaded) and `inspect` (a final sniff when the session ends).
New vectors are added by writing a Detector, without touching the session loop.
"""
import json
from urllib.parse import urlparse
from playwright.sync_api import Page, Response
from loki.models import IncidentReport
from loki.personas.base import BasePersona


def _append_unique(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


class Detector:
    """Base class: override any of the three hooks. All hooks default to no-ops."""

    def attach(self, page: Page, report: IncidentReport) -> None:
        pass

    def after_navigation(self, page: Page, report: IncidentReport) -> None:
        pass

    def inspect(self, page: Page, report: IncidentReport) -> None:
        pass


class JavaScriptErrorDetector(Detector):
    """Unhandled exceptions, console errors and unhandled promise rejections."""

    _REJECTION_SCRIPT = """
        window.addEventListener('unhandledrejection', function(event) {
            var reason = event.reason;
            var msg = '';
            if (reason instanceof Error) {
                msg = reason.stack || reason.message;
            } else if (typeof reason === 'object') {
                try { msg = JSON.stringify(reason); } catch(e) { msg = String(reason); }
            } else {
                msg = String(reason);
            }
            if (window.__loki_record_rejection) {
                window.__loki_record_rejection(msg);
            }
        });
    """

    def attach(self, page: Page, report: IncidentReport) -> None:
        page.on("pageerror", lambda err: report.crashes.append(str(err)))
        page.on("console", lambda msg: report.console_errors.append(msg.text) if msg.type == "error" else None)

        def record_rejection(source, reason: str):
            _append_unique(report.unhandled_rejections, f"Unhandled Promise Rejection: {reason}")

        page.expose_binding("__loki_record_rejection", record_rejection)
        page.add_init_script(self._REJECTION_SCRIPT)


class NetworkDetector(Detector):
    """HTTP 4xx/5xx responses and failed requests (CORS, dead endpoints, dropped connections)."""

    def attach(self, page: Page, report: IncidentReport) -> None:
        def handle_response(response: Response):
            if response.status >= 400:
                suffix = f" ({response.status_text})" if response.status_text else ""
                report.http_errors.append(f"HTTP {response.status}{suffix} on {response.url}")

        def handle_request_failed(request):
            failure = request.failure or "Request failed"
            _append_unique(report.failed_requests, f"[{request.method}] {request.url} ({request.resource_type}) - {failure}")

        page.on("response", handle_response)
        page.on("requestfailed", handle_request_failed)


class DialogDetector(Detector):
    """Unexpected alert/confirm/prompt dialogs, dismissed so the session keeps going."""

    def attach(self, page: Page, report: IncidentReport) -> None:
        def handle_dialog(dialog):
            _append_unique(report.unexpected_dialogs, f"Unexpected {dialog.type} dialog: '{dialog.message}'")
            try:
                dialog.dismiss()
            except Exception:
                pass

        page.on("dialog", handle_dialog)


ERROR_TITLE_KEYWORDS = (
    "500 internal server error",
    "404 not found",
    "page not found",
    "server error",
    "application error",
    "error 404",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
    "something went wrong",
)
ERROR_ROUTE_PATTERNS = ("/500", "/404", "/error", "/crash", "/oops", "/server-error", "/page-not-found")


def sniff_error_page(page: Page) -> str | None:
    """Whether the page currently shows a known error screen (by title) or crash route (by URL)."""
    try:
        if page.is_closed():
            return None
        title = (page.title() or "").lower()
        url = page.url or ""
        if any(kw in title for kw in ERROR_TITLE_KEYWORDS):
            return f"Application error page detected by title: '{page.title()}' ({url})"

        path = urlparse(url).path.lower().rstrip("/")
        if any(path.endswith(p) or path == p for p in ERROR_ROUTE_PATTERNS):
            return f"Application navigated to error route: '{path}' ({url})"
    except Exception:
        pass
    return None


class NavigationDetector(Detector):
    """Browser error pages during the session, and application error screens at the end."""

    def attach(self, page: Page, report: IncidentReport) -> None:
        def handle_framenavigated(frame):
            if frame == page.main_frame:
                url = frame.url or ""
                if url.startswith("chrome-error://") or "about:neterror" in url or url.startswith("about:crash"):
                    _append_unique(report.navigation_errors, f"Navigated to browser error page: {url}")

        page.on("framenavigated", handle_framenavigated)

    def inspect(self, page: Page, report: IncidentReport) -> None:
        err_page = sniff_error_page(page)
        if err_page:
            _append_unique(report.navigation_errors, err_page)


def sniff_broken_resources(page: Page) -> list[str]:
    """Completed <img> tags in the DOM that failed to load (naturalWidth === 0)."""
    try:
        if page.is_closed():
            return []
        broken = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('img').forEach(img => {
                if (img.complete && img.naturalWidth === 0 && img.src && !img.src.startsWith('data:')) {
                    results.push(img.src);
                }
            });
            return results;
        }""")
        return [f"Broken image in DOM (0px natural width): {src}" for src in broken]
    except Exception:
        return []


class ResourceDetector(Detector):
    """Sub-resources (<img>, <script>, <link>, ...) that fail to load, live and in the final DOM."""

    _RESOURCE_ERROR_SCRIPT = """
        window.addEventListener('error', function(event) {
            var target = event.target;
            if (target && target !== window && target.tagName) {
                var tag = target.tagName.toUpperCase();
                var src = target.src || target.href || target.currentSrc || '';
                if (src && window.__loki_record_resource_failure) {
                    window.__loki_record_resource_failure(tag, src);
                }
            }
        }, true);
    """

    def attach(self, page: Page, report: IncidentReport) -> None:
        def record_resource_failure(source, tag: str, src: str):
            _append_unique(report.resource_failures, f"Failed to load <{tag.upper()}> resource: {src}")

        page.expose_binding("__loki_record_resource_failure", record_resource_failure)
        page.add_init_script(self._RESOURCE_ERROR_SCRIPT)

    def inspect(self, page: Page, report: IncidentReport) -> None:
        for broken in sniff_broken_resources(page):
            _append_unique(report.resource_failures, broken)


def sniff_mobile_layout(page: Page) -> list[str]:
    """Mobile responsiveness issues: horizontal scroll overflow and a missing/invalid viewport meta tag."""
    try:
        if page.is_closed():
            return []
        vp = page.viewport_size
        vp_width = vp["width"] if vp else 390
        return page.evaluate("""(vpWidth) => {
            const issues = [];
            const docWidth = Math.max(
                document.documentElement.scrollWidth || 0,
                document.body ? document.body.scrollWidth : 0
            );

            // Detect horizontal overflow (standard mobile UX bug)
            if (docWidth > vpWidth + 5) {
                issues.push(`Horizontal scroll overflow detected: page content (${docWidth}px) exceeds mobile viewport width (${vpWidth}px) by ${docWidth - vpWidth}px.`);
            }

            // Detect missing or invalid viewport meta tag
            const metaViewport = document.querySelector('meta[name="viewport"]');
            if (!metaViewport) {
                issues.push("Missing <meta name='viewport'> tag: mobile devices will render unoptimized scaled desktop view.");
            } else {
                const content = metaViewport.getAttribute('content') || '';
                if (!content.includes('width=device-width')) {
                    issues.push("<meta name='viewport'> tag missing 'width=device-width' directive.");
                }
            }

            return issues;
        }""", vp_width)
    except Exception:
        return []


class MobileLayoutDetector(Detector):
    """Responsive layout issues, sniffed on load and at the end, only under device emulation."""

    def after_navigation(self, page: Page, report: IncidentReport) -> None:
        if report.device_name:
            report.layout_issues.extend(sniff_mobile_layout(page))

    def inspect(self, page: Page, report: IncidentReport) -> None:
        if report.device_name:
            for issue in sniff_mobile_layout(page):
                _append_unique(report.layout_issues, issue)


class UiFreezeDetector(Detector):
    """White screens / frozen UIs left behind by API chaos (only for personas that inject it)."""

    def __init__(self, persona: BasePersona | None):
        self.persona = persona

    def inspect(self, page: Page, report: IncidentReport) -> None:
        api_chaos = getattr(self.persona, "api_chaos", None)
        if not api_chaos:
            return
        freeze = api_chaos.sniff_white_screen_or_freeze(page)
        if freeze:
            reason = freeze.get("reason", "Application collapsed or became non-responsive")
            _append_unique(report.layout_issues, f"[UI Freeze / Blank Screen] {reason}")


def default_detectors(persona: BasePersona | None = None) -> list[Detector]:
    """The full detector set used by `loki run`."""
    return [
        JavaScriptErrorDetector(),
        NetworkDetector(),
        DialogDetector(),
        NavigationDetector(),
        ResourceDetector(),
        MobileLayoutDetector(),
        UiFreezeDetector(persona),
    ]


def capture_dom_snapshot(page: Page) -> str:
    """Concise JSON snapshot of the final interactive UI state, used as evidence for rules evaluation."""
    dom_info = page.evaluate("""() => {
        const elements = [];
        document.querySelectorAll('button, input, select, a, .status, .alert, .badge, [role="alert"]').forEach(el => {
            elements.push({
                tag: el.tagName.toLowerCase(),
                id: el.id || undefined,
                classes: el.className || undefined,
                text: (el.innerText || el.value || '').trim(),
                disabled: el.disabled !== undefined ? el.disabled : undefined,
                visible: el.offsetParent !== null
            });
        });
        return {
            title: document.title,
            url: window.location.href,
            interactive_elements: elements
        };
    }""")
    return json.dumps(dom_info, indent=2)
