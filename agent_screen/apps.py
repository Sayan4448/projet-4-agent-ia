"""App identity: turn a spoken name into a real program, launch it, verify it.

Why this module exists
----------------------
The worst failure of earlier versions was "open Brave" ending with a random
taskbar icon being clicked (Discord), because two things were wrong:

1. `open_app` fell back to typing the name into the Start menu and then
   REPORTED SUCCESS even when nothing had started (silent false positive).
2. The model had no way to switch to an app that was already running, so it
   guessed among look-alike icons.

Here, opening an app is deterministic and *verified*:

    resolve_app(name) -> a concrete target: exe path, Start-menu shortcut (.lnk)
                         or a UWP/Store AppID — or None. Pure: no launching.
    launch_app(name)  -> focuses it if it already runs, else launches it and
                         waits until a new window really belongs to it.
                         Reports ok=true/false honestly.
    focus_app(name)   -> brings the running app matching a spoken name forward.

The app table itself is data in `app_catalog.py`; everything about the windows
on screen (enumeration, identity, activation) lives in `display.py`. This
module only decides *which* program a name means and *whether it came up*.

No PowerShell string is ever built from user/model text here (the old
`Start-Process '{name}'` was injectable): we use ShellExecute / Popen lists.
"""
import glob as _glob
import os
import re
import shutil
import subprocess
import time

from . import display
from .app_catalog import APPS, START_MENU_ROOTS

_WIN = os.name == "nt"

_STOPWORDS = {
    "open", "ouvre", "ouvrir", "lance", "lancer", "demarre", "demarrer", "start",
    "app", "apps", "application", "program", "programme", "logiciel", "le", "la",
    "les", "un", "une", "des", "the", "a", "s'il", "te", "plait", "please", "moi",
    "window", "fenetre", "fenêtre",
}# ------------------------------------------------------------------- helpers
def tokens(text: str) -> list:
    """Normalised words of an app name, without stopwords/extension/accents."""
    t = display.fold(text)
    t = re.sub(r"\.(exe|lnk|cmd|bat|com)$", "", t)
    out = []
    for raw in re.split(r"[^a-z0-9+]+", t):
        if raw and raw not in _STOPWORDS:
            out.append(raw)
    return out


def score(query_tokens, key_tokens) -> float:
    """0..1 similarity used to match a spoken name against a catalogue key."""
    q, k = set(query_tokens or ()), set(key_tokens or ())
    if not q or not k:
        return 0.0
    if q <= k:
        return 1.0
    if k <= q:
        return 0.9
    return len(q & k) / len(q | k)


def find_app_entry(name: str):
    """Best catalogue entry for `name`, or None. Pure (no filesystem access)."""
    q = tokens(name)
    if not q:
        return None
    best, best_score = None, 0.0
    for entry in APPS:
        s = max(score(q, tokens(key)) for key in entry["keys"])
        for exe in entry["exes"]:
            s = max(s, score(q, tokens(exe)))
        if s > best_score:
            best, best_score = entry, s
    return best if best_score >= 0.5 else None


def _app_paths(exe: str):
    """Executable registered under App Paths (32/64-bit, machine or user)."""
    if not _WIN:
        return None
    import winreg
    bases = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths")
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for base in bases:
            try:
                with winreg.OpenKey(root, base + "\\" + exe) as k:
                    val = winreg.QueryValue(k, None)
                if val and os.path.isfile(val):
                    return val
            except OSError:
                continue
            except Exception:  # noqa: BLE001 - registry access must never crash
                continue
    return None


_SHORTCUT_CACHE = {"t": 0.0, "items": []}
_START_APPS_CACHE = {"t": 0.0, "items": []}
_CACHE_TTL = 120.0


def start_menu_shortcuts() -> list:
    """[(display_name, .lnk path)] from both Start Menu folders (cached)."""
    now = time.time()
    if _SHORTCUT_CACHE["items"] and now - _SHORTCUT_CACHE["t"] < _CACHE_TTL:
        return _SHORTCUT_CACHE["items"]
    items = []
    for root in START_MENU_ROOTS:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if fn.lower().endswith(".lnk"):
                    items.append((os.path.splitext(fn)[0], os.path.join(dirpath, fn)))
    _SHORTCUT_CACHE.update(t=now, items=items)
    return items


def _ps_lines(script: str, timeout: float = 10.0) -> list:
    """Run a small PowerShell snippet and return its stdout lines (UTF-8)."""
    ps = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return []
    cmd = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
           "$ProgressPreference='SilentlyContinue';" + script)
    try:
        res = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                             capture_output=True, text=True, timeout=timeout,
                             encoding="utf-8", errors="replace")
        return [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001 - optional lookup only
        return []


def start_apps() -> list:
    """[(name, AppID)] of UWP/Store apps installed for the user (cached)."""
    now = time.time()
    if _START_APPS_CACHE["items"] and now - _START_APPS_CACHE["t"] < _CACHE_TTL:
        return _START_APPS_CACHE["items"]
    items = []
    for line in _ps_lines("Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }"):
        if "|" in line:
            name, _, appid = line.rpartition("|")
            if name.strip() and appid.strip():
                items.append((name.strip(), appid.strip()))
    _START_APPS_CACHE.update(t=now, items=items)
    return items


# -------------------------------------------------------------------- resolve
def resolve_app(name: str):
    """Turn a spoken/written app name into a launch plan, or None.

    Returns {"kind": "exe"|"lnk"|"appid", "target": ..., "name": ...,
             "titles": (...), "method": "..."}.
    Never builds a shell command line: callers get a path to hand to
    ShellExecute / Popen as a single argument.
    """
    raw = str(name or "").strip().strip('"').strip("'")
    if not raw:
        return None
    entry = find_app_entry(raw)
    q = tokens(raw)
    exe_candidates, path_candidates, glob_candidates = [], [], []
    if entry:
        exe_candidates.extend(entry["exes"])
        path_candidates.extend(entry["paths"])
        glob_candidates.extend(entry.get("globs", ()))
    if q and len(q) == 1:
        exe_candidates.append(q[0] + ".exe")
    if raw.lower().endswith((".exe", ".cmd", ".bat")):
        exe_candidates.insert(0, raw)

    titles = tuple(entry["titles"]) if entry else (raw.lower(),)
    display_name = entry["keys"][0] if entry else raw

    def _plan(kind, target, name, method, extra_titles=()):
        """Launch plan. `exes` lists the process names the window may belong
        to — it is what makes the post-launch verification trustworthy."""
        procs = list(exe_candidates)
        if kind == "exe" and target:
            procs.append(os.path.basename(str(target)))
        return {"kind": kind, "target": target, "name": name,
                "titles": tuple(titles) + tuple(extra_titles),
                "exes": tuple(dict.fromkeys(p for p in procs if p)),
                "method": method}

    # 1. versioned installs (Discord app-1.0.1234\Discord.exe, Slack app-*…)
    for pattern in glob_candidates:
        try:
            hits = sorted((h for h in _glob.glob(pattern) if os.path.isfile(h)), reverse=True)
        except Exception:  # noqa: BLE001 - a broken pattern is not fatal
            hits = []
        for hit in hits:
            return _plan("exe", hit, display_name, "glob-path")
    # 2. usual install locations
    for path in path_candidates:
        if path and os.path.isfile(path):
            return _plan("exe", path, display_name, "known-path")
    # 3. executable on PATH
    for exe in exe_candidates:
        found = shutil.which(exe)
        if found:
            return _plan("exe", found, display_name, "path")
    # 4. App Paths registry
    for exe in exe_candidates:
        found = _app_paths(os.path.basename(exe))
        if found:
            return _plan("exe", found, display_name, "registry")
    # 5. Start Menu shortcut (works for almost everything installed)
    lnk = _best_shortcut(raw)
    if lnk:
        return _plan("lnk", lnk[1], lnk[0], "start-menu", (lnk[0].lower(),))
    # 6. UWP / Store apps (the only way to reach e.g. "Paramètres")
    uwp = _best_start_app(raw)
    if uwp:
        return _plan("appid", uwp[1], uwp[0], "uwp", (uwp[0].lower(),))
    return None


def _best_shortcut(raw: str):
    """Best Start-Menu shortcut for a spoken name.

    Only the QUERY is scored, against the shortcut's real name: scoring each
    catalogue key against the candidate made "parametres" match "WSL Settings"
    (the English key 'settings' scored 1.0 against any "... Settings").
    """
    q = tokens(raw)
    best, best_score, best_depth = None, 0.0, 99
    for display_name, path in start_menu_shortcuts():
        s = score(q, tokens(display_name))
        if s < 0.5:
            continue
        depth = path.count(os.sep)
        if s > best_score or (s == best_score and depth < best_depth):
            best, best_score, best_depth = (display_name, path), s, depth
    return best


def _best_start_app(raw: str):
    """Best Store/UWP app for a spoken name (query scored against its real name)."""
    q = tokens(raw)
    best, best_score = None, 0.0
    for display_name, appid in start_apps():
        s = score(q, tokens(display_name))
        if s > best_score:
            best, best_score = (display_name, appid), s
    return best if best_score >= 0.6 else None


# --------------------------------------------------------- window matching
def _window_matches(w: dict, patterns, exes):
    """(score, title, process) of one window against the app we are looking for.

    Score meaning: 3 = title and owning process match, 2 = process matches,
    1 = title matches only, 0 = unknown new window, -1 = the window provably
    belongs to ANOTHER program (e.g. 'brave - Bloc-notes' titled after Brave
    but owned by notepad.exe): callers must not treat that as a match.
    """
    title = str(w.get("title", "")).strip()
    proc = display.window_exe(w.get("hwnd")) if w.get("hwnd") else ""
    if not title or display.is_noise(title):
        return 0, "", proc
    low = display.fold(title)
    title_hit = any(display.fold(p) in low for p in patterns if p)
    wanted = {str(e).lower() for e in (exes or ()) if e}
    proc_hit = bool(proc) and proc.lower() in wanted
    if wanted and proc and not proc_hit:
        return -1, title, proc
    if proc_hit and title_hit:
        return 3, title, proc
    if proc_hit:
        return 2, title, proc
    if title_hit:
        return 1, title, proc
    return 0, title, proc


def find_running_window(patterns, exes=(), fuzzy: bool = True) -> str:
    """Title of an ALREADY OPEN window that is confidently this app, or ''."""
    best, best_score = "", 0
    q = set()
    for p in patterns or ():
        q |= set(tokens(p))
    for w in display.list_windows():
        sc, title, _proc = _window_matches(w, patterns, exes)
        if sc > best_score and sc >= 1:
            best, best_score = title, sc
        elif fuzzy and title and sc == 0:
            s = score(q, tokens(title))
            if s >= 0.75 and s > best_score:
                best, best_score = title, s
    return best


def focus_app(name: str) -> dict:
    """Bring the running app matching a spoken name to the front.

    The name is matched against open windows the way an app name is matched
    against the catalogue, so "bloc-notes" finds a "Document - Notepad"
    window; the actual activation is display.activate_window.
    """
    raw = str(name or "").strip()
    if not raw:
        return {"ok": False, "title": "", "error": "no window title given"}
    return display.activate_window(find_running_window((raw,), ()) or raw)


# --------------------------------------------------------------------- launch
def _spawn(plan: dict) -> None:
    """Start the resolved target. No shell string is ever involved."""
    kind, target = plan["kind"], plan["target"]
    if kind == "appid":
        try:
            os.startfile("shell:AppsFolder\\" + target)
        except OSError:
            subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + target],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    elif kind == "exe":
        os.startfile(target)
    else:
        os.startfile(target)


def _wait_for_window(before, patterns, exes, wait: float):
    """(ok, title, verified) for a NEW window belonging to the app.

    `verified` is False when we only saw an unattributable new window: the app
    may have opened, or it may be a splash screen / another program. Callers
    report that nuance instead of pretending the launch was confirmed.
    """
    deadline = time.time() + max(0.5, float(wait))
    weak, weak_verified = "", False
    while time.time() < deadline:
        try:
            current = display.list_windows()
        except Exception:  # noqa: BLE001
            current = []
        for w in current:
            title = str(w.get("title", "")).strip()
            if not title or title in before or display.is_noise(title):
                continue
            sc, matched, _proc = _window_matches(w, patterns, exes)
            if sc >= 2:
                return True, matched, True
            if sc == 1 and not weak:
                # right title, process unknown: good but not proven
                weak, weak_verified = matched, False
            elif sc <= 0 and not weak:
                # a brand-new window we cannot attribute (unknown process, or a
                # process we did not expect, e.g. Calculator.exe for calc):
                # weak evidence — it must never be reported as verified
                weak, weak_verified = title, False
        time.sleep(0.3)
    if weak:
        return True, weak, weak_verified
    return False, "", False


def launch_app(name: str, wait: float = 8.0, keyboard_fallback=None) -> dict:
    """Launch (or focus) an app and VERIFY that it really came up.

    `keyboard_fallback(name)` is an optional callable used only as a last
    resort (typing the name in the Start menu); it is provided by
    input_control so this module stays free of pyautogui.
    """
    raw = str(name or "").strip()
    if not raw:
        return {"ok": False, "opened": None, "error": "no application name given"}

    plan = resolve_app(raw)
    if plan:
        exes = tuple(plan.get("exes") or ())
        patterns = tuple(plan["titles"]) + (plan["name"],)
    else:
        exes = ()
        patterns = (raw.lower(),)

    # already running? focus it — instant, and it never confuses look-alike icons
    running = find_running_window(patterns, exes)
    if running:
        display.activate_window(running)
        return {"opened": raw, "ok": True, "method": "focus",
                "already_running": True, "window": running, "verified": True}

    before = {w["title"] for w in display.interesting_windows(0)}
    tries = []
    if plan:
        try:
            _spawn(plan)
        except Exception as e:  # noqa: BLE001
            tries.append(f"{plan['method']}: {e}")
        else:
            ok, found_title, verified = _wait_for_window(before, patterns, exes, wait)
            if ok:
                return {"opened": raw, "ok": True, "method": plan["method"],
                        "window": found_title, "verified": verified}
            tries.append(f"{plan['method']} ({plan['target']}): no window appeared")
    else:
        tries.append("application not found on this system")

    if keyboard_fallback is not None:
        try:
            keyboard_fallback(raw)
            ok, found_title, verified = _wait_for_window(before, patterns, exes, wait)
            if ok:
                return {"opened": raw, "ok": True, "method": "start-menu-search",
                        "window": found_title, "verified": verified}
            tries.append("start-menu search: no window appeared")
        except Exception as e:  # noqa: BLE001
            tries.append(f"start-menu search: {e}")

    return {"ok": False, "opened": raw,
            "error": f"could not open '{raw}' ({'; '.join(tries)})"}
