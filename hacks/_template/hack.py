"""Starting point for a TV-specific hack.

Reuse the core building blocks instead of rewriting them: capture and serving already
work, so a hack usually only needs a new way to tell the TV to play the URL.

Run from the repo root:  python3 hacks/<brand>-<model>/hack.py --to 192.168.1.42
"""
import argparse
import signal
import sys
import threading

sys.path.insert(0, __file__.rsplit("/hacks/", 1)[0])  # make `tvcast` importable

from tvcast.cast import capture, discovery, ffmpeg as ff, sckcap  # noqa: E402
from tvcast.cast.server import StreamServer  # noqa: E402
from tvcast.cast.session import Session  # noqa: E402


class MyLauncher:
    """Implement these three methods for your TV. See tvcast/cast/launcher.py for DLNA."""

    name = "mytv"

    def __init__(self, ip):
        self.ip = ip

    def play(self, url, title="Mac screen"):
        raise NotImplementedError("tell the TV to play `url`")

    def stop(self):
        pass

    def state(self):
        return "PLAYING"  # or STOPPED / TRANSITIONING / UNKNOWN if you can ask the TV


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True, help="TV address")
    p.add_argument("--port", type=int, default=8090)
    args = p.parse_args()

    ffmpeg = ff.find_ffmpeg() or sys.exit(ff.INSTALL_HINT)
    spec = ff.VideoSpec()
    helper = sckcap.ensure_helper(print)
    if helper:
        size = sckcap.fit_size(*sckcap.display_size(), spec.width, spec.height)
        factory = capture.make_sck_factory(ffmpeg, helper, spec, size)
    else:
        devices = ff.list_devices(ffmpeg)
        factory = capture.make_avfoundation_factory(ffmpeg, ff.screen_index(devices), None, spec)

    server = StreamServer(factory, port=args.port, log=lambda m: print("  http:", m))
    port = server.start()
    url = f"http://{discovery.local_ip_for(args.to)}:{port}{server.path}"
    print("serving", url)

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    return Session(MyLauncher(args.to), server, url, print, stop).run()


if __name__ == "__main__":
    sys.exit(main())
