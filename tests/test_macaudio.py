import unittest
from unittest import mock

from tvcast.cast import macaudio


class TestMutedWhileCasting(unittest.TestCase):
    def run_with(self, initially_muted, enabled=True):
        calls = []

        def fake(script):
            calls.append(script)
            if "get volume settings" in script:
                return "true" if initially_muted else "false"
            return ""

        with mock.patch.object(macaudio, "_osascript", side_effect=fake):
            with macaudio.MutedWhileCasting(enabled=enabled):
                pass
        return calls

    def test_mutes_then_restores_when_it_was_unmuted(self):
        calls = self.run_with(initially_muted=False)
        self.assertIn("set volume with output muted", calls)
        self.assertEqual(calls[-1], "set volume without output muted")

    def test_leaves_alone_when_already_muted(self):
        calls = self.run_with(initially_muted=True)
        self.assertFalse(any(c.startswith("set volume") for c in calls))

    def test_disabled_touches_nothing(self):
        self.assertEqual(self.run_with(initially_muted=False, enabled=False), [])


if __name__ == "__main__":
    unittest.main()
