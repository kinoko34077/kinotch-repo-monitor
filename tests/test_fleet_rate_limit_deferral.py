"""Regression: provider rate-limit errors must not be retried blindly by fleet shell."""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/history-archive-fleet-hourly.yml"


class FleetRateLimitDeferralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_provider_limit_is_distinguished_from_other_transient_errors(self):
        expression = r'"error_code":"(graphql_rate_limit|rate_limited(_until_[0-9TZ]+)?)"'
        allowed = [
            '{"status":"ERROR","error_code":"graphql_rate_limit"}',
            '{"status":"ERROR","error_code":"rate_limited"}',
            '{"status":"ERROR","error_code":"rate_limited_until_20261102T155000Z"}',
        ]
        disallowed = [
            '{"status":"ERROR","error_code":"http_500"}',
            '{"status":"ERROR","error_code":"graphql_other_error"}',
            '{"status":"OK","error_code":null}',
        ]
        for line in allowed:
            with self.subTest(line=line):
                self.assertRegex(line, expression)
        for line in disallowed:
            with self.subTest(line=line):
                self.assertNotRegex(line, expression)
        self.assertIn(expression, self.text)

    def test_failure_cannot_be_marked_success_on_rate_limit(self):
        text = self.text
        self.assertIn('safe_scan_log="$(mktemp)"', text)
        self.assertIn('trap \'rm -f "$safe_scan_log"\' EXIT', text)
        self.assertIn('| tee "$safe_scan_log"; then', text)
        self.assertIn('grep -Eq', text)
        self.assertIn('"$safe_scan_log"; then\n                echo "::warning::Source index', text)
        self.assertIn('break\n              fi\n              echo "::warning::Source index', text)
        self.assertIn('failures=$((failures + 1))', text)
        self.assertIn('echo "::error::$failures sources were not completely scanned."', text)

    def test_source_scope_and_credentials_are_unchanged(self):
        text = self.text
        self.assertIn('cron: "11 * * * *"', text)
        self.assertIn('cron: "37 4 * * *"', text)
        self.assertIn('permission-issues: read', text)
        self.assertIn('permission-pull-requests: read', text)
        self.assertIn('permission-contents: write', text)
        self.assertIn('for index in $(seq "$first" "$last"); do', text)
        self.assertIn('for scan_attempt in 1 2 3; do', text)
        self.assertIn('git push -q origin HEAD:main', text)


if __name__ == "__main__":
    unittest.main()
