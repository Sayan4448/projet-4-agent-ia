"""Offline coverage of the local-AI path (Ollama / LM Studio), the model
picker lists and the provider parameter retries. No network, no model."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_screen import agent, ai_client, settings

TAGS = {"models": [
    {"name": "a-coder:1b", "capabilities": ["completion"], "size": 1},
    {"name": "nomic-embed-text:latest", "capabilities": ["embedding"], "size": 2},
    {"name": "b-caption:1b", "capabilities": ["completion", "vision"], "size": 3},
    {"name": "z-vision:12b", "capabilities": ["completion", "vision", "tools"], "size": 9},
]}


def _resp(status, payload=None, text=""):
    r = Mock(status_code=status, text=text or json.dumps(payload or {}))
    r.json.return_value = payload or {}
    return r


class LocalAITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(settings, "config_file", return_value=Path(self.tmp.name) / "config.json")
        p.start()
        self.addCleanup(p.stop)

    # ------------------------------------------------------------ auto-pick
    def test_text_chat_never_persists_a_blind_model(self):
        """A chat without screenshot used to pick the smallest text model
        (a 1B coder) and persist it: the Agent tab then ran blind on it."""
        settings.save({"provider": "ollama", "models": {"ollama": ""}})
        with patch.object(ai_client, "_get", return_value=_resp(200, TAGS)), \
                patch.object(ai_client, "_call_provider_single", return_value="ok") as call:
            ai_client.chat_with_fallback("ollama", "bonjour")
        self.assertEqual(call.call_args.args[2], "z-vision:12b")
        self.assertEqual(settings.load()["models"]["ollama"], "z-vision:12b")

    def test_no_local_model_explains_what_to_do(self):
        settings.save({"provider": "ollama", "models": {"ollama": ""}})
        with patch.object(ai_client, "_get", return_value=_resp(200, {"models": []})):
            with self.assertRaises(ai_client.AIError) as ctx:
                ai_client.chat_with_fallback("ollama", "bonjour")
        self.assertIn("ollama pull", str(ctx.exception))
        self.assertNotIn("Tous les fournisseurs", str(ctx.exception))

    # ------------------------------------------------------------- requests
    def test_local_request_survives_a_slow_cold_start(self):
        """Measured on a 12B vision model without full GPU offload: 190 s for the
        first agent call. The old 120 s floor (180 s max) made it fail every time."""
        ok = _resp(200, {"message": {"content": "OK"}})
        with patch.object(ai_client, "_post", return_value=ok) as post:
            ai_client._call_provider_single("ollama", "", "m", "sys", "prompt", "IMG", True)
        body = post.call_args.args[2]
        self.assertGreaterEqual(post.call_args.kwargs["timeout"], 600)
        # a local error is not transient: no blind 5xx retry on a 3-minute request
        self.assertEqual(post.call_args.kwargs["retry_5xx"], 0)
        # agent prompt (~2800 tokens) + answer does not fit Ollama's 4096 default
        self.assertGreaterEqual(body["options"]["num_ctx"], 8192)

    def test_local_error_shows_the_server_reason(self):
        bad = _resp(500, {"error": "model requires more system memory (8.4 GiB) than is available"})
        with patch.object(ai_client, "_post", return_value=bad):
            with self.assertRaises(ai_client.AIError) as ctx:
                ai_client._call_provider_single("ollama", "", "m", "sys", "prompt", None, False)
        self.assertIn("more system memory", str(ctx.exception))

    def test_lmstudio_retries_without_json_object(self):
        """LM Studio rejects response_format json_object (it wants json_schema)."""
        bad = _resp(400, {"error": "'response_format.type' must be 'json_schema' or 'text'"})
        ok = _resp(200, {"choices": [{"message": {"content": '{"a":1}'}}]})
        with patch.object(ai_client, "_post", side_effect=[bad, ok]) as post:
            text = ai_client._call_provider_single("lmstudio", "", "m", "sys", "prompt", None, True)
        self.assertEqual(text, '{"a":1}')
        self.assertNotIn("response_format", post.call_args.args[2])

    # ---------------------------------------------------------- model lists
    def test_ollama_list_hides_embeddings_and_puts_vision_first(self):
        with patch.object(ai_client, "_get", return_value=_resp(200, TAGS)):
            self.assertEqual(ai_client.list_models("ollama"),
                             ["z-vision:12b", "b-caption:1b", "a-coder:1b"])

    def test_loading_local_models_starts_ollama(self):
        with patch.object(ai_client, "_get",
                          side_effect=[ai_client.AIError("refused"), _resp(200, TAGS)]), \
                patch.object(ai_client, "_ensure_local_server", return_value=True) as ensure:
            self.assertEqual(len(ai_client.list_models("ollama")), 3)
        ensure.assert_called_once_with("ollama")

    def test_gemini_list_hides_models_that_cannot_chat(self):
        settings.save({"api_keys": {"gemini": "fake-key-123456"}})
        names = ["gemini-3.5-flash", "gemini-2.5-flash-image", "lyria-3.5",
                 "gemini-3.5-transcribe", "deep-research-preview-04-2026",
                 "nano-banana-pro-preview", "gemini-2.5-flash-lite"]
        listing = _resp(200, {"models": [{"name": f"models/{n}"} for n in names]})
        with patch.object(ai_client, "_get", return_value=listing):
            self.assertEqual(ai_client.list_models("gemini"),
                             ["gemini-3.5-flash", "gemini-2.5-flash-lite"])

    def test_every_cloud_provider_proposes_models(self):
        for p in settings.PROVIDERS:
            if p in settings.LOCAL_PROVIDERS:
                continue
            self.assertIn(settings.DEFAULTS["models"][p], settings.SUGGESTED_MODELS[p])

    # ------------------------------------------------------- cloud fallback
    def test_gemini_quota_tries_a_sibling_model(self):
        """Free-tier quotas are per model: a 429 on one model leaves the same
        key usable on a sibling."""
        seen = []

        def fake_call(provider, key, model, *a, **kw):
            seen.append(model)
            if model == "gemini-3.5-flash":
                raise ai_client.AIError("Limite de requêtes/quota atteinte chez Google Gemini (429).")
            return f"ok via {model}"

        settings.save({"provider": "gemini", "api_keys": {"gemini": "key12345678"},
                       "models": {"gemini": "gemini-3.5-flash"}})
        with patch.object(ai_client, "_call_provider_single", side_effect=fake_call):
            reply, _ = ai_client.chat_with_fallback("gemini", "hi")
        self.assertEqual(seen, ["gemini-3.5-flash", "gemini-2.5-flash"])
        self.assertEqual(reply, "ok via gemini-2.5-flash")

    def test_openai_reasoning_models_get_the_params_they_accept(self):
        """gpt-5 / o-series reject max_tokens and a custom temperature."""
        ok = _resp(200, {"choices": [{"message": {"content": "OK"}}]})
        replies = [
            _resp(400, text="Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."),
            _resp(400, text="Unsupported value: 'temperature' does not support 0.2 with this model."),
            ok]
        with patch.object(ai_client, "_post", side_effect=replies) as post:
            text = ai_client._call_provider_single("openai", "k", "gpt-5", "sys", "prompt", None, True)
        body = post.call_args.args[2]
        self.assertEqual(text, "OK")
        self.assertEqual(body["max_completion_tokens"], 2048)
        self.assertNotIn("max_tokens", body)
        self.assertNotIn("temperature", body)
        self.assertIn("response_format", body)

    # ---------------------------------------------------------- agent prompt
    def test_static_instructions_lead_so_servers_can_cache_them(self):
        """Everything identical from step to step sits in the system prompt:
        local servers reuse the evaluated prefix (measured 155 s -> 45 s per step)."""
        seen = []

        def fake_chat(*_a, **kw):
            seen.append(kw)
            return '{"thought":"x","actions":[],"done":true,"summary":"s"}', "ollama"

        run = agent.AgentRun("goal", "ollama", max_steps=1, memory_enabled=False)
        with patch.object(agent, "chat_with_fallback", side_effect=fake_chat), \
                patch("agent_screen.display.capture_for_model", return_value=("IMG", 1.0)), \
                patch("agent_screen.display.interesting_windows", return_value=[]):
            run.run()
        self.assertIn("Available actions", seen[0]["system"])
        self.assertIn("Reply ONLY with JSON", seen[0]["system"])
        self.assertNotIn("Available actions", seen[0]["prompt"])
        self.assertIn("Goal: goal", seen[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
