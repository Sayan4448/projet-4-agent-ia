"""Small, local and atomic conversation store. It never calls an AI service."""
import json
import os
import tempfile
import threading
import time
import uuid

from .paths import conversations_file

_lock = threading.Lock()
MAX_CONVERSATIONS = 200
MAX_MESSAGES = 200
MAX_TEXT = 30000


def _clean_message(message):
    if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
        return None
    text = str(message.get("text", ""))[:MAX_TEXT]
    return {"role": message["role"], "text": text,
            "provider": str(message.get("provider", ""))[:30]}


def _clean_conversation(item):
    if not isinstance(item, dict):
        return None
    messages = [_clean_message(m) for m in item.get("messages", [])[:MAX_MESSAGES]]
    messages = [m for m in messages if m]
    try:
        updated = float(item.get("updated", 0))
    except (TypeError, ValueError):
        updated = 0
    return {"id": str(item.get("id") or uuid.uuid4().hex)[:64],
            "title": str(item.get("title") or "Nouvelle discussion")[:80],
            "favorite": bool(item.get("favorite", False)), "updated": updated,
            "messages": messages}


def load_all():
    path = conversations_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = [_clean_conversation(x) for x in raw] if isinstance(raw, list) else []
    items = [x for x in items if x]
    return sorted(items, key=lambda x: (not x["favorite"], -x["updated"]))[:MAX_CONVERSATIONS]


def _write(items):
    path = conversations_file()
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".conversations-", suffix=".tmp", delete=False) as f:
            name = f.name
            json.dump(items, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def save_conversation(conversation):
    clean = _clean_conversation(conversation)
    if clean is None:
        raise ValueError("Discussion invalide")
    clean["updated"] = time.time()
    with _lock:
        items = [x for x in load_all() if x["id"] != clean["id"]]
        items.append(clean)
        items.sort(key=lambda x: (not x["favorite"], -x["updated"]))
        _write(items[:MAX_CONVERSATIONS])
    return clean


def delete(conversation_id):
    with _lock:
        items = [x for x in load_all() if x["id"] != conversation_id]
        _write(items)


def new_conversation():
    return {"id": uuid.uuid4().hex, "title": "Nouvelle discussion",
            "favorite": False, "updated": time.time(), "messages": []}


def title_from(text):
    """Free title: derive it locally instead of spending an AI request."""
    one_line = " ".join(str(text).split())
    return (one_line[:47] + "…") if len(one_line) > 48 else (one_line or "Nouvelle discussion")
