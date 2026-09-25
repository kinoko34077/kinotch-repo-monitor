import unittest
from pathlib import Path
from unittest.mock import patch

import repo_monitor
from repo_monitor import __main__


class EntrypointTests(unittest.TestCase):
    def test_normal_entrypoint_delegates_to_web_server(self):
        with patch("repo_monitor.web_server.serve", return_value=0) as serve:
            __main__.main(["--port", "17777", "--no-browser"])
        serve.assert_called_once_with(host="127.0.0.1", port=17777, open_browser=False)

    def test_entrypoint_source_has_no_tkinter_dependency(self):
        source = (Path(repo_monitor.__file__).resolve().parent / "__main__.py").read_text(encoding="utf-8")
        self.assertNotIn("tkinter", source)
        self.assertIn("web_server", source)


if __name__ == "__main__":
    unittest.main()
