"""Saved automations: open something directly, then optionally hand a goal to
the agent — on demand, or when Windows starts.

An automation is {name, target, goal, at_startup}:
- `target` is opened WITHOUT any AI call (instant, free, deterministic): an
  app name ("discord"), a web link, or a Discord link — a group/channel link
  opens the desktop app straight in that conversation;
- `goal`, if any, is then run by the agent like a goal typed in the window.

Same atomic-write discipline as sessions.py; stored in data/automations.json.
"""
import json
import os
import re
import sys
import tempfile
import threading
import time
import uuid

from .paths import data_dir

_lock = threading.Lock()
MAX_AUTOMATIONS = 50
STARTUP_FLAG = "--startup"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "AgentScreen"

# https://discord.com/channels/<server or @me>/<channel>[/<message>] — what
# "Copier le lien du message" and the browser address bar both give
_DISCORD_RE = re.compile(
    r"^(?:https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com|discord://-?)"
    r"/channels/(@me|\d+)/(\d+)", re.I)


def automations_file():
    return data_dir() / "automations.json"


def _clean(item):
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "").strip()[:80]
    target = str(item.get("target") or "").strip()[:500]
    goal = str(item.get("goal") or "").strip()[:2000]
    if not name or not (target or goal):
        return None
    return {"id": str(item.get("id") or uuid.uuid4().hex)[:64], "name": name,
            "target": target, "goal": goal, "at_startup": bool(item.get("at_startup"))}


def load_all() -> list:
    try:
        raw = json.loads(automations_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = [_clean(x) for x in raw] if isinstance(raw, list) else []
    return [x for x in items if x][:MAX_AUTOMATIONS]


def _write(items):
    path = automations_file()
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".automations-", suffix=".tmp",
                                         delete=False) as f:
            name = f.name
            json.dump(items, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def save(item) -> dict:
    """Add or replace (same id) one automation."""
    clean = _clean(item)
    if clean is None:
        raise ValueError("Donne un nom, et au moins une cible à ouvrir ou un objectif.")
    with _lock:
        items = load_all()
        for i, old in enumerate(items):
            if old["id"] == clean["id"]:
                items[i] = clean
                break
        else:
            items.append(clean)
        _write(items[:MAX_AUTOMATIONS])
    return clean


def delete(automation_id) -> None:
    with _lock:
        _write([x for x in load_all() if x["id"] != automation_id])


# ------------------------------------------------------------------ opening
def discord_link(target: str) -> str:
    """The desktop-app form of a Discord conversation link, or '' if it is
    not one. discord://-/channels/A/B opens Discord directly in that group,
    channel or DM instead of a browser tab."""
    m = _DISCORD_RE.match(str(target or "").strip())
    return f"discord://-/channels/{m.group(1)}/{m.group(2)}" if m else ""


def open_target(target: str) -> dict:
    """Open what an automation points at. No AI, no screenshot."""
    target = str(target or "").strip()
    from . import apps, input_control
    link = discord_link(target)
    if link:
        try:
            os.startfile(link)          # handled by the installed Discord app
        except (OSError, AttributeError):
            # Discord not installed (or not Windows): the web version still works
            target = link.replace("discord://-", "https://discord.com", 1)
        else:
            # the link navigates Discord but leaves it minimised or behind the
            # other windows (measured); it may also still be starting
            for _ in range(20):
                if apps.focus_app("discord").get("ok"):
                    break
                time.sleep(0.5)
            return {"ok": True, "opened": link}
    if re.match(r"^(https?://|www\.)", target, re.I):
        return input_control.open_url(target)
    return apps.launch_app(target, keyboard_fallback=input_control.start_menu_search)


# ---------------------------------------------------------- Windows startup
def startup_command() -> str:
    """Command Windows runs at sign-in: this app, flagged so it knows to play
    the automations marked 'au démarrage'."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {STARTUP_FLAG}'
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")   # no console window
    return f'"{pythonw if os.path.isfile(pythonw) else exe}" "{os.path.join(root, "run_app.py")}" {STARTUP_FLAG}'


def windows_startup_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, RUN_NAME)[0])
    except (ImportError, OSError):
        return False


def set_windows_startup(enabled: bool) -> None:
    """Add/remove this app in the current user's sign-in programs (HKCU Run:
    no admin rights, visible and removable in Task Manager > Startup)."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
