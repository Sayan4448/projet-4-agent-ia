"""Offline coverage of local providers, browser isolation, batching and overlay."""
import ctypes
import json
from pathlib import Path
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from agent_screen import agent, ai_client, browser_mode, gui, input_control, settings
from agent_screen.overlay import AgentOverlay


class ModesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(settings, "config_file", return_value=Path(self.tmp.name) / "config.json")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: agent.release(agent.active_run()))

    def test_new_settings_round_trip_and_bounds(self):
        cfg = settings.save({"execution_mode": "browser", "eco_mode": True, "virtual_cursor": False,
                             "actions_per_capture": 99, "limit_actions_per_capture": False,
                             "local_urls": {"ollama": "http://localhost:11435/"}})
        self.assertEqual(settings.load(), cfg)
        self.assertEqual(cfg["actions_per_capture"], 3)
        self.assertEqual(cfg["local_urls"]["ollama"], "http://localhost:11435")

    def test_eco_reduces_payload_without_overwriting_settings(self):
        run = agent.AgentRun("goal", "gemini", eco_mode=True, image_width=1920,
                             screenshot_each_action=True, jpeg_quality=90)
        self.assertEqual((run.image_width, run.jpeg_quality), (960, 60))
        self.assertFalse(run.screenshot_each_action)
        self.assertEqual(settings.load()["image_width"], 1280)

    def test_browser_dispatch_rejects_desktop_and_os_shortcuts(self):
        session = browser_mode.BrowserSession()
        page = Mock(url="https://example.invalid")
        with patch.object(session, "_active_page", return_value=page), \
             patch.object(agent, "execute_action") as desktop:
            for name in ("run_terminal_command", "open_app", "focus_window", "key_down", "mouse_drag"):
                with self.assertRaises(ValueError):
                    session.execute(name, {})
            for keys in (["win", "r"], ["alt", "f4"], ["ctrl", "l"]):
                with self.assertRaises(ValueError):
                    session.execute("hotkey", {"keys": keys})
            for url in ("file:///C:/Windows", "javascript://alert(1)", "ms-settings://display"):
                with self.assertRaises(ValueError):
                    session.execute("open_url", {"url": url})
        desktop.assert_not_called()
        page.goto.assert_not_called()

    def test_browser_clicks_use_page_coordinates_and_bounds(self):
        session = browser_mode.BrowserSession()
        session.scale = 2
        page = Mock(url="https://example.invalid")
        with patch.object(session, "_active_page", return_value=page):
            session.execute("mouse_click", {"x": 20, "y": 30})
            # normalized 0-1000 -> page px: 20/1000*1280, 30/1000*800
            page.mouse.click.assert_called_once_with(25.6, 24.0, button="left", click_count=1)
            for args in ({}, {"x": -200, "y": 2}, {"x": 9999, "y": 1}):
                with self.assertRaises(ValueError):
                    session.execute("mouse_click", args)

    def test_browser_loop_never_touches_desktop_and_enforces_batch_limit(self):
        session = Mock()
        session.screenshot.return_value = "IMG"
        session.execute.return_value = {"ok": True}
        answers = [(json.dumps({"actions": [{"name": "type_text", "args": {"text": str(i)}} for i in range(9)]}), "gemini"),
                   ('{"done":true,"summary":"ok"}', "gemini")]
        run = agent.AgentRun("goal", "gemini", execution_mode="browser", actions_per_capture=2, max_steps=2, step_delay=0)
        with patch.object(browser_mode, "BrowserSession", return_value=session), \
             patch.object(agent, "chat_with_fallback", side_effect=answers) as chat, \
             patch.object(agent, "execute_action") as desktop, \
             patch.object(agent, "_virtual_action") as virtual, \
             patch.object(agent.input_control, "release_all_keys") as release, \
             patch.object(agent.input_control, "mouse_up") as mouse_up, \
             patch.object(agent.display, "capture_for_model") as grab:
            result = run.run()
        self.assertTrue(result["ok"], result)
        self.assertEqual(session.execute.call_count, 2)
        self.assertEqual(session.screenshot.call_count, 2)
        session.close.assert_called_once()
        for unused in (desktop, virtual, release, mouse_up, grab):
            unused.assert_not_called()
        self.assertNotIn("run_terminal_command", chat.call_args.kwargs["prompt"])
        self.assertIn("up to 2 actions", chat.call_args.kwargs["prompt"])

    def test_capture_limit_cannot_exceed_three(self):
        for enabled in (True, False):
            run = agent.AgentRun("goal", "gemini", actions_per_capture=99,
                                 limit_actions_per_capture=enabled)
            self.assertLessEqual(run.action_limit, 3)

    def test_virtual_double_click_message_order(self):
        with patch.object(input_control, "_point_target", return_value=(123, 10, 20)), \
             patch.object(input_control, "_focus_like_a_click"), \
             patch.object(input_control, "_post") as post, \
             patch.object(input_control.pyautogui, "moveTo") as move:
            input_control.virtual_mouse_double_click(100, 200)
        self.assertEqual([c.args[1] for c in post.call_args_list], [
            input_control.WM_MOUSEMOVE, input_control.WM_LBUTTONDOWN,
            input_control.WM_LBUTTONUP, input_control.WM_LBUTTONDBLCLK,
            input_control.WM_LBUTTONUP])
        move.assert_not_called()

    def test_virtual_wheel_uses_screen_coordinates(self):
        for method, msg in ((input_control.virtual_mouse_scroll, input_control.WM_MOUSEWHEEL),
                            (input_control.virtual_mouse_hscroll, input_control.WM_MOUSEHWHEEL)):
            with patch.object(input_control, "_point_target", return_value=(123, 10, 20)), \
                 patch.object(input_control, "_post") as post:
                method(-2, x=-400, y=200)
            post.assert_called_once_with(123, msg, ((-240 & 0xffff) << 16),
                                         input_control._lparam(-400, 200))

    def test_virtual_post_failure_is_not_success(self):
        with patch.object(input_control.ctypes.windll.user32, "PostMessageW", return_value=0):
            with self.assertRaises(OSError):
                input_control._post(123, input_control.WM_MOUSEMOVE)

    def test_virtual_post_checks_windows_failure(self):
        with patch.object(input_control, "_check_target"), \
             patch.object(input_control.pyautogui, "failSafeCheck"), \
             patch.object(input_control.ctypes.windll.user32, "PostMessageW", return_value=0):
            with self.assertRaisesRegex(OSError, "refusé"):
                input_control._post(123, input_control.WM_MOUSEMOVE)

    def test_no_implicit_virtual_click_at_origin(self):
        input_control.reset_virtual_input()
        with self.assertRaises(ValueError):
            input_control.virtual_mouse_click()

    def test_virtual_type_goes_to_the_last_clicked_window(self):
        """Typing used to ask GetForegroundWindow — but a background process
        cannot reliably set it, so the text went to whatever owned focus. The
        chars must go to the window under the last virtual click instead."""
        input_control.reset_virtual_input()
        posts = []
        with patch.object(input_control, "_point_target", return_value=(456, 10, 20)), \
             patch.object(input_control, "_focus_like_a_click"), \
             patch.object(input_control, "_check_target"), \
             patch.object(input_control.pyautogui, "failSafeCheck"), \
             patch.object(input_control.ctypes.windll.user32, "IsWindow", return_value=1), \
             patch.object(input_control.ctypes.windll.user32, "PostMessageW",
                          side_effect=lambda h, m, w, l: posts.append((h, m, w)) or 1):
            input_control.virtual_mouse_click(100, 200)
            posts.clear()
            input_control.virtual_type("LESGAZO")
        self.assertTrue(posts)
        self.assertTrue(all(h == 456 for h, _m, _w in posts))
        self.assertEqual([w for _h, m, w in posts if m == input_control.WM_CHAR],
                         [ord(c) for c in "LESGAZO"])

    def test_virtual_press_key_reaches_the_clicked_window(self):
        input_control.reset_virtual_input()
        posts = []
        with patch.object(input_control, "_point_target", return_value=(456, 10, 20)), \
             patch.object(input_control, "_focus_like_a_click"), \
             patch.object(input_control, "_check_target"), \
             patch.object(input_control.pyautogui, "failSafeCheck"), \
             patch.object(input_control.ctypes.windll.user32, "IsWindow", return_value=1), \
             patch.object(input_control.ctypes.windll.user32, "MapVirtualKeyW", return_value=28), \
             patch.object(input_control.ctypes.windll.user32, "PostMessageW",
                          side_effect=lambda h, m, w, l: posts.append((h, m, w)) or 1):
            input_control.virtual_mouse_click(100, 200)
            posts.clear()
            res = input_control.virtual_press_key("enter")
            system = input_control.virtual_press_key("win")
        self.assertEqual(res, {"virtual_pressed": "enter"})
        self.assertEqual([(h, m, w) for h, m, w in posts],
                         [(456, input_control.WM_KEYDOWN, 0x0D),
                          (456, input_control.WM_KEYUP, 0x0D)])
        self.assertIsNone(system)   # system keys keep the physical path
        input_control.reset_virtual_input()

    def test_swallowed_typing_breaks_the_batch_before_enter(self):
        """A field that ignores the keystrokes must not see an enter pressed
        blindly right after: the failed typing stops the batch."""
        from scripts.test_media_autonomy import image
        run = agent.AgentRun("goal", "gemini", max_steps=2, step_delay=0, memory_enabled=False)
        reply = json.dumps({"actions": [{"name": "type_text", "args": {"text": "LESGAZO"}},
                                         {"name": "press_key", "args": {"key": "enter"}}]})
        with patch.object(run, "_shot", return_value=image(0)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", return_value=(reply, "gemini")), \
             patch.object(agent.display, "screen_fingerprint", return_value=(0,) * 144), \
             patch.object(input_control, "virtual_type", return_value={"virtual_typed": 7}), \
             patch.object(input_control, "transient_type",
                          return_value={"typed": 7, "transient": True}) as tt, \
             patch.object(input_control, "virtual_press_key") as vk, \
             patch.object(input_control, "mouse_up"):
            result = run.run()
        vk.assert_not_called()
        self.assertEqual(tt.call_count, 2)      # one discreet retry per attempt
        self.assertFalse(result["ok"])

    def test_confirmed_typing_lets_the_batch_continue(self):
        from scripts.test_media_autonomy import image
        run = agent.AgentRun("goal", "gemini", max_steps=2, step_delay=0, memory_enabled=False)
        replies = [
            (json.dumps({"actions": [{"name": "type_text", "args": {"text": "LESGAZO"}},
                                      {"name": "press_key", "args": {"key": "enter"}}]}), "gemini"),
            (json.dumps({"done": True, "summary": "sent"}), "gemini"),
        ]
        with patch.object(run, "_shot", return_value=image(0)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", side_effect=replies), \
             patch.object(agent.display, "screen_fingerprint",
                          side_effect=[(0,) * 144, (9,) * 144,
                                       (9,) * 144, (20,) * 144]), \
             patch.object(input_control, "virtual_type", return_value={"virtual_typed": 7}) as vt, \
             patch.object(input_control, "virtual_press_key",
                          return_value={"virtual_pressed": "enter"}) as vk, \
             patch.object(input_control, "transient_type") as tt, \
             patch.object(input_control, "mouse_up"):
            result = run.run()
        vt.assert_called_once_with("LESGAZO")
        vk.assert_called_once_with("enter")   # sent on the first try: no retry
        tt.assert_not_called()
        self.assertEqual(result["outcome"], "done")

    def test_unsent_enter_is_retried_then_fails_honestly(self):
        """Enter after a confirmed typing that changes nothing must not be
        reported as sent: one retry, then an honest ok=false so the model
        re-observes instead of believing the message went out."""
        from scripts.test_media_autonomy import image
        run = agent.AgentRun("goal", "gemini", max_steps=2, step_delay=0, memory_enabled=False)
        replies = [
            (json.dumps({"actions": [{"name": "type_text", "args": {"text": "salut"}},
                                      {"name": "press_key", "args": {"key": "enter"}}]}), "gemini"),
            (json.dumps({"done": True, "summary": "sent"}), "gemini"),
        ]
        flat = tuple([9] * 144)
        with patch.object(run, "_shot", return_value=image(0)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", side_effect=replies), \
             patch.object(agent.display, "screen_fingerprint",
                          side_effect=[(0,) * 144, flat, flat, flat, flat]), \
             patch.object(input_control, "virtual_type", return_value={"virtual_typed": 5}), \
             patch.object(input_control, "virtual_press_key",
                          return_value={"virtual_pressed": "enter"}) as vk, \
             patch.object(input_control, "transient_type"), \
             patch.object(input_control, "mouse_up"):
            result = run.run()
        self.assertEqual(vk.call_count, 2)     # pressed, then retried once
        self.assertFalse(result["ok"])        # still nothing on screen: honest failure
        self.assertTrue(any("Enter after typing" in h["summary"] for h in run.history))

    def test_retry_can_save_the_send(self):
        from scripts.test_media_autonomy import image
        run = agent.AgentRun("goal", "gemini", max_steps=2, step_delay=0, memory_enabled=False)
        replies = [
            (json.dumps({"actions": [{"name": "type_text", "args": {"text": "salut"}},
                                      {"name": "press_key", "args": {"key": "enter"}}]}), "gemini"),
            (json.dumps({"done": True, "summary": "sent"}), "gemini"),
        ]
        flat = tuple([9] * 144)
        with patch.object(run, "_shot", return_value=image(0)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", side_effect=replies), \
             patch.object(agent.display, "screen_fingerprint",
                          side_effect=[(0,) * 144, flat, flat, flat, tuple([40] * 144)]), \
             patch.object(input_control, "virtual_type", return_value={"virtual_typed": 5}), \
             patch.object(input_control, "virtual_press_key",
                          return_value={"virtual_pressed": "enter"}) as vk, \
             patch.object(input_control, "transient_type"), \
             patch.object(input_control, "mouse_up"):
            result = run.run()
        self.assertEqual(vk.call_count, 2)     # first Enter missed, retry landed
        self.assertEqual(result["outcome"], "done")

    def test_main_enter_is_not_marked_extended(self):
        """Every posted Enter carried the KB extended flag, so Chromium read
        NumpadEnter (event.code='NumpadEnter') and Discord's send handler
        ignored the press — 'typed but never sent'. The main Enter must not
        set bit 24; real extended keys (PageUp, arrows, Delete) keep it."""
        lp = input_control._key_lparam(0x0D, False)
        self.assertEqual((lp >> 24) & 1, 0, "main Enter must not be extended")
        self.assertEqual((lp >> 16) & 0xFF, 0x1C, "scan code of Enter")
        for vk in (0x21, 0x25, 0x26, 0x2E):
            self.assertEqual((input_control._key_lparam(vk, False) >> 24) & 1, 1)
        up = input_control._key_lparam(0x0D, True)
        self.assertEqual((up >> 30) & 3, 3, "keyup transition bits")

    def test_prompt_teaches_spelled_names_and_type_verification(self):
        self.assertIn("L-E-S-G-A-Z-O", agent.SYSTEM_PROMPT)
        self.assertIn("next screenshot MUST show the text", agent.SYSTEM_PROMPT)

    def test_dead_zone_refuses_third_nearby_ineffective_click(self):
        """Re-aiming 10 px around a dead target used to defeat the exact-match
        anti-spam: three ineffective clicks in the same area now stop the run
        with a 'switch method' instruction."""
        from scripts.test_media_autonomy import image
        run = agent.AgentRun("goal", "gemini", max_steps=4, step_delay=0, memory_enabled=False)
        replies = [
            (json.dumps({"actions": [{"name": "mouse_click", "args": a}]}), "gemini")
            for a in ({"x": 40, "y": 50}, {"x": 45, "y": 48}, {"x": 42, "y": 52},
                      {"x": 43, "y": 51})
        ]
        with patch.object(run, "_shot", return_value=image(0)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", side_effect=replies), \
             patch.object(agent, "_virtual_action", return_value={"ok": True}) as action, \
             patch.object(input_control, "transient_click") as transient, \
             patch.object(input_control, "mouse_up"):
            result = run.run()
        # the two first nearby clicks ran, the third (and the fourth) were refused
        self.assertEqual(action.call_count, 2)
        transient.assert_not_called()
        self.assertTrue(any("zone" in h["summary"].lower() for h in run.history))
        self.assertFalse(result["ok"])

    def test_effective_click_clears_the_dead_zone(self):
        from scripts.test_media_autonomy import image
        run = agent.AgentRun("goal", "gemini", max_steps=2, step_delay=0, memory_enabled=False)
        replies = [
            (json.dumps({"actions": [{"name": "mouse_click", "args": {"x": 40, "y": 50}}]}), "gemini"),
            (json.dumps({"actions": [{"name": "mouse_click", "args": {"x": 42, "y": 51}}]}), "gemini"),
        ]
        shots = iter([image(0), image(255), image(255)])
        with patch.object(run, "_shot", side_effect=lambda: next(shots)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", side_effect=replies), \
             patch.object(agent, "_virtual_action", return_value={"ok": True}) as action, \
             patch.object(input_control, "mouse_up"):
            run.run()
        # step 1 changed the screen (0 -> 255): the zone was cleared, so the
        # nearby click of step 2 is still allowed instead of being refused
        self.assertEqual(action.call_count, 2)
        self.assertEqual(run._bad_click_zone, [(42, 51)])

    def test_speed_setting_round_trip_and_profile_values(self):
        cfg = settings.save({"speed": "rapide"})
        try:
            self.assertEqual(cfg["speed"], "rapide")
            self.assertEqual(cfg["step_delay"], settings.SPEEDS["rapide"]["step_delay"])
            self.assertEqual(settings.load()["speed"], "rapide")
            # an unknown value is refused, the current choice survives
            self.assertEqual(settings.save({"speed": "turbo"})["speed"], "rapide")
        finally:
            settings.save({"speed": "normal"})

    def test_type_settle_is_bounded_and_used_by_the_run(self):
        self.assertEqual(agent.AgentRun("g", "gemini", type_settle=0.2).type_settle, 0.2)
        self.assertEqual(agent.AgentRun("g", "gemini", type_settle=99).type_settle, 0.5)

    def test_scroll_coordinates_are_scaled_and_bounded(self):
        run = agent.AgentRun("goal", "gemini")
        run.scale = 1.5
        run.geometry = {"origin": (-1920, 0), "scale_y": 1.5, "width": 1280, "height": 720,
                        "real_w": 1920, "real_h": 1080}
        for name in ("mouse_scroll", "mouse_hscroll"):
            self.assertIn(name, agent.PIXEL_ACTIONS)
        # normalized 0-1000 -> real px: 100/1000*1920 + (-1920), 200/1000*1080
        self.assertEqual(run._to_real({"x": 100, "y": 200}), {"x": -1728, "y": 216})
        for args in ({"x": 9999, "y": 10}, {"x": -200, "y": 20}, {"x": 100}):
            with self.assertRaises(ValueError):
                run._to_real(args)

    def test_repeated_ineffective_clicks_never_resume_spamming(self):
        from scripts.test_media_autonomy import image
        run = agent.AgentRun("goal", "gemini", max_steps=5, step_delay=0, memory_enabled=False)
        reply = json.dumps({"actions": [{"name": "mouse_click", "args": {"x": 40, "y": 50}},
                                         {"name": "type_text", "args": {"text": "must not be sent"}}]})
        with patch.object(run, "_shot", return_value=image(0)), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", return_value=(reply, "gemini")), \
             patch.object(agent, "_virtual_action", return_value={"ok": True}) as action, \
             patch.object(input_control, "transient_click",
                          return_value={"transient_clicked": [40, 50]}) as transient, \
             patch.object(input_control, "mouse_move") as move, \
             patch.object(input_control, "mouse_up") as up:
            result = run.run()
        self.assertEqual(action.call_count, 1)
        self.assertEqual(transient.call_count, 1)   # one discreet physical retry, then refuse
        self.assertEqual(result["outcome"], "max_steps")
        self.assertFalse(result["ok"])
        move.assert_not_called()
        up.assert_not_called()

    def test_action_failure_discards_remaining_batch(self):
        run = agent.AgentRun("goal", "gemini", max_steps=1, step_delay=0, memory_enabled=False)
        reply = json.dumps({"actions": [{"name": "type_text", "args": {"text": "test"}},
                                         {"name": "press_key", "args": {"key": "enter"}}]})
        with patch.object(run, "_shot", return_value="IMG"), \
             patch.object(run, "_windows_text", return_value=""), \
             patch.object(agent, "chat_with_fallback", return_value=(reply, "gemini")), \
             patch.object(agent.display, "screen_fingerprint", return_value=(0,) * 144), \
             patch.object(input_control, "virtual_type", side_effect=OSError("input rejected")), \
             patch.object(agent, "execute_action") as physical:
            result = run.run()
        physical.assert_not_called()
        self.assertFalse(result["ok"])

    def test_auto_overlay_hides_for_captures_and_shows_while_working(self):
        root = tk.Tk()
        root.withdraw()
        overlay = AgentOverlay(root, lambda: None)
        try:
            overlay.start("Bureau")
            root.update()
            self.assertTrue(overlay.hud.winfo_ismapped())      # visible while working
            overlay.hide_for_action()                          # capture/click moment
            root.update()
            self.assertFalse(overlay.hud.winfo_ismapped())
            overlay.show_after_action()                        # back when interacting
            root.update()
            self.assertTrue(overlay.hud.winfo_ismapped())
            overlay.set_mode("hidden")
            root.update()
            self.assertFalse(overlay.hud.winfo_ismapped())
        finally:
            overlay.destroy()
            root.destroy()

    def test_local_session_requires_no_key_and_never_falls_back_to_cloud(self):
        settings.save({"provider": "ollama", "models": {"ollama": "vision-local"},
                       "api_keys": {"gemini": "fake-cloud-key"}})
        with patch.object(ai_client, "_call_provider_single", side_effect=ai_client.AIError("offline")) as call:
            with self.assertRaises(ai_client.AIError):
                ai_client.chat_with_fallback("ollama", "hello")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[:3], ("ollama", "", "vision-local"))

    def test_local_requests_and_model_discovery(self):
        for provider in settings.LOCAL_PROVIDERS:
            response = Mock(status_code=200)
            response.json.return_value = {"message": {"content": "OK"}, "choices": [{"message": {"content": "OK"}}]}
            with patch.object(ai_client, "_post", return_value=response) as post:
                text = ai_client._call_provider_single(provider, "", "vision", "system", "prompt", "BASE64", True, "image/jpeg")
            self.assertEqual(text, "OK")
            url, headers, body = post.call_args.args
            self.assertNotIn("Authorization", headers)
            self.assertIn("BASE64", json.dumps(body))
            self.assertIn("/api/chat" if provider == "ollama" else "/v1/chat/completions", url)
            response.json.return_value = {"models": [{"name": "vision"}], "data": [{"id": "vision"}]}
            with patch.object(ai_client, "_get", return_value=response):
                self.assertEqual(ai_client.list_models(provider), ["vision"])

    def test_cursor_event_is_acknowledged_before_action(self):
        events = []
        def emit(event, **kw):
            events.append(event)
            if event == "cursor":
                kw["ready"].set()
        run = agent.AgentRun("goal", "gemini", virtual_cursor=True, emit=emit)
        with patch.object(agent.input_control, "mouse_position", return_value={"x": 1, "y": 2}):
            run._visualize("mouse_click", {"x": 100, "y": 200})
        self.assertEqual(events, ["cursor"])

    def test_overlay_is_click_through_and_nonactivating(self):
        root = tk.Tk()
        root.withdraw()
        overlay = AgentOverlay(root, lambda: None)
        try:
            overlay.set_mode("always")
            overlay.start("Bureau")
            overlay.show(300, 300, True)
            root.update()
            user = ctypes.windll.user32
            hwnd = user.GetParent(overlay.cursor.winfo_id())
            style = user.GetWindowLongPtrW(hwnd, -20)
            self.assertTrue(style & 0x20)
            self.assertTrue(style & 0x08000000)
            self.assertTrue(overlay.hud.winfo_ismapped())
            overlay.finish()
            self.assertFalse(overlay.hud.winfo_ismapped())
        finally:
            overlay.destroy()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
