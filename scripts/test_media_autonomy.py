"""Offline media, editing-profile, HUD and autonomous budget regressions."""
import base64
import json
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from agent_screen import agent, apps, conversations, display, gui, media, sessions, settings
from agent_screen.overlay import AgentOverlay


def image(value):
    import io
    out = io.BytesIO()
    Image.new("RGB", (32, 18), (value, value, value)).save(out, "JPEG")
    return base64.b64encode(out.getvalue()).decode()


class MediaAutonomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for module, name, path in ((settings, "config_file", root / "config.json"),
                                   (conversations, "conversations_file", root / "conversations.json")):
            p = patch.object(module, name, return_value=path); p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: agent.release(agent.active_run()))

    def test_editors_are_known(self):
        self.assertEqual(apps.find_app_entry("Premiere Pro")["exes"], ("Adobe Premiere Pro.exe",))
        self.assertEqual(apps.find_app_entry("CapCut")["exes"], ("CapCut.exe",))
        self.assertEqual(apps.find_app_entry("DaVinci Resolve")["exes"], ("Resolve.exe",))

    def test_motion_capture_is_bounded_and_stoppable(self):
        calls = []
        with patch.object(media.time, "sleep"):
            frames, seconds = media.capture_motion(lambda: calls.append(1) or "frame", 99)
        self.assertEqual(seconds, 6)
        self.assertEqual(len(frames), media.MAX_MOTION_FRAMES)
        stopped = threading.Event(); stopped.set()
        frames, _ = media.capture_motion(lambda: "never", 5, stopped)
        self.assertEqual(frames, [])

    def test_audio_is_explicit_bounded_and_gemini_only(self):
        song = Path(self.tmp.name) / "audio.mp3"
        song.write_bytes(b"audio")
        with self.assertRaisesRegex(agent.AIError, "Gemini"):
            media.analyze_audio(song, "openai", "analyse")
        with patch.object(media, "_call_gemini_audio", return_value=("transcription", "gemini")) as call:
            result = media.analyze_audio(song, "gemini", "analyse")
        self.assertTrue(result["ok"])
        self.assertEqual(call.call_args.args[1], "audio/mpeg")
        too_big = Path(self.tmp.name) / "big.wav"
        with too_big.open("wb") as f:
            f.truncate(media.MAX_AUDIO_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "20 Mo"):
            media.analyze_audio(too_big, "gemini", "analyse")

    def test_multiple_frames_reach_gemini_in_order(self):
        response = Mock(status_code=200)
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
        with patch("agent_screen.ai_client._post", return_value=response) as post:
            from agent_screen import ai_client
            ai_client._call_gemini("key", "model", "system", "prompt", ["first", "second"], True)
        parts = post.call_args.args[2]["contents"][0]["parts"]
        self.assertEqual([p["inline_data"]["data"] for p in parts[:-1]], ["first", "second"])

    def test_screen_fingerprint_samples_real_image_without_encoding(self):
        with patch.object(display, "_capture_screen", return_value=Image.new("RGB", (80, 60), "white")):
            pixels = display.screen_fingerprint()
        self.assertEqual(len(pixels), 144)
        self.assertEqual(set(pixels), {255})

    def test_active_autonomous_task_does_not_wait_for_external_change(self):
        run = agent.AgentRun("goal", "gemini", autonomous_mode=True, autonomous_max_calls=2,
                             step_delay=0, memory_enabled=False)
        run.autonomous_min_interval = 0
        replies = [(json.dumps({"actions": [{"name": "press_key", "args": {"key": "tab"}}]}), "gemini")] * 2
        with patch.object(run, "_shot", return_value=image(0)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(run, "_autonomous_wait") as idle, \
             patch.object(agent, "chat_with_fallback", side_effect=replies) as call, \
             patch.object(agent, "execute_action", return_value={"ok": True}):
            result = run.run()
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result["outcome"], "autonomous_limit")
        idle.assert_not_called()

    def test_autonomous_wait_is_local_until_change(self):
        """The watch uses a cheap screen sample and takes a full model capture
        only when it wakes — never one screenshot every three seconds."""
        run = agent.AgentRun("goal", "gemini", autonomous_mode=True,
                             autonomous_min_interval=15, autonomous_minutes=5)
        run._started_at = time.monotonic()
        run.autonomous_min_interval = 0
        with patch.object(run, "_shot", return_value=image(255)) as shot, \
             patch.object(display, "screen_fingerprint",
                          side_effect=[tuple([0] * 144), tuple([255] * 144)]), \
             patch.object(run._stop, "wait", return_value=False):
            latest, changed = run._autonomous_wait(image(0))
        self.assertTrue(changed)
        self.assertEqual(latest, image(255))
        self.assertEqual(shot.call_count, 1)

    def test_autonomous_budget_prevents_extra_ai_calls(self):
        run = agent.AgentRun("goal", "gemini", max_steps=40, autonomous_mode=True,
                             autonomous_max_calls=2, autonomous_min_interval=15, step_delay=0)
        run.autonomous_min_interval = 0
        events = []
        run.emit = lambda event, **kw: events.append(event)
        replies = [(json.dumps({"actions": [{"name": "press_key", "args": {"key": "tab"}}]}), "gemini")] * 2
        colors = iter(range(0, 255, 20))
        with patch.object(display, "capture_for_model", side_effect=lambda **kw: (image(next(colors)), 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(display, "screen_fingerprint", return_value=tuple([255] * 144)), \
             patch.object(agent, "chat_with_fallback", side_effect=replies) as chat, \
             patch.object(agent, "execute_action", return_value={"ok": True}), \
             patch.object(run._stop, "wait", return_value=False):
            result = run.run()
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(result["outcome"], "autonomous_limit")
        self.assertIn("autonomous_limit", events)

    def test_default_autonomous_budget_can_reach_twenty_calls(self):
        run = agent.AgentRun("goal", "gemini", max_steps=20, autonomous_mode=True,
                             autonomous_max_calls=20)
        self.assertEqual(min(run.max_steps, run.autonomous_max_calls), 20)

    def test_settings_dialog_syncs_the_autonomous_toggle(self):
        """Toggling 'Autonome' in Settings used to be reverted by the Agent tab's
        stale checkbox — the mode looked broken because it never stayed on."""
        root = tk.Tk(); root.withdraw()
        with patch.object(display, "interesting_windows", return_value=[]):
            app = gui.App(root)
        try:
            cfg = {**app.cfg, "autonomous_mode": True, "execution_mode": "browser",
                   "eco_mode": True, "agent_profile": "video_editing",
                   "virtual_cursor": False, "limit_actions_per_capture": False,
                   "actions_per_capture": 7, "game_mode": True, "window_mode": True,
                   "window_title": "X"}
            with patch.object(display, "interesting_windows", return_value=[]):
                app._apply_cfg_to_controls(cfg)
            self.assertTrue(app.autonomous_var.get())
            self.assertEqual(app.mode_var.get(), "browser")
            self.assertTrue(app.eco_var.get())
            self.assertEqual(app.profile_var.get(), "video_editing")
            self.assertFalse(app.cursor_var.get())
            self.assertFalse(app.limit_var.get())
            self.assertEqual(int(app.action_count.get()), 7)
            app._save_run_options()          # the tab must not revert Settings
            self.assertTrue(settings.load()["autonomous_mode"])
        finally:
            root.destroy()

    def test_scroll_can_target_coordinates(self):
        """The mouse is parked between steps, so mouse_scroll must accept x,y —
        it used to scroll wherever the parked cursor happened to be."""
        with patch.object(agent.input_control, "mouse_scroll") as scroll:
            agent.execute_action("mouse_scroll", {"amount": 5, "x": 100, "y": 200})
        scroll.assert_called_once_with(5, 200, 100)

    def test_parked_mouse_avoids_the_show_desktop_corner(self):
        """The exact bottom-right pixel is Windows' 'Show desktop' button: parking
        there triggered Aero Peek and corrupted the next screenshot."""
        run = agent.AgentRun("goal", "gemini", max_steps=1, step_delay=0)
        answer = json.dumps({"actions": [{"name": "press_key", "args": {"key": "tab"}}]})
        with patch.object(display, "capture_for_model", return_value=(image(0), 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(display, "screen_info",
                          return_value={"primary": {"width_px": 1920, "height_px": 1080}}), \
             patch.object(agent, "chat_with_fallback", return_value=(answer, "gemini")), \
             patch.object(agent, "execute_action", return_value={"ok": True}), \
             patch.object(agent.input_control, "mouse_move") as move:
            run.run()
        move.assert_not_called()   # above the taskbar, not the corner

    def test_agent_decision_tokens_are_bounded(self):
        for eco, expected in ((True, 900), (False, 1600)):
            run = agent.AgentRun("goal", "gemini", max_steps=1, eco_mode=eco, step_delay=0)
            with patch.object(display, "capture_for_model", return_value=(image(0), 1.0)), \
                 patch.object(display, "interesting_windows", return_value=[]), \
                 patch.object(agent, "chat_with_fallback",
                              return_value=(json.dumps({"actions": [{"name": "press_key", "args": {"key": "tab"}}]}), "gemini")) as chat, \
                 patch.object(agent, "execute_action", return_value={"ok": True}):
                run.run()
            self.assertEqual(chat.call_args.kwargs["max_tokens"], expected)

    def test_audio_requires_a_path_explicitly_supplied_by_user(self):
        path = str(Path(self.tmp.name) / "sound.mp3")
        run = agent.AgentRun("analyse le son", "gemini", max_steps=1, step_delay=0)
        answer = json.dumps({"actions": [{"name": "analyze_audio", "args": {"path": path}}]})
        events = []
        run.emit = lambda event, **kw: events.append((event, kw))
        with patch.object(display, "capture_for_model", return_value=(image(0), 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(agent, "chat_with_fallback", return_value=(answer, "gemini")), \
             patch.object(media, "analyze_audio") as analyze:
            run.run()
        analyze.assert_not_called()
        self.assertTrue(any("explicitement" in e[1].get("text", "") for e in events if e[0] == "action_error"))

    def test_hud_message_feeds_active_agent(self):
        root = tk.Tk(); root.withdraw()
        received = []
        overlay = AgentOverlay(root, lambda: None, received.append)
        try:
            overlay.entry.insert(0, "Réponds à ce message")
            overlay.submit()
            self.assertEqual(received, ["Réponds à ce message"])
            self.assertIn("Réponds", overlay.reply.cget("text"))
        finally:
            overlay.destroy(); root.destroy()

    def test_blue_click_marker_lingers_and_is_configurable(self):
        from agent_screen import overlay as overlay_module
        self.assertNotEqual(overlay_module.CURSOR_COLOR, overlay_module.PURPLE)
        self.assertEqual(settings.save({"cursor_linger": 99})["cursor_linger"], 30)
        self.assertEqual(settings.save({"cursor_linger": 3})["cursor_linger"], 3)
        self.assertEqual(settings.save({"cursor_linger": -4})["cursor_linger"], 0)
        root = tk.Tk(); root.withdraw()
        overlay = AgentOverlay(root, lambda: None, linger=5)
        try:
            self.assertEqual(overlay.linger, 5.0)
            with patch.object(overlay.root, "after") as after:   # click -> linger
                overlay._frame(12, True)
            after.assert_called_with(5000, overlay.cursor.withdraw)
            with patch.object(overlay.root, "after") as after:   # move -> quick hide
                overlay._frame(12, False)
            after.assert_called_with(350, overlay.cursor.withdraw)
        finally:
            overlay.destroy(); root.destroy()

    def test_launch_must_be_verified_before_done(self):
        """'Ouvre CapCut' used to finish right after opening the Start menu or a
        splash screen: a launch now forces one verification step before done."""
        run = agent.AgentRun("ouvre capcut", "gemini", max_steps=6, step_delay=0)
        events = []
        run.emit = lambda event, **kw: events.append((event, kw))
        replies = [
            (json.dumps({"actions": [{"name": "open_app", "args": {"name": "capcut"}}]}), "gemini"),
            (json.dumps({"done": True, "summary": "CapCut est ouvert."}), "gemini"),
            (json.dumps({"actions": [{"name": "press_key", "args": {"key": "esc"}}]}), "gemini"),
            (json.dumps({"done": True, "summary": "CapCut prêt, pub fermée."}), "gemini"),
        ]
        colors = iter(range(0, 255, 5))
        with patch.object(display, "capture_for_model",
                          side_effect=lambda **kw: (image(next(colors)), 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(agent, "chat_with_fallback", side_effect=replies) as chat, \
             patch.object(agent, "execute_action", return_value={"ok": True}):
            result = run.run()
        self.assertEqual(result["outcome"], "done")
        self.assertEqual(chat.call_count, 4)   # the early done was refused
        self.assertTrue(any(e[0] == "thought" and "rification" in e[1].get("text", "")
                            for e in events))

    def test_agent_history_window_lists_sessions(self):
        with patch.object(sessions, "sessions_file",
                          return_value=Path(self.tmp.name) / "agent_sessions.json"):
            sessions.save_session({**sessions.new_session("Ouvre CapCut", "Montage"),
                                   "outcome": "done",
                                   "events": [{"kind": "goal", "step": 0, "text": "Ouvre CapCut"},
                                              {"kind": "done", "step": 1, "text": "CapCut prêt."}]})
            root = tk.Tk(); root.withdraw()
            app = gui.App(root)
            try:
                app._open_history()
                tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
                self.assertTrue(tops, "la fenêtre Historique doit s'ouvrir")
                for w in tops:
                    w.destroy()
            finally:
                root.destroy()

    def test_record_video_writes_a_real_mp4(self):
        if not media._ffmpeg_exe():
            self.skipTest("ffmpeg indisponible")
        out = Path(self.tmp.name) / "rec"
        captured = []
        result = media.record_video(
            lambda: (captured.append(1) or Image.new("RGB", (64, 36), (10, 20, 30))),
            seconds=1, fps=3, out_dir=out)
        self.assertTrue(result["ok"])
        self.assertTrue(Path(result["path"]).is_file())
        self.assertTrue(result["file"].endswith(".mp4"))
        self.assertEqual(len(captured), 3)

    def test_record_video_raises_without_ffmpeg(self):
        with patch.object(media, "_ffmpeg_exe", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                media.record_video(lambda: Image.new("RGB", (4, 4)), seconds=1, fps=2,
                                   out_dir=Path(self.tmp.name) / "rec")

    def test_record_video_action_saves_and_emits(self):
        run = agent.AgentRun("enregistre une vidéo", "gemini", max_steps=1, step_delay=0)
        answer = json.dumps({"actions": [{"name": "record_video", "args": {"seconds": 1, "fps": 2}}]})
        events = []
        run.emit = lambda event, **kw: events.append((event, kw))
        with patch.object(display, "capture_for_model", return_value=(image(0), 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(agent, "chat_with_fallback", return_value=(answer, "gemini")), \
             patch.object(media, "record_video",
                          return_value={"ok": True, "path": "P", "file": "f.mp4",
                                        "seconds": 1.0}) as rec:
            run.run()
        rec.assert_called_once()
        self.assertTrue(any(e[0] == "video" for e in events))

    def test_live_message_can_receive_a_reply_without_desktop_action(self):
        run = agent.AgentRun("surveille", "gemini", autonomous_mode=True,
                             autonomous_max_calls=2, autonomous_min_interval=15, step_delay=0)
        run.autonomous_min_interval = 0
        run.guide("où en es-tu ?")
        events = []
        run.emit = lambda event, **kw: events.append((event, kw))
        replies = [(json.dumps({"message": "Je surveille toujours.", "actions": []}), "gemini"),
                   (json.dumps({"actions": [{"name": "press_key", "args": {"key": "tab"}}]}), "gemini")]
        colors = iter(range(0, 255, 20))
        with patch.object(display, "capture_for_model", side_effect=lambda **kw: (image(next(colors)), 1.0)), \
             patch.object(display, "interesting_windows", return_value=[]), \
             patch.object(display, "screen_fingerprint", return_value=tuple([255] * 144)), \
             patch.object(agent, "chat_with_fallback", side_effect=replies), \
             patch.object(agent, "execute_action", return_value={"ok": True}), \
             patch.object(run._stop, "wait", return_value=False):
            result = run.run()
        self.assertEqual(result["ai_calls"], 2)
        self.assertTrue(any(e[0] == "agent_message" and "surveille" in e[1]["text"] for e in events))


if __name__ == "__main__":
    unittest.main()
