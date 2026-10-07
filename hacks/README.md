# hacks

One folder per TV model. Each folder holds a complete `REPORT.md` (copy
`_template/REPORT.md`) and whatever code made that TV play. Rough code is fine here;
the report is not optional. See `CONTRIBUTING.md` for the rules and the path from a hack
to a supported transport in `tvcast`.

| Folder | TV | Transport | Status |
|---|---|---|---|
| `weier-hi3751-android9` | "Weier" no-name set, HiSilicon Hi3751V350, Android 9 | DLNA | Promoted: this is the `tvcast` default path |
| `lg-55ec930v` | LG 55EC930V-ZA, webOS 1.4.0 | DLNA | Reported: owner confirms >1 h in a broader local native build; see report limitations |

Status values: **reported** (one person), **confirmed** (reproduced by someone else),
**promoted** (built into `tvcast`).
