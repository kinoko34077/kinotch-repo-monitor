import json
import tempfile
import unittest
from pathlib import Path

from tools.browser_audit import (
    CheckResult,
    build_report,
    inspect_geometry,
    read_devtools_active_port,
    summarize_checks,
)


class BrowserAuditContractTests(unittest.TestCase):
    def test_active_port_retries_transient_permission_and_partial_file(self):
        class FlakyPath:
            def __init__(self):
                self.calls = 0

            def exists(self):
                return True

            def read_text(self, encoding):
                self.calls += 1
                if self.calls == 1:
                    raise PermissionError("sharing violation")
                if self.calls == 2:
                    return ""
                return "9222\n/devtools/browser/abc"

        path = FlakyPath()
        sleeps = []
        port = read_devtools_active_port(
            path,
            timeout=0.2,
            sleep=lambda delay: sleeps.append(delay),
            clock=iter([0.0, 0.01, 0.02, 0.03]).__next__,
        )

        self.assertEqual(port, 9222)
        self.assertEqual(path.calls, 3)
        self.assertTrue(sleeps)

    def test_narrow_geometry_reports_horizontal_overflow_and_clipping(self):
        result = inspect_geometry(
            {
                "scroll_width": 412,
                "client_width": 360,
                "controls": [
                    {"name": "search", "left": 8, "top": 12, "right": 352, "bottom": 48},
                    {"name": "refresh", "left": 364, "top": 12, "right": 420, "bottom": 48},
                ],
            },
            viewport_width=360,
            viewport_height=800,
        )

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.measured["horizontal_overflow"])
        self.assertEqual(result.measured["clipped_controls"], ["refresh"])

    def test_below_fold_controls_are_reported_without_false_clipping_failure(self):
        result = inspect_geometry(
            {
                "scroll_width": 360,
                "client_width": 360,
                "controls": [
                    {"name": "card-chat", "left": 16, "top": 900, "right": 88, "bottom": 932},
                ],
            },
            viewport_width=360,
            viewport_height=800,
        )

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.measured["clipped_controls"], [])
        self.assertEqual(result.measured["out_of_viewport_controls"], ["card-chat"])

    def test_report_is_machine_readable_and_keeps_residual_boundary_narrow(self):
        checks = [
            CheckResult(
                name="accessibility.screen_reader_speech",
                status="WARN",
                measured={"verified": False},
                rule="CDP AX tree does not prove speech output",
                error="screen reader process not attached",
            ),
            CheckResult(
                name="runtime.api_state",
                status="PASS",
                measured={"count": 3},
                rule="at least one successful /api/state timing",
            ),
        ]
        report = build_report(
            url="http://127.0.0.1:17341/",
            browser="Chrome",
            mode="demo",
            viewport={"width": 1440, "height": 900},
            checks=checks,
            residual_boundaries=["actual screen-reader speech output was not attached"],
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["url"], "http://127.0.0.1:17341/")
        self.assertEqual(loaded["checks"][0]["status"], "WARN")
        self.assertEqual(loaded["residual_boundaries"], ["actual screen-reader speech output was not attached"])

    def test_summary_preserves_warn_without_turning_it_into_failure(self):
        output = summarize_checks(
            [
                CheckResult(name="runtime.api_state", status="PASS", measured={"count": 2}),
                CheckResult(name="accessibility.speech", status="WARN", measured={}),
            ]
        )

        self.assertIn("runtime.api_state=PASS", output)
        self.assertIn("accessibility.speech=WARN", output)
        self.assertIn("overall=PASS WITH NON-BLOCKING BOUNDARY", output)


if __name__ == "__main__":
    unittest.main()
