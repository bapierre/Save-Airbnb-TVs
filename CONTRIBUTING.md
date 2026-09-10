# Contributing

This project lives or dies on TV reports. Every rental has a different TV, and the only
way to support them is for people who stand in front of one to tell us exactly what it is
and what worked. Code without a report is a guess. A report without code is still
valuable.

Vibecoding is welcome. Point your favourite coding agent at the TV in your rental, hack
until it plays, and send us the result. What we ask in return is that the result is
**reproducible by someone who has never seen your TV**. That means the report below, in
full, every time.

## The one rule

**A hack is not a contribution until it has a complete `REPORT.md`.**

Incomplete reports are closed without review. Not because we're strict for fun, but
because a hack we cannot reproduce cannot be promoted into `tvcast`, and this repo would
fill up with folders nobody can use.

## What a TV report must contain

Use the template in `hacks/_template/REPORT.md`. Every field marked required must be
filled in. In short:

| Field | Why we need it |
|---|---|
| Brand and model as printed on the TV or its settings screen | Other travelers search by this. |
| Platform: Android TV / Tizen / webOS / Roku / Fire OS / Linux no-name, and its version | Decides which launcher path applies. |
| `tvprobe --report` output, pasted verbatim | The comparable, sanitized fingerprint. Never paste `--json`; it contains full MACs. |
| Which transport ended up working, and which ones did not | The whole point. |
| The exact command(s) that produced a playing picture | Reproducibility. |
| Whether sound worked, and how | Half the bugs live here. |
| Latency estimate and how long it stayed stable | Separates "flashed once" from "watched an episode". |
| Mac model and macOS version, ffmpeg version | Capture and encoder behaviour differ. |
| What you tried that failed, briefly | Saves the next person hours. |

If you cannot fill a field, write `unknown` and say why. Blank is not acceptable.

## Where things go

```
hacks/
  _template/            copy this to start
  <brand>-<model>/      one folder per TV model, lowercase, dashes
    REPORT.md           required
    *.py, *.sh, ...     whatever made it work; can be rough
tvcast/                 the supported core; changes here need tests
```

Folder names: `samsung-ue43nu7100`, `lg-43uk6300`, `weier-hi3751`. If you do not know
the model, use the platform and chipset from `tvprobe`, like `noname-hi3751-android9`.

A hack folder can contain anything: a Python script, a shell one-liner, an ADB recipe, a
Swift snippet. It does not need tests. It does need the report.

## From hack to core

Maintainers read reports and promote the interesting parts into `tvcast`:

1. **Reported.** A `hacks/<tv>/` folder with a complete `REPORT.md` is merged as-is once
   the report checks out. Merged does not mean endorsed; it means documented.
2. **Confirmed.** A second person reproduces it on the same or a similar TV and says so in
   an issue or PR. The README's tested-TV table gets a row.
3. **Promoted.** The technique becomes a launcher or an option in `tvcast`, with unit
   tests, and the hack folder gets a note pointing at it.

If you want to skip straight to step 3, open a PR against `tvcast/` that follows the
code rules below and reference the report(s) it is based on.

## Code rules for `tvcast/`

- Python 3.9 or newer, **standard library only**. No third-party packages. ffmpeg is the
  only external binary; `swiftc` is optional.
- Every change in `tvcast/` comes with tests in `tests/`. Tests must not touch the
  network or run ffmpeg; use fixtures and fakes like the existing tests do.
- New transports implement the launcher interface: `play(url, title)`, `stop()`,
  `state()`. Look at `tvcast/cast/launcher.py`.
- Keep modules small and single-purpose. Capture, serve, launch and watch are separate
  for a reason.
- Run the suite before you push:

```bash
python3 -m unittest discover -s tests -t . -v
```

## Privacy: what never goes in a report or a commit

- Full MAC addresses. `tvprobe --report` masks them to the vendor prefix. If you paste
  anything else, mask them yourself: `aa:bb:cc:xx:xx:xx`.
- Wi-Fi network names, passwords, the rental's address or host name.
- Your Mac's hostname, username, or home directory paths.
- Screenshots that show any of the above.

Private LAN addresses like `192.168.1.42` are fine.

## Pull request checklist

The PR template asks for this; here it is in one place:

- [ ] `hacks/<brand>-<model>/REPORT.md` is complete, or the PR touches only `tvcast/` and
      references existing reports.
- [ ] `tvprobe --report` output is included, not `--json`.
- [ ] No full MACs, SSIDs, hostnames or home paths anywhere in the diff.
- [ ] For `tvcast/` changes: tests added and the suite passes.
- [ ] The commit messages say what changed and why, not "fix" or "update".

## Using a coding agent

If an AI agent wrote your hack, say so in the report; it is not a problem. Do point the
agent at `AGENTS.md` first. It contains the same rules in a form agents follow well, and
it will save you a round of review comments.

## Questions

Open a discussion or an issue. "Is my TV worth trying?" is a fine question: paste the
`tvprobe --report` output and we will tell you which path to try first.
