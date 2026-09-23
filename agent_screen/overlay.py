"""Native click-through cursor and non-activating activity HUD (Tk main thread)."""
import ctypes
import os
import tkinter as tk

PURPLE = "#a78bfa"
BLUE = "#3b82f6"          # the AI cursor is blue, so the user can tell it apart
BLUE_HALO = "#93c5fd"
CURSOR_COLOR = BLUE
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
    def __init__(self, root, stop, send_message=None, linger=5.0):
        self.root = root
        self.send_message = send_message
        # how long the blue marker stays at the click point before fading out
        try:
            self.linger = max(0.0, min(60.0, float(linger)))
        except (TypeError, ValueError):
            self.linger = 5.0
        self.mode = "auto"      # auto-hide the HUD while the agent clicks
        self._started = False
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
        top = tk.Frame(self.hud, bg="#211a36")
        top.pack(fill="x")
        self.label = tk.Label(top, bg="#211a36", fg="#ede9fe", font=("Segoe UI", 10, "bold"),
                              text="●  AGENT ACTIF", padx=16, pady=10)
        self.label.pack(side="left")
        tk.Button(top, text="■ Stop", command=stop, bg="#4c2549", fg="white",
                  relief="flat", padx=12, pady=7).pack(side="right", padx=8, pady=5)
        self.reply = tk.Label(self.hud, bg="#211a36", fg="#b8aaca", text="",
                              wraplength=420, justify="left", anchor="w", padx=12)
        self.reply.pack(fill="x")
        compose = tk.Frame(self.hud, bg="#211a36")
        compose.pack(fill="x", padx=10, pady=(4, 10))
        self.entry = tk.Entry(compose, bg="#11101a", fg="white", insertbackground="white",
                              relief="flat", width=44)
        self.entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.entry.bind("<Return>", lambda _e: self.submit())
        tk.Button(compose, text="Envoyer", command=self.submit, bg="#6d40ce", fg="white",
                  relief="flat", padx=10, pady=4).pack(side="left", padx=(6, 0))
        _native(self.hud)

    def start(self, mode):
        self.label.configure(text=f"●  AGENT ACTIF  ·  {mode}")
        self.reply.configure(text="Dis-moi quoi faire pendant que je travaille.")
        self.hud.geometry(f"470x116+{max(10, self.root.winfo_screenwidth() // 2 - 235)}+16")
        self._started = True
        if self.mode == "always":
            self.hud.deiconify()

    def set_mode(self, mode):
        """auto = hidden while the agent clicks, visible between steps;
        always = always visible; hidden = never shown."""
        self.mode = mode if mode in ("auto", "always", "hidden") else "auto"
        if self.mode == "hidden":
            self.hud.withdraw()
        elif self.mode == "always" and getattr(self, "_started", False):
            self.hud.deiconify()

    def hide_for_action(self):
        """Disappear while a click/scroll is delivered so the agent can never
        click the chat interface by accident."""
        if getattr(self, "_started", False):
            self.hud.withdraw()

    def show_after_action(self):
        if self.mode == "always" and getattr(self, "_started", False):
            self.hud.deiconify()

    def submit(self):
        text = self.entry.get().strip()
        if not text or not self.send_message:
            return
        self.entry.delete(0, "end")
        self.reply.configure(text="Vous : " + text[:180])
        self.send_message(text)

    def message(self, text):
        self.reply.configure(text=str(text)[:240])

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
        color = BLUE_HALO if click else BLUE
        c.create_oval(45-radius, 45-radius, 45+radius, 45+radius, outline=color, width=3)
        c.create_polygon(45, 45, 45, 75, 53, 68, 61, 82, 68, 78, 60, 65, 72, 64,
                         fill=BLUE, outline="white", width=2)
        c.create_text(78, 94, text="IA", fill="white", font=("Segoe UI", 9, "bold"))
        if frame < 12:
            self.timer = self.root.after(45, lambda: self._frame(frame + 1, click))
        elif click:
            # a click marker stays where the AI clicked, long enough to see it
            self.timer = self.root.after(max(0, int(self.linger * 1000)),
                                         self.cursor.withdraw)
        else:
            self.timer = self.root.after(350, self.cursor.withdraw)

    def finish(self):
        self._started = False
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.cursor.withdraw()
        self.hud.withdraw()

    def destroy(self):
        self.finish()
        self.cursor.destroy()
        self.hud.destroy()
