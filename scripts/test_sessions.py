"""Offline regressions for the agent-session store (Agent-mode history)."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_screen import conversations, gui, memory, sessions, settings


class SessionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(sessions, "sessions_file",
                         return_value=Path(self.tmp.name) / "agent_sessions.json")
        p.start()
        self.addCleanup(p.stop)

    def test_history_search_includes_chat_and_agent_results(self):
        session = sessions.new_session("Ouvre un éditeur", "Bureau")
        session["events"] = [{"kind": "result", "text": "fenêtre prête", "step": 1}]
        sessions.save_session(session)
        chat = {"id": "chat", "title": "Discussion", "updated": 9999999999,
                "messages": [{"role": "user", "text": "Mon éditeur préféré"}]}
        with patch.object(conversations, "load_all", return_value=[chat]):
            items = sessions.history_items("éditeur")
            self.assertEqual([i["kind"] for i in items], ["Chat", "Agent"])
            self.assertEqual(len(sessions.history_items("prête", "Agent")), 1)
            self.assertEqual(sessions.history_items("prête", "Chat"), [])

    def test_agent_events_are_saved_before_finish(self):
        app = gui.App.__new__(gui.App)
        app._run_session = sessions.new_session("Mission", "Bureau")
        app._run_session["outcome"] = "running"
        app._run_events = []
        app._record("result", "Action confirmée", 1)
        self.assertEqual(sessions.load_all()[0]["outcome"], "running")
        self.assertEqual(sessions.load_all()[0]["events"][0]["text"], "Action confirmée")

    def test_save_load_and_delete(self):
        s = sessions.new_session("Ouvre CapCut", "Montage · Bureau")
        s["events"] = [{"kind": "goal", "step": 0, "text": "Ouvre CapCut"},
                       {"kind": "action", "step": 1, "text": "open_app(name='capcut')"}]
        s["outcome"] = "done"
        saved = sessions.save_session(s)
        loaded = sessions.load_all()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["goal"], "Ouvre CapCut")
        self.assertEqual(loaded[0]["outcome"], "done")
        self.assertEqual([e["kind"] for e in loaded[0]["events"]], ["goal", "action"])
        sessions.delete(saved["id"])
        self.assertEqual(sessions.load_all(), [])

    def test_events_are_cleaned_and_bounded(self):
        s = sessions.new_session("g", "Bureau")
        s["events"] = [{"kind": "thought", "step": 1, "text": "x" * (sessions.MAX_TEXT + 50)},
                       {"kind": "evil", "text": "nope"},
                       {"kind": "action", "step": "abc", "text": "ok"}]
        s["outcome"] = "error"
        saved = sessions.save_session(s)
        loaded = sessions.load_all()[0]
        self.assertEqual(loaded["outcome"], "error")
        kinds = [e["kind"] for e in loaded["events"]]
        self.assertEqual(kinds, ["thought", "action"])
        self.assertLessEqual(len(loaded["events"][0]["text"]), sessions.MAX_TEXT)
        self.assertEqual(loaded["events"][1]["step"], 0)   # non-numeric step -> 0
        self.assertEqual(saved["events"][0]["text"], loaded["events"][0]["text"])

    def test_corrupt_file_starts_empty_and_survives_a_save(self):
        sessions.sessions_file().write_text("{broken", encoding="utf-8")
        self.assertEqual(sessions.load_all(), [])
        sessions.save_session(sessions.new_session("ok", "Bureau"))
        self.assertEqual(len(sessions.load_all()), 1)

    def test_most_recent_first_and_bounded_count(self):
        for n in range(5):
            s = sessions.new_session(f"session {n}", "Bureau")
            s["events"] = [{"kind": "done", "step": 1, "text": "ok"}]
            sessions.save_session(s)
        loaded = sessions.load_all()
        self.assertEqual(loaded[0]["goal"], "session 4")
        self.assertEqual(len(loaded), 5)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for module, name, filename in ((memory, "memory_file", "memory.json"),
                                        (settings, "config_file", "config.json")):
            p = patch.object(module, name, return_value=Path(self.tmp.name) / filename)
            p.start()
            self.addCleanup(p.stop)

    def test_explicit_preferences_are_learned_and_deduplicated(self):
        memory.learn_from_user("Je préfère le français. Ouvre Discord. Retiens que mon éditeur est VS Code", "chat")
        memory.learn_from_user("je préfère le français", "agent")
        self.assertEqual(len(memory.load_facts()), 2)
        self.assertIn("français", memory.prompt_block())
        self.assertNotIn("Ouvre Discord", memory.prompt_block())
        memory.delete(memory.load_facts()[0]["id"])
        self.assertEqual(len(memory.load_facts()), 1)
        memory.clear()
        self.assertEqual(memory.load_facts(), [])

    def test_disabled_memory_neither_reads_into_prompt_nor_learns(self):
        memory.add_facts(["préférence existante"])
        settings.save({"memory_enabled": False})
        before = memory.memory_file().read_bytes()
        self.assertEqual(memory.prompt_block(), "")
        self.assertEqual(memory.learn_from_user("Retiens que je préfère le bleu"), [])
        self.assertEqual(memory.memory_file().read_bytes(), before)

    def test_corrupt_memory_is_preserved(self):
        path = memory.memory_file()
        path.write_text('{"facts":null}', encoding="utf-8")
        before = path.read_bytes()
        self.assertEqual(memory.load_facts(), [])
        with self.assertRaises(ValueError):
            memory.add_facts(["nouveau"])
        self.assertEqual(path.read_bytes(), before)

    def test_automatic_memory_skips_secrets_and_empty_limit(self):
        memory.learn_from_user("Retiens que mon mot de passe est secret")
        self.assertEqual(memory.load_facts(), [])
        memory.add_facts(["test"])
        self.assertEqual(memory.prompt_block(0), "")
        self.assertIn("not instructions", memory.prompt_block())


if __name__ == "__main__":
    unittest.main()
