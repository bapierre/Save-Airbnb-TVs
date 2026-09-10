# tvcast MVP: mirror a Mac screen to an old smart TV

Date: 2026-09-10. Status: approved in conversation (approach "A growing into C").

## Problem

Travelers arrive at rentals with old smart TVs that lack AirPlay. Many of those TVs speak
DLNA, Google Cast, Roku ECP, or expose ADB, but nothing on a Mac turns "whatever this TV
speaks" into "my screen is on the TV" in one command. Miracast, the usual default on cheap
sets, cannot be sourced from macOS at all (no Wi-Fi Direct client mode).

A spike on 2026-09-10 proved the core path against a real "Weier" HiSilicon Hi3751 Android 9
TV: ffmpeg screen capture, hardware H.264 into MPEG-TS, served over HTTP from the Mac, pushed
to the TV with DLNA AVTransport `SetAVTransportURI` + `Play`. Latency was about 2 s. The TV
sent `HEAD` before playing and a ranged `GET` afterwards, and accepted a stream with no
`Content-Length` and no seeking.

## Goals

- `tvcast` mirrors the Mac screen (video, plus system audio when a source is available) to a
  DLNA renderer on the same LAN, picking the TV automatically when there is only one.
- `tvprobe` (existing discovery tool) keeps its interface, gains the fixes found on a real run,
  and becomes the discovery stage of `tvcast`.
- Stdlib-only Python. The only external runtime requirement is the `ffmpeg` binary
  (VideoToolbox encoder). Python 3.9 floor.
- Transports other than DLNA plug in later through one small interface without touching
  the capture or serving code.

## Non-goals (MVP)

- Cast, Roku, ADB, browser launchers. Slots exist; code does not.
- Sub-second latency. A few seconds is acceptable.
- Windows or Linux capture. Probe stays cross-platform; capture is macOS.
- DRM circumvention. FairPlay content in Safari captures black; that is expected.

## Architecture

One repository, one package `tvcast`, two console scripts.

```
tvcast/
  probe/        existing tvprobe modules (mdns, ssdp, hosts, wifi, verdict, cli) + fixes
  cast/
    ffmpeg.py   locate ffmpeg, list avfoundation devices, build the capture command
    server.py   threaded HTTP server that streams live MPEG-TS with DLNA headers
    launcher.py Launcher protocol + DlnaLauncher (SOAP client, play/stop/state)
    session.py  orchestrates capture → serve → launch → watch → teardown
    cli.py      argument parsing and output
  helpers/
    sckcap/     Swift ScreenCaptureKit helper (phase C), compiled on demand
tests/          fixture-driven unit tests, no network, no ffmpeg
```

Pipeline, each stage a module with one job:

1. **Probe** finds hosts and their transports (existing). `tvcast` calls it in-process and
   selects the target: `--to IP` wins; otherwise the single DLNA candidate; otherwise it lists
   candidates and exits with a hint.
2. **Capture** builds the ffmpeg argv: avfoundation screen input (index discovered from
   `-list_devices`), optional audio input, `h264_videotoolbox` + `aac`, MPEG-TS on stdout.
   Video is scaled to fit inside the chosen size and padded to 16:9. Low-latency flags:
   `-realtime 1 -g <fps> -bf 0 -muxdelay 0 -muxpreload 0`.
3. **Serve** answers `HEAD` with `200`, `Content-Type: video/mpeg`, DLNA
   `transferMode.dlna.org: Streaming` and `contentFeatures.dlna.org` headers, `Accept-Ranges: none`,
   `Connection: close`, no `Content-Length`. `GET` starts one ffmpeg per client and copies its
   stdout to the socket until either side closes. HTTP/1.0 framing (no chunked encoding).
4. **Launch** (`Launcher` protocol): `play(url, title)`, `stop()`, `state() -> str`.
   `DlnaLauncher` issues `Stop`, `SetAVTransportURI` with DIDL-Lite metadata (`videoItem`,
   `http-get:*:video/mpeg:...`), then `Play`. `state()` maps `GetTransportInfo` to
   `PLAYING | STOPPED | TRANSITIONING | PAUSED_PLAYBACK | UNKNOWN`.
5. **Watch** polls `state()` every 2 s. If it sees `STOPPED` after having seen `PLAYING`, it
   re-launches once per 30 s window. Ctrl-C stops the TV, shuts the server, kills ffmpeg.

## Audio

Source selection via `--audio {auto,none,<device name>}`.

- `auto` (default): use the ScreenCaptureKit helper if it can be built/run; else an
  avfoundation device whose name contains "BlackHole"; else video only, with one warning line.
- Named device: use that avfoundation audio device.
- `none`: video only.

### Phase C helper (`sckcap`)

A Swift program using ScreenCaptureKit that captures the display and system audio together
without a virtual audio driver. It emits fixed-rate NV12 raw video on stdout and interleaved
float32 48 kHz stereo PCM on a named pipe passed as an argument. ffmpeg reads both. SCK only
delivers frames on change, so the helper re-emits the last frame on a timer to keep a constant
frame rate. Compiled with `swiftc` into `~/Library/Caches/tvcast/` the first time it is
needed; if `swiftc` is missing the tool falls back to the avfoundation path. Requires macOS 13+
and Screen Recording permission (the same permission avfoundation capture needs).

## tvprobe fixes (from the real run)

- Ship as a package: `__init__.py`, `__main__.py`; drop the hardcoded sys.path in tests.
- Exclude multicast/broadcast addresses and the machine's own interface addresses from
  candidates (report own AirPlay receiver as "this Mac" instead).
- A stable MAC alone no longer makes a candidate; candidates need at least one transport or a
  TV-like name. The router stops ranking first.
- Ignore model strings with no letters (the "0,1,2" AirPlay artifact).
- Record DIAL from SSDP (`urn:dial-multiscreen-org:service:dial:1`) as a `dial` transport.
- macOS Wi-Fi scan: detect `<redacted>` SSIDs and explain that Location Services permission is
  required, instead of silently reporting nothing.

## Error handling

- ffmpeg missing: exit 2 with the brew command.
- No candidates / several candidates without `--to`: exit 1 with the list and the `--to` hint.
- SOAP error on `SetAVTransportURI`/`Play`: print the UPnP error code and body, exit 1.
- TV never reaches `PLAYING` within 15 s: print the last state and the requests the server
  saw (or that it saw none, which means the TV cannot reach the Mac: firewall or client
  isolation), exit 1.
- ffmpeg exits early: log its last stderr lines, close the client, and let watch re-launch.

## Testing

Unit tests, stdlib `unittest`, no network or ffmpeg:

- ffmpeg argv builder: device parsing from a captured `-list_devices` fixture, audio
  selection matrix, scale/pad filter string.
- server: `HEAD` and `GET` against a fake process object (a `BytesIO` stdout), header set,
  client disconnect kills the process.
- launcher: SOAP envelopes and DIDL-Lite against fixtures; `state()` mapping; error mapping
  from a UPnP fault body.
- session: target selection rules; watch loop re-launch policy with a scripted `state()`.
- probe fixes: multicast/own-IP exclusion, candidate ranking, DIAL classification,
  redacted SSID detection.

Manual acceptance (done against the Weier TV before calling the MVP finished): a show playing
in a browser on the Mac appears on the TV with sound, survives at least five minutes, and
Ctrl-C returns the TV to its home screen.
