# TV report: LG 55EC930V-ZA

## The TV

- **Brand and model (required):** LG 55EC930V-ZA, confirmed from the owner's TV settings photograph.
- **Platform and version (required):** webOS 1.4.0-2536 (afro-ashley), shown in that photograph.
- **Chipset, if visible:** unknown; not exposed by the inspected device description.
- **Year or firmware version:** unknown; firmware was not separately recorded.
- **Built-in casting the TV advertises:** DLNA with AVTransport and DIAL in the probe below. Other protocols were not revalidated in this trial.

## The network fingerprint (required)

Collected on 2026-10-08 with the unchanged probe from upstream commit
`70bb9029aac69719022233a70267a6e4644050b0`:

```sh
python3 -m tvcast.probe --report --no-wifi --timeout 5 --port-timeout 0.3
```

The complete output follows, with only device names belonging to another computer,
mDNS instance identifiers and the TV's UUID redacted for privacy. No hosts or fields
were omitted. These explicit redactions are necessary because `--report` still
includes those identifiers; this is not raw `--json` output. Private LAN addresses
and already-masked MAC vendor prefixes are retained.

```json
{
  "tvcast_version": "0.1.0",
  "platform": "Darwin 25.3.0 (arm64)",
  "candidates": [
    {
      "ip": "192.168.1.187",
      "mac": "c4:36:6c:xx:xx:xx",
      "name": "[LG] webOS TV",
      "model": "LG TV",
      "transports": [
        "dlna",
        "dial"
      ],
      "avtransport_control": "http://192.168.1.187:1366/AVTransport/<device-id>/control.xml",
      "open_ports": [
        1900,
        3000
      ],
      "score": 7,
      "reasons": [
        "speaks dlna",
        "stable (non-randomized) MAC",
        "name mentions 'tv'"
      ]
    },
    {
      "ip": "192.168.1.198",
      "mac": "6a:9a:ab:xx:xx:xx",
      "name": "<redacted device name>",
      "model": null,
      "transports": [
        "airplay"
      ],
      "avtransport_control": null,
      "open_ports": [
        5000,
        7000
      ],
      "score": 0,
      "reasons": []
    }
  ],
  "hosts": [
    {
      "ip": "192.168.1.187",
      "mac": "c4:36:6c:xx:xx:xx",
      "mac_randomized": false,
      "open_ports": [
        1900,
        3000
      ],
      "has_avtransport": true,
      "has_dial": true,
      "avtransport_control": "http://192.168.1.187:1366/AVTransport/<device-id>/control.xml",
      "friendly_name": "[LG] webOS TV",
      "model": "LG TV",
      "manufacturer": "LG Electronics."
    },
    {
      "ip": "192.168.1.198",
      "mac": "(randomized)",
      "mac_randomized": true,
      "open_ports": [
        5000,
        7000
      ],
      "airplay_info": null,
      "mdns_instances": [
        "<redacted mDNS instance>",
        "<redacted mDNS instance>"
      ],
      "mdns_services": [
        "_airplay._tcp.local",
        "_raop._tcp.local"
      ],
      "model": "0,1,2"
    }
  ],
  "direct_groups": [],
  "p2p_supported": false,
  "wifi_redacted": false,
  "actions": [
    "dlna",
    "dial"
  ],
  "other_hosts": 5
}
```

## What worked (required)

- **Transport that played a picture:** DLNA, using the native macOS TVCast GUI with local modifications described below. The owner confirmed that the Mac's screen and video appeared on the LG.
- **Exact command(s), copy-pasted:** the local app was built from its source checkout with:

```sh
cd macapp
./make-app.sh release
```

The resulting app was installed and opened through the macOS GUI. In TVCast, the LG
was selected using manual descriptor entry, quality was set to **Sharp (1080p)**,
and casting was started. The descriptor address used in the earlier trial was
`http://192.168.1.187:1697/`; on 2026-10-08 its port was **1366**. Discover the current
address each time; these ports are not permanent.

- **Sound:** yes, system audio via the native ScreenCaptureKit capture path. The owner confirmed that sound and picture were synchronized normally.
- **Latency estimate:** about 1.5 seconds, estimated by the owner.
- **How long it stayed stable:** the owner reported a playback session of more than one hour. Continuous end-to-end stability was not measured.
- **Anything the TV needed first:** switched on, at its home screen rather than the Screen Share screen. The owner confirmed this preparation. No pairing or developer mode was used.

On 2026-10-08, a read-only AVTransport `GetTransportInfo` request returned
`PLAYING`, status `OK`, speed `1`. The installed TVCast process had an established
TCP stream connection to the LG. These observations corroborate the owner's report;
image, audio and perceived latency were assessed by the owner, not inferred from
transport state.

Native discovery on the PR branch (`3da09c6`) also found the LG and its current
AVTransport URL on 2026-10-08:

```sh
cd macapp
swift run tvcast-native discover
```

## What did not work (required, keep it short)

- Native automatic discovery initially found no renderer, while the Python probe found the LG. A fresh native discovery run on 2026-10-08 succeeded, as recorded above; the cause of the earlier failure remains unknown.
- Manual descriptor connection initially failed with a macOS `Local network prohibited` log. Later the installed app connected successfully; the precise permission-state transition was not observed.
- A probe on 2026-10-07 did not find the LG. The owner reconnected the TV, and the 2026-10-08 probe above found it again.

## Your setup (required)

- **Mac model and macOS version:** Apple silicon MacBook Pro (`MacBookPro18,1`), macOS 26.3 (25D125).
- **ffmpeg version:** Homebrew FFmpeg 9.0.2.
- **tvcast commit or version:** upstream `70bb9029aac69719022233a70267a6e4644050b0` plus local native-app changes for the playback trial. The narrower lifecycle fix at `3da09c6` passed automated tests and discovered the LG; that app build was not installed for the playback trial.
- **Written with a coding agent?** Yes, Codex; the owner supplied the observations of picture, sound, latency and stability.

## Files in this folder

- `REPORT.md`: the device fingerprint, owner-confirmed playback results, reproduction details and limitations. No TV-specific code is added.

## Notes for maintainers

The hardware trial used a broader local build with manual descriptor entry, a regular
app window and network restrictions, in addition to lifecycle fixes. Those local
changes are not all included in this PR. Building the PR alone therefore does not
reproduce that complete GUI setup; successful playback on the PR branch itself is
**unknown**, because the installed app was not replaced during this report.

The proposed Stop/Quit and startup-cancellation fixes are generic native Swift
changes. Their failure cases and fixes are reproducible without the TV using fake
sources, loopback clients and anonymous pipes:

```sh
cd macapp
swift run tvcast-selftest
swift run -c release tvcast-selftest
swift build --product TVCastApp
cd ..
python3 -m unittest discover -s tests -t . -v
```

The report records a single owner's trial, not independent confirmation of support
for this model. No TV-specific workaround is promoted into the core by this PR.
