import html
import json
from pathlib import Path
from typing import Any
from loki.templates import render


class HTMLReporter:
    """Generates standalone, responsive HTML test reports with embedded replay video and AI scorecards."""

    @staticmethod
    def _safe_int(val: Any, default: int = 0) -> int:
        """Safely casts a value to an integer, falling back to default on None, TypeError, or ValueError."""
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @classmethod
    def generate(cls, data: dict[str, Any], output_file: Path) -> Path:
        """Renders incident or test session data into an HTML dashboard."""
        run_id = html.escape(str(data.get("run_id", "LOKI Test Run")))
        target_url = html.escape(str(data.get("target_url", "")))
        timestamp = html.escape(str(data.get("timestamp", "")))
        raw_duration = data.get("duration_seconds")
        try:
            duration_val = float(raw_duration) if raw_duration is not None else 0.0
        except (ValueError, TypeError):
            duration_val = 0.0
        duration = f"{duration_val:.2f}s"
        persona = html.escape(str(data.get("persona", "Unguided Chaos")))
        video_file = data.get("video_file")
        crashes = data.get("crashes") or []
        http_errors = data.get("http_errors") or []
        console_errors = data.get("console_errors") or []
        failed_requests = data.get("failed_requests") or []
        unhandled_rejections = data.get("unhandled_rejections") or []
        navigation_errors = data.get("navigation_errors") or []
        resource_failures = data.get("resource_failures") or []
        unexpected_dialogs = data.get("unexpected_dialogs") or []
        actions = data.get("actions_taken") or []
        rules_evals = data.get("rules_evaluations") or []
        device = data.get("device")
        orientation = data.get("orientation", "portrait")
        browser = html.escape(str(data.get("browser") or "chromium"))
        layout_issues = data.get("layout_issues") or []
        concurrency = cls._safe_int(data.get("concurrency"), 1)
        concurrency_lanes = data.get("concurrency_lanes") or []

        # Verdict calculation
        has_violations = any(str(r.get("status") or "").upper() == "VIOLATED" for r in rules_evals)
        has_failures = (
            len(crashes) > 0
            or len(http_errors) > 0
            or len(console_errors) > 0
            or len(failed_requests) > 0
            or len(unhandled_rejections) > 0
            or len(navigation_errors) > 0
            or len(resource_failures) > 0
            or len(unexpected_dialogs) > 0
        )
        has_layout_issues = len(layout_issues) > 0

        if has_failures or has_violations or has_layout_issues:
            verdict_badge = '<span class="badge badge-danger">FAIL / ISSUES DETECTED</span>'
        else:
            verdict_badge = '<span class="badge badge-success">ALL CHECKS PASSED</span>'

        # Rules table rows
        rules_rows = ""
        if rules_evals:
            for r in rules_evals:
                st = str(r.get("status") or "UNKNOWN").upper()
                if st == "PASSED":
                    badge = '<span class="badge badge-success">✔ PASSED</span>'
                elif st == "VIOLATED":
                    badge = '<span class="badge badge-danger">❌ VIOLATED</span>'
                else:
                    badge = f'<span class="badge badge-warning">{html.escape(st)}</span>'

                rule_text = html.escape(str(r.get("rule") or ""))
                obs_text = html.escape(str(r.get("observation") or ""))
                rules_rows += f"""
                <tr>
                    <td style="font-weight: 500;">{rule_text}</td>
                    <td style="text-align: center;">{badge}</td>
                    <td style="color: #8b949e; font-size: 13px;">{obs_text}</td>
                </tr>
                """
        else:
            rules_rows = '<tr><td colspan="3" style="text-align: center; color: #8b949e; padding: 20px;">No business rules evaluated for this run.</td></tr>'

        # Actions list
        actions_html = ""
        for act in actions:
            actions_html += f'<li class="timeline-item"><span class="bullet"></span><span class="action-text">{html.escape(act)}</span></li>\n'

        # Failures & Crashes list
        total_failures = (
            len(crashes)
            + len(console_errors)
            + len(http_errors)
            + len(failed_requests)
            + len(unhandled_rejections)
            + len(navigation_errors)
            + len(resource_failures)
            + len(unexpected_dialogs)
        )
        crashes_html = ""
        if total_failures > 0:
            for c in crashes:
                crashes_html += f'<div class="error-item"><strong>Unhandled Exception:</strong> {html.escape(str(c))}</div>'
            for ur in unhandled_rejections:
                crashes_html += f'<div class="error-item"><strong>Unhandled Promise Rejection:</strong> {html.escape(str(ur))}</div>'
            for ce in console_errors:
                crashes_html += f'<div class="error-item"><strong>Console Error (Silent Break):</strong> {html.escape(str(ce))}</div>'
            for h in http_errors:
                crashes_html += f'<div class="error-item"><strong>HTTP Failure:</strong> {html.escape(str(h))}</div>'
            for fr in failed_requests:
                crashes_html += f'<div class="error-item"><strong>Request Failed / CORS:</strong> {html.escape(str(fr))}</div>'
            for ne in navigation_errors:
                crashes_html += f'<div class="error-item"><strong>Navigation / Error Page:</strong> {html.escape(str(ne))}</div>'
            for rf in resource_failures:
                crashes_html += f'<div class="error-item"><strong>Broken Resource:</strong> {html.escape(str(rf))}</div>'
            for ud in unexpected_dialogs:
                crashes_html += f'<div class="error-item"><strong>Unexpected Dialog:</strong> {html.escape(str(ud))}</div>'
        else:
            crashes_html = '<div class="no-errors">🛡️ Zero unhandled crashes, console errors, or network/DOM failures detected.</div>'

        failures_color = "var(--accent-red)" if total_failures > 0 else "var(--accent-green)"
        failures_stat_card = f"""
            <div class="stat-card">
                <div class="stat-label">Failures Detected</div>
                <div class="stat-value" style="color: {failures_color};">{total_failures}</div>
            </div>
        """

        browser_stat_card = f"""
            <div class="stat-card">
                <div class="stat-label">Browser Engine</div>
                <div class="stat-value" style="text-transform: capitalize;">🌐 {browser}</div>
            </div>
        """

        # Video section
        video_html = ""
        if video_file and (output_file.parent / video_file).exists():
            video_html = f"""
            <div class="card">
                <h2>📹 Incident Session Replay</h2>
                <div class="video-container">
                    <video controls autoplay muted loop>
                        <source src="{html.escape(video_file)}" type="video/webm">
                        Your browser does not support the video tag.
                    </video>
                </div>
            </div>
            """

        # Device stat card
        device_stat_card = ""
        if device:
            device_stat_card = f"""
            <div class="stat-card">
                <div class="stat-label">Emulated Device</div>
                <div class="stat-value">📱 {html.escape(device)} ({html.escape(orientation)})</div>
            </div>
            """

        # Seed stat card
        seed_val = data.get("seed")
        seed_stat_card = ""
        if seed_val is not None:
            seed_stat_card = f"""
            <div class="stat-card">
                <div class="stat-label">Random Seed</div>
                <div class="stat-value" style="font-family: monospace;">🎲 {html.escape(str(seed_val))}</div>
            </div>
            """

        # API Chaos stat card
        api_faults = data.get("api_faults", [])
        api_stat_card = ""
        if api_faults:
            api_stat_card = f"""
            <div class="stat-card">
                <div class="stat-label">Injected API Faults</div>
                <div class="stat-value" style="color: var(--accent-yellow);">⚡ {len(api_faults)}</div>
            </div>
            """

        # Mobile & Responsive layout audit section
        layout_html = ""
        if device:
            if layout_issues:
                issues_li = "".join(f'<li style="margin-bottom: 6px;">{html.escape(issue)}</li>' for issue in layout_issues)
                layout_html = f"""
                <div class="card">
                    <h2>📱 Mobile & Responsive Layout Audit</h2>
                    <div style="background-color: #21262d; border-radius: 6px; padding: 16px; border-left: 4px solid var(--accent-red);">
                        <p style="margin-top: 0; font-weight: bold; color: var(--accent-red);">⚠ Responsive Design Anomalies Detected ({html.escape(device)}):</p>
                        <ul style="margin: 0; padding-left: 20px; color: #e6edf3;">
                            {issues_li}
                        </ul>
                    </div>
                </div>
                """
            else:
                layout_html = f"""
                <div class="card">
                    <h2>📱 Mobile & Responsive Layout Audit</h2>
                    <div class="no-errors">
                        🛡️ Zero mobile layout overflows detected on {html.escape(device)} ({html.escape(orientation)}). Clean responsive scaling.
                    </div>
                </div>
                """

        # Concurrency probe section (multi-lane synchronized click)
        concurrency_html = ""
        if concurrency > 1 and concurrency_lanes:
            success_count = sum(
                1 for lane in concurrency_lanes
                for r in (lane.get("responses") or [])
                if cls._safe_int(r.get("status"), 0) < 400
            )
            lane_rows = ""
            for lane in concurrency_lanes:
                lane_responses = lane.get("responses") or []
                lane_crashes = lane.get("crashes") or []
                statuses = ", ".join(
                    f"{r.get('method', 'REQ')} {r.get('status') if r.get('status') is not None else 'N/A'}"
                    for r in lane_responses
                ) or "—"
                crash_text = "; ".join(str(c) for c in lane_crashes) or "none"
                lane_rows += f"""
                <tr>
                    <td>Lane {lane.get('lane')}</td>
                    <td style="font-family: monospace; font-size: 12px;">{html.escape(str(lane.get('selector') or 'n/a'))}</td>
                    <td style="font-size: 12px;">{html.escape(statuses)}</td>
                    <td style="font-size: 12px; color: var(--accent-red);">{html.escape(crash_text)}</td>
                </tr>
                """
            warning_banner = ""
            if success_count > 1:
                warning_banner = f"""
                <div style="background-color: #21262d; border-radius: 6px; padding: 16px; border-left: 4px solid var(--accent-red); margin-bottom: 16px;">
                    <strong style="color: var(--accent-red);">⚠ {success_count} lanes recorded a successful response for the same synchronized action.</strong>
                    Inspect the target endpoint for a missing server-side idempotency lock.
                </div>
                """
            concurrency_html = f"""
            <div class="card">
                <h2>🔀 Concurrency Probe ({concurrency} synchronized lanes)</h2>
                {warning_banner}
                <table>
                    <thead>
                        <tr><th>Lane</th><th>Target Selector</th><th>Tracked Responses</th><th>Crashes</th></tr>
                    </thead>
                    <tbody>
                        {lane_rows}
                    </tbody>
                </table>
            </div>
            """

        # Ghost in the Wire: API & Session Chaos Telemetry
        api_faults = data.get("api_faults", [])
        api_chaos_html = ""
        freeze_issues = [x for x in layout_issues if "[UI Freeze" in str(x) or "Blank Screen" in str(x)]
        if api_faults or freeze_issues:
            freeze_banner = ""
            if freeze_issues:
                lis = "".join(f"<li>{html.escape(str(issue))}</li>" for issue in freeze_issues)
                freeze_banner = f"""
                <div style="background-color: rgba(248, 81, 73, 0.15); border-left: 4px solid var(--accent-red); padding: 14px 18px; border-radius: 6px; margin-bottom: 16px;">
                    <strong style="color: var(--accent-red);">⚠ Critical UI Freeze / Blank Screen Sniffed!</strong>
                    <p style="margin: 6px 0 0 0; color: #f0f6fc; font-size: 13px;">
                        The client application failed gracefully: unhandled promise rejections, unmounted component trees, or an infinite spinner were detected following API disruption.
                    </p>
                    <ul style="margin-top: 8px; margin-bottom: 0; padding-left: 20px; font-size: 12px; font-family: monospace; color: #ff7b72;">
                        {lis}
                    </ul>
                </div>
                """
            elif api_faults:
                freeze_banner = """
                <div style="background-color: rgba(63, 185, 80, 0.1); border-left: 4px solid var(--accent-green); padding: 10px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; color: var(--accent-green);">
                    🛡️ UI Resilience Verified: Application maintained DOM rendering integrity without unmounting or infinite loading during semantic API faults.
                </div>
                """

            type_counts: dict[str, int] = {}
            for f in api_faults:
                ft = str(f.get("fault_type") or f.get("strategy") or "API Fault")
                type_counts[ft] = type_counts.get(ft, 0) + 1

            pill_badges = " ".join(
                f'<span class="badge badge-warning" style="margin-right: 6px; font-size: 11px;">{html.escape(k)}: {v}</span>'
                for k, v in type_counts.items()
            )

            fault_rows = ""
            for f in api_faults:
                method = html.escape(str(f.get("method") or "GET"))
                url = html.escape(str(f.get("url") or ""))
                ftype = html.escape(str(f.get("fault_type") or f.get("strategy") or "API Fault"))
                status = f.get("injected_status") if f.get("injected_status") is not None else f.get("status")
                if status is not None and str(status).strip() != "":
                    try:
                        status_num = int(status)
                        status_cls = "badge-danger" if status_num >= 500 else ("badge-warning" if status_num >= 400 else "badge-success")
                        status_html = f'<span class="badge {status_cls}">{status_num}</span>'
                    except (ValueError, TypeError):
                        status_html = f'<span class="badge badge-warning">{html.escape(str(status))}</span>'
                else:
                    status_html = '<span class="badge badge-warning">Mutated</span>'

                details_obj = f.get("details", {})
                if isinstance(details_obj, dict):
                    if "stripped_keys" in details_obj:
                        details_str = f"Stripped keys: <code>{html.escape(str(details_obj['stripped_keys']))}</code>"
                    elif "strategy" in details_obj:
                        details_str = f"Strategy: <code>{html.escape(str(details_obj['strategy']))}</code>"
                    elif "error_payload" in details_obj:
                        details_str = f"Payload: <code>{html.escape(json.dumps(details_obj['error_payload']))}</code>"
                    elif "mutated_keys" in details_obj:
                        details_str = f"Mutated keys: <code>{html.escape(str(details_obj['mutated_keys']))}</code>"
                    else:
                        details_str = f"<code>{html.escape(json.dumps(details_obj)[:100])}</code>"
                else:
                    details_str = html.escape(str(details_obj)[:100])

                fault_rows += f"""
                <tr>
                    <td style="font-weight: bold; font-family: monospace;">{method}</td>
                    <td style="text-align: center;">{status_html}</td>
                    <td style="font-family: monospace; font-size: 12px; color: var(--accent-yellow);">{ftype}</td>
                    <td style="font-family: monospace; font-size: 12px; word-break: break-all;">{url}</td>
                    <td style="font-size: 12px; color: #8b949e;">{details_str}</td>
                </tr>
                """

            if not fault_rows:
                fault_rows = '<tr><td colspan="5" style="text-align: center; color: #8b949e; padding: 16px;">Zero in-flight network faults recorded.</td></tr>'

            api_chaos_html = f"""
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                    <h2 style="margin: 0;">⚡ Ghost in the Wire: API & Session Chaos Telemetry</h2>
                    <div>{pill_badges}</div>
                </div>
                <p style="color: var(--text-dim); font-size: 13px; margin-top: 0; margin-bottom: 14px;">
                    Synthetic in-flight semantic fault injection intercepted network traffic to verify frontend fault tolerance, auth token recovery, and error boundary resilience.
                </p>
                {freeze_banner}
                <table>
                    <thead>
                        <tr>
                            <th style="width: 8%;">Method</th>
                            <th style="width: 10%; text-align: center;">Injected</th>
                            <th style="width: 20%;">Fault Vector</th>
                            <th style="width: 32%;">Target Endpoint</th>
                            <th style="width: 30%;">Mutation / Payload Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {fault_rows}
                    </tbody>
                </table>
            </div>
            """

        # Sanitized Network HAR section
        har_html = ""
        har_file = data.get("har_file")
        if har_file and (output_file.parent / har_file).exists():
            try:
                with open(output_file.parent / har_file, encoding="utf-8") as f:
                    har_data = json.load(f)
                entries = har_data.get("log", {}).get("entries", [])
                if entries:
                    req_rows = ""
                    for entry in entries[:25]:
                        req = entry.get("request") or {}
                        res = entry.get("response") or {}
                        method = html.escape(str(req.get("method") or "GET"))
                        req_url = html.escape(str(req.get("url") or ""))
                        raw_status = res.get("status")
                        status_code = cls._safe_int(raw_status, 0)
                        status_cls = "badge-success" if 200 <= status_code < 400 else ("badge-danger" if status_code >= 500 else "badge-warning")
                        status_display = html.escape(str(raw_status if raw_status is not None else status_code))
                        entry_time = entry.get("time")
                        time_ms = f"{cls._safe_int(entry_time, 0):.0f}ms" if entry_time is not None else "0ms"
                        req_rows += f"""
                        <tr>
                            <td style="font-weight: bold; font-family: monospace;">{method}</td>
                            <td style="text-align: center;"><span class="badge {status_cls}">{status_display}</span></td>
                            <td style="font-family: monospace; font-size: 12px; word-break: break-all;">{req_url}</td>
                            <td style="text-align: right; color: #8b949e; font-size: 12px;">{time_ms}</td>
                        </tr>
                        """

                    har_html = f"""
                    <div class="card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <h2 style="margin: 0;">🌐 Sanitized Network Archive ({len(entries)} requests)</h2>
                            <span class="badge badge-success" style="font-size: 11px;">🔒 Auth & Cookies Redacted</span>
                        </div>
                        <p style="color: var(--text-dim); font-size: 13px; margin-top: 0;">
                            All authorization headers, session cookies, and API keys have been scrubbed by <strong>LOKI Network Scrubber</strong>.
                            Trace file: <code>{html.escape(har_file)}</code>.
                        </p>
                        <table>
                            <thead>
                                <tr>
                                    <th style="width: 10%;">Method</th>
                                    <th style="width: 10%; text-align: center;">Status</th>
                                    <th style="width: 65%;">Target Endpoint (Scrubbed)</th>
                                    <th style="width: 15%; text-align: right;">Latency</th>
                                </tr>
                            </thead>
                            <tbody>
                                {req_rows}
                            </tbody>
                        </table>
                    </div>
                    """
            except Exception:
                pass

        html_content = render(
            "report.html",
            run_id=run_id,
            timestamp=timestamp,
            verdict_badge=verdict_badge,
            target_url=target_url,
            persona=persona,
            failures_stat_card=failures_stat_card,
            browser_stat_card=browser_stat_card,
            device_stat_card=device_stat_card,
            seed_stat_card=seed_stat_card,
            api_stat_card=api_stat_card,
            duration=duration,
            actions_count=len(actions),
            video_html=video_html,
            layout_html=layout_html,
            concurrency_html=concurrency_html,
            api_chaos_html=api_chaos_html,
            rules_rows=rules_rows,
            crashes_html=crashes_html,
            har_html=har_html,
            actions_html=actions_html,
        )
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_file
