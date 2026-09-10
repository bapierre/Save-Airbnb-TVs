# Instructions for coding agents

You are helping someone make the TV in their rental play their Mac screen. Read this
before touching anything. `CONTRIBUTING.md` has the human version of the same rules.

## What this repo is

- `tvcast/probe/`: finds TVs on the LAN and reports what they speak (`tvprobe`).
- `tvcast/cast/`: captures the Mac screen and audio, serves it as live MPEG-TS over
  HTTP, and tells the TV to play the URL (`tvcast`). DLNA is the shipped launcher.
- `hacks/<brand>-<model>/`: per-TV experiments with a mandatory `REPORT.md`.
- `tests/`: stdlib `unittest`, no network, no ffmpeg. Run:
  `python3 -m unittest discover -s tests -t . -v`

## Facts you should not rediscover

- macOS cannot send Miracast. There is no Wi-Fi Direct client mode. Do not try.
- Old TVs cannot accept a pushed stream; they can fetch a URL. That is the whole trick.
- Real TVs send `HEAD` before `GET`, want `transferMode.dlna.org: Streaming`, tolerate
  `Accept-Ranges: none`, and give up if the first byte takes more than about a second.
- A TV in standby or a screensaver accepts a URL and then reports STOPPED for anything.
  Have the human press a button on the remote before you debug the stream.
- DRM video (Netflix in Safari) captures black. That is not a bug you can fix.

## When working on a hack for a new TV

1. Copy `hacks/_template/` to `hacks/<brand>-<model>/` (lowercase, dashes).
2. Run `tvprobe --report --no-wifi` and put the output in `REPORT.md` first, before
   writing code. Use `--report`, never `--json`: `--json` contains full MAC addresses.
3. Reuse `tvcast.cast.capture`, `tvcast.cast.server` and `tvcast.cast.session`.
   Usually the only new code is a launcher with `play(url, title)`, `stop()`, `state()`.
   `hacks/_template/hack.py` shows the wiring.
4. Fill **every required field** in `REPORT.md`. Ask the human for the ones you cannot
   observe (brand on the label, what the TV screen showed, whether sound came out).
   Do not invent values. Write `unknown` and why if you must.
5. Record what failed too, one line each. Failed attempts are data.
6. Add a row to `hacks/README.md`.

## When changing `tvcast/`

- Standard library only. No `pip install` anything. ffmpeg is the only binary.
- Python 3.9 syntax. No `match`, no `X | Y` type unions, no `list[str]` at runtime
  outside annotations.
- Write the failing test first, then the code. Fakes and fixtures, like the existing
  tests; never hit the network or spawn ffmpeg in tests.
- Keep the separation: `ffmpeg.py` builds argv, `capture.py` runs processes,
  `server.py` serves bytes, `launcher.py` talks to TVs, `session.py` decides what to do,
  `cli.py` parses flags. Do not merge these.
- A new transport is a new launcher class plus its tests, plus a one-line entry in
  the README's roadmap or tested-TV table.

## Privacy rules (hard)

Never commit, paste into an issue, or leave in a report:

- Full MAC addresses. Mask as `aa:bb:cc:xx:xx:xx`. CI rejects unmasked ones.
- Wi-Fi network names or passwords.
- Hostnames, usernames, `/Users/<name>` paths, email addresses.

Private LAN addresses like `192.168.1.42` are fine.

## Before you say you are done

- The suite passes.
- `git grep -nE '([0-9a-f]{2}:){5}[0-9a-f]{2}'` shows only masked or fictional values.
- The report answers: which TV, what worked, exact commands, sound, latency, stability,
  what failed, what setup. If any of those is missing, you are not done.
- Tell the human, in plain words, what you verified on the real TV and what you did not.
