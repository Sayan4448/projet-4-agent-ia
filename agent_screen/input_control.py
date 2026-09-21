"""Mouse and keyboard control via PyAutoGUI + raw SendInput (Scan Codes) for games.

PyAutoGUI uses virtual-key events: some games (DirectInput/Raw Input, e.g.
Counter-Strike) ignore them. So key holds and mouse up/down go through a
small ctypes SendInput layer with scan codes — what games actually read.

Failsafe: slam the mouse into the top-left corner to abort everything.
"""
import ctypes
import os
import re
import shutil
import subprocess
import time
import urllib.parse

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

_MAX_STR = 200

# ------------------------------------------------------------------ SendInput
ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

# scan codes for the keys games care about
SCAN = {
    "w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "q": 0x10,
    "space": 0x39, "ctrl": 0x1D, "shift": 0x2A, "e": 0x12, "r": 0x13,
    "f": 0x21, "g": 0x22, "b": 0x30, "z": 0x2C, "x": 0x2D, "c": 0x2E,
    "v": 0x2F, "tab": 0x0F, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05,
    "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
}

_held_keys = set()


def _send_scan(scan: int, up: bool = False):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = _KEYBDINPUT(0, scan, flags, 0, 0)
    if ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
        raise OSError("Windows a refusé la touche simulée. Vérifie les droits de la fenêtre cible.")


def key_down(key: str) -> dict:
    pyautogui.failSafeCheck()
    k = str(key).lower().strip()
    if k not in SCAN:
        raise ValueError(f"key '{key}' cannot be held (try: {', '.join(sorted(SCAN))})")
    _send_scan(SCAN[k])
    _held_keys.add(k)
    return {"key_down": k}


def key_up(key: str) -> dict:
    k = str(key).lower().strip()
    if k not in SCAN:
        raise ValueError(f"key '{key}' cannot be released (try: {', '.join(sorted(SCAN))})")
    _send_scan(SCAN[k], up=True)
    _held_keys.discard(k)
    return {"key_up": k}


def release_all_keys() -> dict:
    errors = []
    for k in list(_held_keys):
        try:
            key_up(k)
        except OSError as e:
            errors.append(str(e))
    if errors:
        raise OSError("; ".join(errors))
    return {"released": "all held keys"}


def mouse_down(button: str = "left") -> dict:
    pyautogui.failSafeCheck()
    b = str(button or "left").lower()
    if b not in ("left", "right"):
        raise ValueError("button must be left or right")
    down = MOUSEEVENTF_LEFTDOWN if b == "left" else MOUSEEVENTF_RIGHTDOWN
    inp = _INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = _MOUSEINPUT(0, 0, 0, down, 0, 0)
    if ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
        raise OSError("Windows a refusé le bouton simulé. Vérifie les droits de la fenêtre cible.")
    return {"mouse_down": b}


def mouse_up(button: str = "left") -> dict:
    b = str(button or "left").lower()
    if b not in ("left", "right"):
        raise ValueError("button must be left or right")
    up = MOUSEEVENTF_LEFTUP if b == "left" else MOUSEEVENTF_RIGHTUP
    inp = _INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = _MOUSEINPUT(0, 0, 0, up, 0, 0)
    if ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
        raise OSError("Windows a refusé le relâchement du bouton.")
    return {"mouse_up": b}


def mouse_move_rel(dx: int, dy: int) -> dict:
    """Relative mouse move (aiming). dx positive = right, dy positive = down."""
    pyautogui.failSafeCheck()
    dx, dy = int(dx), int(dy)
    inp = _INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = _MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)
    if ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
        raise OSError("Windows a refusé le mouvement simulé. Vérifie les droits de la fenêtre cible.")
    return {"moved_rel": [dx, dy]}


# ------------------------------------------------------- PyAutoGUI (classic)
def _clamp_str(text, name) -> str:
    text = str(text or "")
    if len(text) > _MAX_STR:
        raise ValueError(f"{name} is too long (max {_MAX_STR} chars)")
    return text


def mouse_move(x: int, y: int) -> dict:
    x, y = int(x), int(y)
    pyautogui.moveTo(x, y, duration=0.04)  # fast: less dead time between steps
    return {"moved_to": [x, y]}


def mouse_click(x=None, y=None, button: str = "left", clicks: int = 1) -> dict:
    button = str(button or "left").lower()
    if button not in ("left", "right", "middle"):
        raise ValueError("button must be left, right or middle")
    clicks = max(1, min(3, int(clicks or 1)))
    if x is None or y is None:
        pyautogui.click(button=button, clicks=clicks, interval=0.08)
    else:
        pyautogui.click(int(x), int(y), button=button, clicks=clicks, interval=0.08)
    return {"clicked": [x, y], "button": button, "clicks": clicks}


def mouse_double_click(x=None, y=None, button: str = "left") -> dict:
    if x is None or y is None:
        pyautogui.doubleClick(button=button)
    else:
        pyautogui.doubleClick(int(x), int(y), button=button)
    return {"double_clicked": [x, y], "button": button}


def mouse_drag(x: int, y: int, duration: float = 0.4) -> dict:
    x, y = int(x), int(y)
    pyautogui.dragTo(x, y, duration=max(0.1, min(3.0, float(duration))), button="left")
    return {"dragged_to": [x, y]}


def mouse_scroll(amount: int, y: int = None, x: int = None) -> dict:
    amount = int(amount)
    if x is not None and y is not None:
        pyautogui.moveTo(int(x), int(y))
    pyautogui.scroll(amount)
    return {"scrolled": amount}


def mouse_hscroll(amount: int) -> dict:
    """Horizontal scroll: positive = right."""
    amount = int(amount)
    pyautogui.hscroll(amount)
    return {"hscrolled": amount}


def mouse_position() -> dict:
    return {"x": int(pyautogui.position()[0]), "y": int(pyautogui.position()[1])}


def type_text(text: str) -> dict:
    """Paste Unicode through Win32 (no Tk interpreter in an agent worker).

    Restore a previous text clipboard only if nobody changed it during paste.
    """
    text = str(text or "")
    if len(text) > 12000:
        raise ValueError("text is too long (max 12000 chars)")
    if not text:
        return {"typed": 0}
    if os.name != "nt":
        pyautogui.write(text, interval=0.01)
        return {"typed": len(text)}
    pyautogui.failSafeCheck()
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    from ctypes import wintypes
    for fn, args, result in (
        (kernel32.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL),
        (kernel32.GlobalLock, [wintypes.HGLOBAL], ctypes.c_void_p),
        (kernel32.GlobalUnlock, [wintypes.HGLOBAL], wintypes.BOOL),
        (kernel32.GlobalFree, [wintypes.HGLOBAL], wintypes.HGLOBAL),
        (user32.GetClipboardData, [wintypes.UINT], wintypes.HANDLE),
        (user32.SetClipboardData, [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
    ):
        fn.argtypes, fn.restype = args, result

    def open_clipboard():
        for _ in range(20):
            if user32.OpenClipboard(None):
                return
            time.sleep(0.025)
        raise OSError("Presse-papiers occupé, réessaie la saisie.")

    def put(value):
        raw = value.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(0x0002, len(raw))
        if not handle:
            raise OSError("GlobalAlloc failed")
        try:
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise OSError("GlobalLock failed")
            try:
                ctypes.memmove(pointer, raw, len(raw))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.EmptyClipboard() or not user32.SetClipboardData(13, handle):
                raise OSError("Impossible de préparer la saisie Unicode.")
            handle = None  # Windows owns the memory now
        finally:
            if handle:
                kernel32.GlobalFree(handle)

    old = None
    open_clipboard()
    try:
        handle = user32.GetClipboardData(13)
        if handle:
            pointer = kernel32.GlobalLock(handle)
            if pointer:
                try:
                    old = ctypes.wstring_at(pointer)
                finally:
                    kernel32.GlobalUnlock(handle)
        put(text)
        sequence = user32.GetClipboardSequenceNumber()
    finally:
        user32.CloseClipboard()
    try:
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
    finally:
        if old is not None and user32.GetClipboardSequenceNumber() == sequence:
            open_clipboard()
            try:
                if user32.GetClipboardSequenceNumber() == sequence:
                    put(old)
            finally:
                user32.CloseClipboard()
    return {"typed": len(text), "chars": True}


def press_key(key: str) -> dict:
    key = _clamp_str(key, "key").lower().strip()
    aliases = {
        "win": "winleft", "windows": "winleft", "super": "winleft",
        "cmd": "winleft", "control": "ctrl", "esc": "escape",
        "return": "enter", "printscreen": "printscreen", "prtsc": "printscreen",
        "del": "delete", "ins": "insert", "volumeup": "volumeup",
    }
    key = aliases.get(key, key)
    if key not in pyautogui.KEYBOARD_KEYS:
        raise ValueError(
            f"unknown key '{key}'. e.g. enter, esc, tab, ctrl, alt, win, shift, "
            "space, backspace, delete, up, down, left, right, home, end, "
            "pageup, pagedown, f1..f12, volumeup, volumedown, volumemute"
        )
    pyautogui.press(key)
    return {"pressed": key}


def hotkey(*keys) -> dict:
    cleaned = []
    for k in keys:
        k = _clamp_str(k, "key").lower().strip()
        aliases = {"win": "winleft", "windows": "winleft", "cmd": "winleft",
                   "control": "ctrl", "esc": "escape"}
        cleaned.append(aliases.get(k, k))
    if not cleaned:
        raise ValueError("hotkey needs at least one key")
    pyautogui.hotkey(*cleaned)
    return {"hotkey": "+".join(cleaned)}


def get_held_keys() -> list:
    return sorted(_held_keys)


# -------------------------------------------------- System & Research actions
_URL_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.I)


def start_menu_search(name: str) -> None:
    """Last-resort launch: type the name in the Start menu.

    Used as the fallback of apps.launch_app, which still verifies afterwards
    that a window appeared — so this can never report a false success.
    """
    press_key("win")
    time.sleep(0.5)
    type_text(name)
    time.sleep(0.6)
    press_key("enter")
    time.sleep(0.4)


def run_terminal_command(command: str, timeout: float = 20.0) -> dict:
    """Execute a PowerShell command and capture its output (UTF-8 safe).

    The console output encoding is forced to UTF-8: without it, PowerShell 5.1
    writes in the OEM code page and every accented character comes back as '?'.
    """
    command = str(command or "").strip()
    if not command:
        return {"command": "", "stdout": "", "stderr": "", "exit_code": 0, "ok": True}

    timeout = max(5.0, min(300.0, float(timeout)))

    shell = (shutil.which("powershell.exe") or shutil.which("powershell")
             or shutil.which("pwsh") or "powershell.exe")
    prefix = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
              "$OutputEncoding=[System.Text.Encoding]::UTF8;"
              "$ProgressPreference='SilentlyContinue';")

    try:
        res = subprocess.run(
            [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", prefix + command],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        stdout = (res.stdout or "").strip()
        stderr = (res.stderr or "").strip()
        return {
            "command": command,
            "stdout": stdout[:4000],
            "stdout_truncated": len(stdout) > 4000,
            "stderr": stderr[:1000],
            "exit_code": res.returncode,
            "ok": res.returncode == 0,
        }
    except subprocess.TimeoutExpired as e:
        partial = e.stdout
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return {"command": command, "stdout": (partial or "").strip()[:2000],
                "stderr": "", "exit_code": -1, "ok": False,
                "error": f"command still running after {timeout:.0f}s (killed)"}
    except Exception as e:  # noqa: BLE001
        return {"command": command, "stdout": "", "stderr": "", "exit_code": -1,
                "ok": False, "error": str(e)}


def open_url(url: str) -> dict:
    """Open an http(s) URL in the default browser, and report if it failed.

    webbrowser.open() returns False when no browser is registered; the old code
    ignored that and claimed success, leaving the user with nothing happening.
    """
    import webbrowser

    raw = str(url or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("open_url needs a URL")
    if not _URL_RE.match(raw):
        raw = "https://" + raw.lstrip("/")
    if not raw.lower().startswith(("http://", "https://")):
        return {"opened_url": raw, "ok": False,
                "error": "only http/https URLs are supported (use open_app for programs)"}
    ok = False
    try:
        ok = bool(webbrowser.open(raw))
    except Exception:  # noqa: BLE001 - fall through to ShellExecute
        ok = False
    if not ok:
        try:
            os.startfile(raw)      # Windows: ShellExecute with the user's browser
            ok = True
        except Exception as e:  # noqa: BLE001
            try:
                subprocess.Popen(["xdg-open", raw])   # other platforms
                ok = True
            except Exception:  # noqa: BLE001
                return {"opened_url": raw, "ok": False,
                        "error": f"could not open a web browser: {e}"}
    time.sleep(0.5)
    return {"opened_url": raw, "ok": True}


def search_web(query: str) -> dict:
    """Run a web search in the default browser (URLs are opened as such)."""
    q = str(query or "").strip().strip('"').strip("'")
    if not q:
        raise ValueError("search_web needs a query")
    if _URL_RE.match(q):
        res = open_url(q)
        res["searched"] = q
        return res
    url = "https://www.google.com/search?q=" + urllib.parse.quote(q)
    res = open_url(url)
    res["searched"] = q
    return res
