# TV report: Samsung AU7700 43"

## The TV

- **Brand and model (required):** Samsung AU7700 43", model `UA43AU7700KXXT` (from the
  TV's own UPnP/Samsung API, not the back label).
- **Platform and version (required):** Tizen; the TV's API reports `"os": "Tizen"`. Exact
  version unknown: Settings > About was not checked.
- **Chipset, if visible:** not shown in the probe.
- **Year or firmware version:** the `AU` series is Samsung's 2021 line (from the model
  code). Firmware not checked.
- **Built-in casting the TV advertises:** AirPlay (`_airplay._tcp`), DLNA AVTransport,
  DIAL, Samsung remote API (8001), Spotify Connect. AirPlay was not tried, so whether it
  drops Wi-Fi is unknown (AirPlay normally does not).

## The network fingerprint (required)

```json
{
  "tvcast_version": "0.1.0",
  "platform": "Darwin 27.2.0 (arm64)",
  "candidates": [
    {
      "ip": "192.168.1.35",
      "mac": "80:8a:bd:xx:xx:xx",
      "name": "Samsung AU7700 43 TV",
      "model": "UA43AU7700KXXT",
      "transports": [
        "airplay",
        "dlna",
        "dial",
        "samsung"
      ],
      "avtransport_control": "http://192.168.1.35:9197/upnp/control/AVTransport1",
      "open_ports": [
        8001,
        8080,
        9080
      ],
      "score": 10,
      "reasons": [
        "speaks samsung",
        "speaks dlna",
        "stable (non-randomized) MAC",
        "name mentions 'tv'"
      ]
    },
    {
      "ip": "192.168.1.36",
      "mac": "48:5c:2c:xx:xx:xx",
      "name": "Android TV",
      "model": "SKWAMX3",
      "transports": [
        "cast",
        "dial"
      ],
      "avtransport_control": null,
      "open_ports": [
        8008,
        8009
      ],
      "score": 7,
      "reasons": [
        "speaks cast",
        "stable (non-randomized) MAC",
        "name mentions 'tv'"
      ]
    }
  ],
  "hosts": [
    {
      "ip": "192.168.1.35",
      "mac": "80:8a:bd:xx:xx:xx",
      "mac_randomized": false,
      "open_ports": [
        8001,
        8080,
        9080
      ],
      "samsung_info": {
        "name": "Samsung AU7700 43 TV",
        "model": "UA43AU7700KXXT",
        "os": "Tizen"
      },
      "mdns_instances": [
        "Samsung AU7700 43 TV._airplay._tcp.local",
        "1a08xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx._spotify-connect._tcp.local"
      ],
      "mdns_services": [
        "_airplay._tcp.local",
        "_spotify-connect._tcp.local"
      ],
      "has_avtransport": true,
      "has_dial": true,
      "avtransport_control": "http://192.168.1.35:9197/upnp/control/AVTransport1",
      "friendly_name": "Samsung AU7700 43 TV",
      "model": "UA43AU7700KXXT",
      "manufacturer": "Samsung Electronics"
    },
    {
      "ip": "192.168.1.36",
      "mac": "48:5c:2c:xx:xx:xx",
      "mac_randomized": false,
      "open_ports": [
        8008,
        8009
      ],
      "cast_info": {
        "name": "Android TV",
        "model": null,
        "manufacturer": null
      },
      "mdns_instances": [
        "SKWAMX3-d9e2xxxxxxxxxxxxxxxxxxxxxxxxxxxx._googlecast._tcp.local",
        "Android TV._androidtvremote2._tcp.local"
      ],
      "mdns_services": [
        "_googlecast._tcp.local",
        "_androidtvremote2._tcp.local"
      ],
      "model": "SKWAMX3",
      "friendly_name": "Android TV",
      "has_avtransport": false,
      "has_dial": true,
      "avtransport_control": null,
      "manufacturer": "SkyworthDigital"
    }
  ],
  "direct_groups": [],
  "p2p_supported": false,
  "wifi_redacted": false,
  "actions": [
    "airplay",
    "dlna",
    "dial",
    "samsung"
  ],
  "other_hosts": 1
}
```

(A second TV on the same LAN, a Skyworth Android TV `SKWAMX3`, shows up too. It is not
part of this report.)

## What worked (required)

- **Transport that played a picture:** dlna (stock `tvcast`, no new code).
- **Exact command(s), copy-pasted:**

```
python3 -m tvcast.cast.cli --to 192.168.1.35
```

- **Sound:** yes, via the ScreenCaptureKit helper (tvcast log: `ScreenCaptureKit 1108x720
  with system audio`). The human confirmed sound came out of the TV.
- **Latency estimate:** about 3 to 5 s (human estimate).
- **How long it stayed stable:** played for the length of this session (several
  minutes). No long run (a full episode) tested yet.
- **Anything the TV needed first:** nothing. There was no "Allow device?" popup and no
  wake press was needed. The TV was already on.

Request pattern from the TV: `HEAD`, `GET`, disconnect after 1880 bytes, then `HEAD`,
`GET` again, then `TRANSITIONING` → `PLAYING`. The first GET looks like a format sniff.

## What did not work (required, keep it short)

- Nothing failed in this session. Only the default settings were tried; `--quality 1080p`
  and AirPlay mirroring were not tested.

## Your setup (required)

- **Mac model and macOS version:** Mac16,8, macOS 27.2
- **ffmpeg version:** ffmpeg version 9.0.2
- **tvcast commit or version:** `70bb902` (tvcast 0.1.0)
- **Written with a coding agent?** yes, Claude Code (Claude Opus 5.5).

## Files in this folder

- `REPORT.md`: this file. No code: stock `tvcast` worked unchanged.

## Notes for maintainers

- This is the first Tizen set reported, and stock DLNA works with no changes. It is a
  candidate for the tested-TV table in the README.
- The probe-then-reconnect pattern (a short first GET) is tolerated by the current server.
- Latency (3 to 5 s) is higher than "about a second". This is likely the Samsung player's
  buffer, not the network; not investigated.
