import threading
import unittest

from tvcast.cast.launcher import UpnpError
from tvcast.cast.session import Target, SelectionError, select_target, Watcher, Session

A = Target("192.168.0.115", "HiDPTAndroid", "http://192.168.0.115:25826/c")
B = Target("192.168.0.50", "Other", "http://192.168.0.50:1/c")


class TestSelect(unittest.TestCase):
    def test_single_renderer_is_chosen(self):
        self.assertEqual(select_target([A], None), A)

    def test_to_picks_by_ip(self):
        self.assertEqual(select_target([A, B], "192.168.0.50"), B)

    def test_multiple_without_to_raises_listing_them(self):
        with self.assertRaises(SelectionError) as ctx:
            select_target([A, B], None)
        self.assertIn("192.168.0.115", str(ctx.exception))
        self.assertIn("--to", str(ctx.exception))

    def test_none_raises(self):
        with self.assertRaises(SelectionError):
            select_target([], None)

    def test_to_not_found_raises(self):
        with self.assertRaises(SelectionError):
            select_target([A], "10.0.0.1")


class TestWatcher(unittest.TestCase):
    def test_timeout_if_never_playing(self):
        w = Watcher(start_timeout=15)
        self.assertIsNone(w.tick("TRANSITIONING", 0))
        self.assertIsNone(w.tick("STOPPED", 10))
        self.assertEqual(w.tick("STOPPED", 16), "timeout")

    def test_relaunch_once_per_window_after_playing(self):
        w = Watcher(start_timeout=15, relaunch_window=30)
        self.assertIsNone(w.tick("PLAYING", 1))
        self.assertEqual(w.tick("STOPPED", 60), "relaunch")
        self.assertIsNone(w.tick("STOPPED", 70))       # inside window: no second relaunch
        self.assertIsNone(w.tick("PLAYING", 75))
        self.assertEqual(w.tick("STOPPED", 100), "relaunch")

    def test_relaunch_that_never_plays_times_out(self):
        w = Watcher(start_timeout=15, relaunch_window=30)
        w.tick("PLAYING", 1)
        self.assertEqual(w.tick("STOPPED", 60), "relaunch")
        self.assertIsNone(w.tick("STOPPED", 70))
        self.assertEqual(w.tick("STOPPED", 80), "timeout")

    def test_unknown_state_is_tolerated_while_playing(self):
        w = Watcher()
        w.tick("PLAYING", 1)
        self.assertIsNone(w.tick("UNKNOWN", 50))
        self.assertIsNone(w.tick("PLAYING", 52))


class FakeLauncher:
    def __init__(self, states, fail_play=False):
        self.states = list(states)
        self.calls = []
        self.nudge_calls = []
        self.fail_play = fail_play

    def play(self, url, title="Mac screen"):
        self.calls.append(("play", url))
        if self.fail_play:
            raise UpnpError(716, "Resource not found")

    def stop(self):
        self.calls.append(("stop",))

    def state(self):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def position(self):
        return "00:00:01"

    def nudge(self):
        self.nudge_calls.append(1)


class FakeServer:
    path = "/screen.ts"

    def __init__(self, requests=()):
        self.requests = list(requests)
        self.stopped = False

    def stop(self):
        self.stopped = True


class TestSession(unittest.TestCase):
    def make(self, launcher, server, stop, clock_step=2, sleep=None, logs=None):
        clock = iter(range(0, 100000, clock_step))
        return Session(launcher, server, "http://m/screen.ts",
                       log=(logs.append if logs is not None else lambda *_: None),
                       stop_event=stop, sleep=sleep or (lambda _: None), clock=lambda: next(clock))

    def test_session_plays_polls_and_stops_on_event(self):
        launcher = FakeLauncher(["TRANSITIONING", "PLAYING", "PLAYING"])
        stop = threading.Event()
        polls = []

        def sleep(_):
            polls.append(1)
            if len(polls) >= 3:
                stop.set()

        server = FakeServer()
        s = self.make(launcher, server, stop, sleep=sleep)
        self.assertEqual(s.run(), 0)
        self.assertEqual(launcher.calls[0], ("play", "http://m/screen.ts"))
        self.assertEqual(launcher.calls[-1], ("stop",))
        self.assertTrue(server.stopped)

    def test_session_times_out_when_tv_never_fetches(self):
        launcher = FakeLauncher(["STOPPED"])
        logs = []
        s = self.make(launcher, FakeServer(), threading.Event(), clock_step=5, logs=logs)
        self.assertEqual(s.run(), 1)
        self.assertTrue(any("never fetched" in m for m in logs))

    def test_session_times_out_when_tv_fetched_but_never_played(self):
        launcher = FakeLauncher(["STOPPED"])
        logs = []
        server = FakeServer(requests=[{"method": "HEAD", "path": "/screen.ts"},
                                      {"method": "GET", "path": "/screen.ts"}])
        s = self.make(launcher, server, threading.Event(), clock_step=5, logs=logs)
        self.assertEqual(s.run(), 1)
        self.assertTrue(any("HEAD, GET" in m for m in logs))

    def test_start_timeout_retries_before_giving_up(self):
        launcher = FakeLauncher(["STOPPED"])
        logs = []
        s = self.make(launcher, FakeServer(), threading.Event(), clock_step=5, logs=logs)
        s.start_retries = 2
        self.assertEqual(s.run(), 1)
        plays = [c for c in launcher.calls if c[0] == "play"]
        self.assertEqual(len(plays), 3)  # initial + 2 retries
        self.assertTrue(any("remote" in m for m in logs))

    def test_retry_succeeds_when_tv_wakes_up(self):
        launcher = FakeLauncher(["STOPPED", "STOPPED", "STOPPED", "STOPPED", "PLAYING"])
        stop = threading.Event()
        polls = []

        def sleep(_):
            polls.append(1)
            if len(polls) >= 8:
                stop.set()

        s = self.make(launcher, FakeServer(), stop, clock_step=5, sleep=sleep)
        s.start_retries = 2
        self.assertEqual(s.run(), 0)

    def test_unreachable_tv_triggers_rediscovery(self):
        class Unreachable(FakeLauncher):
            def play(self, url, title="Mac screen"):
                self.calls.append(("play", url))
                raise UpnpError(None, "cannot reach")

            def state(self):
                return "UNKNOWN"

        old = Unreachable(["UNKNOWN"])
        new = FakeLauncher(["PLAYING"])
        stop = threading.Event()
        polls = []

        def sleep(_):
            polls.append(1)
            if len(polls) >= 12:
                stop.set()

        s = self.make(old, FakeServer(), stop, clock_step=5, sleep=sleep)
        s.rediscover = lambda: new
        s.start_retries = 0
        # initial play on the old launcher fails as unreachable -> rediscover -> play on new
        self.assertEqual(s.run(), 0)
        self.assertEqual(old.calls[0], ("play", "http://m/screen.ts"))
        self.assertEqual(new.calls[0], ("play", "http://m/screen.ts"))
        self.assertEqual(new.calls[-1], ("stop",))

    def test_unknown_state_while_playing_rediscovers(self):
        old = FakeLauncher(["PLAYING", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"])
        new = FakeLauncher(["PLAYING"])
        stop = threading.Event()
        polls = []

        def sleep(_):
            polls.append(1)
            if len(polls) >= 10:
                stop.set()

        s = self.make(old, FakeServer(), stop, clock_step=5, sleep=sleep)
        s.rediscover = lambda: new
        self.assertEqual(s.run(), 0)
        self.assertEqual(new.calls[0], ("play", "http://m/screen.ts"))

    def test_nudge_fires_while_playing_when_enabled(self):
        launcher = FakeLauncher(["PLAYING"])
        stop = threading.Event()
        polls = []

        def sleep(_):
            polls.append(1)
            if len(polls) >= 8:
                stop.set()

        s = self.make(launcher, FakeServer(), stop, clock_step=5, sleep=sleep)
        s.nudge_interval = 12
        s.run()
        self.assertGreaterEqual(len(launcher.nudge_calls), 1)

    def test_no_nudge_by_default(self):
        launcher = FakeLauncher(["PLAYING"])
        stop = threading.Event()
        polls = []

        def sleep(_):
            polls.append(1)
            if len(polls) >= 6:
                stop.set()

        s = self.make(launcher, FakeServer(), stop, clock_step=5, sleep=sleep)
        s.run()
        self.assertEqual(launcher.nudge_calls, [])

    def test_play_failure_exits_1(self):
        launcher = FakeLauncher(["STOPPED"], fail_play=True)
        logs = []
        s = self.make(launcher, FakeServer(), threading.Event(), logs=logs)
        self.assertEqual(s.run(), 1)
        self.assertTrue(any("716" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
