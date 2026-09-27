import subprocess
import unittest
from unittest.mock import Mock, patch

from repo_monitor import git_inspector


class GitRemoteTests(unittest.TestCase):
    def test_run_git_disables_fsmonitor_without_safe_directory_override(self):
        repo = Mock()
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("repo_monitor.git_inspector.subprocess.run", return_value=completed) as run:
            git_inspector._run_git(repo, "status")

        command = run.call_args.args[0]
        self.assertEqual(command[0], "git")
        self.assertEqual(command[1:3], ["-c", "core.fsmonitor=false"])
        self.assertEqual(command[3], "--no-pager")
        self.assertFalse(any(arg.startswith("safe.directory=") for arg in command))

    def test_remote_url_normalizes_common_browser_destinations(self):
        convert = getattr(git_inspector, "remote_to_web_url", lambda _value: "")
        cases = {
            "https://github.com/kinoko34077/kinotch-repo-monitor.git": "https://github.com/kinoko34077/kinotch-repo-monitor",
            "git@github.com:kinoko34077/kinotch-repo-monitor.git": "https://github.com/kinoko34077/kinotch-repo-monitor",
            "ssh://git@gitlab.com/group/repo.git": "https://gitlab.com/group/repo",
            "https://example.com/team/repo": "https://example.com/team/repo",
            "file:///C:/repo": "",
            "C:/repo": "",
            r"C:\repo": "",
            "../repo.git": "",
        }
        for remote, expected in cases.items():
            with self.subTest(remote=remote):
                self.assertEqual(convert(remote), expected)


if __name__ == "__main__":
    unittest.main()
