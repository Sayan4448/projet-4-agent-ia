"""Offline coverage of saved automations (no app launched, no registry write)."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import MagicMock, patch

from agent_screen import automations, gui, settings


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for module, name, path in ((settings, "config_file", root / "config.json"),
                                   (automations, "automations_file", root / "automations.json")):
            p = patch.object(module, name, return_value=path)
            p.start()
            self.addCleanup(p.stop)

    def test_discord_links_open_the_desktop_app_in_the_conversation(self):
        want = "discord://-/channels/@me/1234567890"
        for link in ("https://discord.com/channels/@me/1234567890",
                     "https://discord.com/channels/@me/1234567890/9876543210",   # message link
                     "https://ptb.discord.com/channels/@me/1234567890",
                     "discord://-/channels/@me/1234567890"):
            self.assertEqual(automations.discord_link(link), want)
        self.assertEqual(automations.discord_link("https://discord.com/channels/11/22"),
                         "discord://-/channels/11/22")
        for other in ("discord", "https://example.com/channels/1/2", "https://discord.com/app", ""):
            self.assertEqual(automations.discord_link(other), "")

    def test_targets_are_opened_without_the_ai(self):
        with patch.object(automations.os, "startfile", create=True) as start:
            self.assertTrue(automations.open_target("https://discord.com/channels/@me/42")["ok"])
        start.assert_called_once_with("discord://-/channels/@me/42")
        with patch("agent_screen.input_control.open_url", return_value={"ok": True}) as web, \
                patch("agent_screen.apps.launch_app", return_value={"ok": True}) as app:
            automations.open_target("https://example.com/page")
            automations.open_target("discord")
        web.assert_called_once_with("https://example.com/page")
        self.assertEqual(app.call_args.args[0], "discord")

    def test_discord_link_falls_back_to_the_web_without_the_app(self):
        with patch.object(automations.os, "startfile", create=True, side_effect=OSError("no handler")), \
                patch("agent_screen.input_control.open_url", return_value={"ok": True}) as web:
            automations.open_target("discord://-/channels/@me/42")
        web.assert_called_once_with("https://discord.com/channels/@me/42")

    def test_store_round_trip_and_validation(self):
        first = automations.save({"name": "Gazo", "target": "https://discord.com/channels/@me/42",
                                  "at_startup": 1})
        automations.save({"name": "Bonjour", "goal": "Dis bonjour"})
        self.assertEqual([a["name"] for a in automations.load_all()], ["Gazo", "Bonjour"])
        self.assertIs(automations.load_all()[0]["at_startup"], True)
        automations.save({**first, "name": "Les gazo"})          # same id: replaced
        self.assertEqual([a["name"] for a in automations.load_all()], ["Les gazo", "Bonjour"])
        automations.delete(first["id"])
        self.assertEqual([a["name"] for a in automations.load_all()], ["Bonjour"])
        for bad in ({"name": "", "target": "x"}, {"name": "vide"}, "nope"):
            with self.assertRaises(ValueError):
                automations.save(bad)
        automations.automations_file().write_text("{corrupt", encoding="utf-8")
        self.assertEqual(automations.load_all(), [])

    def test_windows_startup_registers_this_app_with_the_flag(self):
        fake = MagicMock()
        with patch.dict("sys.modules", {"winreg": fake}):
            automations.set_windows_startup(True)
            name, _zero, _kind, command = fake.SetValueEx.call_args.args[1:]
            self.assertEqual(name, automations.RUN_NAME)
            self.assertTrue(command.endswith(automations.STARTUP_FLAG))
            self.assertIn('"', command)                           # paths with spaces
            automations.set_windows_startup(False)
            fake.DeleteValue.assert_called_once()

    def test_startup_plays_flagged_automations_in_order(self):
        """Targets open at once; goals queue and run one after the other."""
        automations.save({"name": "Groupe", "target": "discord", "goal": "dis bonjour",
                          "at_startup": True})
        automations.save({"name": "Météo", "goal": "donne la météo", "at_startup": True})
        automations.save({"name": "Manuelle", "target": "notepad"})
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        app = gui.App(root)
        app.AUTOMATION_SETTLE_MS = 0
        started = []
        with patch.object(automations, "open_target", return_value={"ok": True}) as opened, \
                patch.object(app, "_start_run",
                             side_effect=lambda: started.append(app.goal_entry.get())):
            app._run_startup_automations()
            for _ in range(200):                 # the opener runs off the UI thread
                root.update()
                time.sleep(0.01)   # the UI pump ticks every few ms
                if started:
                    break
            self.assertEqual([c.args[0] for c in opened.call_args_list], ["discord"])
            self.assertEqual(started, ["dis bonjour"])
            app._next_automation()               # what the end of a run triggers
            for _ in range(200):
                root.update()
                time.sleep(0.01)   # the UI pump ticks every few ms
                if len(started) == 2:
                    break
            self.assertEqual(started, ["dis bonjour", "donne la météo"])

    def test_the_queue_waits_for_a_run_that_is_still_releasing(self):
        """A run's 'finished' event reaches the UI before the run lets go of
        the desktop: the next automation must wait, not be dropped."""
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        app = gui.App(root)
        app._automation_queue = [{"id": "1", "name": "n", "target": "", "goal": "suite",
                                  "at_startup": False}]
        started = []
        with patch.object(gui.agent, "active_run", side_effect=[object(), None, None]), \
                patch.object(app, "_start_run",
                             side_effect=lambda: started.append(app.goal_entry.get())):
            app._next_automation()
            self.assertEqual(started, [])             # busy: nothing yet, nothing lost
            for _ in range(200):
                root.update()
                time.sleep(0.01)
                if started:
                    break
        self.assertEqual(started, ["suite"])


if __name__ == "__main__":
    unittest.main()
