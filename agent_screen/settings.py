"""Settings persistence: config.json (+ optional .env fallback for API keys)."""
import json
import os
import tempfile
import threading

from .paths import config_file, env_file_candidates, legacy_config_candidates

LOCAL_PROVIDERS = ("ollama", "lmstudio")
PROVIDERS = ["gemini", "openai", "anthropic", "groq", "deepseek", "openrouter", *LOCAL_PROVIDERS]

def _default_models() -> dict:
    return {
        "gemini": "gemini-3.5-flash-lite",
        "openai": "gpt-4.1-mini",
        "anthropic": "claude-sonnet-4-5",
        "groq": "meta-llama/llama-4-scout-17b-16e-instruct",
        "deepseek": "deepseek-chat",
        "openrouter": "google/gemini-2.5-flash",
        "ollama": "",
        "lmstudio": "",
    }

DEFAULTS = {
    "provider": "gemini",
    "api_keys": {p: "" for p in PROVIDERS},
    "models": _default_models(),
    "max_steps": 12,
    "grid": True,               # coordinate grid overlay on screenshots
    "image_width": 1280,        # downscaled image width for the model (0 = full)
    "game_mode": False,         # raw scan-code keys + relative mouse (games)
    "window_mode": False,       # capture only the selected window
    "window_title": "",         # window title substring for window capture
    "step_delay": 0.4,          # seconds between steps (low latency)
    "screenshot_each_action": False,  # extra screenshot after every action
    "jpeg_quality": 80,         # screenshot JPEG quality (0 = PNG)
    "free_mouse": True,         # give the mouse back between steps
    "language": "fr",           # ui language: 'fr' or 'en'
    "models_available": {},     # provider -> [model ids] cached from the API
    "execution_mode": "desktop",
    "eco_mode": False,
    "virtual_cursor": True,
    "limit_actions_per_capture": True,
    "actions_per_capture": 3,
    "local_urls": {"ollama": "http://127.0.0.1:11434", "lmstudio": "http://127.0.0.1:1234/v1"},
}


def _merge_modes(cfg, source):
    """Shared validation for persisted run options and local server addresses."""
    for key in ("eco_mode", "virtual_cursor", "limit_actions_per_capture"):
        if key in source:
            cfg[key] = bool(source[key])
    if source.get("execution_mode") in ("desktop", "browser"):
        cfg["execution_mode"] = source["execution_mode"]
    if "actions_per_capture" in source:
        try:
            cfg["actions_per_capture"] = max(1, min(12, int(source["actions_per_capture"])))
        except (ValueError, TypeError, OverflowError):
            pass
    urls = source.get("local_urls")
    if isinstance(urls, dict):
        from urllib.parse import urlsplit
        for p in LOCAL_PROVIDERS:
            value = str(urls.get(p, "")).strip().rstrip("/")
            try:
                parsed = urlsplit(value)
                if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username:
                    cfg["local_urls"][p] = value
            except ValueError:
                pass

# env var names per provider, for the optional .env fallback
ENV_KEYS = {
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
}

_lock = threading.Lock()


def _write_config(path, cfg):
    """Replace only a complete config; keep a damaged original for recovery."""
    if _unreadable_config(path):
        raise ValueError(f"Configuration illisible, fichier conservé : {path}")
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".config-", suffix=".tmp", delete=False) as f:
            name = f.name
            json.dump(cfg, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def _unreadable_config(path) -> bool:
    """True when `path` exists but cannot be used as a config.

    Such a file is preserved, never replaced: it may be half-written by another
    instance, or it may not be a config at all.
    """
    try:
        if not path.is_file():
            return False
        return not isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
    except (OSError, ValueError):
        return True


def migrate_legacy_keys() -> bool:
    """Import the API keys of an older version's config (v1.0-1.2 wrote them
    next to the exe instead of LOCALAPPDATA).

    Explicit on purpose: the entry points call it once at startup, because
    reading a config must never write one. It writes only when there really is
    something to import, only to the real config file, and never over a file it
    could not parse — silently replacing that file with defaults plus migrated
    keys would destroy settings the user still has.
    """
    with _lock:
        target = config_file()
        if _unreadable_config(target):
            return False
        cfg = _deep_merged_config()
        if any(cfg["api_keys"].get(p) for p in PROVIDERS):
            return False                    # nothing to migrate
        for legacy in legacy_config_candidates():
            try:
                old = json.loads(legacy.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            keys = old.get("api_keys", {}) if isinstance(old, dict) else {}
            if not isinstance(keys, dict):
                continue
            # skip placeholder junk like 'sk-test': only real keys are migrated
            imported = [p for p in PROVIDERS
                        if len(str(keys.get(p, "") or "").strip()) >= 20]
            if not imported:
                continue
            for p in imported:
                cfg["api_keys"][p] = str(keys[p]).strip()
            models = old.get("models", {})
            if isinstance(models, dict):
                for p in PROVIDERS:
                    m = str(models.get(p, "") or "").strip()
                    if m:
                        cfg["models"][p] = m
            _write_config(target, cfg)
            return True
    return False


def _deep_merged_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    f = config_file()
    if f.is_file():
        try:
            stored = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                _merge_modes(cfg, stored)
                # every other field below is coerced, so a hand-edited config.json
                # cannot crash the app either: a non-string provider ('42') broke
                # get_provider_keys() before the window ever appeared
                prov = str(stored.get("provider", cfg["provider"]) or "").strip().lower()
                cfg["provider"] = prov if prov in PROVIDERS else cfg["provider"]
                keys = stored.get("api_keys", {})
                if isinstance(keys, dict):
                    for p in PROVIDERS:
                        cfg["api_keys"][p] = str(keys.get(p, "") or "")
                models = stored.get("models", {})
                if isinstance(models, dict):
                    for p in PROVIDERS:
                        cfg["models"][p] = str(models.get(p, cfg["models"][p]) or cfg["models"][p])
                try:
                    cfg["max_steps"] = max(1, min(40, int(stored.get("max_steps", cfg["max_steps"]) or cfg["max_steps"])))
                except (TypeError, ValueError):
                    pass
                cfg["grid"] = bool(stored.get("grid", cfg["grid"]))
                try:
                    cfg["image_width"] = max(0, min(2560, int(stored.get("image_width", cfg["image_width"]) or 0)))
                except (TypeError, ValueError):
                    pass
                cfg["game_mode"] = bool(stored.get("game_mode", cfg["game_mode"]))
                cfg["window_mode"] = bool(stored.get("window_mode", cfg["window_mode"]))
                cfg["window_title"] = str(stored.get("window_title", cfg["window_title"]) or "")
                try:
                    cfg["step_delay"] = max(0.0, min(10.0, float(stored.get("step_delay", cfg["step_delay"]))))
                except (TypeError, ValueError):
                    pass
                cfg["screenshot_each_action"] = bool(stored.get("screenshot_each_action", cfg["screenshot_each_action"]))
                cfg["free_mouse"] = bool(stored.get("free_mouse", cfg["free_mouse"]))
                try:
                    cfg["jpeg_quality"] = max(0, min(95, int(stored.get("jpeg_quality", cfg["jpeg_quality"]) or 0)))
                except (TypeError, ValueError):
                    pass
                ma = stored.get("models_available")
                if isinstance(ma, dict):
                    clean = {p: [str(x) for x in ma[p]][:300]
                             for p in PROVIDERS if isinstance(ma.get(p), list)}
                    cfg["models_available"] = clean
                lang = str(stored.get("language", cfg["language"])).lower()
                cfg["language"] = lang if lang in ("fr", "en") else "fr"
        except (OSError, ValueError):
            pass
    return cfg


def load() -> dict:
    with _lock:
        return _deep_merged_config()


def save(partial: dict) -> dict:
    """Merge a partial settings dict into config.json and return the new settings."""
    with _lock:
        cfg = _deep_merged_config()
        provider = str(partial.get("provider", "")).strip().lower()
        _merge_modes(cfg, partial)
        if provider in PROVIDERS:
            cfg["provider"] = provider
        keys = partial.get("api_keys")
        if isinstance(keys, dict):
            for p in PROVIDERS:
                if p in keys:
                    # strip copy/paste artifacts (spaces, quotes, prefix labels)
                    raw = str(keys.get(p, "") or "").strip().strip('"').strip("'")
                    raw = raw.split(":")[-1].strip() if raw.lower().startswith(("gemini:", "openai:")) else raw
                    cfg["api_keys"][p] = ", ".join(split_keys(raw))
        models = partial.get("models")
        if isinstance(models, dict):
            for p in PROVIDERS:
                if p in models:
                    cfg["models"][p] = str(models.get(p, "") or "").strip()
        try:
            cfg["max_steps"] = max(1, min(40, int(partial.get("max_steps", cfg["max_steps"]))))
        except (TypeError, ValueError):
            pass
        if "grid" in partial:
            cfg["grid"] = bool(partial["grid"])
        if "image_width" in partial:
            try:
                cfg["image_width"] = max(0, min(2560, int(partial["image_width"] or 0)))
            except (TypeError, ValueError):
                pass
        if "game_mode" in partial:
            cfg["game_mode"] = bool(partial["game_mode"])
        if "window_mode" in partial:
            cfg["window_mode"] = bool(partial["window_mode"])
        if "window_title" in partial:
            cfg["window_title"] = str(partial["window_title"] or "")
        if "step_delay" in partial:
            try:
                cfg["step_delay"] = max(0.0, min(10.0, float(partial["step_delay"])))
            except (TypeError, ValueError):
                pass
        if "screenshot_each_action" in partial:
            cfg["screenshot_each_action"] = bool(partial["screenshot_each_action"])
        if "free_mouse" in partial:
            cfg["free_mouse"] = bool(partial["free_mouse"])
        if "jpeg_quality" in partial:
            try:
                cfg["jpeg_quality"] = max(0, min(95, int(partial["jpeg_quality"] or 0)))
            except (TypeError, ValueError):
                pass
        if isinstance(partial.get("models_available"), dict):
            ma = dict(cfg["models_available"])
            for p, lst in partial["models_available"].items():
                if p in PROVIDERS and isinstance(lst, list):
                    ma[p] = [str(x) for x in lst][:300]
            cfg["models_available"] = ma
        if "language" in partial:
            lang = str(partial["language"] or "fr").lower()
            cfg["language"] = lang if lang in ("fr", "en") else "fr"
        _write_config(config_file(), cfg)
        return json.loads(json.dumps(cfg))


def split_keys(raw: str) -> list:
    """Split comma, semicolon, newline or space separated keys."""
    if not raw:
        return []
    import re
    parts = re.split(r"[,;\s]+", str(raw))
    out = []
    for p in parts:
        s = p.strip().strip('"').strip("'")
        if s and len(s) >= 4 and s not in out:
            out.append(s)
    return out


def get_provider_keys(provider: str) -> list:
    """All configured keys for a provider (config.json + environment)."""
    provider = (provider or "").lower()
    keys = []
    raw = load()["api_keys"].get(provider, "")
    if raw:
        keys.extend(split_keys(raw))
    for env_name in ENV_KEYS.get(provider, []):
        val = os.environ.get(env_name, "").strip()
        if val:
            for k in split_keys(val):
                if k not in keys:
                    keys.append(k)
    return keys


def get_available_providers() -> list:
    """List providers that have at least one usable key configured."""
    return [p for p in PROVIDERS if get_provider_keys(p)]


def get_api_key(provider: str) -> str:
    """Key from config.json first, then from environment / .env file."""
    provider = (provider or "").lower()
    keys = get_provider_keys(provider)
    if keys:
        return keys[0]
    return ""


def env_file_path():
    for candidate in env_file_candidates():
        if candidate.is_file():
            return candidate
    return None
