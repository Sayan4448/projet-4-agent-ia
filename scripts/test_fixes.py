"""Test suite for Agent Screen bugfixes and fallback mechanism."""
import base64
import os
import unittest
from unittest.mock import patch

from agent_screen import (agent, ai_client, apps, display, gui, input_control, paths,
                          server, settings)
from agent_screen.ai_client import AIError, chat_with_fallback

class TestAgentScreen(unittest.TestCase):
    def test_split_keys(self):
        # Single key
        self.assertEqual(settings.split_keys("key1_abcdef12345"), ["key1_abcdef12345"])
        # Multiple keys with comma
        self.assertEqual(
            settings.split_keys("key1_abcdef12345, key2_abcdef12345"),
            ["key1_abcdef12345", "key2_abcdef12345"]
        )
        # Multiple keys with newline
        self.assertEqual(
            settings.split_keys("key1_abcdef12345\nkey2_abcdef12345"),
            ["key1_abcdef12345", "key2_abcdef12345"]
        )
        # Multiple keys with semicolon
        self.assertEqual(
            settings.split_keys("key1_abcdef12345; key2_abcdef12345"),
            ["key1_abcdef12345", "key2_abcdef12345"]
        )

    def test_img_widths_tuple(self):
        # Ensure img_widths is a valid list and not broken by T()
        self.assertIn("1280", settings.load().get("image_width", 1280).__str__())
        from agent_screen.gui import S
        self.assertTrue(len(S["img_widths"]) >= 5)
        self.assertEqual(S["img_widths"][0], "0")
        self.assertEqual(S["img_widths"][2], "1280")

    def test_screenshot_fast_jpeg(self):
        # Test that fast screenshot produces lightweight jpeg
        b64, scale = display.capture_for_model(grid=False, max_width=1280, jpeg_quality=80)
        self.assertTrue(len(b64) > 0)
        # the capture owns the scale: agent._to_real() multiplies by it
        self.assertGreaterEqual(scale, 1.0)
        raw = base64.b64decode(b64)
        # JPEG header starts with \xff\xd8
        self.assertTrue(raw.startswith(b"\xff\xd8"))
        # JPEG should be reasonably compact (< 400KB)
        self.assertTrue(len(raw) < 500000)

    def test_agent_run_emits_finished(self):
        # Test that AgentRun always emits 'finished' event on stop
        events = []
        run = agent.AgentRun("Goal test", "gemini", max_steps=1, emit=lambda ev, **kw: events.append((ev, kw)))
        run.stop()
        res = run.run()
        self.assertEqual(res["outcome"], "stopped")
        event_names = [e[0] for e in events]
        self.assertIn("finished", event_names)

    def test_fallback_mechanism(self):
        # Test that chat_with_fallback attempts fallback when first candidate fails
        from unittest.mock import patch
        fallback_calls = []

        def fake_call(provider, key, model, system, prompt, b64_png, is_json,
                      mime="image/png", max_tokens=2048):
            if key == "bad_key":
                raise ai_client.AIError("429 Quota exceeded")
            return f"Success from {provider} with {key}"

        with patch("agent_screen.ai_client._call_provider_single", side_effect=fake_call):
            with patch("agent_screen.settings.load", return_value={
                "provider": "gemini",
                "api_keys": {"gemini": "bad_key, good_key_12345"},
                "models": {"gemini": "gemini-2.5-flash"},
            }):
                reply, eff_prov = ai_client.chat_with_fallback(
                    "gemini", "Hello",
                    on_fallback=lambda info: fallback_calls.append(info)
                )
                self.assertIn("good_key_12345", reply)
                self.assertEqual(eff_prov, "gemini")
                self.assertEqual(len(fallback_calls), 1)
                self.assertEqual(fallback_calls[0]["from_provider"], "gemini")

    def test_terminal_command(self):
        from agent_screen import input_control
        res = input_control.run_terminal_command("Write-Output 'Hello from PowerShell'")
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("Hello from PowerShell", res["stdout"])

    def test_action_execution_terminal(self):
        res = agent.execute_action("run_terminal_command", {"command": "Write-Output 'AgentTest'"})
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("AgentTest", res["stdout"])

class TestReliabilityFixes(unittest.TestCase):
    """Regression tests for the v1.6 reliability work.

    They must stay offline, side-effect free (no app is ever launched, no API
    call is made) and fast. `mock` patches target the module attribute, which
    is how the production code resolves it at call time.
    """

    def tearDown(self):
        owned = agent.active_run()
        if owned is not None:                 # never leak the desktop between tests
            agent.release(owned)

    # -------------------------------------------------------- run robustness
    def test_capture_failure_still_notifies_the_ui(self):
        """A capture blowing up must not freeze the window: run() emits
        'finished' (the old try/finally-only loop killed the thread silently)."""
        events = []
        run = agent.AgentRun("goal", "gemini", max_steps=2,
                             emit=lambda ev, **kw: events.append(ev))
        with patch("agent_screen.display.capture_for_model",
                   side_effect=RuntimeError("capture KO")):
            res = run.run()
        self.assertEqual(res["outcome"], "error")
        self.assertIn("finished", events)
        self.assertIn("error", events)
        self.assertIn("capture KO", res["error"])

    def test_loop_executes_a_step_then_finishes(self):
        """Single coverage of the decision loop: prompt -> action -> history ->
        done, with no model and no real input."""
        replies = [
            '{"thought":"go","actions":[{"name":"mouse_click",'
            '"args":{"x":5,"y":5}}],"done":false,"summary":""}',
            '{"thought":"finished","actions":[],"done":true,"summary":"fini"}',
        ]
        prompts, events = [], []

        def fake_chat(*_a, **kw):
            prompts.append(kw["prompt"])
            return replies[min(len(prompts) - 1, 1)], "gemini"

        run = agent.AgentRun("goal", "gemini", max_steps=3, step_delay=0,
                             emit=lambda ev, **kw: events.append((ev, kw)))
        with patch("agent_screen.agent.chat_with_fallback", side_effect=fake_chat), \
                patch("agent_screen.display.capture_for_model",
                      return_value=("IMG", 1.0)), \
                patch("agent_screen.display.interesting_windows",
                      return_value=[{"title": "Brave", "w": 800, "h": 600, "hwnd": 1}]), \
                patch("agent_screen.input_control.mouse_click",
                      return_value={"clicked": [5, 5]}):
            res = run.run()
        self.assertEqual(res["outcome"], "done")
        self.assertIn("Brave", prompts[0])                       # windows inventory sent
        self.assertIn("mouse_click(x=5, y=5)", run.history[0]["summary"])
        self.assertIn("finished", [ev for ev, _ in events])

    def test_prompt_lists_open_windows_and_never_asks_to_click_icons(self):
        run = agent.AgentRun("goal", "gemini", max_steps=2, emit=lambda ev, **kw: None)
        with patch("agent_screen.display.interesting_windows",
                   return_value=[{"title": "Brave"}, {"title": "Discord"}]):
            text = run._windows_text()
        self.assertIn("Brave", text)
        self.assertIn("focus_window", text)
        self.assertIn("focus_window", agent.SYSTEM_PROMPT)

    def test_summarize_reports_failure_to_the_model(self):
        self.assertIn("FAILED", agent._summarize(
            "open_app", {"name": "brave"}, {"ok": False, "error": "no window appeared"}))
        self.assertIn("OK", agent._summarize(
            "open_app", {"name": "brave"},
            {"ok": True, "method": "path", "window": "Brave", "verified": True}))
        self.assertNotIn("NOT confirmed", agent._summarize(
            "open_app", {"name": "brave"},
            {"ok": True, "method": "path", "window": "Brave", "verified": True}))
        self.assertIn("exit 0", agent._summarize(
            "run_terminal_command", {"command": "x"}, {"stdout": "y", "exit_code": 0}))

    # --------------------------------------------------------- action vocabulary
    def test_the_action_vocabulary_has_one_owner(self):
        """The vocabulary used to live in five places (the dispatcher, the prompt,
        CLASSIC_ACTIONS, _summarize, the release table): `mouse_hscroll` was
        dispatchable but announced nowhere, so the model could never use it."""
        import inspect
        import re as _re
        source = inspect.getsource(agent.execute_action)
        dispatched = set(_re.findall(r'if name == "(\w+)"', source))
        self.assertEqual(dispatched - set(agent.ACTIONS), set(),
                         "dispatche mais annonce nulle part")
        self.assertEqual(set(agent.ACTIONS) - dispatched, set(),
                         "declare mais pas dispatche")
        announced = agent.CLASSIC_ACTIONS + agent.GAME_ACTIONS
        for name, action in agent.ACTIONS.items():
            self.assertIn(action.signature, announced, f"{name} n'est annonce nulle part")
        for name in set(_re.findall(r'name == "(\w+)"', inspect.getsource(agent._summarize))):
            self.assertIn(name, agent.ACTIONS)
        # coordinates: anything the dispatcher refuses to run without must be in the
        # scaled set, and everything scaled must announce x and y
        self.assertEqual(set(_re.findall(r'_xy\(args, "(\w+)"\)', source))
                         - set(agent.PIXEL_ACTIONS), set(),
                         "coordonnees obligatoires mais non converties en pixels reels")
        for name in agent.PIXEL_ACTIONS:
            words = set(_re.findall(r"[A-Za-z_]\w*", agent.ACTIONS[name].signature))
            self.assertTrue({"x", "y"} <= words, f"{name} n'annonce pas ses coordonnees")
        # held inputs: the pair is declared once and both halves are real actions
        for name, action in agent.ACTIONS.items():
            if action.release:
                self.assertIn(action.release[0], dispatched)
                self.assertEqual(agent._release_pair(name, {})[0], action.release[0])
        self.assertIn("mouse_hscroll", agent.CLASSIC_ACTIONS)

    def test_announced_signatures_match_what_the_dispatcher_accepts(self):
        """`hotkey('ctrl','l')` was announced while the dispatcher wanted keys=[...]:
        the real model then invented {'key1','key2'} on a live run. Every argument
        the dispatcher (or its helpers) reads must appear in the signature the model
        reads — coordinates included."""
        import inspect
        import re as _re
        source = inspect.getsource(agent.execute_action)
        branches = _re.split(r'\n    if name == "', source)[1:]
        self.assertEqual(len(branches), len(agent.ACTIONS))
        for branch in branches:
            name, body = branch.split('"', 1)
            action = agent.ACTIONS[name]
            read = set(_re.findall(r'args(?:\.get)?\(\s*"(\w+)"', body))
            if "_xy(args" in body:
                read |= set(_re.findall(r'args(?:\.get)?\(\s*"(\w+)"',
                                        inspect.getsource(agent._xy)))
            if "_keys(args)" in body:
                read |= set(_re.findall(r'args(?:\.get)?\(\s*"(\w+)"',
                                        inspect.getsource(agent._keys)))
            # words of the announcement ONLY: comparing read against read|words
            # would be a tautology and would never catch a diverged signature
            words = set(_re.findall(r"[A-Za-z_]\w*", action.signature))
            if action.pixel:
                for axis in ("x", "y"):
                    self.assertIn(axis, words, f"{name}: l'axe {axis} n'est pas annonce")
            else:
                self.assertTrue(read & words,
                                f"{name}: aucun argument lu par le dispatcher n'est annonce")

    # ------------------------------------------------------------ app launching
    def test_app_name_matching_in_french_and_english(self):
        self.assertEqual(apps.find_app_entry("Ouvre Brave s'il te plait")["keys"][0], "brave")
        self.assertEqual(apps.find_app_entry("bloc-notes")["keys"][0], "notepad")
        self.assertEqual(apps.find_app_entry("calculatrice")["keys"][0], "calculator")
        self.assertEqual(apps.find_app_entry("Discord")["keys"][0], "discord")
        self.assertIsNone(apps.find_app_entry("zzzz-inexistant"))
        self.assertEqual(apps.tokens("Brave.exe"), ["brave"])
        self.assertEqual(apps.tokens("Ouvre  la  Calculatrice"), ["calculatrice"])

    def test_a_query_only_matches_the_named_app(self):
        """Scoring the query against the candidate's real name — and no longer
        taking a max over the catalogue keys — is what stops 'parametres' from
        matching 'WSL Settings' (entry key 'settings' scored 1.0 against it)."""
        shortcuts = [("WSL Settings", r"C:\ProgramData\x\WSL Settings.lnk"),
                     ("Paramètres", r"C:\ProgramData\x\Parametres.lnk")]
        with patch("agent_screen.apps.start_menu_shortcuts", return_value=shortcuts):
            self.assertEqual(apps._best_shortcut("parametres")[0], "Paramètres")
            self.assertIsNone(apps._best_shortcut("Regedit"))

    def test_running_window_match_and_process_veto(self):
        """A Notepad window called 'brave - Bloc-notes' must not count as Brave
        (this is the exact false positive that made the agent open Discord)."""
        fake = [{"title": "brave - Bloc-notes", "w": 800, "h": 600, "hwnd": 1},
                {"title": "Discord", "w": 900, "h": 700, "hwnd": 2}]
        procs = {1: "notepad.exe", 2: "Discord.exe"}
        with patch("agent_screen.display.list_windows", return_value=fake), \
                patch("agent_screen.display.window_exe",
                      side_effect=lambda h: procs.get(h, "")):
            self.assertEqual(apps.find_running_window(("brave",), ("brave.exe",)), "")
            self.assertEqual(apps.find_running_window(("discord",), ("discord.exe",)),
                             "Discord")

    def test_launch_verification_never_claims_false_success(self):
        with patch("agent_screen.display.list_windows", return_value=[]):
            ok, title, verified = apps._wait_for_window(set(), ("brave",),
                                                        ("brave.exe",), 0.6)
        self.assertFalse(ok)
        self.assertEqual(title, "")
        fake = [{"title": "Brave", "w": 800, "h": 600, "hwnd": 7}]
        with patch("agent_screen.display.list_windows", return_value=fake), \
                patch("agent_screen.display.window_exe", return_value="brave.exe"):
            ok, title, verified = apps._wait_for_window(set(), ("brave",),
                                                        ("brave.exe",), 0.6)
        self.assertTrue(ok)
        self.assertEqual(title, "Brave")
        self.assertTrue(verified)

    def test_open_app_cannot_inject_a_shell_command(self):
        """The old code did f"Start-Process '{name}'"; names are data now."""
        plan = apps.resolve_app("brave'; Start-Process calc; '")
        if plan is not None:
            self.assertNotIn(";", plan["target"])
            self.assertTrue(os.path.isfile(plan["target"]))

    def test_resolve_plan_shape_and_unknown_app(self):
        """launch_app reads plan['exes']; a plan without it crashed on the first
        real launch (unit tests that never call launch_app missed it)."""
        plan = apps.resolve_app("notepad")
        if plan is not None:
            for key in ("kind", "target", "name", "titles", "exes", "method"):
                self.assertIn(key, plan)
            self.assertTrue(plan["exes"])
        res = apps.launch_app("definitely-not-an-app-xyz", wait=0.5)
        self.assertFalse(res["ok"])
        self.assertIn("not found", res["error"])

    def test_resolve_app_on_this_machine(self):
        if os.name != "nt":
            self.skipTest("windows only")
        for name in ("notepad", "calc", "explorer"):
            plan = apps.resolve_app(name)
            self.assertIsNotNone(plan, f"aucune résolution pour {name}")
            self.assertTrue(plan["titles"])
            if plan["kind"] == "exe":
                self.assertTrue(os.path.isfile(plan["target"]), plan["target"])
        self.assertIsNone(apps.resolve_app("definitely-not-an-app-xyz"))
        self.assertEqual(apps.resolve_app(""), None)

    # ------------------------------------------------------------ web actions
    def test_open_url_requires_http(self):
        res = input_control.open_url("file:///C:/Windows/win.ini")
        self.assertFalse(res["ok"])
        self.assertIn("http", res["error"])
        with self.assertRaises(ValueError):
            input_control.open_url("")

    def test_search_web_builds_a_google_query(self):
        seen = {}

        def fake_open(url):
            seen["url"] = url
            return {"opened_url": url, "ok": True}

        with patch("agent_screen.input_control.open_url", side_effect=fake_open):
            res = input_control.search_web("météo Paris")
            self.assertTrue(seen["url"].startswith("https://www.google.com/search?q="))
            self.assertIn("m%C3%A9t%C3%A9o", seen["url"])
            self.assertEqual(res["searched"], "météo Paris")
            input_control.search_web("https://example.com/x")
            self.assertEqual(seen["url"], "https://example.com/x")
        with self.assertRaises(ValueError):
            input_control.search_web("")

    # ------------------------------------------------------------ terminal
    def test_terminal_keeps_accents(self):
        """PowerShell 5.1 writes the OEM code page: without forcing UTF-8 the
        output lost every accent ('h?llo' instead of 'héllo')."""
        res = input_control.run_terminal_command("Write-Output 'héllo à tous — ç'")
        self.assertEqual(res["exit_code"], 0)
        self.assertTrue(res["ok"])
        self.assertIn("héllo à tous", res["stdout"])

    def test_terminal_handles_empty_and_failing_commands(self):
        self.assertTrue(input_control.run_terminal_command("")["ok"])
        bad = input_control.run_terminal_command("exit 3")
        self.assertEqual(bad["exit_code"], 3)
        self.assertFalse(bad["ok"])
        broken = input_control.run_terminal_command("Get-ThisCmdletDoesNotExist -Foo")
        self.assertFalse(broken["ok"])

    def test_grid_lines_sit_on_the_real_pixel_labels(self):
        """The precision claim of the grid: the line the model reads as '600'
        must be drawn at the image pixel that a real x=600 becomes (600*scale)."""
        from PIL import Image
        real_w, real_h, scale = 1920, 1080, 1.5
        img = display._draw_grid(Image.new("RGB", (1280, 720)), real_w, real_h, scale)
        drawn = []
        for x in range(img.width):
            r, g, b = img.getpixel((x, img.height // 2))
            if r > g + 20 and r > b + 20 and r > 20:      # the red grid line, blended
                if not drawn or x - drawn[-1][-1] > 2:    # a new line (2 px wide)
                    drawn.append([x])
                else:
                    drawn[-1].append(x)
        starts = [run[0] for run in drawn]
        expected = [int(x * scale) for x in range(0, 900, 100)]   # what fits in 1280 px
        self.assertEqual(starts[:len(expected)], expected)

    def test_alive_helper_rejects_a_closed_dialog(self):
        """Closing Settings while the model list loads used to deliver the result
        into destroyed widgets (a swallowed TclError)."""
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        win = tk.Toplevel(root)
        win.withdraw()
        self.assertTrue(gui._alive(win))
        win.destroy()
        self.assertFalse(gui._alive(win))
        root.destroy()
        self.assertFalse(gui._alive(win))

    def test_a_second_run_cannot_start_from_the_keyboard(self):
        """<Return> in the goal field (and the preset list) call _start_run directly,
        so they bypass the disabled Run button: the app used to spawn a second run
        that shared the one mouse, and Stop only ever stopped the newest one."""
        import threading
        import tkinter as tk
        started, stopped = [], []

        class FakeRun:
            """Mimics the run contract: it holds the mouse until it really ends."""

            def __init__(self, goal, *_a, **_kw):
                self.goal, self.stopped = goal, False
                self._done = threading.Event()
                started.append(goal)

            def run(self):
                try:
                    self._done.wait(5)
                finally:
                    agent.release(self)

            def stop(self):
                self.stopped = True
                stopped.append(self.goal)
                self._done.set()

        cfg = dict(settings.load())
        cfg["api_keys"] = dict(cfg["api_keys"], gemini="AIza" + "x" * 32)
        root = tk.Tk()
        root.withdraw()
        app = gui.App(root)
        app.goal_entry.insert(0, "ouvre Brave")
        with patch("agent_screen.gui.AgentRun", FakeRun), \
                patch("agent_screen.gui.load", side_effect=lambda: dict(cfg)), \
                patch("agent_screen.gui.get_api_key", return_value="AIza" + "x" * 32):
            app._start_run()                     # what <Return> invokes
            app._start_run()                     # the user pressing it again
            app._start_run()
            presets = list(app.preset_cb["values"])
            if presets:
                app.preset_cb.set(presets[0])
                app._on_preset()
            app._stop_run()
        self.assertEqual(started, ["ouvre Brave"])   # only one run ever existed
        self.assertEqual(stopped, ["ouvre Brave"])   # and Stop stopped that one
        root.destroy()

    # ------------------------------------------------------------- config file
    def test_a_hand_edited_provider_never_breaks_startup(self):
        """config.json is user-editable. `{"provider": 42}` reached
        get_provider_keys() -> App.__init__ and killed the app before any window
        appeared (silently in the frozen exe). Every other field is coerced on
        load; the provider was the one that was not."""
        import json
        import pathlib
        import tempfile
        for bad in (42, ["gemini"], "", None, "chatgpt"):
            f = pathlib.Path(tempfile.mkdtemp()) / "config.json"
            f.write_text(json.dumps({"provider": bad}), encoding="utf-8")
            with patch("agent_screen.settings.config_file", return_value=f):
                cfg = settings.load()
                self.assertEqual(cfg["provider"], "gemini", bad)   # the default
                settings.get_provider_keys(cfg["provider"])        # must not raise
        f = pathlib.Path(tempfile.mkdtemp()) / "config.json"
        f.write_text(json.dumps({"provider": "OpenAI"}), encoding="utf-8")
        with patch("agent_screen.settings.config_file", return_value=f):
            self.assertEqual(settings.load()["provider"], "openai")

    def test_reading_a_config_never_writes_it(self):
        """The exact accident: a config path pointing at a foreign, unparsable file
        plus a real key source. `load()` used to migrate *and write*, which
        replaced that file with a config holding the user's key (it destroyed the
        README). Reading must leave every byte alone, and the migration must
        refuse a file it could not parse instead of replacing it."""
        import hashlib
        import pathlib
        import shutil
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp())
        foreign = tmp / "foreign.txt"
        shutil.copyfile("installer/AgentScreen.wxs", foreign)     # a copy, never the original
        before = hashlib.sha256(foreign.read_bytes()).hexdigest()
        with patch("agent_screen.settings.config_file", return_value=foreign), \
                patch("agent_screen.settings.legacy_config_candidates",
                      return_value=[settings.config_file()]):
            cfg = settings.load()
            migrated = settings.migrate_legacy_keys()
        self.assertEqual(hashlib.sha256(foreign.read_bytes()).hexdigest(), before)
        self.assertFalse(migrated)
        self.assertEqual(cfg["provider"], "gemini")      # a usable config anyway

    def test_a_legacy_config_still_migrates_explicitly(self):
        """Keys of an older version's config still come across — but only through
        the explicit call, and `load()` alone must create nothing."""
        import json
        import pathlib
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp())
        target = tmp / "config.json"
        old = tmp / "old" / "config.json"
        old.parent.mkdir()
        old.write_text(json.dumps({"api_keys": {"gemini": "A" * 24},
                                   "models": {"gemini": "legacy-model"}}), encoding="utf-8")
        with patch("agent_screen.settings.config_file", return_value=target), \
                patch("agent_screen.settings.legacy_config_candidates", return_value=[old]):
            settings.load()
            self.assertFalse(target.exists(), "lire ne doit rien ecrire")
            self.assertTrue(settings.migrate_legacy_keys())
            migrated = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(migrated["api_keys"]["gemini"], "A" * 24)
        self.assertEqual(migrated["models"]["gemini"], "legacy-model")

    def test_a_corrupt_config_is_preserved_and_starts_with_defaults(self):
        """A config that cannot be parsed (half-written by another instance, a
        crash during a save) must not be replaced by defaults + migrated keys:
        the app starts on the defaults and the file keeps its bytes."""
        import hashlib
        import pathlib
        import tempfile
        import tkinter as tk
        tmp = pathlib.Path(tempfile.mkdtemp())
        corrupt = tmp / "config.json"
        corrupt.write_text('{"provider": "gemi', encoding="utf-8")
        before = hashlib.sha256(corrupt.read_bytes()).hexdigest()
        with patch("agent_screen.settings.config_file", return_value=corrupt), \
                patch("agent_screen.settings.legacy_config_candidates",
                      return_value=[settings.config_file()]):
            cfg = settings.load()
            migrated = settings.migrate_legacy_keys()
            root = tk.Tk()
            root.withdraw()
            with patch("agent_screen.display.take_screenshot", return_value="x"):
                app = gui.App(root)
            root.destroy()
        self.assertEqual((cfg["provider"], cfg["max_steps"]), ("gemini", 12))
        self.assertFalse(migrated)
        self.assertEqual(hashlib.sha256(corrupt.read_bytes()).hexdigest(), before)
        self.assertIsNotNone(app)                     # the window still came up

    def test_the_current_config_is_not_its_own_legacy_source(self):
        """In dev the first legacy candidate *was* the current config, which is what
        let a patched path import the user's real keys and write them elsewhere."""
        self.assertNotIn(settings.config_file(), paths.legacy_config_candidates())

    def test_closing_the_window_frees_a_held_key(self):
        """The run thread dies with the process, so its finally may never run:
        closing mid-run used to leave 'w' held on the user's keyboard."""
        import tkinter as tk
        released, ups = [], []
        with patch("agent_screen.input_control.release_all_keys",
                   side_effect=lambda: released.append(1) or {}), \
                patch("agent_screen.input_control.mouse_up",
                      side_effect=lambda b="left": ups.append(b) or {}), \
                patch("agent_screen.gui.messagebox.askyesno", return_value=True):
            root = tk.Tk()
            root.withdraw()
            app = gui.App(root)
            app.run = type("R", (), {"stopped": False, "stop": lambda self: None})()
            app._on_close()
        self.assertTrue(released, "release_all_keys doit etre appele a la fermeture")
        self.assertEqual(sorted(ups), ["left", "right"])

    # ------------------------------------------------- malformed model output
    def test_hotkey_accepts_the_string_models_actually_send(self):
        """'ctrl+c' used to be unpacked character by character, so the user got
        c, t, r, l, '+' and c pressed together instead of Ctrl+C."""
        seen = []
        with patch("agent_screen.input_control.hotkey", side_effect=lambda *k: seen.append(k) or {}):
            agent.execute_action("hotkey", {"keys": "ctrl+c"})
            agent.execute_action("hotkey", {"keys": "ctrl + shift"})
            agent.execute_action("hotkey", {"keys": ["alt", "tab"]})
        self.assertEqual(seen, [("ctrl", "c"), ("ctrl", "shift"), ("alt", "tab")])

    def test_hotkey_signature_in_the_prompt_matches_the_dispatcher(self):
        """The live run showed the model inventing {'key1':'alt','key2':'f4'}: the
        prompt announced hotkey('ctrl','l') while the dispatcher wants keys=[...]."""
        self.assertIn("hotkey(keys=[", agent.SYSTEM_PROMPT)
        self.assertIn("hotkey(keys=[", agent.CLASSIC_ACTIONS)
        self.assertNotIn("hotkey('ctrl'", agent.SYSTEM_PROMPT)
        with self.assertRaises(ValueError) as ctx:
            agent.execute_action("hotkey", {"key1": "alt", "key2": "f4"})
        self.assertIn("key", str(ctx.exception))

    def test_missing_coordinates_read_as_a_sentence(self):
        """The model used to see "mouse_move ERROR:'x'" (a bare KeyError)."""
        for name, args in (("mouse_move", {}), ("mouse_drag", {"x": 5})):
            with self.assertRaises(ValueError) as ctx:
                agent.execute_action(name, args)
            self.assertIn("x and y", str(ctx.exception))
            self.assertIn(name, str(ctx.exception))

    def test_candidates_without_a_model_say_why(self):
        """An empty model used to skip every candidate in silence, so the run
        died on 'all providers failed. Details:' with nothing after it."""
        cfg = {"provider": "gemini", "api_keys": {"gemini": "AIza" + "x" * 32},
               "models": {}, "models_available": {}}
        with patch("agent_screen.settings.load", side_effect=lambda: dict(cfg)):
            with self.assertRaises(AIError) as ctx:
                chat_with_fallback("gemini", "hi")
        self.assertIn("aucun modèle", str(ctx.exception))

    # ------------------------------------------------------------- web pages
    def test_web_pages_share_the_dom_helper(self):
        """The Settings page used $ without defining it, so it rendered empty
        (no key fields at all); $ now lives in the shared shell, before every
        page script."""
        for page in (server._home_page(), server._settings_page(), server._screen_page()):
            self.assertIn("const $ = id => document.getElementById(id);", page)
            self.assertLess(page.index("const $ = id"), page.index("<main>"),
                            "le helper doit etre defini avant le script de la page")

    def test_only_one_run_owns_the_mouse_across_app_and_page(self):
        """The desktop window and the local page share one mouse: whichever starts
        first wins and the page is refused with 409 — and the owner is freed again
        when that run ends (a real run, blocked inside its first model call)."""
        import json
        import threading
        import time
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer

        gate = threading.Event()

        def fake_chat(*_a, **_kw):
            gate.wait(15)
            return ('{"thought":"ok","actions":[],"done":true,"summary":"fini"}',
                    "gemini")

        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def _stop():
            gate.set()
            srv.shutdown()
            srv.server_close()

        self.addCleanup(_stop)

        def post(goal):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/run",
                data=json.dumps({"goal": goal}).encode(),
                headers={"Content-Type": "application/json"})
            try:
                r = urllib.request.urlopen(req, timeout=30)
                return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        with patch("agent_screen.agent.chat_with_fallback", side_effect=fake_chat), \
                patch("agent_screen.display.capture_for_model",
                      return_value=("IMG", 1.0)), \
                patch("agent_screen.display.interesting_windows", return_value=[]):
            first = threading.Thread(target=lambda: post("A"))
            first.start()
            for _ in range(60):
                if agent.active_run() is not None:
                    break
                time.sleep(0.1)
            self.assertIsNotNone(agent.active_run(), "le run doit posséder la souris")
            code, body = post("B")            # the page, while that run is live
            gate.set()
            first.join(30)
            self.assertIsNone(agent.active_run())   # freed when the run ended
            again = post("C")                       # and the page works again
        self.assertEqual(code, 409)
        self.assertIn("already in progress", body["error"])
        self.assertEqual(again[0], 200)

    def test_a_run_that_dies_still_frees_the_mouse(self):
        """A thread dying (KeyboardInterrupt, SystemExit) must not leave the mouse
        claimed: the run releases it in a finally, whatever happens."""
        run = agent.AgentRun("goal", "gemini", max_steps=2, emit=lambda *a, **k: None)
        with patch("agent_screen.display.capture_for_model",
                   side_effect=KeyboardInterrupt("ctrl-c")):
            with self.assertRaises(KeyboardInterrupt):
                run.run()
        self.assertIsNone(agent.active_run())
        with patch("agent_screen.agent.chat_with_fallback",
                   return_value=('{"actions":[],"done":true,"summary":"ok"}', "gemini")), \
                patch("agent_screen.display.capture_for_model", return_value=("IMG", 1.0)), \
                patch("agent_screen.display.interesting_windows", return_value=[]):
            res = agent.run_goal("again", "gemini", max_steps=1)
        # it ran at all: a still-claimed mouse would have raised RunBusy here (the
        # outcome is "error", since a 'done' with no action is refused by design)
        self.assertIn("outcome", res)
        self.assertIsNone(agent.active_run())

    def test_the_app_refuses_while_the_page_owns_the_mouse(self):
        """One owner, two surfaces: the window must not start a run while the local
        page holds one (this is what made two agents share one mouse)."""
        import tkinter as tk
        page_run = agent.AgentRun("page run", "gemini", emit=lambda *a, **k: None)
        agent.claim(page_run)
        root = tk.Tk()
        root.withdraw()
        app = gui.App(root)
        app.goal_entry.insert(0, "ouvre Brave")
        try:
            with patch("agent_screen.gui.AgentRun") as built:
                app._start_run()
            self.assertFalse(built.called, "aucun run ne doit être construit")
            self.assertEqual(app.status_lbl["text"], app._("busy"))
            self.assertIsNone(app.run)
        finally:
            agent.release(page_run)
            root.destroy()

    def test_a_dead_run_never_leaves_run_disabled(self):
        """A run thread that dies without emitting 'finished' used to leave the Run
        button disabled forever: the poller compares the window's handle with the
        one owner and restores the buttons."""
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        app = gui.App(root)
        app.run_btn.config(state="disabled")          # as _start_run leaves it
        app.stop_btn.config(state="normal")
        app.run = agent.AgentRun("ghost", "gemini", emit=lambda *a, **k: None)
        app._pump()                                   # one tick of the poller
        self.assertIsNone(app.run)
        self.assertEqual(str(app.run_btn["state"]), "normal")
        self.assertEqual(str(app.stop_btn["state"]), "disabled")
        root.destroy()

    def test_a_client_that_left_does_not_raise(self):
        """Reloading mid-run aborted the socket, so writing the response raised
        ConnectionAbortedError and the server spewed a traceback at the user."""
        class DeadSocket:
            def write(self, *_a):
                raise ConnectionAbortedError("[WinError 10053] abandonnee")

        handler = server.Handler.__new__(server.Handler)
        handler.wfile = DeadSocket()
        handler.send_response = handler.send_header = handler.end_headers = lambda *a, **k: None
        handler._send(200, "x")      # must not raise
        handler._json({"error": "boom"}, 409)

    def test_the_app_can_open_its_local_page(self):
        """The installer creates no shortcut for the local page, so the app's 🌐
        button is the only way in: it starts the page once and opens the browser;
        a second click must not try to bind the port again."""
        import tkinter as tk
        started, opened = [], []
        root = tk.Tk()
        root.withdraw()
        app = gui.App(root)
        with patch("agent_screen.gui.server.start",
                   side_effect=lambda: started.append(1) or object()), \
                patch("agent_screen.gui.webbrowser.open",
                      side_effect=lambda u: opened.append(u)):
            app._open_local_page()
            app._open_local_page()
        self.assertEqual(len(started), 1)
        self.assertEqual(opened, [f"http://{server.HOST}:{server.PORT}/"] * 2)

        app._web_starting = False
        with patch("agent_screen.gui.server.start", side_effect=OSError("port pris")), \
                patch("agent_screen.gui.webbrowser.open",
                      side_effect=lambda u: opened.append(u)):
            app._open_local_page()
        self.assertEqual(app.status_lbl["text"], app._("web_failed"))
        self.assertEqual(len(opened), 2)      # no browser on a port we do not own
        root.destroy()

    def test_goal_runner_shows_what_ran(self):
        """The page read a never-existing st.action/st.error: the user saw the
        thoughts and nothing about the commands executed on their PC."""
        page = server._home_page()
        self.assertIn("st.summary", page)
        self.assertIn("st.actions", page)
        self.assertNotIn("st.action ?", page)
        self.assertIn("res.error", page)   # an already-running/refused run must be told



if __name__ == "__main__":
    unittest.main()
