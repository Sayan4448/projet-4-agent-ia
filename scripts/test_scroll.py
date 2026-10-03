"""Offline coverage of scrolling and of the "did the screen change?" check.
Real-window proof lives in scripts/smoke_scroll.py."""
import json
import unittest
from unittest.mock import Mock, patch

from agent_screen import agent, browser_mode, display, input_control

CELLS = display.FINE[0] * display.FINE[1]


def sample(changed_cells=0, delta=60):
    return tuple([delta] * changed_cells + [0] * (CELLS - changed_cells))


class ScreenChangeTests(unittest.TestCase):
    def test_a_typed_word_is_a_visible_change(self):
        """Measured on a real page: typing 'salut' moves ~50 cells out of
        130 000. The old screen-wide mean read 0.02 for it against a threshold
        of 6, so every typing was reported as ignored (then pasted twice)."""
        still = sample()
        self.assertTrue(agent._changed(still, sample(50)))      # a word
        self.assertTrue(agent._changed(still, sample(14)))      # one character
        self.assertFalse(agent._changed(still, still))
        self.assertFalse(agent._changed(still, sample(4)))      # caret blink
        self.assertFalse(agent._changed(still, sample(5000, delta=3)))  # jpeg noise
        self.assertTrue(agent._changed(still, ()))              # no sample: assume yes


class ScrollTests(unittest.TestCase):
    def setUp(self):
        input_control.reset_virtual_input()
        self.addCleanup(input_control.reset_virtual_input)

    def test_amounts_are_wheel_notches_whatever_the_model_meant(self):
        self.assertEqual(input_control.wheel_notches(-3), -3)
        self.assertEqual(input_control.wheel_notches("5"), 5)
        self.assertEqual(input_control.wheel_notches(-500), -5)     # pixels
        self.assertEqual(input_control.wheel_notches(99999), 20)    # bounded
        with self.assertRaises(ValueError):
            input_control.wheel_notches(0)

    def test_physical_scroll_sends_whole_notches_on_the_right_axis(self):
        """pyautogui.scroll(3) is 3/120 of a notch on Windows, and its hscroll
        scrolls vertically: neither moved anything."""
        sent = []

        def fake_send(_n, inp, _size):
            mi = inp._obj.mi
            sent.append((mi.dwFlags, ctypes_long(mi.mouseData)))
            return 1

        with patch.object(input_control.ctypes.windll.user32, "SendInput", side_effect=fake_send), \
                patch.object(input_control.pyautogui, "moveTo") as move:
            self.assertEqual(input_control.mouse_scroll(-3, 200, 100), {"scrolled": -3})
            self.assertEqual(input_control.mouse_hscroll(2), {"hscrolled": 2})
        move.assert_called_once_with(100, 200)
        self.assertEqual(sent, [(input_control.MOUSEEVENTF_WHEEL, -360),
                                (input_control.MOUSEEVENTF_HWHEEL, 240)])

    def test_virtual_scroll_without_coordinates_uses_the_active_window(self):
        """'mouse_scroll(amount=-3)' as first action raised 'Indique les
        coordonnées du curseur virtuel' although x,y are documented optional."""
        with patch.object(input_control, "_active_window_center", return_value=(500, 400)), \
                patch.object(input_control, "_point_target", return_value=(123, 10, 20)), \
                patch.object(input_control, "_post") as post:
            result = input_control.virtual_mouse_scroll(-3)
        post.assert_called_once_with(123, input_control.WM_MOUSEWHEEL,
                                     ((-360 & 0xffff) << 16), input_control._lparam(500, 400))
        self.assertEqual(result, {"virtual_scrolled": -3})

    def test_browser_scroll_happens_where_the_model_points(self):
        session = browser_mode.BrowserSession()
        session.context = Mock()
        page = Mock(url="https://example.com/", is_closed=Mock(return_value=False))
        session.context.pages = [page]
        session.size = (1000, 500)
        session.execute("mouse_scroll", {"amount": -3, "x": 500, "y": 500})
        page.mouse.move.assert_called_once_with(500.0, 250.0)
        page.mouse.wheel.assert_called_once_with(0, 300)

    def _run_one_scroll(self, fingerprints, **run_kw):
        run = agent.AgentRun("goal", "gemini", max_steps=1, step_delay=0,
                             memory_enabled=False, **run_kw)
        reply = json.dumps({"actions": [{"name": "mouse_scroll",
                                         "args": {"amount": -3, "x": 500, "y": 500}}]})
        with patch.object(run, "_shot", return_value="IMG"), \
                patch.object(run, "_windows_text", return_value=""), \
                patch.object(agent, "chat_with_fallback", return_value=(reply, "gemini")), \
                patch.object(agent.display, "screen_fingerprint", side_effect=fingerprints), \
                patch.object(agent, "_virtual_action",
                             return_value={"virtual_scrolled": -3}) as virtual, \
                patch.object(input_control, "transient_scroll",
                             return_value={"transient_scrolled": -3}) as transient:
            result = run.run()
        return result, virtual, transient

    def test_a_scroll_that_moved_nothing_says_so(self):
        """At the end of a list (or over a non-scrollable area) the model used to
        get a plain success and scroll again, forever."""
        still = sample()
        result, virtual, transient = self._run_one_scroll([still, still, still])
        virtual.assert_called_once()
        transient.assert_called_once()        # one discreet physical retry
        self.assertIn("Nothing moved", result["steps"][0]["summary"])

    def test_a_scroll_that_moved_is_a_plain_success(self):
        result, _virtual, transient = self._run_one_scroll([sample(), sample(9000)])
        transient.assert_not_called()
        self.assertNotIn("Nothing moved", result["steps"][0]["summary"])


def ctypes_long(value):
    """mouseData is an unsigned DWORD carrying a signed wheel delta."""
    return value - (1 << 32) if value >= (1 << 31) else value


if __name__ == "__main__":
    unittest.main()
