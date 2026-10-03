"""Reproduction harness for the scroll bugs: real windows, real wheel events.

Each check scrolls a real target and reads back how far it actually moved:
- a Tk text widget (classic Win32 message handling),
- a Chromium page (what Discord, Brave and every Electron app are made of),
- the dedicated browser session of the browser mode.

The physical checks move the real cursor for a few milliseconds.

Run: .venv/Scripts/python.exe scripts/smoke_scroll.py [--no-browser]
"""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes

sys.path.insert(0, ".")
from agent_screen import agent, input_control  # noqa: E402

results = []


def window_at(x, y) -> str:
    """Title of the top-level window that would receive an event at (x, y)."""
    hwnd, _, _ = input_control._point_target(x, y)
    root = ctypes.windll.user32.GetAncestor(ctypes.c_void_p(hwnd), 2)
    title = ctypes.create_unicode_buffer(200)
    ctypes.windll.user32.GetWindowTextW(ctypes.c_void_p(root), title, 200)
    return title.value


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}  {detail}")


def tk_target(state_file):
    """Child process: a scrollable Tk window that reports its real position.
    It must be another process — the agent refuses to act on its own windows."""
    root = tk.Tk()
    root.title("smoke_scroll")
    root.geometry("640x420+160+160")
    root.attributes("-topmost", True)
    text = tk.Text(root, wrap="none", width=60, height=20)
    text.pack(fill="both", expand=True)
    text.insert("1.0", "\n".join(f"ligne {i:03d} " + "x" * 400 for i in range(400)))

    def report():
        state = {"x": root.winfo_rootx() + root.winfo_width() // 2,
                 "y": root.winfo_rooty() + root.winfo_height() // 2,
                 "hwnd": root.winfo_id(), "yview": text.yview()[0], "xview": text.xview()[0]}
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        root.after(40, report)

    root.after(300, report)
    root.mainloop()


def tk_checks():
    state_file = os.path.join(tempfile.mkdtemp(), "state.json")
    child = subprocess.Popen([sys.executable, __file__, "--target", state_file])

    def state():
        for _ in range(100):
            try:
                with open(state_file, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):       # not written yet / mid-write
                time.sleep(0.05)
        raise RuntimeError("la fenêtre cible ne répond pas")

    def moved(action, view):
        # never scroll someone else's window: on a desktop in use another
        # window can be on top of the target at any moment
        if "smoke_scroll" not in window_at(state()["x"], state()["y"]):
            return None, "SKIPPED: another window covers the target"
        before = state()[view]
        try:
            action()
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {e}"
        time.sleep(0.4)
        return state()[view] - before, ""

    old = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(old))
    try:
        st = state()
        cx, cy = st["x"], st["y"]
        d, err = moved(lambda: input_control.virtual_mouse_scroll(-3, cy, cx), "yview")
        check("virtual scroll down, Tk", bool(d and d > 0), err or f"moved {d:.4f}")
        d, err = moved(lambda: input_control.virtual_mouse_scroll(3, cy, cx), "yview")
        check("virtual scroll up, Tk", bool(d and d < 0), err or f"moved {d:.4f}")
        d, err = moved(lambda: input_control.virtual_mouse_hscroll(3, cy, cx), "xview")
        check("virtual scroll right, Tk", bool(d and d > 0), err or f"moved {d:.4f}")

        input_control.reset_virtual_input()
        ctypes.windll.user32.SetForegroundWindow(wintypes.HWND(st["hwnd"]))
        time.sleep(0.3)
        active = ctypes.windll.user32.GetForegroundWindow()
        if ctypes.windll.user32.GetAncestor(wintypes.HWND(st["hwnd"]), 2) != active:
            # Windows refused the focus change (someone is using the PC):
            # scrolling "the active window" would scroll theirs
            print("SKIP virtual scroll without x,y: the target is not the active window")
        else:
            d, err = moved(lambda: agent._virtual_action("mouse_scroll", {"amount": -3}), "yview")
            check("virtual scroll without x,y (first action of a run)", bool(d and d > 0),
                  err or f"moved {d:.4f}")

        d, err = moved(lambda: input_control.mouse_scroll(-3, cy, cx), "yview")
        check("physical scroll down 3 notches, Tk", bool(d and d > 0.01), err or f"moved {d:.4f}")
        d, err = moved(lambda: input_control.mouse_hscroll(3, cy, cx), "xview")
        check("physical scroll right, Tk", bool(d and d > 0), err or f"moved {d:.4f}")
    finally:
        ctypes.windll.user32.SetCursorPos(old.x, old.y)
        child.terminate()


def browser_checks():
    from agent_screen.browser_mode import BrowserSession
    session = BrowserSession()
    try:
        session.start()
    except Exception as e:  # noqa: BLE001
        print(f"SKIP browser checks: {e}")
        return
    try:
        page = session.page
        page.set_content("<body style='margin:0'><div style='height:9000px;width:6000px;"
                         "background:linear-gradient(#123,#fed)'>long page</div></body>")
        page.evaluate("document.title = 'smoke_scroll_page'")
        agent.execute_action("focus_window", {"title": "smoke_scroll_page"})
        time.sleep(0.8)
        session.screenshot()                      # sets origin/size like a real run
        cx = session.origin[0] + 400
        cy = session.origin[1] + 300

        def scroll_y():
            time.sleep(0.6)                       # smooth scrolling settles
            return page.evaluate("scrollY")

        if "smoke_scroll_page" in window_at(cx, cy):
            input_control.virtual_mouse_scroll(-3, cy, cx)
            y = scroll_y()
            check("virtual scroll down, Chromium window", y >= 100, f"scrollY={y}")
        else:
            print("SKIP virtual scroll, Chromium window: another window covers it")
        page.evaluate("scrollTo(0,0)")
        session.execute("mouse_scroll", {"amount": -3})
        y = scroll_y()
        check("browser-mode scroll down 3 notches", y >= 100, f"scrollY={y}")
    finally:
        session.close()


if __name__ == "__main__":
    if "--target" in sys.argv:
        tk_target(sys.argv[-1])
        sys.exit(0)
    tk_checks()
    if "--no-browser" not in sys.argv:
        browser_checks()
    print(f"{sum(results)}/{len(results)} ok")
    sys.exit(0 if all(results) else 1)
