"""Offline regressions for the agent-session store (Agent-mode history)."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_screen import sessions


class SessionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(sessions, "sessions_file",
                         return_value=Path(self.tmp.name) / "agent_sessions.json")
        p.start()
        self.addCleanup(p.stop)

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


if __name__ == "__main__":
    unittest.main()
