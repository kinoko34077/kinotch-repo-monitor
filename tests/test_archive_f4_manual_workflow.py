"""F4 manual seven-kind archive workflow contract; no network calls."""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "history-archive-fleet-hourly.yml"


class ManualSevenKindWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = WORKFLOW.read_text(encoding="utf-8")

    def test_schedules_and_explicit_manual_gate(self):
        self.assertIn('cron: "11 * * * *"', self.content)
        self.assertIn('cron: "37 4 * * *"', self.content)
        self.assertIn("manual_all_seven:", self.content)
        self.assertIn("manual_reconcile_complete:", self.content)
        self.assertIn("manual_v02_pages:", self.content)
        self.assertIn('"$' + '{{ inputs.manual_all_seven }}" == "true"', self.content)

    def test_opt_in_five_lanes_and_safe_resume(self):
        section = self.content.split("\n  archive-v02-manual:\n", 1)[1]
        self.assertIn("github.event_name == 'workflow_dispatch'", section.splitlines()[0])
        self.assertIn("inputs.manual_all_seven", section.splitlines()[0])
        self.assertIn("for lane in pr-body pr-comment pr-review-body pr-review-comment commit-comment", section)
        self.assertIn("--source-index", section)
        self.assertIn("--lane", section)
        self.assertIn("--reconcile-complete", section)
        self.assertIn("state=$state", section)

    def test_existing_token_permissions_and_fail_closed(self):
        section = self.content.split("\n  archive-v02-manual:\n", 1)[1]
        self.assertIn("permission-issues: read", section)
        self.assertIn("permission-pull-requests: read", section)
        self.assertIn("permission-contents: write", section)
        self.assertIn("repositories: github-history-archive", section)
        self.assertNotIn("permission-actions: write", section)
        self.assertNotIn("permission-administration: write", section)
        self.assertIn("Unpushed private evidence prevents safe branch switch", section)
        self.assertIn("FAILED or UNAVAILABLE; no completion inferred", section)
        self.assertIn("if (( fail > 0 )); then", section)



class ManualSchedulerBehaviorTests(unittest.TestCase):
    """Execute the real workflow shell against a deterministic fake collector."""
    def run_case(self, case, *, reconcile=False):
        import os
        import shutil
        import subprocess
        import tempfile
        import textwrap

        bash = shutil.which("bash")
        if not bash or not shutil.which("jq"):
            self.skipTest("bash and jq required for real shell regression")
        section = WORKFLOW.read_text(encoding="utf-8").split(
            "\n  archive-v02-manual:\n", 1)[1]
        script = textwrap.dedent(section.split("        run: |\n", 1)[1])
        script = script.replace(
            "\x24{{ inputs.manual_v02_only }}", "true")
        prelude = r'''
git() {
    if [[ "$1" == status ]]; then
        if [[ -f "$DIRTY" ]]; then echo ' M tracking/example.json'; fi
    elif [[ "$1" == ls-remote ]]; then
        return 1
    fi
    return 0
}
sleep() { :; }
python() {
    local index="" lane="" reconcile=no
    while (( $# )); do
        case "$1" in
            --source-index) index="$2"; shift ;;
            --lane) lane="$2"; shift ;;
            --reconcile-complete) reconcile=yes ;;
        esac
        shift
    done
    local key="$index/$lane" n
    n=$(grep -c "^$key " "$CALLS" || true)
    echo "$key $reconcile" >> "$CALLS"
    if [[ "$key" == "1/pr-body" ]]; then
        if [[ "$CASE" == dirty ]]; then touch "$DIRTY"; fi
        if [[ "$CASE" == persistent || "$CASE" == dirty || "$n" == 0 ]]; then
            echo '{"state":"FAILED","error_code":"SOURCE_OR_CHECKPOINT_FAILURE","raw":"NEVER_LOG_THIS"}' >&2
            return 1
        fi
    fi
    if [[ "$key" == "2/pr-comment" && "$n" == 0 ]]; then
        echo '{"state":"ACTIVE"}'
    else
        echo '{"state":"COMPLETE"}'
    fi
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "history-evidence"
            work.mkdir()
            config = root / "history-code" / "config"
            config.mkdir(parents=True)
            (config / "fleet-repositories.txt").write_text(
                "owner/one\nowner/two\nowner/three\n", encoding="utf-8")
            calls = root / "calls"
            calls.touch()
            summary = root / "summary"
            env = dict(os.environ, SOURCE_FIRST="1", SOURCE_LAST="3",
                       MAX_V02_PAGES="2", MAX_V02_CYCLES="2",
                       V02_PAUSE_SECONDS="0",
                       RECONCILE_COMPLETE=str(reconcile).lower(),
                       GITHUB_STEP_SUMMARY=str(summary), CALLS=str(calls),
                       DIRTY=str(root / "dirty"), CASE=case)
            proc = subprocess.run([bash, "-c", prelude + "\n" + script],
                                  cwd=work, env=env, text=True,
                                  capture_output=True, timeout=30)
            report = summary.read_text(encoding="utf-8") if summary.exists() else ""
            return proc, calls.read_text(encoding="utf-8").splitlines(), report

    def test_deferred_failure_retries_after_independent_work(self):
        proc, calls, report = self.run_case("recover", reconcile=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        keys = [c.split()[0] for c in calls]
        self.assertEqual(keys.count("1/pr-body"), 2)
        self.assertEqual(keys.count("2/pr-comment"), 2)
        self.assertEqual(keys.count("3/commit-comment"), 1)
        self.assertLess(keys.index("3/commit-comment"), keys.index("2/pr-comment", keys.index("2/pr-comment") + 1))
        self.assertEqual(keys[-1], "1/pr-body")
        self.assertIn("2/pr-comment no", calls)
        self.assertIn("Complete lanes: 15/15", report)
        self.assertNotIn("NEVER_LOG_THIS", proc.stdout + proc.stderr + report)

    def test_persistent_failure_is_not_success_and_other_lanes_continue(self):
        proc, calls, report = self.run_case("persistent")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls[-1], "1/pr-body no")
        self.assertIn("1/pr-comment no", calls)
        self.assertIn("3/commit-comment no", calls)
        self.assertIn("Final failed lanes: 1", report)
        self.assertIn("Complete lanes: 14/15", report)
        self.assertIn("SOURCE_OR_CHECKPOINT_FAILURE", proc.stdout + report)
        self.assertNotIn("NEVER_LOG_THIS", proc.stdout + proc.stderr + report)

    def test_dirty_failure_stops_before_another_lane(self):
        proc, calls, _ = self.run_case("dirty")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls, ["1/pr-body no"])
        self.assertIn("Failed source left unpushed evidence", proc.stdout)


if __name__ == "__main__":
    unittest.main()
