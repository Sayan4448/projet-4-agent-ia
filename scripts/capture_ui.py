"""Generate a clean native UI illustration with isolated example settings."""
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
from agent_screen import gui, settings, display


def main():
    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(settings, "config_file", return_value=Path(tmp) / "config.json"), \
         patch.object(display, "interesting_windows", return_value=[]):
        settings.save({"provider": "ollama", "models": {"ollama": "Modèle vision local"}})
        root = tk.Tk()
        app = gui.App(root)
        app.goal_entry.insert(0, "Recherche les prévisions météo pour mon prochain voyage")
        app._add_card("01 · Choisissez votre espace", "Bureau pour vos applications. Navigateur pour une session dédiée.", color=gui.TXT)
        app._add_card("02 · Gardez le contrôle", "Curseur IA visible, actions par capture et bouton Stop toujours accessible.", color=gui.TXT, accent=gui.OK)
        root.update()
        root.lift()
        root.after(500, lambda: capture(root))
        root.mainloop()


def capture(root):
    root.update()
    import ctypes
    user = ctypes.windll.user32
    user.GetParent.restype = ctypes.c_void_p
    hwnd = user.GetParent(root.winfo_id())
    display._capture_hwnd_printwindow(hwnd).convert("RGB").save("docs/interface.png")
    root.destroy()
    print("docs/interface.png")


if __name__ == "__main__":
    main()
