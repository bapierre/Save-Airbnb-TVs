## What this PR does

<!-- One paragraph. Which TV, which transport, what changed. -->

## Type

- [ ] New hack folder under `hacks/<brand>-<model>/` (report required, code can be rough)
- [ ] Change to the core in `tvcast/` (tests required)
- [ ] Docs only

## Report checklist (for hacks)

- [ ] `REPORT.md` copied from `hacks/_template/` with **every required field filled**
- [ ] `tvprobe --report` output pasted (not `--json`)
- [ ] The exact commands that produced a playing picture are in the report
- [ ] Sound, latency, stability and "what the TV needed first" are answered
- [ ] The `hacks/README.md` table has a row for this folder

## Core checklist (for `tvcast/` changes)

- [ ] Standard library only, Python 3.9 compatible
- [ ] Tests added in `tests/`, no network or ffmpeg needed
- [ ] `python3 -m unittest discover -s tests -t . -v` passes
- [ ] Based on report(s): <!-- link issues or hack folders -->

## Privacy

- [ ] No full MAC addresses, Wi-Fi names, hostnames, usernames or home paths in the diff

## Written with a coding agent?

<!-- Yes/no, which one. Fine either way; it helps us calibrate review. -->
