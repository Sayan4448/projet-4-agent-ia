"""The screen and the windows on it: capture, window facts, window control.

Windows (single owner of "which windows exist and what they are"):
- `list_windows()`            : every visible titled window, widest first
- `window_exe(hwnd)`          : process owning a window (tells look-alikes apart)
- `find_window(t)` / `get_window_rect(t)` : locate a window by title
- `is_noise(t)` / `interesting_windows(n)` : which windows are worth talking about
- `activate_window(t)`        : bring a window to the front

Screenshots:
- `take_screenshot(...)`      : full screen or ONE window (PrintWindow), base64
- `capture_for_model(...)`    : same, plus the image->real pixel scale it applied.
  The capture knows the scale because it did the resizing; callers must never
  re-derive it from the returned image.

The grid is the key fix for precise clicking: the model reads coordinates
from the labeled grid instead of guessing pixel positions.

All screen reading is DPI-aware so coordinates map 1:1 to real screen pixels.
"""
import base64
import ctypes
from ctypes import wintypes
import io
import os
import platform
import time

from .paths import shots_dir

_SYSTEM = platform.system()

# make THIS process DPI-aware as early as possible (screens + coordinates)
if _SYSTEM == "Windows":
    # ctypes defaults to a 32-bit int: handles must remain pointer-sized on x64.
    for dll, signatures in (
        (ctypes.windll.user32, {
            "GetDC": ([wintypes.HWND], wintypes.HDC),
            "GetWindowDC": ([wintypes.HWND], wintypes.HDC),
            "ReleaseDC": ([wintypes.HWND, wintypes.HDC], ctypes.c_int),
            "PrintWindow": ([wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL),
            "GetForegroundWindow": ([], wintypes.HWND),
        }),
        (ctypes.windll.gdi32, {
            "CreateCompatibleDC": ([wintypes.HDC], wintypes.HDC),
            "CreateCompatibleBitmap": ([wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP),
            "SelectObject": ([wintypes.HDC, wintypes.HANDLE], wintypes.HANDLE),
            "DeleteObject": ([wintypes.HANDLE], wintypes.BOOL),
            "DeleteDC": ([wintypes.HDC], wintypes.BOOL),
            "GetDIBits": ([wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                           ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
        }),
        (ctypes.windll.kernel32, {
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "QueryFullProcessImageNameW": ([wintypes.HANDLE, wintypes.DWORD,
                                            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        }),
    ):
        for name, (args, result) in signatures.items():
            fn = getattr(dll, name)
            fn.argtypes, fn.restype = args, result
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ------------------------------------------------------------- win32 consts
DWMWA_EXTENDED_FRAME_BOUNDS = 9
PW_RENDERFULLCONTENT = 0x00000002  # captured DWM content (incl. hardware-accelerated apps)
SHOT_CLEAN_EVERY = 30              # clean data/shots only once every N captures
_SHOT_TICK = {"n": 0}


def screen_info() -> dict:
    """Return physical pixel dimensions and DPI scaling of the primary screen."""
    info = {"primary": {}, "virtual": {}, "system": _SYSTEM}
    if _SYSTEM == "Windows":
        user32 = ctypes.windll.user32
        info["primary"] = {
            "width_px": int(user32.GetSystemMetrics(0)),   # SM_CXSCREEN
            "height_px": int(user32.GetSystemMetrics(1)),  # SM_CYSCREEN
        }
        info["virtual"] = {
            "width_px": int(user32.GetSystemMetrics(78)),  # SM_CXVIRTUALSCREEN
            "height_px": int(user32.GetSystemMetrics(79)),  # SM_CYVIRTUALSCREEN
        }
        try:
            hdc = user32.GetDC(0)
            dpi = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
            user32.ReleaseDC(0, hdc)
            info["primary"]["dpi"] = dpi
            info["primary"]["scale_percent"] = round(dpi * 100 / 96)
        except Exception:
            pass
    else:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            info["primary"] = {"width_px": img.width, "height_px": img.height}
        except Exception:
            pass
    return info


# ------------------------------------------------------------- window tools
def _enum_windows():
    user32 = ctypes.windll.user32
    results = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title:
            results.append((hwnd, title))
        return True

    user32.EnumWindows(cb, 0)
    return results


def list_windows() -> list:
    """Visible windows with a title: [{'title','w','h','hwnd'}], widest first."""
    out = []
    for hwnd, title in _enum_windows():
        try:
            r = get_window_rect_by_hwnd(hwnd)
        except Exception:  # noqa: BLE001
            continue
        w, h = r["w"], r["h"]
        if w >= 200 and h >= 150:
            out.append({"title": title, "w": w, "h": h, "hwnd": hwnd})
    out.sort(key=lambda x: -x["w"] * x["h"])
    return out


_ACCENTS = (("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"), ("à", "a"), ("â", "a"),
            ("ç", "c"), ("î", "i"), ("ï", "i"), ("ô", "o"), ("ö", "o"), ("û", "u"),
            ("ù", "u"), ("ü", "u"), ("œ", "oe"), ("æ", "ae"), ("’", "'"))


def fold(text) -> str:
    """Lowercase + accent-folded: how this module compares titles (and how
    apps.py compares app names), so a comparison never depends on spelling."""
    t = str(text or "").lower()
    for a, b in _ACCENTS:
        t = t.replace(a, b)
    return t


# windows that are never the app the user asked for: shell noise, overlays,
# invisible helpers and our own UI. One policy, used by the model's window
# inventory, the launch verification and the UI picker alike.
_NOISE = (
    "program manager", "windows input experience", "expérience d’entrée",
    "expérience d'entrée", "nvidia", "geforce", "microsoft text",
    "windows shell", "dwm", "overlay", "msctfime", "default ime",
    "agent screen", "agentcursor", "windows push notifications",
    "notification", "snipping tool overlay", "task host", "search",
    # the Start menu itself is never the app the user asked to open: without
    # this, the start-menu-search fallback counted its own window as "the app
    # appeared" and the agent stopped before the app was really open
    "menu demarrer", "start menu", "demarrer",
)


def is_noise(title: str) -> bool:
    """True for windows nobody means to capture or to focus."""
    low = fold(title)
    return any(fold(n) in low for n in _NOISE)


def interesting_windows(limit: int = 15) -> list:
    """Visible windows minus the noise, widest first (limit <= 0 = no limit)."""
    out = []
    try:
        windows = list_windows()
    except Exception:  # noqa: BLE001 - window enumeration is best effort
        return out
    for w in windows:
        title = str(w.get("title", "")).strip()
        if not title or is_noise(title) or any(o["title"] == title for o in out):
            continue
        out.append({**w, "title": title})
        if limit and len(out) >= limit:
            break
    return out


SW_RESTORE = 9


def activate_window(title: str) -> dict:
    """Bring the window whose title contains `title` to the front.

    SetForegroundWindow is refused when another app owns the foreground lock;
    SwitchToThisWindow is the usual way around it. Reports honestly whether the
    window ended up in front.
    """
    found = find_window(title) if title else None
    if not found:
        return {"ok": False, "title": title,
                "error": f"no open window matches '{title}' (use open_app to launch it)"}
    hwnd, _rect, real_title = found
    if _SYSTEM != "Windows":
        return {"ok": False, "title": real_title, "error": "window activation needs Windows"}
    try:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        if user32.GetForegroundWindow() != hwnd:
            try:
                user32.SwitchToThisWindow(hwnd, True)
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass
        ok = user32.GetForegroundWindow() == hwnd
        return {"ok": ok, "title": real_title, "window": real_title,
                "error": "" if ok else "window found but could not be focused"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "title": real_title, "error": str(e)}


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def window_exe(hwnd) -> str:
    """File name of the executable owning a window ('' when unavailable).

    Used to tell apps apart when their titles look alike: a Notepad window
    called 'brave - Bloc-notes' must never be mistaken for Brave.
    """
    if _SYSTEM != "Windows" or not hwnd:
        return ""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        if not pid.value:
            return ""
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - process lookup is best effort
        return ""
    return ""


def get_window_rect_by_hwnd(hwnd) -> dict:
    """DWM extended frame bounds for hwnd (excludes invisible borders)."""
    user32 = ctypes.windll.user32
    dwm = ctypes.windll.dwmapi
    rect = wintypes.RECT()
    res = dwm.DwmGetWindowAttribute(
        ctypes.c_void_p(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect), ctypes.sizeof(rect))
    if res != 0:  # DWM unavailable -> classic rect
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {"x": int(rect.left), "y": int(rect.top),
            "w": int(rect.right - rect.left), "h": int(rect.bottom - rect.top)}


def find_window(title: str):
    """Case-insensitive substring match on window titles (widest wins)."""
    t = fold(title).strip()
    if not t:
        return None
    best = None
    for hwnd, wtitle in _enum_windows():
        if t in fold(wtitle):
            try:
                r = get_window_rect_by_hwnd(hwnd)
            except Exception:  # noqa: BLE001
                continue
            if best is None or r["w"] * r["h"] > best[1]["w"] * best[1]["h"]:
                best = (hwnd, r, wtitle)
    return best  # (hwnd, rect, title) or None


def get_window_rect(title: str):
    found = find_window(title)
    return found[1] if found else None


def _capture_hwnd(hwnd, rect: dict):
    """BitBlt the window rect (DWM bounds)."""
    from PIL import ImageGrab
    x, y = rect["x"], rect["y"]
    return ImageGrab.grab(bbox=(x, y, x + rect["w"], y + rect["h"]), all_screens=True)


def _capture_hwnd_printwindow(hwnd, rect=None):
    """PrintWindow with PW_RENDERFULLCONTENT — works for DirectX/DWM content."""
    from PIL import Image
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    r = rect or get_window_rect_by_hwnd(hwnd)
    outer = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(outer)):
        raise OSError("GetWindowRect failed")
    w, h = outer.right - outer.left, outer.bottom - outer.top
    if w <= 0 or h <= 0:
        raise ValueError("window has zero size")

    hdc_window = user32.GetWindowDC(hwnd)
    if not hdc_window:
        raise OSError("GetWindowDC failed")
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    bmp = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
    previous = gdi32.SelectObject(hdc_mem, bmp)

    try:
        ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
        if not ok:
            # Try standard PrintWindow
            ok = user32.PrintWindow(hwnd, hdc_mem, 0)
        if not ok:
            raise OSError("PrintWindow failed")

        class BMPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_ulong), ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_ushort),
                        ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_ulong),
                        ("biSizeImage", ctypes.c_ulong), ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_ulong),
                        ("biClrImportant", ctypes.c_ulong)]

        bmi = BMPINFOHEADER(ctypes.sizeof(BMPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.SelectObject(hdc_mem, previous)
        if gdi32.GetDIBits(hdc_mem, bmp, 0, h, buf, ctypes.byref(bmi), 0) != h:
            raise OSError("GetDIBits failed")

        img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
        x, y = r["x"] - outer.left, r["y"] - outer.top
        return img.crop((x, y, x + r["w"], y + r["h"]))
    finally:
        gdi32.SelectObject(hdc_mem, previous)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_window)


def _capture_screen():
    """Capture real pixels or stop: a placeholder cannot guide desktop input."""
    from PIL import ImageGrab
    try:
        return ImageGrab.grab(all_screens=True)
    except Exception as e:
        raise RuntimeError("Capture indisponible : déverrouille le bureau Windows puis réessaie.") from e


def _capture_window_fallback(hwnd, window_title, rect):
    """BitBlt the window rect, or grab the whole screen if it disappeared.

    The previous version re-called find_window() and indexed the result with
    [1] without checking for None: when the target window closed in between,
    take_screenshot raised TypeError and the whole agent run died silently.
    """
    try:
        if rect is None and window_title:
            found = find_window(window_title)
            rect = found[1] if found else None
        if rect and int(rect.get("w", 0)) > 0 and int(rect.get("h", 0)) > 0:
            return _capture_hwnd(hwnd, rect)
    except Exception:  # noqa: BLE001 - fall through to the screen grab
        pass
    return _capture_screen()


def capture_frame():
    """Raw PIL RGB image of the full desktop, for video recording.

    Distinct from `take_screenshot`: no grid, no downscale, no base64, no copy
    saved to disk — video recording needs the raw pixels as fast as possible.
    """
    return _capture_screen().convert("RGB")


def screen_fingerprint(window_title: str | None = None, size=(16, 9)) -> tuple:
    """Tiny grayscale sample of the screen (or one window) for local comparison.

    Never encoded, never saved: the autonomous watch loop calls this every few
    seconds for up to an hour, so it must stay cheap and leave no files behind.
    """
    from PIL import Image
    img = None
    if window_title:
        found = find_window(window_title)
        if found:
            try:
                img = _capture_hwnd(found[0], found[1])
            except Exception:  # noqa: BLE001 - fall back to the whole screen
                img = None
    if img is None:
        img = _capture_screen()
    small = img.convert("L").resize(size, Image.BILINEAR)
    pixels = getattr(small, "get_flattened_data", small.getdata)
    return tuple(pixels())


def take_screenshot(grid: bool = False, max_width: int = 0,
                    window_title: str | None = None,
                    jpeg_quality: int = 0) -> str:
    """Base64 screenshot of the full screen, or ONLY `window_title`.

    See `capture_for_model` for the parameters; this is the plain-image entry
    point (UI, API, tests) which does not care about the pixel scale.
    """
    return capture_for_model(grid, max_width, window_title, jpeg_quality)[0]


def capture_for_model(grid: bool = False, max_width: int = 0,
                      window_title: str | None = None,
                      jpeg_quality: int = 0, with_geometry: bool = False) -> tuple:
    """Capture for the model: (base64 image, image px -> real px scale).

    grid      : draw a labeled coordinate grid so the model can aim precisely.
    max_width : downscale the image to this width for the model (0 = keep 1:1).
    window_title : case-insensitive substring of the window title to capture.
    jpeg_quality : >0 encodes JPEG at this quality (3-8x lighter payload =
                   much lower API latency). 0 keeps lossless PNG.

    Coordinates in the returned image are relative to the WINDOW origin when
    a window capture is requested, else to the SCREEN origin. `scale` is what
    converts a coordinate the model read in the image back to a real pixel.
    A copy is saved in data/shots/.
    """
    from PIL import Image, ImageGrab

    hwnd = None
    rect = None
    if window_title:
        found = find_window(window_title)
        if found:
            hwnd, rect, _wtitle = found

    img = None
    origin = (0, 0)
    if _SYSTEM == "Windows":
        origin = (ctypes.windll.user32.GetSystemMetrics(76),
                  ctypes.windll.user32.GetSystemMetrics(77))
    if hwnd is not None:
        try:
            if ctypes.windll.user32.IsIconic(hwnd):
                raise ValueError("La fenêtre choisie est réduite. Restaure-la avant de lancer l'agent.")
            try:
                img = _capture_hwnd_printwindow(hwnd, rect)
            except Exception:
                img = _capture_hwnd(hwnd, rect)
            origin = (rect["x"], rect["y"])
        except Exception as e:
            raise RuntimeError(f"Capture de la fenêtre impossible : {e}") from e
    elif window_title:
        raise ValueError(f"Fenêtre introuvable : {window_title}. Actualise la sélection.")
    if img is None:
        img = _capture_screen()

    real_w, real_h = img.size
    if real_w <= 0 or real_h <= 0:
        raise RuntimeError("La capture obtenue est vide. Restaure ou redimensionne la fenêtre cible.")
    shrink = 1.0
    if max_width and max_width < real_w:
        shrink = max_width / real_w
        # BILINEAR instead of LANCZOS: a screenshot does not need the sharpest
        # resampler, and this halves the resize cost (~28ms -> ~14ms at 1920px)
        img = img.resize((max_width, max(1, int(real_h * shrink))), Image.BILINEAR)

    if grid:
        # Labels and action arguments use ONE space: pixels of the sent image.
        img = _draw_grid(img, img.width, img.height, 1.0)

    buf = io.BytesIO()
    ext = "png"
    if jpeg_quality and jpeg_quality > 0:
        # no optimize=: it only shaves bytes off an image the model reads once,
        # at the cost of CPU on every capture
        img.convert("RGB").save(buf, format="JPEG", quality=int(jpeg_quality))
        ext = "jpg"
    else:
        img.convert("RGB").save(buf, format="PNG", compress_level=1)
    data = buf.getvalue()

    # Copying every shot to disk must not slow the loop down: the file write is
    # cheap, but glob+stat over the whole folder is not, so housekeeping runs
    # only once every SHOT_CLEAN_EVERY captures.
    try:
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (shots_dir() / f"shot_{stamp}.{ext}").write_bytes(data)
        _SHOT_TICK["n"] += 1
        if _SHOT_TICK["n"] % SHOT_CLEAN_EVERY == 0:
            saved = sorted(shots_dir().glob("shot_*"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in saved[120:]:
                try:
                    old.unlink()
                except OSError:
                    pass
    except OSError:
        pass

    # real_w / img.width: the factor callers need, i.e. image px -> real px
    result = (base64.b64encode(data).decode("ascii"), real_w / img.width)
    if with_geometry:
        return (*result, {"origin": origin, "scale_y": real_h / img.height,
                          "width": img.width, "height": img.height,
                          "real_w": real_w, "real_h": real_h})
    return result


def _draw_grid(img, real_w: int, real_h: int, scale: float):
    """Grid labeled in NORMALIZED 0-1000 coordinates — the convention vision
    models (Gemini especially) are trained to emit. Lines every 50 units,
    labels every 100, both axes."""
    from PIL import ImageDraw

    d = ImageDraw.Draw(img, "RGBA")
    w, h = img.width, img.height
    small = w < 700
    fs = 8 if small else max(9, int(12 * (scale or 1.0)))
    step = 100 if small else 50

    for n in range(0, 1001, step):
        px = round(n * w / 1000)
        d.line([(px, 0), (px, h)], fill=(255, 80, 80, 45), width=1)
        if n % 100 == 0:
            d.text((min(px + 2, w - fs * 3 - 2), 2), str(n), fill=(255, 210, 80, 230))
            d.text((min(px + 2, w - fs * 3 - 2), h - fs - 3), str(n), fill=(255, 210, 80, 230))
    for n in range(0, 1001, step):
        py = round(n * h / 1000)
        d.line([(0, py), (w, py)], fill=(255, 80, 80, 45), width=1)
        if n % 100 == 0:
            d.text((2, min(py + 2, h - fs - 3)), str(n), fill=(255, 210, 80, 230))
            d.text((w - fs * 3 - 2, min(py + 2, h - fs - 3)), str(n), fill=(255, 210, 80, 230))
    return img
