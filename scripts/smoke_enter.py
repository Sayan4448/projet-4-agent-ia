"""Reproduction harness for the "typed but never sent" Discord bug.

Creates a REAL native Win32 window whose WndProc mimics a message box:
- WM_CHAR characters accumulate in a field buffer,
- WM_KEYDOWN VK_RETURN "sends" if the buffer is non-empty, then clears it.

The counters prove exactly what the target application receives:
- `extended_enters`: Enter keydowns carrying the KB extended flag (bit 24)
  — Chromium reads those as NumpadEnter, and send handlers that check
  event.code ignore them. That was the root cause of the bug.
- `sent`: iterations where Enter found text in the field (message sent).
- `empty_enters`: Enter arrived while the field was empty (ordering/timing
  failure — the React state race shape).

Run: .venv/Scripts/python.exe scripts/smoke_enter.py [iterations=100]
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes

sys.path.insert(0, ".")
from agent_screen import input_control  # noqa: E402

WM_CHAR = 0x0102
WM_KEYDOWN = 0x0100
WM_DESTROY = 0x0002
VK_RETURN = 0x0D

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


wc = WNDCLASSEXW()
stats = {"chars": 0, "enters": 0, "extended_enters": 0,
         "sent": 0, "empty_enters": 0}
buffer = []
lock = threading.Lock()


def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_CHAR:
        with lock:
            buffer.append(chr(wparam))
        stats["chars"] += 1
    elif msg == WM_KEYDOWN and wparam == VK_RETURN:
        stats["enters"] += 1
        if (lparam >> 24) & 1:
            stats["extended_enters"] += 1
        with lock:
            text = "".join(buffer)
            buffer.clear()
        if text:
            stats["sent"] += 1
        else:
            stats["empty_enters"] += 1
    elif msg == WM_DESTROY:
        user32.PostQuitMessage(0)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def pump(hwnd_out, ready):
    # a window's messages only reach the GetMessage loop of the thread that
    # CREATED it — so create it here, inside the pumping thread
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "Smoke enter",
                                  0x00CF0000,  # WS_OVERLAPPEDWINDOW
                                  200, 200, 420, 220, None, None, wc.hInstance, None)
    if not hwnd:
        raise OSError("CreateWindowExW failed")
    user32.ShowWindow(hwnd, 5)   # SW_SHOW
    hwnd_out.append(hwnd)
    ready.set()
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    proc = WNDPROC(wnd_proc)
    wc.cbSize = ctypes.sizeof(wc)
    wc.lpfnWndProc = proc
    wc.lpszClassName = "AgentScreenSmokeEnter"
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.hCursor = user32.LoadCursorW(None, 32512)
    if not user32.RegisterClassExW(ctypes.byref(wc)):
        raise OSError("RegisterClassExW failed")
    hwnd_out, ready = [], threading.Event()
    threading.Thread(target=pump, args=(hwnd_out, ready), daemon=True).start()
    ready.wait(5.0)
    hwnd = hwnd_out[0]
    time.sleep(0.3)

    # the harness window lives in OUR process: bypass the anti-self-click
    # guard on purpose (that guard protects the real assistant UI, not this
    # test target), then aim the virtual pipeline at it like a real click
    input_control._check_target = lambda _hwnd: None
    input_control.reset_virtual_input()
    input_control._v_hwnd[0] = hwnd

    for i in range(n):
        input_control.virtual_type("salut")
        time.sleep(0.03)               # chars must land before Enter
        input_control.virtual_press_key("enter")
        time.sleep(0.03)
        if (i + 1) % 25 == 0:
            print(f"  ... {i + 1}/{n}")

    time.sleep(0.2)
    user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE: destroys on the owner thread
    total = stats["enters"] or n
    print(f"\niterations       : {n}")
    print(f"chars received   : {stats['chars']} (expected {5 * n})")
    print(f"enters received  : {stats['enters']} (expected {n})")
    print(f"EXTENDED enters  : {stats['extended_enters']}  <-- must be 0 "
          "(nonzero = NumpadEnter bug)")
    print(f"messages SENT    : {stats['sent']} / {n}  "
          f"({100.0 * stats['sent'] / max(1, total):.1f} %)")
    print(f"enters on empty  : {stats['empty_enters']}  <-- must be 0 "
          "(ordering failure)")
    ok = (stats["sent"] == n and stats["extended_enters"] == 0
          and stats["empty_enters"] == 0)
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
