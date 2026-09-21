"""Native click-through cursor and non-activating activity HUD (Tk main thread)."""
import ctypes
import os
import tkinter as tk

PURPLE = "#a78bfa"
KEY = "#010203"


def _native(window, click_through=False):
    if os.name != "nt":
        return
    window.update_idletasks()
    user = ctypes.windll.user32
    user.GetParent.restype = ctypes.c_void_p
    hwnd = user.GetParent(window.winfo_id())
    get = user.GetWindowLongPtrW
    put = user.SetWindowLongPtrW
    get.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get.restype = ctypes.c_ssize_t
    put.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    put.restype = ctypes.c_ssize_t
    style = get(hwnd, -20) | 0x08000000 | 0x00000080  # NOACTIVATE | TOOLWINDOW
    if click_through:
        style |= 0x00000020 | 0x00080000
    put(hwnd, -20, style)
    try:
        user.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), 0x11)  # exclude from screenshots
    except Exception:
        pass


class AgentOverlay:
    def __init__(self, root, stop):
        self.root = root
        self.timer = None
        self.cursor = tk.Toplevel(root)
        self.cursor.withdraw()
        self.cursor.title("AgentCursor")
        self.cursor.overrideredirect(True)
        self.cursor.attributes("-topmost", True)
        self.cursor.configure(bg=KEY)
        if os.name == "nt":
            self.cursor.attributes("-transparentcolor", KEY)
        self.canvas = tk.Canvas(self.cursor, width=110, height=110, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        _native(self.cursor, True)
        self.hud = tk.Toplevel(root)
        self.hud.withdraw()
        self.hud.title("Agent Screen Activity")
        self.hud.overrideredirect(True)
        self.hud.attributes("-topmost", True)
        self.hud.configure(bg="#211a36", highlightbackground=PURPLE, highlightthickness=1)
        self.label = tk.Label(self.hud, bg="#211a36", fg="#ede9fe", font=("Segoe UI", 10, "bold"),
                              text="●  AGENT ACTIF", padx=16, pady=12)
        self.label.pack(side="left")
        tk.Button(self.hud, text="■ Stop", command=stop, bg="#4c2549", fg="white",
                  relief="flat", padx=12, pady=7).pack(side="right", padx=8)
        _native(self.hud)

    def start(self, mode):
        self.label.configure(text=f"●  AGENT ACTIF  ·  {mode}")
        self.hud.geometry(f"+{max(10, self.root.winfo_screenwidth() // 2 - 200)}+16")
        self.hud.deiconify()

    def status(self, text):
        self.label.configure(text="●  " + text[:55])

    def show(self, x, y, click=False):
        if self.timer:
            self.root.after_cancel(self.timer)
        self.cursor.geometry(f"110x110{int(x)-45:+d}{int(y)-45:+d}")
        self.cursor.deiconify()
        if os.name == "nt":
            user = ctypes.windll.user32
            hwnd = user.GetParent(self.cursor.winfo_id())
            user.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), int(x)-45, int(y)-45,
                              110, 110, 0x0010)  # physical negative monitor coordinates, no activation
        self._frame(0, click)

    def _frame(self, frame, click):
        c = self.canvas
        c.delete("all")
        radius = 12 + frame * 2 if click else 20
        color = "#c4b5fd" if click else PURPLE
        c.create_oval(45-radius, 45-radius, 45+radius, 45+radius, outline=color, width=3)
        c.create_polygon(45, 45, 45, 75, 53, 68, 61, 82, 68, 78, 60, 65, 72, 64,
                         fill=PURPLE, outline="white", width=2)
        c.create_text(78, 94, text="IA", fill="white", font=("Segoe UI", 9, "bold"))
        if frame < 12:
            self.timer = self.root.after(45, lambda: self._frame(frame + 1, click))
        else:
            self.timer = self.root.after(350, self.cursor.withdraw)

    def finish(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.cursor.withdraw()
        self.hud.withdraw()

    def destroy(self):
        self.finish()
        self.cursor.destroy()
        self.hud.destroy()
