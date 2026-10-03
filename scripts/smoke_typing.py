"""Real-window check of verified typing and sending, on a Chromium page — what
Discord and every Electron app are made of.

The page mimics a chat box: a textarea, Enter "sends" (appends to a list and
clears the field). The agent's own code clicks, types and presses Enter through
virtual input, then the page tells what it really received:
- the field holds the text exactly once (the old change check never saw the
  text appear, so it pasted it a second time);
- the run reports the typing as confirmed instead of "aucun changement visible";
- Enter sends the message once.

Run: .venv/Scripts/python.exe scripts/smoke_typing.py
"""
import sys
import time

sys.path.insert(0, ".")
from agent_screen import agent, input_control  # noqa: E402
from agent_screen.browser_mode import BrowserSession  # noqa: E402

PAGE = """<title>smoke_typing_page</title>
<body style='margin:0;background:#313338;color:#ddd;font:15px Segoe UI'>
<div id=log style='padding:20px;height:560px'></div>
<textarea id=t style='position:fixed;left:80px;top:640px;width:900px;height:44px;
 background:#383a40;color:#eee;font:16px Segoe UI;border:0;padding:10px'></textarea>
<script>
window.sent = []; window.clicks = 0;
document.addEventListener('click', () => clicks++);
t.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); if (t.value) { sent.push(t.value);
    log.innerHTML += '<p>' + t.value + '</p>'; t.value = ''; } }
});
</script></body>"""

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}  {detail}")


def main():
    session = BrowserSession()
    session.start()
    try:
        page = session.page
        page.set_content(PAGE)
        agent.execute_action("focus_window", {"title": "smoke_typing_page"})
        time.sleep(1.0)
        session.screenshot()                      # sets origin like a real run
        x, y = session.origin[0] + 300, session.origin[1] + 662
        hwnd, _, _ = input_control._point_target(x, y)
        if "smoke_typing_page" not in _title(hwnd):
            print("SKIP: another window covers the test page")
            return
        run = agent.AgentRun("smoke", "gemini", virtual_input=True, memory_enabled=False)
        input_control.reset_virtual_input()
        agent._virtual_action("mouse_click", {"x": x, "y": y})
        time.sleep(0.4)
        check("the click focused the field",
              page.evaluate("document.activeElement.id") == "t")
        clicks = page.evaluate("window.clicks")
        check("one virtual click is one click for the page", clicks == 1, f"clicks={clicks}")

        result = run._type_verified("salut", 1)
        time.sleep(0.3)
        value = page.evaluate("t.value")
        check("typing is reported as done", result.get("ok") is not False, str(result)[:90])
        check("the field holds the text exactly once", value == "salut", f"field={value!r}")
        check("the run knows the typing landed", run._typing_confirmed)

        result = run._enter_verified({"key": "enter"}, 1)
        time.sleep(0.3)
        sent = page.evaluate("window.sent")
        check("Enter is reported as done", result.get("ok") is not False, str(result)[:90])
        check("the message was sent exactly once", sent == ["salut"], f"sent={sent}")
    finally:
        session.close()


def _title(hwnd) -> str:
    import ctypes
    root = ctypes.windll.user32.GetAncestor(ctypes.c_void_p(hwnd), 2)
    title = ctypes.create_unicode_buffer(200)
    ctypes.windll.user32.GetWindowTextW(ctypes.c_void_p(root), title, 200)
    return title.value


if __name__ == "__main__":
    main()
    print(f"{sum(results)}/{len(results)} ok")
    sys.exit(0 if results and all(results) else 1)
