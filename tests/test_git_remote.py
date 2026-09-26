import subprocess
import unittest
from pathlib import PureWindowsPath
from unittest.mock import Mock, patch

from repo_monitor import git_inspector


class GitRemoteTests(unittest.TestCase):
    def test_run_git_uses_git_normalized_process_local_safe_directory(self):
        repo = Mock()
        repo.resolve.return_value = PureWindowsPath(r"C:\Users\kinok\Documents\Programs\IDS-Composit")
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("repo_monitor.git_inspector.subprocess.run", return_value=completed) as run:
            git_inspector._run_git(repo, "status")

        command = run.call_args.args[0]
        self.assertEqual(command[0], "git")
        self.assertEqual(
            command[1:3],
            ["-c", "safe.directory=C:/Users/kinok/Documents/Programs/IDS-Composit"],
        )
        self.assertEqual(command[3], "--no-pager")

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
