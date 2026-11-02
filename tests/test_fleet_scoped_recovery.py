"""Bounded manual recovery must not alter normal fleet schedule or permissions."""
from pathlib import Path
import unittest

FLEET = Path(__file__).resolve().parents[1] / ".github/workflows/history-archive-fleet-hourly.yml"

class ScopedFleetRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = FLEET.read_text(encoding="utf-8")

    def test_manual_inputs_are_number_typed_and_bounded(self):
        text = self.text
        self.assertIn("      start_source_index:", text)
        self.assertIn("      end_source_index:", text)
        self.assertIn("        type: number", text)
        self.assertIn("        default: 1", text)
        self.assertIn("        default: 0", text)
        self.assertIn("first=\"${MANUAL_FIRST:-1}\"", text)
        self.assertIn("last=\"${MANUAL_LAST:-0}\"", text)
        self.assertIn("(( first > last || last > total ))", text)
        self.assertIn('if [[ "$last" == "0" ]]; then last="$total"; fi', text)

    def test_schedule_is_unmodified_and_only_manual_can_scope(self):
        text = self.text
        self.assertIn('cron: "11 * * * *"', text)
        self.assertIn('cron: "37 4 * * *"', text)
        self.assertIn('if [[ "${{ github.event_name }}" == "workflow_dispatch" ]]; then', text)
        self.assertIn('first=1\n          last="$total"', text)
        self.assertIn('for index in $(seq "$first" "$last"); do', text)

    def test_resume_preserves_existing_source_and_archive_write_gates(self):
        text = self.text
        self.assertIn('permission-issues: read', text)
        self.assertIn('permission-pull-requests: read', text)
        self.assertIn('repositories: github-history-archive\n          permission-contents: write', text)
        self.assertIn('git add -A -- archive/ tracking/', text)
        self.assertIn('for attempt in 1 2 3 4; do', text)
        self.assertIn('echo "- Attempted source indices: $first-$last (count: $range_count)"', text)
        self.assertIn('if [[ "$failures" -ne 0 ]]; then', text)
        self.assertIn('if [[ "$scanned" -eq 1 ]]; then', text)

if __name__ == "__main__":
    unittest.main()
