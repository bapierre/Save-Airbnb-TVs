# TV report: <brand> <model>

Copy this folder to `hacks/<brand>-<model>/` and fill every section. Fields marked
**(required)** must not be blank; write `unknown` plus why if you truly cannot find out.

## The TV

- **Brand and model (required):** as printed on the back label or in Settings > About.
- **Platform and version (required):** Android TV 9 / Tizen 4.0 / webOS 5 / Roku OS 12 /
  Fire OS 7 / Linux no-name. Where you found it.
- **Chipset, if visible:** often in `tvprobe` names, e.g. `Hi3751V350`, `MT9632`.
- **Year or firmware version:** if shown.
- **Built-in casting the TV advertises:** Miracast / "Screen mirroring" / AirPlay / Cast /
  none. Does opening it drop the TV off Wi-Fi? (Miracast mode usually does.)

## The network fingerprint (required)

Paste the full output of:

```
tvprobe --report --no-wifi
```

Do **not** paste `tvprobe --json`; it contains full MAC addresses and your own machine's
addresses.

```json
<paste here>
```

## What worked (required)

- **Transport that played a picture:** dlna / cast / roku / adb / browser / other.
- **Exact command(s), copy-pasted:**

```
<commands>
```

- **Sound:** yes via ScreenCaptureKit helper / yes via BlackHole / no / unknown.
- **Latency estimate:** e.g. "about 2 s".
- **How long it stayed stable:** e.g. "a 45 minute episode", "30 seconds then froze".
- **Anything the TV needed first:** home screen, a specific app open, developer mode,
  a remote press to wake up, a confirmation dialog.

## What did not work (required, keep it short)

One line per attempt: what you tried, what happened.

- `tvcast --quality 1080p`: TV showed a spinner then STOPPED after 5 s.
- ADB on 5555: connection refused.

## Your setup (required)

- **Mac model and macOS version:**
- **ffmpeg version:** `ffmpeg -version | head -1`
- **tvcast commit or version:** `git rev-parse --short HEAD`
- **Written with a coding agent?** yes / no. Which one, if yes.

## Files in this folder

What each file is and how to run it.

## Notes for maintainers

Anything that looks promotable into `tvcast` (a new launcher, a header the TV needed, a
codec setting), and anything you are unsure about.
