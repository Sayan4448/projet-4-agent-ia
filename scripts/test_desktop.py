"""Desktop regressions: no external API or real mouse/keyboard actions."""
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from agent_screen import agent, ai_client, display, gui, input_control, settings


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config.json"
        p = patch.object(settings, "config_file", return_value=self.config)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(display, "shots_dir", return_value=Path(self.temp.name))
        p.start()
        self.addCleanup(p.stop)
        for name in ("release_all_keys", "mouse_up", "mouse_move"):
            p = patch.object(input_control, name, return_value={})
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: agent.release(agent.active_run()))

    def run_replies(self, replies, **kwargs):
        events = []
        run = agent.AgentRun("test", "gemini", max_steps=len(replies), step_delay=0,
                             emit=lambda event, **kw: events.append((event, kw)), **kwargs)
        with patch.object(display, "capture_for_model", return_value=("IMG", 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(agent, "chat_with_fallback",
                          side_effect=[(json.dumps(r), "gemini") for r in replies]), \
             patch.object(agent, "_virtual_action", return_value={"ok": True}) as virtual, \
             patch.object(agent, "execute_action", return_value={"ok": True}) as execute:
            result = run.run()
        return result, events, execute, virtual

    def test_successful_actions_and_individual_captures_are_recorded(self):
        res, events, execute, virtual = self.run_replies([
            {"actions": [{"name": "press_key", "args": {"key": "enter"}},
                         {"name": "press_key", "args": {"key": "tab"}}]},
            {"done": True, "summary": "ok"},
        ], screenshot_each_action=True)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["steps"][0]["actions"]), 2)
        self.assertEqual(virtual.call_count, 2)   # press_key rides the virtual path
        execute.assert_not_called()
        self.assertEqual([e[1]["sub"] for e in events if e[0] == "screenshot" and "sub" in e[1]], [1, 2])

    def test_malformed_action_list_recovers_without_crashing(self):
        res, _, execute, virtual = self.run_replies([
            {"actions": ["bad", None, {"name": "click", "args": "wrong"}]},
            {"actions": [{"name": "press_key", "args": {"key": "enter"}}]},
            {"done": True},
        ])
        self.assertTrue(res["ok"])
        self.assertEqual(virtual.call_count, 1)

    def test_invalid_json_shape_has_a_clear_error(self):
        res, events, execute, virtual = self.run_replies([[1, 2]])
        self.assertEqual(res["outcome"], "error")
        self.assertFalse(execute.called)
        self.assertFalse(virtual.called)
        self.assertTrue(any("Model did not return JSON" in e[1].get("text", "") for e in events))

    def test_failed_action_cannot_justify_success(self):
        run = agent.AgentRun("test", "gemini", max_steps=2, step_delay=0)
        with patch.object(display, "capture_for_model", return_value=("IMG", 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(agent, "chat_with_fallback", side_effect=[
                 ('{"actions":[{"name":"open_app","args":{"name":"missing"}}]}', "gemini"),
                 ('{"done":true}', "gemini")]), \
             patch.object(agent, "execute_action", return_value={"ok": False, "error": "missing"}):
            result = run.run()
        self.assertFalse(result["ok"])

    def test_grid_uses_image_pixels_after_resize(self):
        with patch.object(display, "_capture_screen", return_value=Image.new("RGB", (1920, 1080))), \
             patch.object(display, "_draw_grid", wraps=display._draw_grid) as grid:
            b64, scale, geometry = display.capture_for_model(True, 1280, with_geometry=True)
        self.assertEqual(scale, 1.5)
        self.assertEqual(grid.call_args.args[1:], (1280, 720, 1.0))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(b64))).size, (1280, 720))
        self.assertEqual(geometry["scale_y"], 1.5)

    def test_coordinates_keep_capture_origin_even_if_window_moves(self):
        run = agent.AgentRun("test", "gemini", window_mode=True, window_title="Test")
        run.scale = 1.5
        run.geometry = {"origin": (-1920, 100), "scale_y": 1.6,
                        "real_w": 1920, "real_h": 1080}
        with patch.object(display, "get_window_rect", return_value={"x": 900, "y": 500}) as lookup:
            # normalized: 100/1000*1920 - 1920, 100/1000*1080 + 100
            self.assertEqual(run._to_real({"x": 100, "y": 100}), {"x": -1728, "y": 208})
        self.assertFalse(lookup.called)

    def test_missing_target_window_never_falls_back_to_other_apps(self):
        with patch.object(display, "find_window", return_value=None), \
             patch.object(display, "_capture_screen") as grab:
            with self.assertRaisesRegex(ValueError, "Fenêtre introuvable"):
                display.capture_for_model(window_title="closed")
        self.assertFalse(grab.called)

    def test_multiple_keys_survive_save_and_reload(self):
        settings.save({"api_keys": {"gemini": "key-one\nkey-two key-three;key-one"}})
        self.assertEqual(settings.get_provider_keys("gemini")[:3], ["key-one", "key-two", "key-three"])

    def test_failed_atomic_save_keeps_previous_config(self):
        settings.save({"max_steps": 7})
        before = self.config.read_bytes()
        with patch.object(settings.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                settings.save({"max_steps": 20})
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob(".config-*.tmp")), [])

    def test_save_does_not_overwrite_corrupt_config(self):
        self.config.write_text('{"provider":', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "conservé"):
            settings.save({"provider": "openai"})
        self.assertEqual(self.config.read_text(), '{"provider":')

    def test_retry_keeps_jpeg_mime_for_both_providers(self):
        bad = Mock(status_code=400, text="max_tokens")
        good = Mock(status_code=200)
        for provider in ("openai", "anthropic"):
            good.json.return_value = ({"choices": [{"message": {"content": "OK"}}]}
                                      if provider == "openai" else {"content": [{"text": "OK"}]})
            with patch.object(ai_client, "_post", side_effect=[bad, good]) as post:
                ai_client._call_provider_single(provider, "fake", "model", "system", "prompt", "IMG", False, "image/jpeg")
            body = post.call_args.args[2]
            self.assertIn("image/jpeg", json.dumps(body))

    def test_quota_error_is_not_retried_on_the_same_key(self):
        for provider in ("gemini", "openai", "anthropic"):
            with patch.object(ai_client, "_post", return_value=Mock(status_code=429, text="quota")) as post:
                with self.assertRaises(ai_client.AIError):
                    ai_client._call_provider_single(provider, "fake", "model", "sys", "msg", None, True)
            self.assertEqual(post.call_count, 1)

    def test_stop_interrupts_waiting_for_ai(self):
        started, finish, cancelled = threading.Event(), threading.Event(), threading.Event()
        def request(*a, **kw):
            started.set()
            finish.wait(5)
            return "OK"
        errors = []
        def call():
            try:
                ai_client._call_cancellable(cancelled, "gemini")
            except ai_client.AIError as e:
                errors.append(str(e))
        try:
            with patch.object(ai_client, "_call_provider_single", side_effect=request):
                t = threading.Thread(target=call)
                t.start()
                self.assertTrue(started.wait(1))
                cancelled.set()
                t.join(1)
                self.assertFalse(t.is_alive())
                self.assertEqual(errors, ["Requête annulée."])
        finally:
            finish.set()

    def test_raw_game_input_honors_emergency_stop(self):
        with patch.object(input_control.pyautogui, "failSafeCheck",
                          side_effect=input_control.pyautogui.FailSafeException), \
             patch.object(input_control, "_send_scan") as send:
            with self.assertRaises(input_control.pyautogui.FailSafeException):
                input_control.key_down("w")
        self.assertFalse(send.called)

    def make_app(self):
        root = tk.Tk()
        root.withdraw()
        app = gui.App(root)
        self.addCleanup(lambda: root.destroy() if gui._alive(root) else None)
        return app

    def widgets(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self.widgets(child)

    def test_clearing_chat_discards_pending_reply(self):
        app = self.make_app()
        old = app._chat_generation
        app.chat_sending = True
        app._clear_chat()
        app._handle_event({"event": "chat_reply", "generation": old, "text": "obsolete"})
        self.assertEqual(app.chat_history, [])
        self.assertFalse(app.chat_sending)
        self.assertNotIn("obsolete", app.chat_view.get("1.0", "end"))

    def test_settings_connection_failure_reaches_main_thread(self):
        app = self.make_app()
        errors = []
        app.root.report_callback_exception = lambda *e: errors.append(e)
        app._open_settings()
        buttons = [w for w in self.widgets(app.root) if isinstance(w, gui.ttk.Button)]
        test_button = next(w for w in buttons if w.cget("text") == app._("test"))
        with patch.object(gui, "chat_with_fallback", side_effect=ai_client.AIError("connexion KO")):
            test_button.invoke()
            deadline = time.monotonic() + 2
            while app.q.empty() and time.monotonic() < deadline:
                app.root.update()
                time.sleep(0.01)
            app._pump()
        labels = [w.cget("text") for w in self.widgets(app.root) if isinstance(w, gui.ttk.Label)]
        self.assertTrue(any("connexion KO" in str(t) for t in labels))
        self.assertEqual(errors, [])

    def test_settings_keep_model_edits_when_switching_provider(self):
        app = self.make_app()
        app._open_settings()
        combos = [w for w in self.widgets(app.root) if isinstance(w, gui.ttk.Combobox)]
        provider = next(w for w in combos if "Google Gemini" in w.cget("values"))
        model = next(w for w in combos if str(w.cget("state")) == "normal")
        model.set("my-gemini")
        provider.current(1)
        provider.event_generate("<<ComboboxSelected>>")
        model.set("my-openai")
        provider.current(0)
        provider.event_generate("<<ComboboxSelected>>")
        self.assertEqual(model.get(), "my-gemini")
        button = next(w for w in self.widgets(app.root) if isinstance(w, gui.ttk.Button)
                      and w.cget("text") == app._("save"))
        button.invoke()
        self.assertEqual(settings.load()["models"]["openai"], "my-openai")


if __name__ == "__main__":
    unittest.main()
