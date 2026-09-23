"""Native click-through cursor and non-activating activity HUD (Tk main thread)."""
import ctypes
import os
import tkinter as tk

PURPLE = "#a78bfa"
BLUE = "#3b82f6"          # the AI cursor is blue, so the user can tell it apart
BLUE_HALO = "#93c5fd"
CURSOR_COLOR = BLUE
KEY = "#010203"


def _native(window, click_through=False, activatable=False):
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
    style = get(hwnd, -20) | 0x00000080  # TOOLWINDOW (not in Alt-Tab)
    if not activatable:
        style |= 0x08000000              # NOACTIVATE: never steals focus
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
        # ---- bottom-right activity panel (Neural-Agents style) ----
        # journal of what the agent does + latest screenshot + a chat box.
        # activatable=True: the user CAN focus the entry to talk to the agent
        # (agent clicks on our own windows are refused by input_control anyway).
        self.hud = tk.Toplevel(root)
        self.hud.withdraw()
        self.hud.title("Agent Screen Activity")
        self.hud.overrideredirect(True)
        self.hud.attributes("-topmost", True)
        self.hud.configure(bg="#17121f", highlightbackground=PURPLE, highlightthickness=1)
        top = tk.Frame(self.hud, bg="#17121f")
        top.pack(fill="x")
        self.label = tk.Label(top, bg="#17121f", fg="#ede9fe", font=("Segoe UI", 10, "bold"),
                              text="●  AGENT ACTIF", padx=12, pady=7)
        self.label.pack(side="left")
        tk.Button(top, text="■ Stop", command=stop, bg="#4c2549", fg="white",
                  relief="flat", padx=10, pady=5).pack(side="right", padx=8, pady=4)
        body = tk.Frame(self.hud, bg="#17121f")
        body.pack(fill="both", expand=True, padx=8)
        self.thumb = tk.Label(body, bg="#0d0a14", width=168, height=96)
        self.thumb.pack(side="left", anchor="n", pady=4)
        self.log_txt = tk.Text(body, bg="#0d0a14", fg="#c9bfe0", relief="flat",
                               font=("Consolas", 8), width=22, height=9,
                               state="disabled", wrap="word")
        self.log_txt.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        self.reply = tk.Label(self.hud, bg="#17121f", fg="#b8aaca", text="",
                              wraplength=340, justify="left", anchor="w", padx=12)
        self.reply.pack(fill="x")
        compose = tk.Frame(self.hud, bg="#17121f")
        compose.pack(fill="x", padx=8, pady=(2, 8))
        self.entry = tk.Entry(compose, bg="#11101a", fg="white", insertbackground="white",
                              relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda _e: self.submit())
        tk.Button(compose, text="Envoyer", command=self.submit, bg="#6d40ce", fg="white",
                  relief="flat", padx=8, pady=3).pack(side="left", padx=(6, 0))
        _native(self.hud, activatable=True)
        self._thumb_photo = None
        self._thumb_job = None
        self._last_shot = None

    def _thumb_tick(self):
        """Refresh the latest-screenshot thumbnail while the panel is up."""
        self._thumb_job = None
        if not getattr(self, "_started", False):
            return
        try:
            from .paths import shots_dir
            files = sorted(shots_dir().glob("shot_*"), key=lambda p: p.stat().st_mtime)
            if files and files[-1] != self._last_shot:
                self._last_shot = files[-1]
                from PIL import Image, ImageTk
                img = Image.open(files[-1])
                img.thumbnail((168, 96))
                self._thumb_photo = ImageTk.PhotoImage(img)
                self.thumb.configure(image=self._thumb_photo, width=168, height=96)
        except Exception:  # noqa: BLE001 - a missing/locked shot must never break the panel
            pass
        try:
            self._thumb_job = self.root.after(1200, self._thumb_tick)
        except tk.TclError:
            pass

    def log(self, text):
        """Append a line to the action journal."""
        try:
            import time as _t
            self.log_txt.configure(state="normal")
            self.log_txt.insert("end", f"{_t.strftime('%H:%M:%S')}  {str(text)[:160]}\n")
            lines = int(self.log_txt.index("end-1c").split(".")[0])
            if lines > 120:
                self.log_txt.delete("1.0", f"{lines - 120}.0")
            self.log_txt.configure(state="disabled")
            self.log_txt.see("end")
        except tk.TclError:
            pass

    def start(self, mode):
        self.label.configure(text=f"●  AGENT · {mode}")
        self.reply.configure(text="Dis-moi quoi faire pendant que je travaille.")
        self.log("Session démarrée")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.hud.geometry(f"370x330+{max(10, sw - 386)}+{max(10, sh - 346)}")
        self._started = True
        if self.mode != "hidden":
            self.hud.deiconify()
        self._thumb_tick()

    def set_mode(self, mode):
        """auto = hidden during captures/clicks, visible while the agent works;
        always = always visible; hidden = never shown."""
        self.mode = mode if mode in ("auto", "always", "hidden") else "auto"
        if self.mode == "hidden":
            self.hud.withdraw()
        elif getattr(self, "_started", False):
            self.hud.deiconify()

    def hide_for_action(self):
        """Disappear while a capture is taken or a click/scroll is delivered:
        it must not cover the agent's target (nor appear in its screenshots)."""
        if getattr(self, "_started", False) and self.mode == "auto":
            self.hud.withdraw()

    def show_after_action(self):
        if self.mode != "hidden" and getattr(self, "_started", False):
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
        if self._thumb_job:
            try:
                self.root.after_cancel(self._thumb_job)
            except tk.TclError:
                pass
            self._thumb_job = None
        self.cursor.withdraw()
        self.hud.withdraw()

    def destroy(self):
        self.finish()
        self.cursor.destroy()
        self.hud.destroy()
