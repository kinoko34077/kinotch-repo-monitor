import threading
import time
import unittest

from repo_monitor.devflow_state import DevflowStateProvider, parse_control_issues


ISSUE_BODY = """## Repository

`kinoko34077/example-repo`

## Work Status

`IMPLEMENTING`

## Type

`FEATURE`

## Repository State

`ACTIVE`

## Active Work

`example-repo#12` — implement the feature.

## Next Action

`VERIFY — run CI`
"""


def issue_payload():
    return [
        {
            "number": 59,
            "title": "[REPO] example-repo",
            "body": ISSUE_BODY,
            "html_url": "https://github.com/kinoko34077/devflow/issues/59",
            "updated_at": "2026-09-26T03:00:00Z",
        }
    ]


class DevflowStateTests(unittest.TestCase):
    def test_parse_control_issues_extracts_repository_workflow_fields(self):
        issues = issue_payload() + [
            {
                "number": 60,
                "title": "[SYSTEM] ignore me",
                "body": "not a repository control issue",
                "html_url": "https://github.com/kinoko34077/devflow/issues/60",
            },
        ]

        states = parse_control_issues(issues)

        self.assertEqual(list(states), ["example-repo"])
        state = states["example-repo"]
        self.assertEqual(state.work_status, "IMPLEMENTING")
        self.assertEqual(state.repository_state, "ACTIVE")
        self.assertEqual(state.active_work, "example-repo#12 — implement the feature.")
        self.assertEqual(state.next_action, "VERIFY — run CI")
        self.assertEqual(state.issue_number, 59)
        self.assertEqual(state.issue_url, "https://github.com/kinoko34077/devflow/issues/59")
        self.assertEqual(state.updated_at, "2026-09-26T03:00:00Z")

    def test_provider_caches_one_public_issue_fetch_until_ttl_expires(self):
        calls = []
        now = [1000.0]

        def fetcher():
            calls.append(now[0])
            return issue_payload()

        provider = DevflowStateProvider(fetcher=fetcher, clock=lambda: now[0], ttl_seconds=120.0)

        first = provider.snapshot()
        second = provider.snapshot()
        now[0] += 119.0
        third = provider.snapshot()

        self.assertEqual(len(calls), 1)
        self.assertFalse(first.stale)
        self.assertEqual(first.repositories["example-repo"].work_status, "IMPLEMENTING")
        self.assertEqual(second.repositories, first.repositories)
        self.assertEqual(third.repositories, first.repositories)

        now[0] += 2.0
        provider.snapshot()
        self.assertEqual(len(calls), 2)

    def test_provider_keeps_last_successful_state_when_refresh_fails(self):
        calls = [0]
        now = [1000.0]

        def fetcher():
            calls[0] += 1
            if calls[0] == 1:
                return issue_payload()
            raise OSError("network down")

        provider = DevflowStateProvider(fetcher=fetcher, clock=lambda: now[0], ttl_seconds=120.0, retry_seconds=30.0)
        provider.snapshot()
        now[0] += 121.0

        failed = provider.snapshot()
        immediate_retry = provider.snapshot()

        self.assertTrue(failed.stale)
        self.assertIn("network down", failed.error)
        self.assertIn("example-repo", failed.repositories)
        self.assertEqual(immediate_retry.repositories, failed.repositories)
        self.assertEqual(calls[0], 2)

    def test_nonblocking_snapshot_refreshes_in_background_without_duplicate_fetches(self):
        started = threading.Event()
        release = threading.Event()
        calls = [0]

        def fetcher():
            calls[0] += 1
            started.set()
            release.wait(timeout=2.0)
            return issue_payload()

        provider = DevflowStateProvider(fetcher=fetcher, ttl_seconds=120.0)

        initial = provider.snapshot_nonblocking()
        self.assertEqual(initial.repositories, {})
        self.assertTrue(started.wait(timeout=0.5))

        while_running = provider.snapshot_nonblocking()
        self.assertEqual(while_running.repositories, {})
        self.assertEqual(calls[0], 1)

        release.set()
        deadline = time.monotonic() + 1.0
        completed = provider.snapshot_nonblocking()
        while "example-repo" not in completed.repositories and time.monotonic() < deadline:
            time.sleep(0.01)
            completed = provider.snapshot_nonblocking()

        self.assertIn("example-repo", completed.repositories)
        self.assertEqual(calls[0], 1)


if __name__ == "__main__":
    unittest.main()
