"""Generate a clean illustration of the agent activity panel (docs/agent-panel.png)."""
import ctypes
import tkinter as tk
from agent_screen import display, overlay


def main():
    root = tk.Tk()
    root.withdraw()
    ov = overlay.AgentOverlay(root, stop=lambda: None)
    ov.set_mode("always")
    ov.start("Bureau")
    for line in (
        "Capture 1920x1080 prise",
        "click -> Discord (icône)",
        "click -> champ de message",
        'type -> "bonne nuit"',
        "Mission terminée",
    ):
        ov.log(line)
    ov.message("Discord ouvert — j'écris le message.")
    try:
        from PIL import Image, ImageTk
        img = Image.new("RGB", (168, 96), "#241a3d")
        ov._thumb_photo = ImageTk.PhotoImage(img)
        ov.thumb.configure(image=ov._thumb_photo)
    except Exception:  # noqa: BLE001
        pass
    ov.hud.update()
    ov.hud.after(500, lambda: _capture(ov))
    root.mainloop()


def _capture(ov):
    user = ctypes.windll.user32
    user.GetParent.restype = ctypes.c_void_p
    hwnd = user.GetParent(ov.hud.winfo_id())
    # the panel is excluded from screenshots on purpose; lift that just for this render
    try:
        user.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), 0)
    except Exception:  # noqa: BLE001
        pass
    display._capture_hwnd_printwindow(hwnd).convert("RGB").save("docs/agent-panel.png")
    ov.destroy()
    ov.root.destroy()
    print("docs/agent-panel.png")


if __name__ == "__main__":
    main()
