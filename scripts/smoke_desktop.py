"""Interactive smoke check of the real Windows UI and native input.

Creates only its own windows, uses an isolated config and never calls an AI API.
Run while the desktop is unlocked: python -m scripts.smoke_desktop
"""
import base64
import io
from pathlib import Path
import tempfile
import time
import threading
import tkinter as tk
from unittest.mock import patch

from PIL import Image
from agent_screen import display, gui, input_control, settings


def main():
    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(settings, "config_file", return_value=Path(tmp) / "config.json"), \
         patch.object(display, "shots_dir", return_value=Path(tmp)):
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))
        app = gui.App(root)
        root.update()
        assert root.winfo_ismapped(), "Main app window did not appear"
        app.nb.select(app.tab_chat)
        root.update()
        app._open_settings()
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        assert dialog.winfo_ismapped(), "Settings did not appear"
        dialog.destroy()

        probe = tk.Toplevel(root)
        probe.title("Native Input Verification")
        probe.geometry("640x260+100+100")
        entry = tk.Text(probe)
        entry.pack(fill="both", expand=True)
        probe.lift()
        entry.focus_force()
        root.update()
        display.activate_window("Native Input Verification")
        input_control.mouse_click(entry.winfo_rootx() + 30, entry.winfo_rooty() + 30)
        root.update()
        entry.focus_force()
        # Let native activation events settle before the background paste.
        root.after(250, root.quit)
        root.mainloop()
        assert root.focus_get() is entry, "The test input did not acquire focus"
        errors_before = list(errors)
        text = "Bonjour, été à Paris — ç ! " * 12
        def type_worker():
            try:
                input_control.type_text(text)
            except Exception as e:
                errors.append(str(e))
        worker = threading.Thread(target=type_worker)
        worker.start()
        deadline = time.monotonic() + 3
        while (worker.is_alive() or entry.get("1.0", "end-1c") != text) and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        actual = entry.get("1.0", "end-1c")
        worker.join(1)
        assert actual == text, f"Unicode input differs: expected={text!r}, actual={actual!r}"
        before = input_control.mouse_position()
        entry.delete("1.0", "end")
        clicks = []
        entry.bind("<ButtonPress-1>", lambda event: clicks.append((event.x, event.y)))
        input_control.reset_virtual_input()
        with patch.object(input_control, "_check_target"):
            # Tk (like some toolkits) silently ignores posted mouse messages: the
            # virtual click must not move the cursor and must not raise.
            input_control.virtual_mouse_click(entry.winfo_rootx() + 30, entry.winfo_rooty() + 30)
            root.update()
            assert input_control.mouse_position() == before, "Virtual click moved the physical cursor"
            entry.focus_force()
            root.update()
            input_control.virtual_type("Texte virtuel : été, ç, 東京")
            root.update()
        assert entry.get("1.0", "end-1c") == "Texte virtuel : été, ç, 東京", "Virtual text was not delivered"
        # transient fallback: real injected click, cursor restored immediately
        input_control.transient_click(entry.winfo_rootx() + 30, entry.winfo_rooty() + 30)
        deadline = time.monotonic() + 2
        while not clicks and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert clicks, "Transient click did not reach the test widget"
        assert input_control.mouse_position() == before, "Transient click did not restore the cursor"
        found = display.find_window("Native Input Verification")
        assert found, "Window enumeration failed"
        assert display.window_exe(found[0]).lower().startswith("python"), "Process identity lookup failed"
        image, scale, geometry = display.capture_for_model(
            window_title="Native Input Verification", max_width=320,
            jpeg_quality=80, with_geometry=True)
        shot = Image.open(io.BytesIO(base64.b64decode(image)))
        assert shot.width == 320, shot.size
        assert shot.convert("L").getextrema()[1] - shot.convert("L").getextrema()[0] > 50, "Window capture is blank"
        assert geometry["origin"] == (found[1]["x"], found[1]["y"])
        assert scale >= 1
        assert errors == errors_before == [], errors
        probe.destroy()
        app._on_close()
        print("PASS: native app, Chat tab, Settings, Unicode typing (>200 chars), window capture, process identity, clean exit")


if __name__ == "__main__":
    main()
