"""Opt-in packaged browser smoke check, no AI and no external web requests."""
import json
from pathlib import Path
import tempfile


def browser_check(report):
    from . import __version__
    result = {"version": __version__, "ok": False}
    session = None
    try:
        from . import browser_mode
        original = browser_mode.data_dir
        session = browser_mode.BrowserSession()
        with tempfile.TemporaryDirectory() as tmp:
            browser_mode.data_dir = lambda: Path(tmp)
            try:
                try:
                    session.start()
                    result["mode"] = "headed"
                except Exception as e:
                    # CI runners have no reliable interactive display — a
                    # headless run still validates the packaged driver,
                    # page control, clicks and unicode typing.
                    result["headed_error"] = f"{type(e).__name__}: {e}"
                    session.close()
                    session = browser_mode.BrowserSession()
                    session.start(headless=True)
                    result["mode"] = "headless"
                session.page.set_content("<input style='position:absolute;left:40px;top:40px;width:300px;height:80px' id='check'>")
                session.screenshot(1280, 60, True)
                session.execute("mouse_click", {"x": 100, "y": 70})
                session.execute("type_text", {"text": "Bonjour été"})
                assert session.page.locator("#check").input_value() == "Bonjour été"
                result["ok"] = True
                result["checks"] = ["browser launch", "screenshot", "page click", "unicode input"]
            finally:
                session.close()
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if session is not None:
            browser_mode.data_dir = original
        try:
            output = Path(report)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            return False
    return result["ok"]
