"""A bounded manual v0.2 run must resume/checkpoint, pause and stop safely."""
from pathlib import Path
import unittest

WORKFLOW = (Path(__file__).resolve().parents[1] /
            ".github/workflows/history-archive-fleet-hourly.yml")


class V02CycleDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.job = cls.workflow.split("  archive-v02-manual:", 1)[1]

    def test_configurable_bounded_cycles_and_pause(self):
        s = self.workflow
        self.assertIn("      manual_v02_cycles:", s)
        self.assertIn("      manual_v02_pause_seconds:", s)
        self.assertIn("MAX_V02_CYCLES: ${{ inputs.manual_v02_cycles }}", s)
        self.assertIn("V02_PAUSE_SECONDS: ${{ inputs.manual_v02_pause_seconds }}", s)
        self.assertIn('^([0-9]|[1-5][0-9]|60)$', s)
        self.assertIn('^(1[0-2]|[1-9])$', s)
        self.assertIn('deadline=$((started_at + 45 * 60))', s)
        self.assertIn('for ((cycle=1; cycle<=${MAX_V02_CYCLES:-1}; cycle++)); do', s)
        self.assertIn('sleep "${V02_PAUSE_SECONDS:-5}"', s)

    def test_failed_lanes_defer_and_resume_preserves_safety(self):
        s = self.job
        self.assertIn('COMPLETE|FAILED) continue ;;', s)
        self.assertIn('run_lane "$index" "$lane" retry', s)
        self.assertIn('if (( fail > 0 )); then', s)
        self.assertIn('git ls-remote --exit-code origin "refs/heads/$branch"', s)
        self.assertIn('git switch -q -C "$branch" FETCH_HEAD', s)
        self.assertIn('args+=(--reconcile-complete)', s)
        self.assertIn('Unverified private commit prevents safe branch switch', s)
        self.assertIn('NOT_ATTEMPTED: $key', s)

    def test_public_runner_does_not_execute_duplicate_v01_fleet(self):
        s = self.workflow
        self.assertIn('&& !inputs.manual_v02_only)', s)
        self.assertIn('(inputs.manual_all_seven || inputs.manual_v02_only)', s)
        self.assertIn('manual_v02_only:', s)
        self.assertIn('permission-pull-requests: read', s)
        self.assertIn('repositories: github-history-archive\n          permission-contents: write', s)
        self.assertNotIn("permission-pull-requests: write", s)


if __name__ == "__main__":
    unittest.main()
