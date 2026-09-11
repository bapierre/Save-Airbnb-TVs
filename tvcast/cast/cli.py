"""tvcast: mirror this Mac's screen to a TV on the LAN."""
import argparse
import signal
import sys
import threading

from . import capture, discovery, ffmpeg as ff, macaudio, sckcap
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
        return None, ("video only: the ScreenCaptureKit helper is unavailable and no BlackHole "
                      "device exists. Run `xcode-select --install` for the helper, or install "
                      "BlackHole (`brew install blackhole-2ch`), or use --audio NAME")
    idx = ff.find_audio_device(devices, args.audio)
    if idx is None:
        names = ", ".join(n for _, n in devices["audio"]) or "none"
        raise SystemExit(f"no audio device matching '{args.audio}'. Available: {names}")
    return idx, f"audio device {idx} ({args.audio})"


def main(argv=None):
    p = argparse.ArgumentParser(prog="tvcast", description=__doc__)
    p.add_argument("--to", metavar="IP", help="TV address (skip auto-pick)")
    p.add_argument("--audio", default="auto",
                   help="auto | sck | none | substring of an audio device name (default auto: "
                        "the ScreenCaptureKit helper, else BlackHole, else video only)")
    p.add_argument("--quality", choices=sorted(QUALITY), default="720p")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--bitrate", default="3M",
                   help="video bitrate, also the burst cap (default 3M; try 2M on busy Wi-Fi)")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--timeout", type=float, default=4.0, help="SSDP discovery seconds")
    p.add_argument("--nudge", nargs="?", type=int, const=240, default=0, metavar="SECONDS",
                   help="experimental: every SECONDS (default 240) send a harmless DLNA command "
                        "to try to keep the TV awake. Prefer turning off the TV's screensaver.")
    p.add_argument("--keep-mac-audio", action="store_true",
                   help="do not mute the Mac's speakers while the TV plays the sound")
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

    w, h = QUALITY[args.quality]
    spec = ff.VideoSpec(width=w, height=h, fps=args.fps, bitrate=args.bitrate)
    factory = None
    streaming_audio = False
    if args.audio in ("auto", "sck"):
        helper = sckcap.ensure_helper(log)
        if helper:
            size = sckcap.fit_size(*sckcap.display_size(), w, h)
            factory = capture.make_sck_factory(ffmpeg, helper, spec, size)
            streaming_audio = True
        elif args.audio == "sck":
            log("the ScreenCaptureKit helper could not be built; see the messages above")
            return 2
    if factory is None:
        audio_idx, audio_desc = choose_audio(args, devices)
        log(f"→ {audio_desc}")
        factory = capture.make_avfoundation_factory(ffmpeg, screen, audio_idx, spec)
        streaming_audio = audio_idx is not None
    log(f"→ capture: {factory.description}")

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
    session = Session(DlnaLauncher(target.control_url), server, url, log, stop,
                      nudge_interval=args.nudge)

    def rediscover():
        found = [t for t in discovery.find_renderers(args.timeout) if t.ip == target.ip]
        return DlnaLauncher(found[0].control_url) if found else None

    session.rediscover = rediscover
    with macaudio.MutedWhileCasting(enabled=streaming_audio and not args.keep_mac_audio, log=log):
        return session.run()


if __name__ == "__main__":
    sys.exit(main())
