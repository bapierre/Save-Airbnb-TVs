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

The UI (`Sources/TVCastApp`) is a `MenuBarExtra` with a TV picker, a quality preset (Smooth
480p / Balanced 720p / Sharp 1080p), and Play, Resync and Stop.

If the picture keeps buffering, the Wi-Fi cannot carry the stream: pick a lower quality.
Smooth (480p, ~1.5 Mbps) survives weak or congested 2.4 GHz links that stall 720p.

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

## Signing and notarizing

Signing needs a paid Apple Developer membership and a **Developer ID Application**
certificate. This Mac has none yet (`security find-identity -v -p codesigning` shows zero).
To create one without full Xcode:

1. Keychain Access → Certificate Assistant → *Request a Certificate From a Certificate
   Authority* → "Saved to disk". This makes a `CertificateSigningRequest` file.
2. developer.apple.com/account → Certificates → **+** → **Developer ID Application** →
   upload the request → download the `.cer` → double-click to install it in your login
   keychain.
3. For notarization, create an app-specific password at appleid.apple.com (Sign-In and
   Security → App-Specific Passwords), then store it once:
   ```
   xcrun notarytool store-credentials tvcast-notary \
     --apple-id you@example.com --team-id TEAMID --password APP_SPECIFIC_PASSWORD
   ```

Then build and sign:

```bash
./make-app.sh release
IDENTITY="Developer ID Application: Your Name (TEAMID)" NOTARY_PROFILE=tvcast-notary ./sign.sh
```

`sign.sh` signs with the hardened runtime, submits to Apple's notary service, and staples
the ticket, so `TVCast.app` opens cleanly on any Mac. Omit `NOTARY_PROFILE` to sign only
(fine for your own machine). ffmpeg runs as a separate process, so the hardened runtime
does not require disabling library validation.

A free Apple account cannot make a Developer ID certificate. If you do not want to sign,
ship the app unsigned and tell users to right-click it and choose Open the first time.

## Remaining before distribution

- Bundle a **static ffmpeg** in `Contents/Resources/` so the app is fully self-contained
  (`make-app.sh` copies `$FFMPEG` if set; Homebrew's ffmpeg is not static).
- Code-sign and notarize the app.
- End-to-end cast validation from the app against the TV.

## Relationship to the Python tool

The repository root holds the original `tvcast`/`tvprobe` Python tools, which stay the
cross-platform reference and the place new TV hacks are prototyped. This Swift app is the
macOS-native product that reuses the same proven techniques.
