from __future__ import annotations

import base64
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, call, patch

from tools.render_check import render_with_browser


class RenderCheckBrowserTests(unittest.TestCase):
    def test_render_reuses_devtools_session_and_writes_screenshot(self):
        browser = Path("unused-edge.exe")
        url = "http://127.0.0.1:17341/"
        screenshot_data = b"P" * 1100
        devtools = Mock()
        devtools.call.side_effect = lambda method, params=None: (
            {"data": base64.b64encode(screenshot_data).decode("ascii")}
            if method == "Page.captureScreenshot"
            else {}
        )

        with tempfile.TemporaryDirectory() as directory:
            screenshot = Path(directory) / "render.png"
            with patch(
                "tools.browser_audit.browser_connection",
                return_value=nullcontext((devtools, str(browser))),
            ) as browser_connection:
                with patch("tools.browser_audit.wait_until") as wait_until:
                    render_with_browser(browser, url, screenshot)
                browser_connection.assert_called_once_with(
                    browser, url, headed=False, attach_port=None
                )
                wait_until.assert_called_once_with(
                    devtools,
                    "document.readyState === 'complete' && document.querySelectorAll('.repo-card').length === 2",
                )
                self.assertIn(
                    call(
                        "Page.captureScreenshot",
                        {"format": "png", "captureBeyondViewport": False},
                    ),
                    devtools.call.call_args_list,
                )
                self.assertEqual(screenshot.read_bytes(), screenshot_data)


if __name__ == "__main__":
    unittest.main()
