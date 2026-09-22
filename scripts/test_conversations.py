"""Conversation persistence, favorites and credit-saving Chat behavior."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from agent_screen import conversations, gui, settings


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        for target, value in ((settings, "config_file"),):
            p = patch.object(target, value, return_value=base / "config.json")
            p.start(); self.addCleanup(p.stop)
        p = patch.object(conversations, "conversations_file", return_value=base / "conversations.json")
        p.start(); self.addCleanup(p.stop)

    def make_app(self):
        root = tk.Tk(); root.withdraw()
        app = gui.App(root)
        self.addCleanup(lambda: root.destroy() if gui._alive(root) else None)
        return app

    def test_save_reload_favorite_order_delete_and_title_without_ai(self):
        first = conversations.new_conversation()
        first.update(title="Normal", messages=[{"role": "user", "text": "bonjour"}])
        conversations.save_conversation(first)
        second = conversations.new_conversation()
        second.update(title="Favori", favorite=True,
                      messages=[{"role": "assistant", "text": "réponse", "provider": "ollama"}])
        conversations.save_conversation(second)
        items = conversations.load_all()
        self.assertEqual([x["title"] for x in items], ["Favori", "Normal"])
        self.assertEqual(items[0]["messages"][0]["provider"], "ollama")
        self.assertEqual(conversations.title_from("  une   très longue question " * 10)[-1], "…")
        conversations.delete(second["id"])
        self.assertEqual([x["title"] for x in conversations.load_all()], ["Normal"])

    def test_malformed_messages_do_not_break_startup(self):
        conversations.conversations_file().write_text(
            '[{"id":"bad","title":"Importé","messages":null}]', encoding="utf-8")
        self.assertEqual(conversations.load_all()[0]["messages"], [])

    def test_chat_persists_and_reopens_a_favorite(self):
        app = self.make_app()
        app.chat_history = [("user", "Mon sujet", ""), ("assistant", "Ma réponse", "gemini")]
        app.chat_current["title"] = conversations.title_from("Mon sujet")
        app._persist_chat()
        app._toggle_chat_favorite()
        app._new_chat()
        self.assertEqual(app.chat_history, [])
        app.chat_list.selection_set(0)
        app._open_selected_chat()
        self.assertEqual(app.chat_history[-1], ("assistant", "Ma réponse", "gemini"))
        self.assertTrue(app.chat_current["favorite"])

    def test_chat_eco_context_and_response_limit_reach_provider(self):
        settings.save({"provider": "ollama", "models": {"ollama": "local"},
                       "chat_eco": True, "chat_context_messages": 2,
                       "chat_response_tokens": 384})
        app = self.make_app()
        app.chat_history = [("user", f"question {i}", "") if i % 2 == 0
                            else ("assistant", f"answer {i}", "ollama") for i in range(6)]
        app.chat_entry.insert(0, "dernier message")
        captured = {}
        def reply(*args, **kwargs):
            captured.update(kwargs)
            return "ok", "ollama"
        with patch.object(gui, "chat_with_fallback", side_effect=reply):
            app._send_chat()
            deadline = time.monotonic() + 2
            while app.q.empty() and time.monotonic() < deadline:
                app.root.update(); time.sleep(0.01)
            app._pump()
        self.assertEqual(captured["max_tokens"], 384)
        self.assertNotIn("question 0", captured["prompt"])
        self.assertNotIn("answer 3", captured["prompt"])
        self.assertIn("question 4", captured["prompt"])
        self.assertIn("answer 5", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
