# TVCast.app (native macOS menu-bar app)

A pure-Swift port of the `tvcast` engine with a menu-bar UI. No Python at runtime; it needs
only an `ffmpeg` binary (located on the system for now; bundling a static one is a to-do).

## What works

The engine is built and tested in five layers, all verified against a real HiSilicon TV or
locally:

- **Discovery** — SSDP + UPnP description parsing (`SSDP.swift`).
- **DLNA control** — AVTransport play/stop/state/nudge (`Launcher.swift`).
- **HTTP streaming** — live MPEG-TS server with the DLNA headers TVs need (`HTTPServer.swift`).
- **Session** — watch, relaunch, resync, nudge, re-discover (`Session.swift`).
- **Capture** — ScreenCaptureKit video + system audio into ffmpeg, as a stream source
  (`Capture.swift`, helper in `Sources/sckcap`).

The UI (`Sources/TVCastApp`) is a `MenuBarExtra` with a TV picker and Play, Resync and Stop.

## Build and run

```bash
cd macapp
swift run tvcast-selftest         # engine unit checks (no Xcode needed)
./make-app.sh release             # assemble TVCast.app
open TVCast.app                   # a TV icon appears in the menu bar
```

A TV icon appears in the menu bar. Pick your TV, press Play. macOS will ask for Screen
Recording permission the first time. Resync drops the accumulated delay (e.g. between
episodes); Stop returns the TV to its home screen.

The dev CLI mirrors the engine for testing against a TV:

```bash
swift run tvcast-native discover          # list DLNA TVs
swift run tvcast-native state             # read the TV's transport state
swift run tvcast-native capture 6 out.ts  # capture 6s to a file (no TV)
```

## Remaining before distribution

- Bundle a **static ffmpeg** in `Contents/Resources/` so the app is fully self-contained
  (`make-app.sh` copies `$FFMPEG` if set; Homebrew's ffmpeg is not static).
- Code-sign and notarize the app.
- End-to-end cast validation from the app against the TV.

## Relationship to the Python tool

The repository root holds the original `tvcast`/`tvprobe` Python tools, which stay the
cross-platform reference and the place new TV hacks are prototyped. This Swift app is the
macOS-native product that reuses the same proven techniques.
