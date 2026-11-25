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
        self.assertIn("lanes=(pr-body pr-comment pr-review-body pr-review-comment commit-comment)", section)
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
    def run_case(self, case, *, reconcile=False, cutoff=""):
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
    elif [[ "$1" == rev-parse ]]; then
        if [[ -f "$UNPUSHED" ]]; then echo bbbbb; else echo aaaaa; fi
    elif [[ "$1" == ls-remote ]]; then
        if [[ "$CASE" == branch-error ]]; then return 128; fi
        return 2
    fi
    return 0
}
sleep() { :; }
date() {
    if [[ "$CASE" == deadline ]] && [[ -s "$CALLS" ]]; then echo 3000; else echo 0; fi
}
python() {
    if [[ "$*" == *history_archive.inventory_commit* ]]; then
        if [[ "$CASE" == stale-inventory ]]; then return 1; fi
        if [[ "$CASE" == unavailable ]]; then
            echo '{"state":"VERIFIED","source_count":3,"available_indices":[1,3],"unavailable_indices":[2]}'
        else
            echo '{"state":"VERIFIED","source_count":3,"available_indices":[1,2,3],"unavailable_indices":[]}'
        fi
        return 0
    fi
    local index="" lane="" reconcile=no
    while (( $# )); do
        case "$1" in
            --source-index) index="$2"; shift ;;
            --lane) lane="$2"; shift ;;
            --reconcile-complete) reconcile=yes ;;
            --reconcile-before) reconcile="$2"; shift ;;
        esac
        shift
    done
    local key="$index/$lane" n
    n=$(grep -c "^$key " "$CALLS" || true)
    echo "$key $reconcile" >> "$CALLS"
    if [[ "$key" == "1/pr-body" ]]; then
        if [[ "$CASE" == dirty ]]; then touch "$DIRTY"; fi
        if [[ "$CASE" == unpushed ]]; then touch "$UNPUSHED"; fi
        if [[ "$CASE" == global ]]; then
            echo '{"state":"FAILED","error_code":"NO_SOURCE_TOKEN"}' >&2
            return 1
        fi
        if [[ "$CASE" == persistent || "$CASE" == dirty || "$n" == 0 ]]; then
            echo '{"state":"FAILED","error_code":"SOURCE_OR_CHECKPOINT_FAILURE","raw":"NEVER_LOG_THIS"}' >&2
            return 1
        fi
    fi
    if [[ "$key" == "2/pr-comment" && ( "$n" == 0 || "$CASE" == partial ) ]]; then
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
                       RECONCILE_BEFORE=cutoff,
                       INVENTORY_GENERATION="a" * 40,
                       GITHUB_STEP_SUMMARY=str(summary), CALLS=str(calls),
                       DIRTY=str(root / "dirty"), UNPUSHED=str(root / "unpushed"), CASE=case)
            # Use a file rather than a large Windows bash -c argument.
            script_path = root / "workflow-test.sh"
            script_path.write_text(prelude + "\n" + script, encoding="utf-8", newline="\n")
            syntax = subprocess.run([bash, "-n", script_path.as_posix()],
                                    cwd=work, env=env, text=True,
                                    capture_output=True, timeout=15)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
            proc = subprocess.run([bash, script_path.as_posix()],
                                  cwd=work, env=env, text=True,
                                  capture_output=True, timeout=60)
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

    def test_deadline_reports_unattempted_without_retry(self):
        proc, calls, report = self.run_case("deadline")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls, ["1/pr-body no"])
        self.assertIn("Deadline reached: 1", report)
        self.assertIn("Unattempted lanes: 14", report)
        self.assertIn("Final retries attempted: 0", report)

    def test_branch_lookup_failure_is_not_a_missing_branch(self):
        proc, calls, _ = self.run_case("branch-error")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls, [])
        self.assertIn("Cannot verify private evidence branch", proc.stdout)

    def test_bounded_active_lane_does_not_prevent_later_sources(self):
        proc, calls, report = self.run_case("partial")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(calls.count("2/pr-comment no"), 2)
        self.assertEqual(calls.count("1/pr-body no"), 2)
        self.assertIn("Active lanes: 1", report)
        self.assertIn("Complete lanes: 14/15", report)

    def test_clean_unpushed_commit_is_not_discarded(self):
        proc, calls, _ = self.run_case("unpushed")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls, ["1/pr-body no"])
        self.assertIn("Unverified private commit prevents safe branch switch", proc.stdout)

    def test_global_config_failure_is_not_retried(self):
        proc, calls, _ = self.run_case("global")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls, ["1/pr-body no"])
        self.assertIn("Global collector configuration failure", proc.stdout)

    def test_cutoff_is_forwarded_only_until_confirmed_lane_progress(self):
        cutoff = "2026-11-24T00:00:00Z"
        proc, calls, report = self.run_case("recover", cutoff=cutoff)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2/pr-comment " + cutoff, calls)
        self.assertIn("2/pr-comment no", calls)
        self.assertEqual(calls.count("1/pr-body " + cutoff), 2)
        self.assertIn("Complete lanes: 15/15", report)

    def test_cutoff_conflict_or_invalid_value_refuses_all_collectors(self):
        for reconcile, cutoff in ((True, "2026-11-24T00:00:00Z"), (False, "not-a-timestamp")):
            with self.subTest(reconcile=reconcile, cutoff=cutoff):
                proc, calls, _ = self.run_case("recover", reconcile=reconcile, cutoff=cutoff)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(calls, [])
                self.assertIn("Invalid or conflicting reconciliation cutoff", proc.stdout)

    def test_unavailable_inventory_source_keeps_original_indices(self):
        proc, calls, report = self.run_case("unavailable")
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(any(call.startswith("2/") for call in calls))
        self.assertIn("3/commit-comment no", calls)
        self.assertIn("Unavailable lanes: 5", report)
        self.assertIn("Complete lanes: 10/15", report)

    def test_unverified_inventory_refuses_all_collectors(self):
        proc, calls, _ = self.run_case("stale-inventory")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls, [])
        self.assertIn("Shared inventory generation is not verified", proc.stdout)


class SharedInventoryGenerationTests(unittest.TestCase):
    def test_single_refresh_and_pinned_consumers(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        refresh = content.split("\n  inventory-refresh:\n", 1)[1].split("\n  archive-fleet:\n", 1)[0]
        fleet = content.split("\n  archive-fleet:\n", 1)[1].split("\n  archive-v02-manual:\n", 1)[0]
        typed = content.split("\n  archive-v02-manual:\n", 1)[1]
        self.assertEqual(content.count("history_archive.inventory_commit refresh"), 1)
        self.assertIn("github.ref == 'refs/heads/main'", refresh)
        self.assertIn("permission-issues: read", refresh)
        self.assertIn("repositories: github-history-archive", refresh)
        self.assertIn("permission-contents: write", refresh)
        for job in (fleet, typed):
            self.assertIn("needs: inventory-refresh", job)
            self.assertIn("ref: ${{ needs.inventory-refresh.outputs.generation }}", job)
            self.assertIn("history_archive.inventory_commit inspect", job)
            self.assertIn("available_indices | index($i)", job)
            self.assertIn("persist-credentials: false", job)
        self.assertIn('--sources "$inventory"', fleet)
        self.assertIn('inventory=../history-code/config/fleet-repositories.txt', typed)


if __name__ == "__main__":
    unittest.main()
