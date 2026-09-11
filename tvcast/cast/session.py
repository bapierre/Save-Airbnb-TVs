"""Pick the TV, start playback, keep it playing, tear down cleanly."""
import time
from dataclasses import dataclass

from .launcher import UpnpError


@dataclass(frozen=True)
class Target:
    ip: str
    name: str
    control_url: str


class SelectionError(Exception):
    pass


def select_target(renderers, to):
    if to:
        for r in renderers:
            if r.ip == to:
                return r
        raise SelectionError(
            f"no DLNA renderer answered at {to}. Is the TV on the same Wi-Fi and on its home "
            "screen (not in Miracast mode)?")
    if not renderers:
        raise SelectionError("no DLNA renderer found. Run `tvprobe` to see what is on the network.")
    if len(renderers) == 1:
        return renderers[0]
    listing = "\n".join(f"  {r.ip:15}  {r.name}" for r in renderers)
    raise SelectionError(f"several renderers found; pick one with --to IP:\n{listing}")


class Watcher:
    """Pure policy: given the TV state and the time, say whether to relaunch or give up."""

    def __init__(self, start_timeout=15.0, relaunch_window=30.0):
        self.start_timeout, self.relaunch_window = start_timeout, relaunch_window
        self.started_at = None
        self.seen_playing = False
        self.last_relaunch = None

    def tick(self, state, now):
        if self.started_at is None:
            self.started_at = now
        if state == "PLAYING":
            self.seen_playing = True
            return None
        if not self.seen_playing:
            return "timeout" if now - self.started_at > self.start_timeout else None
        if state == "STOPPED":
            if self.last_relaunch is None or now - self.last_relaunch > self.relaunch_window:
                self.last_relaunch = now
                self.seen_playing = False
                self.started_at = now
                return "relaunch"
        return None


class Session:
    def __init__(self, launcher, server, url, log, stop_event, sleep=time.sleep,
                 clock=time.monotonic, poll_interval=2.0):
        self.launcher, self.server, self.url, self.log = launcher, server, url, log
        self.stop_event, self.sleep, self.clock = stop_event, sleep, clock
        self.poll = poll_interval
        self.start_retries = 2  # TVs in standby or a screensaver need a remote press first
        # Callable returning a fresh launcher, used when the TV stops answering. Some TVs
        # restart their UPnP service on a new random port mid-session.
        self.rediscover = None
        self.unknown_streak = 0

    def _play(self):
        """Ask the TV to play; on an unreachable TV, re-discover it once and try again."""
        try:
            self.launcher.play(self.url)
            return True
        except UpnpError as e:
            if e.code is not None or not self._rediscover():
                self.log(f"TV refused the stream: {e}")
                return False
        try:
            self.launcher.play(self.url)
            return True
        except UpnpError as e:
            self.log(f"TV refused the stream after rediscovery: {e}")
            return False

    def _rediscover(self):
        if not self.rediscover:
            return False
        self.log("TV stopped answering; looking for it again…")
        new = self.rediscover()
        if not new:
            self.log("TV not found. Is it still on the Wi-Fi?")
            return False
        self.launcher = new
        self.log(f"TV found again at {getattr(new, 'control_url', '?')}")
        return True

    def run(self):
        """Returns the process exit code."""
        watcher = Watcher()
        if not self._play():
            self.server.stop()
            return 1
        code = 0
        last = None
        retries_left = self.start_retries
        while not self.stop_event.is_set():
            self.sleep(self.poll)
            if self.stop_event.is_set():
                break
            state = self.launcher.state()
            if state != last:
                self.log(f"TV: {state}")
                last = state
            self.unknown_streak = self.unknown_streak + 1 if state == "UNKNOWN" else 0
            if self.unknown_streak >= 3 and self._rediscover():
                self.unknown_streak = 0
                watcher = Watcher()
                self._play()
                continue
            action = watcher.tick(state, self.clock())
            if action == "timeout":
                if retries_left > 0:
                    retries_left -= 1
                    self.log(f"TV did not start playing. If it is asleep or on a screensaver, "
                             f"press a button on its remote. Retrying ({self.start_retries - retries_left}"
                             f"/{self.start_retries})…")
                    watcher = Watcher()
                    self._play()
                    continue
                self._explain_timeout(state)
                code = 1
                break
            if action == "relaunch":
                self.log("TV stopped; relaunching")
                self._play()
        try:
            self.launcher.stop()
        except UpnpError:
            pass
        self.server.stop()
        return code

    def _explain_timeout(self, state):
        seen = [r for r in self.server.requests if r["path"].startswith(self.server.path)]
        if not seen:
            self.log(f"TV never fetched {self.url} (last state {state}). The TV cannot reach "
                     "this Mac: check the macOS firewall, or the Wi-Fi may isolate clients.")
        else:
            methods = ", ".join(r["method"] for r in seen)
            self.log(f"TV fetched the stream ({methods}) but never reported PLAYING (last state "
                     f"{state}). It may not decode this format; try --quality 720p or --fps 25.")
