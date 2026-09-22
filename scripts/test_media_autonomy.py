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
from agent_screen import agent, apps, conversations, display, gui, media, settings
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

    def test_autonomous_wait_is_local_until_change(self):
        run = agent.AgentRun("goal", "gemini", autonomous_mode=True,
                             autonomous_min_interval=15, autonomous_minutes=5)
        run._started_at = time.monotonic()
        shots = iter([image(0), image(255)])
        run.autonomous_min_interval = 0
        with patch.object(run, "_shot", side_effect=lambda: next(shots)), \
             patch.object(run._stop, "wait", return_value=False):
            latest, changed = run._autonomous_wait(image(0))
        self.assertTrue(changed)
        self.assertEqual(latest, image(255))

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
             patch.object(agent, "chat_with_fallback", side_effect=replies), \
             patch.object(agent, "execute_action", return_value={"ok": True}), \
             patch.object(run._stop, "wait", return_value=False):
            result = run.run()
        self.assertEqual(result["ai_calls"], 2)
        self.assertTrue(any(e[0] == "agent_message" and "surveille" in e[1]["text"] for e in events))


if __name__ == "__main__":
    unittest.main()
