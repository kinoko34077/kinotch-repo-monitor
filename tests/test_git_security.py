import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_monitor.git_inspector import _run_git


class GitInspectionSecurityTests(unittest.TestCase):
    @patch("repo_monitor.git_inspector.subprocess.run")
    def test_run_git_disables_fsmonitor_without_force_trusting_repository(self, run):
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        repo = Path("repo")

        _run_git(repo, "status", "--porcelain=v2")

        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["git", "-c", "core.fsmonitor=false"])
        self.assertFalse(any(arg.startswith("safe.directory=") for arg in command))
        self.assertIn("--no-pager", command)
        self.assertEqual(run.call_args.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")

    @patch("repo_monitor.git_inspector.subprocess.run")
    def test_run_git_surfaces_dubious_ownership_instead_of_bypassing_it(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=128,
            stdout="",
            stderr="fatal: detected dubious ownership in repository at 'X:/repo'",
        )

        with self.assertRaisesRegex(RuntimeError, "dubious ownership"):
            _run_git(Path("repo"), "status", "--porcelain=v2")


if __name__ == "__main__":
    unittest.main()
