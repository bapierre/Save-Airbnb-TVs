# TV report: "Weier" no-name set, HiSilicon Hi3751V350

The TV the project was built against. Everything it taught us is now in `tvcast`, so
there is no code in this folder; run `tvcast`.

## The TV

- **Brand and model:** sold as "Weier"; no model number found on the settings screen.
- **Platform and version:** Android 9 (HiSilicon "HiDPTAndroid" build), from the DLNA
  device name and the player's user agent `stagefright/1.2 (Linux;Android 9)`.
- **Chipset:** Hi3751V350.
- **Built-in casting:** Miracast ("screen mirroring"). Opening it drops the TV off Wi-Fi
  to become a Wi-Fi Direct receiver, so leave it on the home screen instead.

## The network fingerprint

`tvprobe --report --no-wifi`, trimmed to the interesting host:

```json
{
  "candidates": [
    {
      "name": "HiDPTAndroid Hi3751V350_DMR",
      "model": "Hisilicon MediaRenderer",
      "transports": ["dlna"],
      "avtransport_control": "http://<tv>:25826/upnp/service/AVTransport/Control",
      "open_ports": []
    }
  ]
}
```

Full port scan: only 25826 (UPnP) and 14035 (unidentified, silent) open. No ADB, Cast,
DIAL, or Android TV remote service. DLNA DMR 1.50 with AVTransport, RenderingControl
and ConnectionManager. `GetProtocolInfo` lists MPEG-TS, MPEG, MP4, MKV, Motion JPEG and
`application/octet-stream`.

## What worked

- **Transport:** DLNA. `SetAVTransportURI` with DIDL-Lite metadata, then `Play`.
- **Command:** `tvcast`
- **Sound:** yes, via the ScreenCaptureKit helper (AAC in the MPEG-TS).
- **Latency:** about 2 s.
- **Stable:** several minutes in testing; longer runs welcome.
- **Needed first:** TV awake and on its home screen. In standby or screensaver it accepts
  the URL, reports TRANSITIONING, then STOPPED, for any URL including public MP4s.

## What did not work

- Any stream whose first byte took more than ~1 s to arrive: the player reconnects in a
  loop, fetching ~60 KB per attempt. Fixed in `tvcast` by disabling ffmpeg input probing.
- Wake-on-LAN magic packets: no effect.
- Miracast from the Mac: impossible; macOS has no Wi-Fi Direct client mode.

## Setup

- MacBook Pro (Apple silicon), macOS 26.5; ffmpeg 8.0.1 with `h264_videotoolbox`.
- Written with a coding agent: yes (Claude Code).

## Notes for maintainers

The HEAD-then-GET behaviour, the `Accept-Ranges: none` tolerance, and the first-byte
timeout are probably common to every Android stagefright DMR. Expect similar behaviour
from other HiSilicon and MediaTek no-name sets.
