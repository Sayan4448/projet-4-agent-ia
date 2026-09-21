"""Exercise the application's browser driver on a local fixture, without AI."""
import base64
from pathlib import Path
import tempfile
from unittest.mock import patch

from agent_screen.browser_mode import BrowserSession


def main():
    with tempfile.TemporaryDirectory() as tmp, \
         patch("agent_screen.browser_mode.data_dir", return_value=Path(tmp)):
        browser = BrowserSession()
        try:
            browser.start()
            browser.page.set_content("<html><body><input id='text' style='position:absolute;left:80px;top:80px;width:300px;height:60px'>"
                                     "<button style='position:absolute;left:80px;top:180px;width:300px;height:60px' "
                                     "onclick=\"document.getElementById('result').textContent=document.getElementById('text').value\">Copier</button>"
                                     "<p id='result' style='position:absolute;top:300px'></p></body></html>")
            image = browser.screenshot(640, 60, True)
            assert base64.b64decode(image).startswith(b"\xff\xd8")
            browser.execute("mouse_click", {"x": 80, "y": 55})
            browser.execute("type_text", {"text": "Bonjour été — navigateur"})
            browser.execute("mouse_click", {"x": 80, "y": 105})
            assert browser.page.locator("#result").inner_text() == "Bonjour été — navigateur"
            assert browser.execute("hotkey", {"keys": ["ctrl", "a"]})["ok"]
            try:
                browser.execute("run_terminal_command", {"command": "Write-Output test"})
                raise AssertionError("Desktop action accepted")
            except ValueError:
                pass
            print("PASS: dedicated browser, scaled screenshot, page clicks, Unicode input, browser-only action restriction")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
