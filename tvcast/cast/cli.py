"""tvcast: mirror this Mac's screen to a TV on the LAN."""
import argparse
import signal
import sys
import threading

from . import capture, discovery, ffmpeg as ff
from .launcher import DlnaLauncher
from .server import StreamServer
from .session import SelectionError, Session, select_target

QUALITY = {"720p": (1280, 720), "1080p": (1920, 1080)}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def choose_audio(args, devices):
    """Return (audio_index_or_None, description) for the avfoundation path."""
    if args.audio == "none":
        return None, "video only (--audio none)"
    if args.audio == "auto":
        idx = ff.find_audio_device(devices, "blackhole")
        if idx is not None:
            return idx, f"audio from BlackHole device {idx}"
        return None, ("video only: no BlackHole audio device found. Install one with "
                      "`brew install blackhole-2ch` and set it as the output, or use --audio NAME")
    idx = ff.find_audio_device(devices, args.audio)
    if idx is None:
        names = ", ".join(n for _, n in devices["audio"]) or "none"
        raise SystemExit(f"no audio device matching '{args.audio}'. Available: {names}")
    return idx, f"audio device {idx} ({args.audio})"


def main(argv=None):
    p = argparse.ArgumentParser(prog="tvcast", description=__doc__)
    p.add_argument("--to", metavar="IP", help="TV address (skip auto-pick)")
    p.add_argument("--audio", default="auto",
                   help="auto | none | substring of an audio device name (default auto)")
    p.add_argument("--quality", choices=sorted(QUALITY), default="720p")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--bitrate", default="4M")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--timeout", type=float, default=4.0, help="SSDP discovery seconds")
    p.add_argument("--list-devices", action="store_true", help="show capture devices and exit")
    args = p.parse_args(argv)

    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg:
        log(ff.INSTALL_HINT)
        return 2
    devices = ff.list_devices(ffmpeg)
    if args.list_devices:
        for kind in ("video", "audio"):
            print(f"{kind}:")
            for idx, name in devices[kind]:
                print(f"  [{idx}] {name}")
        return 0
    screen = ff.screen_index(devices)
    if screen is None:
        log("ffmpeg lists no 'Capture screen' device. Grant Screen Recording permission to your "
            "terminal in System Settings > Privacy & Security, then retry.")
        return 2

    log(f"→ looking for DLNA renderers ({args.timeout:.0f}s)…")
    try:
        target = select_target(discovery.find_renderers(args.timeout), args.to)
    except SelectionError as e:
        log(str(e))
        return 1
    log(f"→ target: {target.name} at {target.ip}")

    audio_idx, audio_desc = choose_audio(args, devices)
    log(f"→ {audio_desc}")
    w, h = QUALITY[args.quality]
    spec = ff.VideoSpec(width=w, height=h, fps=args.fps, bitrate=args.bitrate)
    factory = capture.make_avfoundation_factory(ffmpeg, screen, audio_idx, spec)

    server = StreamServer(factory, port=args.port, log=lambda m: log(f"  http: {m}"))
    try:
        port = server.start()
    except OSError as e:
        log(f"cannot listen on port {args.port}: {e}. Try --port 0 for any free port.")
        return 2
    url = f"http://{discovery.local_ip_for(target.ip)}:{port}{server.path}"
    log(f"→ serving {url}")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    log("→ asking the TV to play (Ctrl-C to stop)")
    session = Session(DlnaLauncher(target.control_url), server, url, log, stop)
    return session.run()


if __name__ == "__main__":
    sys.exit(main())
