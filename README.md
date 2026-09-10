# tvcast

Mirror your Mac screen, with sound, to the old smart TV in your rental.

You arrive at an Airbnb. The TV says "screen mirroring" but it means Miracast, which a
Mac cannot speak. AirPlay is nowhere. `tvcast` finds out what the TV *does* speak on the
Wi-Fi and streams your screen to it in one command.

```
$ tvcast
→ looking for DLNA renderers (4s)…
→ target: HiDPTAndroid Hi3751V350_DMR at 192.168.1.42
→ capture: ScreenCaptureKit 1108x720 with system audio
→ serving http://192.168.1.10:8090/screen.ts
→ asking the TV to play (Ctrl-C to stop)
TV: PLAYING
```

Two commands ship in this package:

| Command | What it does |
|---|---|
| `tvprobe` | Scans the network and reports what each TV-looking device speaks: DLNA, Google Cast, AirPlay, Roku, Samsung, ADB, DIAL, plus Wi-Fi Direct groups. |
| `tvcast` | Captures the screen and system audio, serves it as a live MPEG-TS stream, and tells the TV to play it. DLNA today; more transports on the roadmap. |

## Install

Requirements: macOS 13 or newer, Python 3.9 or newer, and ffmpeg.

```bash
brew install ffmpeg
git clone https://github.com/bapierre/Save-Airbnb-TVs.git
cd Save-Airbnb-TVs
pip install -e .          # or run without installing: python3 -m tvcast.cast
```

The first `tvcast` run compiles a small Swift helper for audio capture. That needs the
Xcode Command Line Tools (`xcode-select --install`). Without them tvcast still works,
either video only or with audio through a BlackHole loopback device.

macOS will ask for **Screen Recording** permission for your terminal the first time.
Grant it in System Settings, Privacy & Security, then run the command again.

## Quick start

1. Put the TV on the same Wi-Fi as your Mac (Settings, Network on the TV) and leave it on
   its home screen. Do not open its Miracast or "screen mirroring" mode: that shuts the
   TV's Wi-Fi off to become a Wi-Fi Direct receiver.
2. Run `tvprobe` to see what the TV speaks. If it lists `dlna`, you are good.
3. Run `tvcast`. Play your show in a browser. Press Ctrl-C to stop; the TV returns to
   its home screen.

```
tvcast                          # auto-pick the only DLNA TV on the network
tvcast --to 192.168.1.42        # several TVs, or discovery is flaky
tvcast --quality 1080p          # default is 720p
tvcast --audio none             # video only
tvcast --audio "BlackHole"      # use a loopback audio device instead of the helper
tvcast --keep-mac-audio         # do not mute the Mac's speakers while casting
tvcast --list-devices           # show what ffmpeg can capture
```

While sound is streaming to the TV, tvcast mutes the Mac's own speakers so the show does
not play twice a few seconds apart, and unmutes them when you stop.

Expect two to three seconds of delay between your screen and the TV. That is fine for
shows and useless for games.

## How it works

Old smart TVs cannot accept a screen stream pushed at them, but almost all of them can
*fetch and play a video from a URL*. tvcast exploits that:

1. **Probe.** SSDP finds UPnP MediaRenderers and reads their description XML. A device
   only counts if it exposes an AVTransport service, which is what lets us hand it a URL.
   Routers answer SSDP too; they do not play video.
2. **Capture.** A ScreenCaptureKit helper grabs the display and the system audio mix
   (no virtual audio driver) and feeds ffmpeg, which encodes with the hardware
   VideoToolbox H.264 encoder and AAC into MPEG-TS.
3. **Serve.** A tiny HTTP server on the Mac streams the MPEG-TS. It answers the TV's
   `HEAD` request and sends the DLNA transfer headers real TVs insist on.
4. **Launch.** A DLNA `SetAVTransportURI` plus `Play` tells the TV to fetch the stream.
5. **Watch.** tvcast polls the TV and relaunches if playback drops. Ctrl-C stops the TV,
   the server, and the capture.

### Things you should know

**macOS cannot send Miracast.** Not with any library, not ever: Miracast rides on Wi-Fi
Direct and macOS exposes no Wi-Fi Direct client or group-owner mode to user space. Apps
that advertise "Miracast for Mac" use DLNA, AirPlay or Google Cast underneath. The good
news: nearly every Miracast TV also speaks DLNA once it is on normal Wi-Fi.

**DRM video captures black.** Netflix, Disney+ and friends in Safari use FairPlay, which
blanks screen capture. In Chrome most services capture fine at 720p. YouTube, Plex,
Jellyfin, browsers and local players all work.

**A sleeping TV will not play.** If the TV is in standby or on a screensaver, its player
accepts the URL and then stops. tvcast retries a few times and tells you to press a
button on the remote.

**Wi-Fi Direct scan on modern macOS.** `tvprobe` looks for `DIRECT-*` networks, but since
macOS 14 the OS hides Wi-Fi names from programs without Location Services permission.
tvprobe says so instead of pretending nothing is there. The name is on the TV's
mirroring screen anyway.

## Troubleshooting

| Symptom | What it means |
|---|---|
| `no DLNA renderer found` | The TV is not on this Wi-Fi, or is in Miracast mode, or has no DLNA renderer (stock Android TV does not). Run `tvprobe` to see what is there. |
| `TV never fetched http://…` | The TV cannot reach your Mac. Check the macOS firewall (allow incoming for python or ffmpeg), or the Wi-Fi may isolate clients from each other. |
| `TV fetched the stream … but never reported PLAYING` | The TV is asleep, on a screensaver, or cannot decode the stream. Press a button on the remote. If that is not it, try `--fps 25` or `--bitrate 2M`. |
| `ffmpeg lists no 'Capture screen' device` | Screen Recording permission is missing for your terminal app. |
| No sound on the TV | The helper did not build (see the messages at startup), so tvcast fell back to video only. Install the Command Line Tools, or install BlackHole and use `--audio BlackHole`. |
| The TV shows a black screen | You are playing DRM content in Safari. Use Chrome, or a non-DRM source. |

## tvprobe

```
tvprobe                        # scan the current subnet
tvprobe --sweep                # ping every address (slower, finds sleeping devices)
tvprobe -n 192.168.1.0/24      # scan a specific subnet
tvprobe --vendor               # look up MAC vendors online
tvprobe --json                 # machine-readable output
tvprobe --no-wifi              # skip the Wi-Fi Direct scan (slow on macOS)
```

| Probe | Looking for |
|---|---|
| mDNS / DNS-SD | Google Cast, AirPlay, RAOP, Android TV remote, Fire TV, Vizio |
| SSDP + description XML | DLNA renderers, and specifically whether **AVTransport** exists; DIAL |
| TCP ports | ADB (5555), Cast (8008/8009), Roku ECP (8060), AirPlay (7000), Samsung (8001) |
| HTTP fingerprints | Device name, model and OS from Cast, Roku, Samsung and AirPlay endpoints |
| ARP | MAC addresses, and whether they are randomized (phones and laptops, not TVs) |
| Wi-Fi scan | `DIRECT-*` groups, meaning an active Miracast sink |

## Tested TVs

| TV | Platform | Transport | Result |
|---|---|---|---|
| "Weier" no-name set, HiSilicon Hi3751V350 | Android 9, stagefright player | DLNA | Works with sound. About 2 s latency. Only speaks DLNA (no ADB, Cast or DIAL). Its player gives up if the first byte takes more than a second or two. |

Add yours with a pull request.

## Roadmap

- Google Cast launcher (default media receiver with the same stream)
- Roku ECP launcher
- ADB launcher for Android TVs with debugging enabled (push VLC, fire an intent)
- TV web browser fallback: an HLS page you type into the TV's browser
- DIAL: launch the TV's own YouTube app with a video
- Linux capture (PipeWire) so the probe and cast both run on Linux

## Development

```bash
python3 -m unittest discover -s tests -t . -v
```

Stdlib only, no third-party Python packages. Tests need neither the network nor ffmpeg.

## Licence

MIT.
