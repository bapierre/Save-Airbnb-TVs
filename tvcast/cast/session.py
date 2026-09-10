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

    def run(self):
        """Returns the process exit code."""
        watcher = Watcher()
        try:
            self.launcher.play(self.url)
        except UpnpError as e:
            self.log(f"TV refused the stream: {e}")
            self.server.stop()
            return 1
        code = 0
        last = None
        while not self.stop_event.is_set():
            self.sleep(self.poll)
            if self.stop_event.is_set():
                break
            state = self.launcher.state()
            if state != last:
                self.log(f"TV: {state}")
                last = state
            action = watcher.tick(state, self.clock())
            if action == "timeout":
                self._explain_timeout(state)
                code = 1
                break
            if action == "relaunch":
                self.log("TV stopped; relaunching")
                try:
                    self.launcher.play(self.url)
                except UpnpError as e:
                    self.log(f"relaunch failed: {e}")
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
