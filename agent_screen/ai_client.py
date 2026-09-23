"""Unified multi-provider chat client (image-capable) using only `requests`.

Providers: Gemini (default), OpenAI, Anthropic, Groq, DeepSeek, OpenRouter.
- Human-readable error messages (no raw JSON dumps in the UI)
- list_models(provider): fetch the models actually available for the key,
  used by the GUI model picker.
- max_tokens auto-retry: if a provider rejects max_tokens, retry with a safe value.
"""
import json
import re
import queue
import threading

import requests

from .settings import get_api_key, LOCAL_PROVIDERS

TIMEOUT = 90

ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
}

PROVIDER_NAMES = {
    "gemini": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "groq": "Groq",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "ollama": "Ollama (local)",
    "lmstudio": "LM Studio (local)",
}

SAFE_MAX_TOKENS = 1024

MSG_RE = '"message"\\s*:\\s*"([^"]+)"'
ERR_RE = '"error"\\s*:\\s*"([^"]+)"'


class AIError(Exception):
    """User-facing AI error (message is already clean and printable)."""


def _provider_name(provider: str) -> str:
    return PROVIDER_NAMES.get(provider, provider)


def _explain_http(provider: str, status: int, text: str) -> str:
    """Turn provider errors into short, actionable French messages."""
    name = _provider_name(provider)
    t = (text or "")[:600]
    low = t.lower()

    def first(patterns):
        for pat in patterns:
            m = re.search(pat, t, re.I)
            if m:
                return m.group(1)[:200]
        return ""

    if status in (401, 403):
        detail = first([MSG_RE, '"error_message"\\s*:\\s*"([^"]+)"'])
        base = f"Clé API {name} refusée ({status}). "
        if "expired" in low or "revoked" in low:
            base += "La clé semble expirée ou révoquée — recrée-la sur le site du fournisseur."
        elif "quota" in low or "billing" in low or "credit" in low:
            base += "Problème de quota/facturation sur le compte du fournisseur."
        else:
            base += "Vérifie la clé dans ⚙ Paramètres (sans espaces, complète)."
        if detail:
            base += f"  [{detail}]"
        return base
    if status == 404:
        detail404 = first([MSG_RE])
        return (f"Modèle introuvable chez {name} (404). "
                f"Choisis un autre modèle dans le sélecteur.  [{detail404}]")
    if status == 429:
        return (f"Limite de requêtes/quota atteinte chez {name} (429). "
                "Attends un peu, ou utilise un autre fournisseur.")
    if status >= 500:
        return (f"Les serveurs {name} sont surchargés ou en panne ({status}). "
                "C'est temporaire — l'agent réessaie déjà automatiquement ; "
                "si ça persiste, choisis un autre modèle dans le sélecteur.")
    detail = first([MSG_RE, ERR_RE])
    return f"Erreur {name} ({status}): {detail or t[:200]}"


def _network_error(e: Exception) -> AIError:
    return AIError("Pas de connexion internet (ou réseau bloqué). "
                   "Vérifie ta connexion puis réessaie.")


# ----------------------------------------------------------------- chat paths
def _content_with_image(prompt: str, b64_png: str, mime: str = "image/png"):
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_png}"}},
    ]


def _normalize_media(media, fallback_mime="image/png"):
    """One or a few media blocks, capped to prevent accidental credit explosions."""
    if not media:
        return []
    if isinstance(media, str):
        return [(media, fallback_mime)]
    out = []
    for item in list(media)[:4]:
        if isinstance(item, str):
            out.append((item, fallback_mime))
        elif isinstance(item, (tuple, list)) and item:
            out.append((str(item[0]), str(item[1] if len(item) > 1 else fallback_mime)))
    return out


def _heal_deprecated_model(api_key: str, failed_model: str, error_text: str):
    """Google retires models over time; the 404 names a replacement
    ('models/gemini-3.5-flash-lite'). If that replacement exists for this
    key, switch to it and persist the choice so the 404 never shows again."""
    m = re.search(r"models/([A-Za-z0-9.\-]+)", error_text or "")
    if not m:
        return None
    suggestion = m.group(1)
    if suggestion == failed_model:
        return None
    try:
        r = _get(f"{ENDPOINTS['gemini']}/{suggestion}?key={api_key}", {})
        if r.status_code < 400:
            try:
                from .settings import save
                save({"models": {"gemini": suggestion}})
            except Exception:  # noqa: BLE001
                pass
            return suggestion
    except AIError:
        pass
    return None


def _post(url: str, headers: dict, body: dict, retry_5xx: int = 2) -> requests.Response:
    """POST with automatic retry on transient 5xx (Gemini free tier often
    answers 503 'model is overloaded' — retrying a few seconds later works)."""
    delay = 3.0
    for attempt in range(retry_5xx + 1):
        try:
            r = requests.post(url, headers=headers, data=json.dumps(body), timeout=TIMEOUT)
        except requests.RequestException as e:
            raise _network_error(e) from e
        if r.status_code < 500 or attempt >= retry_5xx:
            return r
        time.sleep(delay)
        delay *= 2
    return r


def _get(url: str, headers: dict) -> requests.Response:
    try:
        return requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise _network_error(e) from e


def _call_openai_style(provider: str, api_key: str, model: str, system: str,
                       prompt: str, b64_png, is_json: bool, max_tokens: int = 2048,
                       mime: str = "image/png") -> str:
    messages = [{"role": "system", "content": system}]
    media = _normalize_media(b64_png, mime)
    if media:
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {"url": f"data:{m};base64,{data}"}}
                    for data, m in media]
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages, "temperature": 0.2,
            "max_tokens": max_tokens}
    if is_json:
        body["response_format"] = {"type": "json_object"}
    r = _post(ENDPOINTS[provider],
              {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
              body)
    if r.status_code >= 400:
        # some models reject large max_tokens or response_format: retry once
        if r.status_code in (400, 422) and max_tokens != SAFE_MAX_TOKENS:
            return _call_openai_style(provider, api_key, model, system, prompt,
                                      b64_png, is_json, max_tokens=SAFE_MAX_TOKENS, mime=mime)
        if r.status_code in (400, 422) and is_json and "response_format" in body:
            body.pop("response_format")
            r2 = _post(ENDPOINTS[provider],
                       {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                       body)
            if r2.status_code < 400:
                data = r2.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
                if isinstance(content, list):
                    content = "".join(b.get("text", "") for b in content
                                      if isinstance(b, dict))
                return (content or "").strip()
            r = r2
        raise AIError(_explain_http(provider, r.status_code, r.text))
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return (content or "").strip()


def _call_anthropic(api_key: str, model: str, system: str,
                    prompt: str, b64_png, is_json: bool, max_tokens: int = 2048,
                    mime: str = "image/png") -> str:
    content = []
    for data, media_type in _normalize_media(b64_png, mime):
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data}})
    content.append({"type": "text", "text": prompt})
    body = {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": content}]}
    r = _post(ENDPOINTS["anthropic"],
              {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "Content-Type": "application/json"}, body)
    if r.status_code >= 400:
        if r.status_code in (400, 422) and max_tokens != SAFE_MAX_TOKENS:
            return _call_anthropic(api_key, model, system, prompt, b64_png, is_json,
                                   max_tokens=SAFE_MAX_TOKENS, mime=mime)
        raise AIError(_explain_http("anthropic", r.status_code, r.text))
    blocks = r.json().get("content", [])
    return "".join(b.get("text", "") for b in blocks if isinstance(b, dict)).strip()


def _call_gemini(api_key: str, model: str, system: str,
                 prompt: str, b64_png, is_json: bool, max_tokens: int = 2048,
                 mime: str = "image/png") -> str:
    parts = []
    for data, media_type in _normalize_media(b64_png, mime):
        parts.append({"inline_data": {"mime_type": media_type, "data": data}})
    parts.append({"text": prompt})
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
    }
    if is_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    url = f"{ENDPOINTS['gemini']}/{model}:generateContent?key={api_key}"
    r = _post(url, {"Content-Type": "application/json"}, body)
    if r.status_code >= 400:
        if r.status_code in (400, 422) and max_tokens != SAFE_MAX_TOKENS:
            return _call_gemini(api_key, model, system, prompt, b64_png, is_json,
                                max_tokens=SAFE_MAX_TOKENS, mime=mime)
        if r.status_code == 404:
            healed = _heal_deprecated_model(api_key, model, r.text)
            if healed:
                return _call_gemini(api_key, healed, system, prompt, b64_png,
                                    is_json, max_tokens=max_tokens, mime=mime)
        raise AIError(_explain_http("gemini", r.status_code, r.text))
    cands = r.json().get("candidates") or [{}]
    cparts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in cparts).strip()


import time

_FAILED_KEYS_COOLDOWN = 90.0  # seconds
_failed_keys: dict = {}


def _call_provider_single(provider: str, key: str, model: str, system: str,
                          prompt: str, b64_png, is_json: bool, mime: str = "image/png",
                          max_tokens: int = 2048) -> str:
    if provider in LOCAL_PROVIDERS:
        return _call_local(provider, key, model, system, prompt, b64_png, is_json, mime, max_tokens)
    if provider == "gemini":
        return _call_gemini(key, model, system, prompt, b64_png, is_json, max_tokens=max_tokens, mime=mime)
    if provider == "anthropic":
        return _call_anthropic(key, model, system, prompt, b64_png, is_json, max_tokens=max_tokens, mime=mime)
    if provider in ("openai", "groq", "deepseek", "openrouter"):
        return _call_openai_style(provider, key, model, system, prompt, b64_png,
                                   is_json, max_tokens=max_tokens, mime=mime)
    raise AIError(f"Fournisseur inconnu : {provider}")


def _local_base(provider):
    from .settings import load
    base = load()["local_urls"][provider].rstrip("/")
    if provider == "ollama":
        return base.removesuffix("/api").removesuffix("/v1")
    return base if base.endswith("/v1") else base + "/v1"


def _call_local(provider, key, model, system, prompt, image, is_json, mime, max_tokens):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    media = _normalize_media(image, mime)
    user = {"role": "user", "content": prompt}
    body = {"model": model, "stream": False,
            "messages": [{"role": "system", "content": system}, user]}
    if provider == "ollama":
        if media:
            user["images"] = [data for data, _mime in media]
        if is_json:
            body["format"] = "json"
        body["options"] = {"temperature": 0.2, "num_predict": max_tokens}
        url = _local_base(provider) + "/api/chat"
    else:
        if media:
            user["content"] = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}}
                for data, media_type in media]
        if is_json:
            body["response_format"] = {"type": "json_object"}
        body.update(temperature=0.2, max_tokens=max_tokens)
        url = _local_base(provider) + "/chat/completions"
    try:
        r = _post(url, headers, body)
    except AIError as e:
        raise AIError(f"{_provider_name(provider)} inaccessible. Démarre son serveur local et vérifie l'adresse dans Paramètres.") from e
    if r.status_code >= 400:
        raise AIError(_explain_http(provider, r.status_code, r.text) +
                      (" Pour analyser une capture, charge un modèle avec vision." if image else ""))
    data = r.json()
    if provider == "ollama":
        return (data.get("message", {}).get("content") or "").strip()
    return ((data.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()


def _call_cancellable(cancel_event, *args, **kwargs):
    """Let Stop finish promptly while a bounded HTTP request winds down."""
    if cancel_event is None:
        return _call_provider_single(*args, **kwargs)
    result = queue.Queue(maxsize=1)

    def worker():
        try:
            result.put((True, _call_provider_single(*args, **kwargs)))
        except Exception as e:
            result.put((False, e))

    threading.Thread(target=worker, daemon=True).start()
    while not cancel_event.is_set():
        try:
            ok, value = result.get(timeout=0.1)
        except queue.Empty:
            continue
        if ok:
            return value
        raise value
    raise AIError("Requête annulée.")


def chat_with_fallback(provider: str, prompt: str, system: str = "You are a helpful assistant.",
                       b64_png=None, is_json: bool = False, mime: str = "image/png",
                       on_fallback=None, cancel_event=None, allow_fallback=True,
                       max_tokens: int = 2048) -> tuple:
    """Execute chat with automatic fallback across multiple keys and/or providers.
    Returns: (reply_text, effective_provider_used)
    """
    from .settings import load, get_provider_keys, PROVIDERS

    cfg = load()
    primary = (provider or cfg.get("provider") or "gemini").lower()

    # 1. Build candidates list: (cand_provider, cand_key, cand_model)
    candidates = []

    # Keys for primary provider first
    p_keys = get_provider_keys(primary)
    if primary in LOCAL_PROVIDERS:
        p_keys = p_keys or [""]
    p_model = (cfg["models"].get(primary) or "").strip()
    for k in p_keys:
        candidates.append((primary, k, p_model))

    # Other providers that have keys configured
    for other_p in PROVIDERS:
        # Local means local: never leak a local session into a cloud fallback.
        if not allow_fallback or primary in LOCAL_PROVIDERS or other_p in LOCAL_PROVIDERS or other_p == primary:
            continue
        o_keys = get_provider_keys(other_p)
        o_model = (cfg["models"].get(other_p) or "").strip()
        for k in o_keys:
            candidates.append((other_p, k, o_model))

    if not candidates:
        raise AIError(f"Aucune clé API configurée pour {_provider_name(primary)} ni aucun autre fournisseur. "
                      "Renseigne tes clés dans ⚙ Paramètres.")

    # Sort putting recently-failed keys after fresh keys
    now = time.time()
    def candidate_priority(item):
        p, k, m = item
        fail_time = _failed_keys.get(k, 0)
        is_fresh = (now - fail_time) > _FAILED_KEYS_COOLDOWN
        base = 0 if p == primary else 10
        penalty = 0 if is_fresh else 100
        return base + penalty

    candidates.sort(key=candidate_priority)

    errors = []
    for i, (cand_provider, cand_key, cand_model) in enumerate(candidates):
        if cancel_event is not None and cancel_event.is_set():
            raise AIError("Requête annulée.")
        if not cand_model:
            # never skip silently: "all providers failed" with no detail is a lie
            # when no request was even attempted
            errors.append(f"{_provider_name(cand_provider)}: aucun modèle choisi dans ⚙ Paramètres")
            continue
        try:
            res = _call_cancellable(cancel_event, cand_provider, cand_key, cand_model,
                                    system, prompt, b64_png, is_json, mime=mime,
                                    max_tokens=max(128, min(4096, int(max_tokens))))
            if not isinstance(res, str) or not res.strip():
                raise AIError("Le modèle a renvoyé une réponse vide. Essaie un autre modèle.")
            _failed_keys.pop(cand_key, None)
            return res, cand_provider
        except Exception as e:
            if cancel_event is not None and cancel_event.is_set():
                raise AIError("Requête annulée.") from e
            err_msg = str(e)
            _failed_keys[cand_key] = time.time()
            errors.append(f"{_provider_name(cand_provider)}: {err_msg}")

            # Notify fallback if there is a next candidate
            if i + 1 < len(candidates) and on_fallback:
                next_p, next_k, next_m = candidates[i + 1]
                try:
                    on_fallback({
                        "from_provider": cand_provider,
                        "to_provider": next_p,
                        "reason": err_msg,
                        "attempt": i + 1,
                    })
                except Exception:
                    pass

    # All candidates failed
    full_detail = " | ".join(errors[:4])
    raise AIError(f"Tous les fournisseurs/clés ont échoué. Détails : {full_detail}")


def chat(provider: str, prompt: str, system: str = "You are a helpful assistant.",
         b64_png=None, is_json: bool = False, mime: str = "image/png") -> str:
    """Send a prompt (optionally with a screenshot), with automatic fallback."""
    reply, _ = chat_with_fallback(provider, prompt, system=system, b64_png=b64_png,
                                  is_json=is_json, mime=mime)
    return reply


# --------------------------------------------------------------- model lists
def list_models(provider: str) -> list:
    """Models available for the stored key (for the GUI picker). Empty on error."""
    provider = (provider or "").lower()
    key = get_api_key(provider)
    if provider in LOCAL_PROVIDERS:
        try:
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            url = _local_base(provider) + ("/api/tags" if provider == "ollama" else "/models")
            r = _get(url, headers)
            if r.status_code >= 400:
                return []
            data = r.json()
            return sorted(m["name"] for m in data.get("models", [])) if provider == "ollama" else sorted(m["id"] for m in data.get("data", []))
        except Exception:
            return []
    if not key:
        return []
    try:
        if provider == "gemini":
            r = _get(f"{ENDPOINTS['gemini']}?key={key}", {})
            if r.status_code >= 400:
                return []
            out = []
            for m in r.json().get("models", []):
                name = (m.get("name") or "").removeprefix("models/")
                if any(x in name for x in ("embedding", "aqa", "imagen", "veo",
                                           "tts", "native-audio", "image-generation",
                                           "learnlm")):
                    continue
                methods = m.get("supportedGenerationMethods") or []
                if methods and "generateContent" not in methods:
                    continue
                out.append(name)
            return out
        if provider == "openai":
            r = _get("https://api.openai.com/v1/models",
                     {"Authorization": f"Bearer {key}"})
            if r.status_code >= 400:
                return []
            bad = ("embed", "whisper", "tts", "dall-e", "audio", "moderation",
                   "babbage", "davinci", "curie", "transcribe", "realtime", "search")
            out = sorted({m["id"] for m in r.json().get("data", [])
                          if not any(x in m["id"] for x in bad)})
            return out
        if provider == "groq":
            r = _get("https://api.groq.com/openai/v1/models",
                     {"Authorization": f"Bearer {key}"})
            if r.status_code >= 400:
                return []
            bad = ("whisper", "tts", "guard", "prompt-guard")
            return sorted({m["id"] for m in r.json().get("data", [])
                           if not any(x in m["id"] for x in bad)})
        if provider == "deepseek":
            r = _get("https://api.deepseek.com/models",
                     {"Authorization": f"Bearer {key}"})
            if r.status_code >= 400:
                return []
            return sorted({m["id"] for m in r.json().get("data", [])})
        if provider == "openrouter":
            r = _get("https://openrouter.ai/api/v1/models",
                     {"Authorization": f"Bearer {key}"})
            if r.status_code >= 400:
                return []
            ids = [m["id"] for m in r.json().get("data", [])]
            free = [i for i in ids if ":free" in i]
            paid = [i for i in ids if ":free" not in i]
            return sorted(free) + sorted(paid)
        if provider == "anthropic":
            r = _get("https://api.anthropic.com/v1/models?limit=100",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"})
            if r.status_code >= 400:
                return []
            return sorted({m["id"] for m in r.json().get("data", [])})
    except AIError:
        return []
    except Exception:  # noqa: BLE001 - picker must never crash the UI
        return []
    return []
