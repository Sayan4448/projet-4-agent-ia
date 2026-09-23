"""Local, atomic store of finished agent runs: the Agent mode's own history.

Mirrors `conversations.py` (same atomic-write discipline) but for agent
sessions instead of chat discussions: each run keeps its goal, its outcome and
a compact list of text events (thoughts, actions, replies, guidance, errors).
Screenshots are intentionally NOT stored, so the file stays small and personal
images never accumulate in data/agent_sessions.json.
"""
import json
import os
import tempfile
import threading
import time
import uuid

from .paths import data_dir

_lock = threading.Lock()
MAX_SESSIONS = 200
MAX_EVENTS = 500
MAX_TEXT = 4000

KINDS = ("goal", "thought", "action", "action_error", "message", "guidance",
         "banner", "fallback", "video", "done", "error", "note", "result")


def sessions_file():
    return data_dir() / "agent_sessions.json"


def _clean_event(event):
    if not isinstance(event, dict) or event.get("kind") not in KINDS:
        return None
    try:
        step = max(0, min(9999, int(event.get("step", 0) or 0)))
    except (TypeError, ValueError):
        step = 0
    return {"kind": event["kind"], "step": step,
            "text": str(event.get("text", ""))[:MAX_TEXT]}


def _clean_session(item):
    if not isinstance(item, dict):
        return None
    raw_events = item.get("events", [])
    if not isinstance(raw_events, list):
        raw_events = []
    kept = raw_events if len(raw_events) <= MAX_EVENTS else [raw_events[0], *raw_events[-(MAX_EVENTS - 1):]]
    events = [e for e in (_clean_event(e) for e in kept) if e]
    try:
        started = float(item.get("started", 0))
    except (TypeError, ValueError):
        started = 0
    return {"id": str(item.get("id") or uuid.uuid4().hex)[:64],
            "goal": str(item.get("goal") or "")[:200],
            "started": started,
            "outcome": str(item.get("outcome") or "error")[:30],
            "mode": str(item.get("mode") or "")[:80],
            "events": events}


def load_all():
    path = sessions_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = [_clean_session(x) for x in raw] if isinstance(raw, list) else []
    items = [x for x in items if x]
    return sorted(items, key=lambda x: -x["started"])


def history_items(query="", kind="Tous"):
    from . import conversations
    items = [{**s, "kind": "Agent"} for s in load_all()] if kind != "Chat" else []
    if kind != "Agent":
        for c in conversations.load_all():
            items.append({"id": c["id"], "kind": "Chat", "goal": c["title"],
                          "started": c["updated"], "outcome": "chat", "mode": "Chat", "chat": c,
                          "events": [{"kind": "guidance" if m["role"] == "user" else "message",
                                      "step": 0, "text": m["text"]} for m in c["messages"]]})
    query = str(query).strip().casefold()
    if query:
        items = [s for s in items if query in
                 (s["goal"] + " " + " ".join(e["text"] for e in s["events"])).casefold()]
    return sorted(items, key=lambda s: -s["started"])


def _write(items):
    path = sessions_file()
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".agent-sessions-", suffix=".tmp",
                                         delete=False) as f:
            name = f.name
            json.dump(items, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def save_session(session):
    clean = _clean_session(session)
    if clean is None:
        raise ValueError("Session d'agent invalide")
    with _lock:
        items = [x for x in load_all() if x["id"] != clean["id"]]
        items.append(clean)
        items.sort(key=lambda x: -x["started"])
        _write(items)
    return clean


def delete(session_id):
    with _lock:
        items = [x for x in load_all() if x["id"] != session_id]
        _write(items)


def new_session(goal, mode=""):
    return {"id": uuid.uuid4().hex, "goal": str(goal or "")[:200],
            "started": time.time(), "outcome": "error",
            "mode": str(mode or "")[:80], "events": []}
