"""Mute the Mac's own speakers while the TV plays the sound.

ScreenCaptureKit taps audio before the output mixer, so muting the output device does
not affect what the TV receives. Without this the show plays twice, seconds apart.
"""
import subprocess


def _osascript(script):
    try:
        return subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def is_muted():
    return _osascript("output muted of (get volume settings)") == "true"


def set_muted(muted):
    _osascript("set volume with output muted" if muted else "set volume without output muted")


class MutedWhileCasting:
    """Context manager: mute on enter, restore the previous state on exit."""

    def __init__(self, enabled=True, log=lambda m: None):
        self.enabled, self.log = enabled, log
        self.was_muted = None

    def __enter__(self):
        if self.enabled:
            self.was_muted = is_muted()
            if not self.was_muted:
                set_muted(True)
                self.log("→ Mac speakers muted while casting (restored on exit)")
        return self

    def __exit__(self, *exc):
        if self.enabled and self.was_muted is False:
            set_muted(False)
        return False
