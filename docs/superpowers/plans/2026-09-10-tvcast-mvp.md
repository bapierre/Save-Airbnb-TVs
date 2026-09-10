# tvcast MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command, `tvcast`, that mirrors a Mac screen with system audio to a DLNA TV on the same LAN, built on the existing `tvprobe` discovery code.

**Architecture:** A Python package `tvcast` with two sub-packages: `probe` (the existing discovery modules, fixed) and `cast` (ffmpeg argv builder, live MPEG-TS HTTP server, DLNA SOAP launcher, session watcher, CLI). A Swift ScreenCaptureKit helper (`sckcap`) is compiled on demand to supply video plus system audio to ffmpeg without a virtual audio driver.

**Tech Stack:** Python 3.9 stdlib only; ffmpeg 8 with `h264_videotoolbox`; Swift 5+ (`swiftc` from Command Line Tools) for the helper; `unittest` for tests.

**Spec:** `docs/superpowers/specs/2026-09-10-tvcast-mvp-design.md`

## Global Constraints

- Python floor: `>=3.9`. No third-party Python packages, ever.
- Only external runtime binary: `ffmpeg`. `swiftc` is optional (audio helper).
- Package name `tvcast`; console scripts `tvprobe` and `tvcast`.
- Tests: `python3 -m unittest discover -s tests -t . -v` from repo root. No LAN, no ffmpeg in tests.
- Commit after every task. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Source of the existing probe code: `files.zip` in the repo root (flat: cli.py, mdns.py, ssdp.py, hosts.py, wifi.py, verdict.py, test_parsers.py, README.md, pyproject.toml, LICENSE).

---

## File structure

```
pyproject.toml                       package metadata, two console scripts
LICENSE                              MIT (from files.zip)
README.md                            usage for both commands
tvcast/__init__.py                   version string
tvcast/probe/__init__.py
tvcast/probe/__main__.py             python -m tvcast.probe
tvcast/probe/{cli,mdns,ssdp,hosts,wifi,verdict}.py   moved from files.zip, then fixed
tvcast/cast/__init__.py
tvcast/cast/ffmpeg.py                find ffmpeg, parse devices, build argv (pure)
tvcast/cast/capture.py               start/stop the process pipeline that yields MPEG-TS
tvcast/cast/server.py                StreamServer: HEAD/GET live MPEG-TS with DLNA headers
tvcast/cast/launcher.py              SOAP client, DIDL-Lite, DlnaLauncher, UpnpError
tvcast/cast/session.py               select_target, Watcher policy, Session loop
tvcast/cast/sckcap.py                build + locate the Swift helper, display size, fit_size
tvcast/cast/cli.py                   tvcast entry point
tvcast/cast/__main__.py              python -m tvcast.cast
tvcast/helpers/sckcap/main.swift     ScreenCaptureKit helper source
tests/test_probe_parsers.py          moved from files.zip (path hack removed)
tests/test_probe_fixes.py
tests/test_ffmpeg.py
tests/test_server.py
tests/test_launcher.py
tests/test_session.py
tests/test_sckcap.py
```

---

### Task 1: Package scaffold from files.zip

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `tvcast/__init__.py`, `tvcast/probe/__init__.py`, `tvcast/probe/__main__.py`, `tvcast/probe/{cli,mdns,ssdp,hosts,wifi,verdict}.py`, `tests/test_probe_parsers.py`, `tests/__init__.py`
- Delete after extraction: nothing (files.zip is gitignored, keep it locally)

**Interfaces:**
- Produces: importable `tvcast.probe.{mdns,ssdp,hosts,wifi,verdict,cli}` with the same public functions as the zip, `tvcast.probe.cli.main(argv=None) -> int`.

- [ ] **Step 1: Extract and move**

```bash
cd <repo root>
mkdir -p tvcast/probe tvcast/cast tvcast/helpers/sckcap tests
unzip -o -q files.zip -d /tmp/tvprobe-src
cp /tmp/tvprobe-src/{cli,mdns,ssdp,hosts,wifi,verdict}.py tvcast/probe/
cp /tmp/tvprobe-src/LICENSE LICENSE
cp /tmp/tvprobe-src/test_parsers.py tests/test_probe_parsers.py
printf '"""tvcast: mirror a Mac screen to an old smart TV."""\n__version__ = "0.1.0"\n' > tvcast/__init__.py
printf '' > tvcast/probe/__init__.py
printf 'import sys\nfrom .cli import main\nsys.exit(main())\n' > tvcast/probe/__main__.py
printf '' > tvcast/cast/__init__.py
printf '' > tests/__init__.py
```

- [ ] **Step 2: Fix the test import path**

In `tests/test_probe_parsers.py` replace

```python
sys.path.insert(0, "<sandbox path>")

from tvprobe import hosts, mdns, ssdp, verdict, wifi
```

with

```python
from tvcast.probe import hosts, mdns, ssdp, verdict, wifi
```

and remove the now-unused `import sys` if nothing else uses it.

- [ ] **Step 3: Write pyproject.toml**

```toml
[project]
name = "tvcast"
version = "0.1.0"
description = "Mirror a Mac screen to an old smart TV: find what the TV speaks, then stream to it"
readme = "README.md"
requires-python = ">=3.9"
license = { text = "MIT" }
keywords = ["dlna", "chromecast", "miracast", "airplay", "screen-mirroring", "upnp"]

[project.scripts]
tvprobe = "tvcast.probe.cli:main"
tvcast = "tvcast.cast.cli:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["tvcast*"]

[tool.setuptools.package-data]
"tvcast.helpers.sckcap" = ["*.swift"]
```

- [ ] **Step 4: Run the moved tests**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: all tests from the zip PASS (they are pure parser tests).

- [ ] **Step 5: Smoke the CLI**

Run: `python3 -m tvcast.probe --help`
Expected: usage text, exit 0.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml LICENSE tvcast tests
git commit -m "Import tvprobe as tvcast.probe package

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Probe fixes found on the real run

**Files:**
- Modify: `tvcast/probe/verdict.py` (`looks_like_tv`, `best_model`, `classify_host`, `build_report`, `ADVICE`)
- Modify: `tvcast/probe/ssdp.py` (`discover`, `fetch_description`, `describe_all`)
- Modify: `tvcast/probe/cli.py` (`gather`: own-IP and multicast exclusion, DIAL stitching, control URL stitching)
- Modify: `tvcast/probe/wifi.py` (`scan_ssids` redaction detection)
- Modify: `tvcast/probe/hosts.py` (add `own_addresses()`)
- Test: `tests/test_probe_fixes.py`

**Interfaces:**
- Produces: `hosts.own_addresses() -> set[str]`; `hosts.is_multicast_or_broadcast(ip) -> bool`; ssdp entries gain `"dial": bool` and `"avtransport_control": str|None`; host records gain `"has_dial"` and `"avtransport_control"`; `verdict.TRANSPORTS` includes `"dial"`; `wifi.scan_ssids()` returns `[]` and sets `wifi.LAST_SCAN_REDACTED = True` when every SSID is `<redacted>`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_probe_fixes.py
import unittest
from unittest import mock

from tvcast.probe import hosts, ssdp, verdict, wifi


class TestHostFilters(unittest.TestCase):
    def test_multicast_and_broadcast_are_excluded(self):
        self.assertTrue(hosts.is_multicast_or_broadcast("224.0.0.251"))
        self.assertTrue(hosts.is_multicast_or_broadcast("239.255.255.250"))
        self.assertTrue(hosts.is_multicast_or_broadcast("192.168.0.255"))
        self.assertFalse(hosts.is_multicast_or_broadcast("192.168.0.115"))

    def test_own_addresses_parses_ifconfig(self):
        out = "en0: flags=8863\n\tinet 192.168.0.190 netmask 0xffffff00 broadcast 192.168.0.255\n"
        with mock.patch.object(hosts.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout=out)
            with mock.patch.object(hosts.platform, "system", return_value="Darwin"):
                self.assertEqual(hosts.own_addresses(), {"192.168.0.190"})


class TestRanking(unittest.TestCase):
    def test_router_with_only_stable_mac_is_not_a_candidate(self):
        router = {"ip": "192.168.0.1", "mac": "00:11:22:33:44:55", "mac_randomized": False,
                  "open_ports": [1900], "friendly_name": "Generic Router", "model": "Generic Router"}
        report = verdict.build_report([router], [], False, "")
        self.assertEqual(report["candidates"], [])

    def test_dlna_tv_is_a_candidate(self):
        tv = {"ip": "192.168.0.115", "mac": "3c:5a:b4:aa:bb:cc", "mac_randomized": False,
              "open_ports": [], "has_avtransport": True,
              "friendly_name": "HiDPTAndroid Hi3751V350_DMR", "model": "Hisilicon MediaRenderer"}
        report = verdict.build_report([tv], [], False, "")
        self.assertEqual(report["candidates"][0]["ip"], "192.168.0.115")
        self.assertIn("dlna", report["candidates"][0]["transports"])
        self.assertTrue(report["actions"])

    def test_model_without_letters_is_ignored(self):
        host = {"ip": "1.2.3.4", "airplay_info": {"model": "0,1,2"}, "model": "Mac14,5"}
        self.assertEqual(verdict.best_model(host), "Mac14,5")

    def test_dial_is_a_transport(self):
        host = {"ip": "1.2.3.4", "open_ports": [], "has_dial": True}
        self.assertIn("dial", verdict.classify_host(host))


class TestSsdpDial(unittest.TestCase):
    def test_description_records_avtransport_control_url(self):
        xml = b"""<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0">
        <device><friendlyName>TV</friendlyName><deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
        <serviceList><service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
        <controlURL>/upnp/service/AVTransport/Control</controlURL></service></serviceList></device>
        <URLBase>http://192.168.0.115:25826/</URLBase></root>"""
        with mock.patch.object(ssdp.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = xml
            info = ssdp.fetch_description("http://192.168.0.115:25826/description.xml")
        self.assertEqual(info["avtransport_control"],
                         "http://192.168.0.115:25826/upnp/service/AVTransport/Control")

    def test_dial_flag_from_search_target(self):
        found = {"1.2.3.4": {"ip": "1.2.3.4", "headers": {}, "locations": set(),
                             "search_targets": {"urn:dial-multiscreen-org:service:dial:1"}}}
        ssdp.describe_all(found)
        self.assertTrue(found["1.2.3.4"]["dial"])


class TestWifiRedaction(unittest.TestCase):
    def test_redacted_ssids_are_reported(self):
        out = "      Other Local Wi-Fi Networks:\n        <redacted>:\n          PHY Mode: 802.11\n        <redacted>:\n"
        with mock.patch.object(wifi.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout=out)
            with mock.patch.object(wifi.platform, "system", return_value="Darwin"):
                ssids = wifi.scan_ssids()
        self.assertEqual(ssids, [])
        self.assertTrue(wifi.LAST_SCAN_REDACTED)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_probe_fixes -v`
Expected: FAIL/ERROR on every test (missing functions/keys).

- [ ] **Step 3: Implement**

`tvcast/probe/hosts.py`, add:

```python
def is_multicast_or_broadcast(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return addr.is_multicast or ip.endswith(".255") or ip == "255.255.255.255"


def own_addresses():
    """IPv4 addresses of this machine's interfaces (excluding loopback)."""
    system = platform.system()
    try:
        out = subprocess.run(["ifconfig"] if system == "Darwin" else ["ip", "-o", "addr"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    addrs = set()
    for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)", out):
        if not m.group(1).startswith("127."):
            addrs.add(m.group(1))
    return addrs
```

`tvcast/probe/ssdp.py`:
- In `discover`, record which search target each response matched: after parsing headers, `entry.setdefault("search_targets", set()).add(headers.get("st", ""))`.
- In `fetch_description`, while iterating services, capture the `controlURL` of the AVTransport service. Iterate `root.iter()` over `service` elements:

```python
    base = None
    for elem in root.iter():
        if _strip_ns(elem.tag) == "URLBase" and elem.text:
            base = elem.text.strip()
    info["avtransport_control"] = None
    for svc in root.iter():
        if _strip_ns(svc.tag) != "service":
            continue
        fields = {_strip_ns(c.tag): (c.text or "").strip() for c in svc}
        st = fields.get("serviceType", "")
        if st:
            info["services"].append(st)
        if "AVTransport" in st and fields.get("controlURL"):
            info["avtransport_control"] = urllib.parse.urljoin(base or location, fields["controlURL"])
```

(and drop the old `serviceType` branch from the first loop so services are not double-counted; keep friendlyName/manufacturer/modelName/modelNumber/deviceType there). Add `import urllib.parse`.
- In `describe_all`: `entry["dial"] = any("dial" in st for st in entry.get("search_targets", set()))` and `entry["avtransport_control"] = next((d["avtransport_control"] for d in descriptions if d.get("avtransport_control")), None)`.

`tvcast/probe/verdict.py`:
- `TRANSPORTS = ["cast", "airplay", "dlna", "dial", "adb", "roku", "samsung", "miracast"]`
- In `classify_host`, after dlna: `if host.get("has_dial"): found.append("dial")`.
- `best_model`: skip values with no letters: `if info and info.get("model") and re.search("[A-Za-z]", info["model"])`; same guard for `host.get("model")`. Add `import re`.
- `looks_like_tv`: keep scoring but the MAC point stays a tiebreaker. In `build_report` change the skip rule to `if not transports and not name_hit: continue` where `name_hit` is whether the keyword loop matched; simplest: return `(score, reasons, name_hit)` from `looks_like_tv`… keep the signature and instead compute `strong = bool(transports) or any(r.startswith("name mentions") for r in reasons)`; skip when not strong.
- Add `ADVICE["dial"] = ("DIAL available", "The TV can launch its own YouTube/Netflix app from the network. Use `tvcast` DLNA for mirroring; DIAL support is on the roadmap.")`. Every transport in `TRANSPORTS` except `miracast` must have an ADVICE entry (the `build_report` loop indexes `ADVICE[t]`).

`tvcast/probe/cli.py` in `gather`:
- After `known_ips` is built: `own = hostmod.own_addresses()` and filter `known_ips = {ip for ip in known_ips if ip not in own and not hostmod.is_multicast_or_broadcast(ip)}`. Also skip stitching mDNS/SSDP entries whose IP is in `own` or multicast.
- When stitching SSDP: `rec["has_dial"] = entry.get("dial", False)` and `rec["avtransport_control"] = entry.get("avtransport_control")`.
- Include `"avtransport_control"` in each candidate dict in `verdict.build_report` (copy from host).
- In `render`, after the Wi-Fi Direct block, if `report.get("wifi_redacted")` print: `macOS hid every Wi-Fi name (Location Services permission is required to read SSIDs). The DIRECT-* name is shown on the TV's mirroring screen.` Set `report["wifi_redacted"] = wifi.LAST_SCAN_REDACTED` in `gather`.

`tvcast/probe/wifi.py`:
- Module global `LAST_SCAN_REDACTED = False`. In `scan_ssids` Darwin branch, collect names; after the loop: `redacted = [s for s in ssids if s == "<redacted>"]`; `LAST_SCAN_REDACTED = bool(ssids) and len(redacted) == len(ssids)`; return `[s for s in ssids if s != "<redacted>"]`. Use `global LAST_SCAN_REDACTED`.

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: PASS, including the older parser tests.

- [ ] **Step 5: Real run sanity**

Run: `python3 -m tvcast.probe --no-wifi --no-color`
Expected: the HiSilicon TV is the single candidate; the router, this Mac, and multicast addresses are absent; the "What to do next" block lists DLNA.

- [ ] **Step 6: Commit**

```bash
git add tvcast tests
git commit -m "Fix probe ranking, own-host and multicast filtering, DIAL and control URL capture

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: ffmpeg argv builder

**Files:**
- Create: `tvcast/cast/ffmpeg.py`
- Test: `tests/test_ffmpeg.py`

**Interfaces:**
- Produces:
  - `find_ffmpeg() -> str | None`
  - `parse_devices(text: str) -> dict` with keys `"video"` and `"audio"`, each `list[tuple[int, str]]`
  - `list_devices(ffmpeg: str) -> dict` (runs ffmpeg, returns `parse_devices`)
  - `screen_index(devices) -> int | None`
  - `find_audio_device(devices, needle: str) -> int | None` (case-insensitive substring)
  - `@dataclass VideoSpec(width=1280, height=720, fps=30, bitrate="4M")`
  - `avfoundation_inputs(screen: int, audio: int | None, fps: int) -> list[str]`
  - `rawpipe_inputs(width: int, height: int, fps: int, audio_fifo: str | None) -> list[str]`
  - `build_argv(ffmpeg: str, inputs: list[str], spec: VideoSpec, has_audio: bool) -> list[str]`
  - `fit_filter(spec) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ffmpeg.py
import unittest

from tvcast.cast import ffmpeg as ff

LIST_OUTPUT = """[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Camera
[AVFoundation indev @ 0x1] [4] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x1] [1] BlackHole 2ch
"""


class TestDevices(unittest.TestCase):
    def test_parse_devices(self):
        d = ff.parse_devices(LIST_OUTPUT)
        self.assertEqual(d["video"], [(0, "MacBook Pro Camera"), (4, "Capture screen 0")])
        self.assertEqual(d["audio"], [(0, "MacBook Pro Microphone"), (1, "BlackHole 2ch")])

    def test_screen_and_audio_lookup(self):
        d = ff.parse_devices(LIST_OUTPUT)
        self.assertEqual(ff.screen_index(d), 4)
        self.assertEqual(ff.find_audio_device(d, "blackhole"), 1)
        self.assertIsNone(ff.find_audio_device(d, "loopback"))


class TestArgv(unittest.TestCase):
    def test_avfoundation_video_only(self):
        argv = ff.build_argv("ffmpeg", ff.avfoundation_inputs(4, None, 30), ff.VideoSpec(), False)
        self.assertEqual(argv[0], "ffmpeg")
        self.assertIn("4:none", argv)
        self.assertIn("h264_videotoolbox", argv)
        self.assertNotIn("aac", argv)
        self.assertEqual(argv[-2:], ["mpegts", "-"])

    def test_avfoundation_with_audio(self):
        argv = ff.build_argv("ffmpeg", ff.avfoundation_inputs(4, 1, 30), ff.VideoSpec(), True)
        self.assertIn("4:1", argv)
        self.assertIn("aac", argv)
        self.assertIn("-ac", argv)

    def test_rawpipe_inputs(self):
        inputs = ff.rawpipe_inputs(1280, 832, 30, "/tmp/a.fifo")
        self.assertIn("rawvideo", inputs)
        self.assertIn("1280x832", inputs)
        self.assertIn("pipe:0", inputs)
        self.assertIn("/tmp/a.fifo", inputs)
        self.assertIn("f32le", inputs)

    def test_fit_filter_pads_to_16_9(self):
        f = ff.fit_filter(ff.VideoSpec(width=1280, height=720))
        self.assertIn("scale=1280:720:force_original_aspect_ratio=decrease", f)
        self.assertIn("pad=1280:720:(ow-iw)/2:(oh-ih)/2", f)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_ffmpeg -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# tvcast/cast/ffmpeg.py
"""Locate ffmpeg, enumerate avfoundation devices, build the capture command. Pure functions."""
import re
import shutil
import subprocess
from dataclasses import dataclass

CANDIDATES = ["ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
INSTALL_HINT = "ffmpeg not found. Install it with: brew install ffmpeg"

DEVICE_RE = re.compile(r"\[AVFoundation indev @ [^\]]+\] \[(\d+)\] (.+)")


@dataclass
class VideoSpec:
    width: int = 1280
    height: int = 720
    fps: int = 30
    bitrate: str = "4M"


def find_ffmpeg():
    for c in CANDIDATES:
        path = shutil.which(c)
        if path:
            return path
    return None


def parse_devices(text):
    devices = {"video": [], "audio": []}
    section = None
    for line in text.splitlines():
        if "AVFoundation video devices" in line:
            section = "video"
            continue
        if "AVFoundation audio devices" in line:
            section = "audio"
            continue
        m = DEVICE_RE.search(line)
        if m and section:
            devices[section].append((int(m.group(1)), m.group(2).strip()))
    return devices


def list_devices(ffmpeg):
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-f", "avfoundation",
                               "-list_devices", "true", "-i", ""],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return {"video": [], "audio": []}
    return parse_devices(proc.stderr + proc.stdout)


def screen_index(devices):
    for idx, name in devices["video"]:
        if name.lower().startswith("capture screen"):
            return idx
    return None


def find_audio_device(devices, needle):
    needle = needle.lower()
    for idx, name in devices["audio"]:
        if needle in name.lower():
            return idx
    return None


def avfoundation_inputs(screen, audio, fps):
    return ["-f", "avfoundation", "-framerate", str(fps), "-pixel_format", "nv12",
            "-capture_cursor", "1", "-i", f"{screen}:{audio if audio is not None else 'none'}"]


def rawpipe_inputs(width, height, fps, audio_fifo):
    args = ["-f", "rawvideo", "-pix_fmt", "nv12", "-video_size", f"{width}x{height}",
            "-framerate", str(fps), "-i", "pipe:0"]
    if audio_fifo:
        args += ["-f", "f32le", "-ar", "48000", "-ac", "2", "-i", audio_fifo]
    return args


def fit_filter(spec):
    w, h = spec.width, spec.height
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=nv12")


def build_argv(ffmpeg, inputs, spec, has_audio):
    argv = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin"] + inputs
    argv += ["-vf", fit_filter(spec),
             "-c:v", "h264_videotoolbox", "-b:v", spec.bitrate, "-g", str(spec.fps),
             "-bf", "0", "-realtime", "1"]
    if has_audio:
        argv += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
    else:
        argv += ["-an"]
    argv += ["-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-"]
    return argv
```

Note: `-nostdin` must not be used with `rawpipe_inputs` (stdin is the video). Make `build_argv` omit `-nostdin` when `"pipe:0" in inputs`.

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_ffmpeg -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tvcast/cast/ffmpeg.py tests/test_ffmpeg.py
git commit -m "Add ffmpeg device parsing and capture argv builder

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Capture pipeline and stream server

**Files:**
- Create: `tvcast/cast/capture.py`, `tvcast/cast/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces:
  - `class Capture` with `read(n: int) -> bytes` and `stop() -> None`, attribute `procs`.
  - `def start_ffmpeg(argv, stdin=None) -> Capture`
  - `def make_avfoundation_factory(ffmpeg, screen, audio, spec) -> Callable[[], Capture]`
  - `class StreamServer(capture_factory, host="0.0.0.0", port=0, log=None)`, methods `start() -> int` (bound port), `stop()`, attributes `path = "/screen.ts"`, `requests: list[dict]` (method, path, client, headers).
  - `DLNA_HEADERS` dict.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
import http.client
import io
import threading
import unittest

from tvcast.cast.server import StreamServer, DLNA_HEADERS


class FakeCapture:
    def __init__(self, payload):
        self.buf = io.BytesIO(payload)
        self.stopped = threading.Event()

    def read(self, n):
        return self.buf.read(n)

    def stop(self):
        self.stopped.set()


class TestStreamServer(unittest.TestCase):
    def setUp(self):
        self.captures = []

        def factory():
            cap = FakeCapture(b"\x47" * 188 * 10)
            self.captures.append(cap)
            return cap

        self.server = StreamServer(factory, host="127.0.0.1", port=0)
        self.port = self.server.start()

    def tearDown(self):
        self.server.stop()

    def test_head_returns_dlna_headers_without_body(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("HEAD", "/screen.ts")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "video/mpeg")
        for k, v in DLNA_HEADERS.items():
            self.assertEqual(resp.getheader(k), v)
        self.assertIsNone(resp.getheader("Content-Length"))
        self.assertEqual(self.captures, [])
        self.assertEqual(self.server.requests[-1]["method"], "HEAD")

    def test_get_streams_capture_then_stops_it(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/screen.ts", headers={"Range": "bytes=0-"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read()
        self.assertEqual(len(body), 188 * 10)
        self.assertTrue(self.captures[0].stopped.wait(5))

    def test_unknown_path_is_404(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/nope")
        self.assertEqual(conn.getresponse().status, 404)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_server -v`
Expected: ImportError.

- [ ] **Step 3: Implement capture.py**

```python
# tvcast/cast/capture.py
"""Run the process pipeline that produces a live MPEG-TS byte stream."""
import subprocess

from . import ffmpeg as ff


class Capture:
    def __init__(self, procs, stdout):
        self.procs = procs
        self.stdout = stdout

    def read(self, n):
        return self.stdout.read(n)

    def stop(self):
        for p in self.procs:
            try:
                p.kill()
            except OSError:
                pass
        for p in self.procs:
            try:
                p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            self.stdout.close()
        except OSError:
            pass


def start_ffmpeg(argv, stdin=None, extra_procs=()):
    proc = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=0)
    return Capture(list(extra_procs) + [proc], proc.stdout)


def make_avfoundation_factory(ffmpeg, screen, audio, spec):
    argv = ff.build_argv(ffmpeg, ff.avfoundation_inputs(screen, audio, spec.fps), spec,
                         has_audio=audio is not None)

    def factory():
        return start_ffmpeg(argv)
    factory.description = f"avfoundation screen {screen}, audio {audio if audio is not None else 'none'}"
    return factory
```

- [ ] **Step 4: Implement server.py**

```python
# tvcast/cast/server.py
"""HTTP server that streams live MPEG-TS to a DLNA renderer."""
import http.server
import socketserver
import threading

DLNA_HEADERS = {
    "transferMode.dlna.org": "Streaming",
    "contentFeatures.dlna.org": "DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000",
    "Accept-Ranges": "none",
}
CHUNK = 188 * 64


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):  # silence default stderr logging
        pass

    def _record(self):
        rec = {"method": self.command, "path": self.path, "client": self.client_address[0],
               "headers": dict(self.headers.items())}
        self.server.requests.append(rec)
        if self.server.log:
            self.server.log(f"{self.client_address[0]} {self.command} {self.path} "
                            f"UA={self.headers.get('User-Agent', '-')}")

    def _send_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/mpeg")
        for k, v in DLNA_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()

    def do_HEAD(self):
        self._record()
        if self.path.split("?")[0] != self.server.path:
            self.send_error(404)
            return
        self._send_headers()

    def do_GET(self):
        self._record()
        if self.path.split("?")[0] != self.server.path:
            self.send_error(404)
            return
        self._send_headers()
        capture = self.server.capture_factory()
        sent = 0
        try:
            while True:
                chunk = capture.read(CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            capture.stop()
            if self.server.log:
                self.server.log(f"{self.client_address[0]} disconnected after {sent} bytes")


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class StreamServer:
    path = "/screen.ts"

    def __init__(self, capture_factory, host="0.0.0.0", port=0, log=None):
        self.capture_factory = capture_factory
        self.host, self.port, self.log = host, port, log
        self.requests = []
        self._srv = None
        self._thread = None

    def start(self):
        self._srv = _Server((self.host, self.port), _Handler)
        self._srv.capture_factory = self.capture_factory
        self._srv.requests = self.requests
        self._srv.log = self.log
        self._srv.path = self.path
        self.port = self._srv.server_address[1]
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None
```

- [ ] **Step 5: Run tests**

Run: `python3 -m unittest tests.test_server -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tvcast/cast/capture.py tvcast/cast/server.py tests/test_server.py
git commit -m "Add capture pipeline and live MPEG-TS stream server

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: DLNA launcher

**Files:**
- Create: `tvcast/cast/launcher.py`
- Test: `tests/test_launcher.py`

**Interfaces:**
- Produces:
  - `class UpnpError(Exception)` with `.code: int | None`, `.description: str`
  - `soap_envelope(service, action, args: dict) -> str`
  - `parse_soap_response(body: str) -> dict[str, str]` (child elements of the `*Response` element)
  - `parse_upnp_fault(body: str) -> tuple[int | None, str]`
  - `didl_lite(url, title, mime="video/mpeg") -> str` (raw XML, not escaped)
  - `class SoapClient(control_url, opener=urllib.request.urlopen)` with `call(service, action, args) -> dict`
  - `class DlnaLauncher(control_url, client=None)` with `play(url, title="Mac screen")`, `stop()`, `state() -> str`, `position() -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_launcher.py
import io
import unittest
import urllib.error

from tvcast.cast import launcher as L

CONTROL = "http://192.168.0.115:25826/upnp/service/AVTransport/Control"


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_opener(body, status=200):
    calls = []

    def opener(req, timeout=10):
        calls.append(req)
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(body.encode()))
        return FakeResponse(body.encode())
    opener.calls = calls
    return opener


class TestEnvelopes(unittest.TestCase):
    def test_envelope_contains_action_and_escaped_args(self):
        env = L.soap_envelope("AVTransport", "SetAVTransportURI",
                              {"InstanceID": 0, "CurrentURI": "http://x/a?b=1&c=2"})
        self.assertIn('<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">', env)
        self.assertIn("<CurrentURI>http://x/a?b=1&amp;c=2</CurrentURI>", env)

    def test_didl_lite_has_video_item_and_protocol_info(self):
        d = L.didl_lite("http://1.2.3.4:8090/screen.ts", "Mac screen")
        self.assertIn("object.item.videoItem", d)
        self.assertIn('protocolInfo="http-get:*:video/mpeg:', d)
        self.assertIn("<dc:title>Mac screen</dc:title>", d)

    def test_parse_response_and_fault(self):
        body = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                '<u:GetTransportInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
                '<CurrentTransportState>PLAYING</CurrentTransportState><CurrentTransportStatus>OK</CurrentTransportStatus>'
                '</u:GetTransportInfoResponse></s:Body></s:Envelope>')
        self.assertEqual(L.parse_soap_response(body)["CurrentTransportState"], "PLAYING")
        fault = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault>'
                 '<detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>716</errorCode>'
                 '<errorDescription>Resource not found</errorDescription></UPnPError></detail>'
                 '</s:Fault></s:Body></s:Envelope>')
        self.assertEqual(L.parse_upnp_fault(fault), (716, "Resource not found"))


class TestLauncher(unittest.TestCase):
    def test_play_sends_stop_seturi_play(self):
        opener = make_opener('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                             '<s:Body><u:XResponse xmlns:u="x"/></s:Body></s:Envelope>')
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=opener))
        launcher.play("http://1.2.3.4:8090/screen.ts")
        actions = [c.get_header("Soapaction") for c in opener.calls]
        self.assertEqual(actions, ['"urn:schemas-upnp-org:service:AVTransport:1#Stop"',
                                   '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"',
                                   '"urn:schemas-upnp-org:service:AVTransport:1#Play"'])
        self.assertEqual(opener.calls[0].full_url, CONTROL)

    def test_state_maps_transport_state(self):
        body = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                '<u:GetTransportInfoResponse xmlns:u="u"><CurrentTransportState>STOPPED</CurrentTransportState>'
                '</u:GetTransportInfoResponse></s:Body></s:Envelope>')
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=make_opener(body)))
        self.assertEqual(launcher.state(), "STOPPED")

    def test_fault_raises_upnp_error(self):
        fault = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault>'
                 '<detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>716</errorCode>'
                 '<errorDescription>Resource not found</errorDescription></UPnPError></detail>'
                 '</s:Fault></s:Body></s:Envelope>')
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=make_opener(fault, status=500)))
        with self.assertRaises(L.UpnpError) as ctx:
            launcher.play("http://x/screen.ts")
        self.assertEqual(ctx.exception.code, 716)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_launcher -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# tvcast/cast/launcher.py
"""Tell a TV to play a URL. The MVP ships the DLNA AVTransport launcher."""
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

SERVICE_NS = "urn:schemas-upnp-org:service:{service}:1"
STATES = {"PLAYING", "STOPPED", "TRANSITIONING", "PAUSED_PLAYBACK", "NO_MEDIA_PRESENT"}


class UpnpError(Exception):
    def __init__(self, code, description, http_status=None):
        super().__init__(f"UPnP error {code}: {description}")
        self.code, self.description, self.http_status = code, description, http_status


def soap_envelope(service, action, args):
    ns = SERVICE_NS.format(service=service)
    body = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in args.items())
    return ('<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{ns}">{body}</u:{action}></s:Body></s:Envelope>')


def _local(tag):
    return tag.split("}", 1)[-1]


def parse_soap_response(body):
    out = {}
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return out
    for elem in root.iter():
        if _local(elem.tag).endswith("Response"):
            for child in elem:
                out[_local(child.tag)] = (child.text or "").strip()
            break
    return out


def parse_upnp_fault(body):
    code = re.search(r"<errorCode>(\d+)</errorCode>", body)
    desc = re.search(r"<errorDescription>(.*?)</errorDescription>", body, re.S)
    return (int(code.group(1)) if code else None, desc.group(1).strip() if desc else body[:200])


def didl_lite(url, title, mime="video/mpeg"):
    return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
            'xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">'
            f'<item id="0" parentID="-1" restricted="1"><dc:title>{escape(title)}</dc:title>'
            '<upnp:class>object.item.videoItem</upnp:class>'
            f'<res protocolInfo="http-get:*:{mime}:DLNA.ORG_OP=00;DLNA.ORG_CI=0;'
            'DLNA.ORG_FLAGS=01700000000000000000000000000000">'
            f'{escape(url)}</res></item></DIDL-Lite>')


class SoapClient:
    def __init__(self, control_url, opener=urllib.request.urlopen, timeout=10):
        self.control_url, self.opener, self.timeout = control_url, opener, timeout

    def call(self, service, action, args):
        ns = SERVICE_NS.format(service=service)
        req = urllib.request.Request(
            self.control_url, data=soap_envelope(service, action, args).encode("utf-8"),
            method="POST",
            headers={"Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{ns}#{action}"'})
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                return parse_soap_response(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            code, desc = parse_upnp_fault(body)
            raise UpnpError(code, desc, http_status=e.code) from None
        except (urllib.error.URLError, OSError) as e:
            raise UpnpError(None, f"cannot reach {self.control_url}: {e}") from None


class DlnaLauncher:
    name = "dlna"

    def __init__(self, control_url, client=None):
        self.control_url = control_url
        self.client = client or SoapClient(control_url)

    def _avt(self, action, **args):
        return self.client.call("AVTransport", action, {"InstanceID": 0, **args})

    def play(self, url, title="Mac screen"):
        try:
            self._avt("Stop")
        except UpnpError:
            pass  # some renderers fault on Stop when idle
        self._avt("SetAVTransportURI", CurrentURI=url, CurrentURIMetaData=didl_lite(url, title))
        self._avt("Play", Speed="1")

    def stop(self):
        self._avt("Stop")

    def state(self):
        try:
            s = self._avt("GetTransportInfo").get("CurrentTransportState", "UNKNOWN")
        except UpnpError:
            return "UNKNOWN"
        return s if s in STATES else "UNKNOWN"

    def position(self):
        try:
            return self._avt("GetPositionInfo").get("RelTime", "?")
        except UpnpError:
            return "?"
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_launcher -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tvcast/cast/launcher.py tests/test_launcher.py
git commit -m "Add DLNA AVTransport launcher with SOAP client

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Target selection and session watcher

**Files:**
- Create: `tvcast/cast/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `DlnaLauncher` (Task 5) interface `play/stop/state/position`; `StreamServer` (Task 4) `start/stop/requests/path`.
- Produces:
  - `@dataclass Target(ip: str, name: str, control_url: str)`
  - `class SelectionError(Exception)`
  - `select_target(renderers: list[Target], to: str | None) -> Target`
  - `class Watcher(start_timeout=15.0, relaunch_window=30.0)` with `tick(state: str, now: float) -> str | None` returning `None`, `"relaunch"`, or `"timeout"`.
  - `class Session(launcher, server, url, log, stop_event, sleep=time.sleep, clock=time.monotonic)` with `run() -> int` (exit code).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session.py
import threading
import unittest

from tvcast.cast.session import Target, SelectionError, select_target, Watcher, Session

A = Target("192.168.0.115", "HiDPTAndroid", "http://192.168.0.115:25826/c")
B = Target("192.168.0.50", "Other", "http://192.168.0.50:1/c")


class TestSelect(unittest.TestCase):
    def test_single_renderer_is_chosen(self):
        self.assertEqual(select_target([A], None), A)

    def test_to_picks_by_ip(self):
        self.assertEqual(select_target([A, B], "192.168.0.50"), B)

    def test_multiple_without_to_raises_listing_them(self):
        with self.assertRaises(SelectionError) as ctx:
            select_target([A, B], None)
        self.assertIn("192.168.0.115", str(ctx.exception))
        self.assertIn("--to", str(ctx.exception))

    def test_none_raises(self):
        with self.assertRaises(SelectionError):
            select_target([], None)

    def test_to_not_found_raises(self):
        with self.assertRaises(SelectionError):
            select_target([A], "10.0.0.1")


class TestWatcher(unittest.TestCase):
    def test_timeout_if_never_playing(self):
        w = Watcher(start_timeout=15)
        self.assertIsNone(w.tick("TRANSITIONING", 0))
        self.assertIsNone(w.tick("STOPPED", 10))
        self.assertEqual(w.tick("STOPPED", 16), "timeout")

    def test_relaunch_once_per_window_after_playing(self):
        w = Watcher(start_timeout=15, relaunch_window=30)
        self.assertIsNone(w.tick("PLAYING", 1))
        self.assertEqual(w.tick("STOPPED", 60), "relaunch")
        self.assertIsNone(w.tick("STOPPED", 70))       # inside window: no second relaunch
        self.assertIsNone(w.tick("PLAYING", 75))
        self.assertEqual(w.tick("STOPPED", 100), "relaunch")


class FakeLauncher:
    def __init__(self, states):
        self.states = list(states)
        self.calls = []

    def play(self, url, title="Mac screen"):
        self.calls.append(("play", url))

    def stop(self):
        self.calls.append(("stop",))

    def state(self):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def position(self):
        return "00:00:01"


class FakeServer:
    path = "/screen.ts"
    requests = []

    def stop(self):
        pass


class TestSession(unittest.TestCase):
    def test_session_plays_polls_and_stops_on_event(self):
        launcher = FakeLauncher(["TRANSITIONING", "PLAYING", "PLAYING"])
        stop = threading.Event()
        clock = iter(range(0, 1000, 2))
        polls = []

        def sleep(_):
            polls.append(1)
            if len(polls) >= 3:
                stop.set()

        s = Session(launcher, FakeServer(), "http://m/screen.ts", log=lambda *_: None,
                    stop_event=stop, sleep=sleep, clock=lambda: next(clock))
        self.assertEqual(s.run(), 0)
        self.assertEqual(launcher.calls[0], ("play", "http://m/screen.ts"))
        self.assertEqual(launcher.calls[-1], ("stop",))

    def test_session_times_out_when_tv_never_plays(self):
        launcher = FakeLauncher(["STOPPED"])
        stop = threading.Event()
        clock = iter(range(0, 1000, 5))
        s = Session(launcher, FakeServer(), "http://m/screen.ts", log=lambda *_: None,
                    stop_event=stop, sleep=lambda _: None, clock=lambda: next(clock))
        self.assertEqual(s.run(), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_session -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# tvcast/cast/session.py
"""Pick the TV, start playback, keep it playing, tear down cleanly."""
import time
from dataclasses import dataclass

from .launcher import UpnpError


@dataclass(frozen=True)
class Target:
    ip: str
    name: str
    control_url: str


class SelectionError(Exception):
    pass


def select_target(renderers, to):
    if to:
        for r in renderers:
            if r.ip == to:
                return r
        raise SelectionError(f"no DLNA renderer answered at {to}. Is the TV on the same Wi-Fi and "
                             "on its home screen (not in Miracast mode)?")
    if not renderers:
        raise SelectionError("no DLNA renderer found. Run `tvprobe` to see what is on the network.")
    if len(renderers) == 1:
        return renderers[0]
    listing = "\n".join(f"  {r.ip:15}  {r.name}" for r in renderers)
    raise SelectionError(f"several renderers found; pick one with --to IP:\n{listing}")


class Watcher:
    def __init__(self, start_timeout=15.0, relaunch_window=30.0):
        self.start_timeout, self.relaunch_window = start_timeout, relaunch_window
        self.started_at = None
        self.seen_playing = False
        self.last_relaunch = None

    def tick(self, state, now):
        if self.started_at is None:
            self.started_at = now
        if state == "PLAYING":
            self.seen_playing = True
            return None
        if not self.seen_playing:
            return "timeout" if now - self.started_at > self.start_timeout else None
        if state == "STOPPED":
            if self.last_relaunch is None or now - self.last_relaunch > self.relaunch_window:
                self.last_relaunch = now
                self.seen_playing = False
                self.started_at = now
                return "relaunch"
        return None


class Session:
    def __init__(self, launcher, server, url, log, stop_event, sleep=time.sleep,
                 clock=time.monotonic, poll_interval=2.0):
        self.launcher, self.server, self.url, self.log = launcher, server, url, log
        self.stop_event, self.sleep, self.clock, self.poll = stop_event, sleep, clock, poll_interval

    def run(self):
        watcher = Watcher()
        try:
            self.launcher.play(self.url)
        except UpnpError as e:
            self.log(f"TV refused the stream: {e}")
            return 1
        code = 0
        last = None
        while not self.stop_event.is_set():
            self.sleep(self.poll)
            if self.stop_event.is_set():
                break
            state = self.launcher.state()
            if state != last:
                self.log(f"TV: {state}")
                last = state
            action = watcher.tick(state, self.clock())
            if action == "timeout":
                self._explain_timeout(state)
                code = 1
                break
            if action == "relaunch":
                self.log("TV stopped; relaunching")
                try:
                    self.launcher.play(self.url)
                except UpnpError as e:
                    self.log(f"relaunch failed: {e}")
        try:
            self.launcher.stop()
        except UpnpError:
            pass
        self.server.stop()
        return code

    def _explain_timeout(self, state):
        seen = [r for r in self.server.requests if r["path"].startswith(self.server.path)]
        if not seen:
            self.log(f"TV never fetched {self.url} (last state {state}). The TV cannot reach this Mac: "
                     "check the macOS firewall, or the Wi-Fi may isolate clients.")
        else:
            methods = ", ".join(r["method"] for r in seen)
            self.log(f"TV fetched the stream ({methods}) but never reported PLAYING (last state {state}). "
                     "It may not decode this format; try --quality 720p or --fps 25.")
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_session -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tvcast/cast/session.py tests/test_session.py
git commit -m "Add target selection and playback watcher session

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: tvcast CLI, video-only end to end

**Files:**
- Create: `tvcast/cast/cli.py`, `tvcast/cast/__main__.py`, `tvcast/cast/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: everything above; `tvcast.probe.ssdp.discover/describe_all`; `tvcast.probe.hosts.own_addresses`.
- Produces: `discovery.find_renderers(timeout) -> list[Target]`; `discovery.local_ip_for(target_ip) -> str`; `cli.main(argv=None) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discovery.py
import unittest
from unittest import mock

from tvcast.cast import discovery
from tvcast.cast.session import Target


class TestFindRenderers(unittest.TestCase):
    def test_only_entries_with_control_url_become_targets(self):
        found = {
            "192.168.0.115": {"ip": "192.168.0.115", "friendly_name": "HiDPTAndroid",
                              "avtransport_control": "http://192.168.0.115:25826/c"},
            "192.168.0.1": {"ip": "192.168.0.1", "friendly_name": "Router", "avtransport_control": None},
        }
        with mock.patch.object(discovery.ssdp, "discover", return_value=found), \
             mock.patch.object(discovery.ssdp, "describe_all", return_value=found):
            targets = discovery.find_renderers(timeout=0)
        self.assertEqual(targets, [Target("192.168.0.115", "HiDPTAndroid", "http://192.168.0.115:25826/c")])

    def test_local_ip_for_uses_udp_route(self):
        ip = discovery.local_ip_for("127.0.0.1")
        self.assertTrue(ip.startswith("127.") or ip.count(".") == 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_discovery -v`
Expected: ImportError.

- [ ] **Step 3: Implement discovery.py**

```python
# tvcast/cast/discovery.py
"""Find DLNA renderers via the probe's SSDP code, and figure out which local IP the TV can reach."""
import socket

from ..probe import ssdp
from .session import Target


def find_renderers(timeout=4.0):
    found = ssdp.discover(timeout=timeout, targets=[
        "urn:schemas-upnp-org:device:MediaRenderer:1",
        "urn:schemas-upnp-org:service:AVTransport:1"])
    ssdp.describe_all(found)
    targets = []
    for ip, entry in sorted(found.items()):
        ctl = entry.get("avtransport_control")
        if ctl:
            targets.append(Target(ip, entry.get("friendly_name") or "(unnamed renderer)", ctl))
    return targets


def local_ip_for(target_ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 9))
        return s.getsockname()[0]
    finally:
        s.close()
```

- [ ] **Step 4: Implement cli.py**

```python
# tvcast/cast/cli.py
"""tvcast: mirror this Mac's screen to a TV on the LAN."""
import argparse
import signal
import sys
import threading

from . import capture, discovery, ffmpeg as ff
from .launcher import DlnaLauncher
from .server import StreamServer
from .session import SelectionError, Session, select_target

QUALITY = {"720p": (1280, 720), "1080p": (1920, 1080)}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def choose_audio(args, devices):
    """Return (audio_index_or_None, description)."""
    if args.audio == "none":
        return None, "video only (--audio none)"
    if args.audio == "auto":
        idx = ff.find_audio_device(devices, "blackhole")
        if idx is not None:
            return idx, f"BlackHole device {idx}"
        return None, ("video only: no BlackHole audio device found. Install one with "
                      "`brew install blackhole-2ch` and set it as the output, or use --audio NAME")
    idx = ff.find_audio_device(devices, args.audio)
    if idx is None:
        names = ", ".join(n for _, n in devices["audio"]) or "none"
        raise SystemExit(f"no audio device matching '{args.audio}'. Available: {names}")
    return idx, f"audio device {idx} ({args.audio})"


def main(argv=None):
    p = argparse.ArgumentParser(prog="tvcast", description=__doc__)
    p.add_argument("--to", metavar="IP", help="TV address (skip auto-pick)")
    p.add_argument("--audio", default="auto", help="auto | none | substring of an audio device name")
    p.add_argument("--quality", choices=sorted(QUALITY), default="720p")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--bitrate", default="4M")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--timeout", type=float, default=4.0, help="SSDP discovery seconds")
    p.add_argument("--list-devices", action="store_true", help="show capture devices and exit")
    args = p.parse_args(argv)

    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg:
        log(ff.INSTALL_HINT)
        return 2
    devices = ff.list_devices(ffmpeg)
    if args.list_devices:
        for kind in ("video", "audio"):
            print(f"{kind}:")
            for idx, name in devices[kind]:
                print(f"  [{idx}] {name}")
        return 0
    screen = ff.screen_index(devices)
    if screen is None:
        log("ffmpeg lists no 'Capture screen' device. Grant Screen Recording permission to your terminal "
            "in System Settings > Privacy & Security, then retry.")
        return 2

    log(f"→ looking for DLNA renderers ({args.timeout:.0f}s)…")
    try:
        target = select_target(discovery.find_renderers(args.timeout), args.to)
    except SelectionError as e:
        log(str(e))
        return 1
    log(f"→ target: {target.name} at {target.ip}")

    audio_idx, audio_desc = choose_audio(args, devices)
    log(f"→ {audio_desc}")
    w, h = QUALITY[args.quality]
    spec = ff.VideoSpec(width=w, height=h, fps=args.fps, bitrate=args.bitrate)
    factory = capture.make_avfoundation_factory(ffmpeg, screen, audio_idx, spec)

    server = StreamServer(factory, port=args.port, log=lambda m: log(f"  http: {m}"))
    port = server.start()
    url = f"http://{discovery.local_ip_for(target.ip)}:{port}{server.path}"
    log(f"→ serving {url}")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    log("→ asking the TV to play (Ctrl-C to stop)")
    session = Session(DlnaLauncher(target.control_url), server, url, log, stop)
    return session.run()


if __name__ == "__main__":
    sys.exit(main())
```

`tvcast/cast/__main__.py`:

```python
import sys
from .cli import main
sys.exit(main())
```

- [ ] **Step 5: Run tests**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: PASS.

- [ ] **Step 6: Real run, video only**

Run: `python3 -m tvcast.cast --audio none` for ~30 s then Ctrl-C (or `timeout 40 python3 -m tvcast.cast --audio none`).
Expected: log shows the target, the HEAD and GET from the TV, `TV: PLAYING`, and on stop the TV returns to its home screen.

- [ ] **Step 7: Commit**

```bash
git add tvcast/cast tests/test_discovery.py
git commit -m "Add tvcast CLI: discover, serve, and launch on DLNA

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: ScreenCaptureKit helper for system audio (phase C)

**Files:**
- Create: `tvcast/helpers/sckcap/main.swift`, `tvcast/helpers/__init__.py`, `tvcast/helpers/sckcap/__init__.py`, `tvcast/cast/sckcap.py`
- Modify: `tvcast/cast/capture.py` (add `make_sck_factory`), `tvcast/cast/cli.py` (`choose_audio` auto path tries sckcap first)
- Test: `tests/test_sckcap.py`

**Interfaces:**
- Produces:
  - `sckcap.fit_size(display_w, display_h, max_w, max_h) -> tuple[int, int]` (even dimensions, aspect kept, fits inside)
  - `sckcap.display_size() -> tuple[int, int]` via CoreGraphics ctypes
  - `sckcap.source_path() -> str`, `sckcap.cache_dir() -> str`
  - `sckcap.ensure_helper(log) -> str | None` (compiles with `swiftc` when needed; `None` if unavailable)
  - `sckcap.supported() -> bool` (Darwin and macOS >= 13)
  - `capture.make_sck_factory(ffmpeg, helper, spec, capture_size) -> factory`
  - helper CLI: `sckcap --width W --height H --fps N --audio-fifo PATH`; stdout = NV12 frames at constant rate; fifo = float32 interleaved stereo 48 kHz; stderr = diagnostics.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sckcap.py
import os
import unittest

from tvcast.cast import sckcap


class TestFitSize(unittest.TestCase):
    def test_wide_display_limited_by_width(self):
        self.assertEqual(sckcap.fit_size(3024, 1964, 1280, 720), (1108, 720))

    def test_16_9_display_fills(self):
        self.assertEqual(sckcap.fit_size(1920, 1080, 1280, 720), (1280, 720))

    def test_dimensions_are_even(self):
        w, h = sckcap.fit_size(1512, 982, 1280, 720)
        self.assertEqual((w % 2, h % 2), (0, 0))
        self.assertLessEqual(h, 720)


class TestPaths(unittest.TestCase):
    def test_source_exists(self):
        self.assertTrue(os.path.exists(sckcap.source_path()))
        self.assertTrue(sckcap.source_path().endswith("main.swift"))

    def test_cache_dir_is_under_user_caches(self):
        self.assertIn("Caches", sckcap.cache_dir())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_sckcap -v`
Expected: ImportError.

- [ ] **Step 3: Write the Swift helper**

```swift
// tvcast/helpers/sckcap/main.swift
// sckcap: ScreenCaptureKit capture helper for tvcast.
// stdout: NV12 raw frames at a constant rate. --audio-fifo: float32 interleaved stereo 48 kHz.
import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

struct Options {
    var width = 1280
    var height = 720
    var fps = 30
    var audioFifo: String? = nil
    var displayIndex = 0
}

func parseOptions() -> Options {
    var o = Options()
    var args = Array(CommandLine.arguments.dropFirst())
    while !args.isEmpty {
        let a = args.removeFirst()
        func next() -> String { args.isEmpty ? "" : args.removeFirst() }
        switch a {
        case "--width": o.width = Int(next()) ?? o.width
        case "--height": o.height = Int(next()) ?? o.height
        case "--fps": o.fps = Int(next()) ?? o.fps
        case "--audio-fifo": o.audioFifo = next()
        case "--display-index": o.displayIndex = Int(next()) ?? 0
        default:
            FileHandle.standardError.write("sckcap: unknown option \(a)\n".data(using: .utf8)!)
            exit(2)
        }
    }
    return o
}

func err(_ s: String) { FileHandle.standardError.write("sckcap: \(s)\n".data(using: .utf8)!) }

final class FrameStore {
    private let lock = NSLock()
    private var frame: Data
    init(black width: Int, height: Int) {
        var d = Data(count: width * height)
        d.resetBytes(in: 0..<(width * height))
        d.withUnsafeMutableBytes { $0.update(repeating: 16) }
        var uv = Data(count: width * height / 2)
        uv.withUnsafeMutableBytes { $0.update(repeating: 128) }
        d.append(uv)
        frame = d
    }
    func set(_ d: Data) { lock.lock(); frame = d; lock.unlock() }
    func get() -> Data { lock.lock(); defer { lock.unlock() }; return frame }
}

final class Output: NSObject, SCStreamOutput, SCStreamDelegate {
    let store: FrameStore
    let width: Int
    let height: Int
    var audio: FileHandle?
    let audioLock = NSLock()

    init(store: FrameStore, width: Int, height: Int) {
        self.store = store; self.width = width; self.height = height
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        switch type {
        case .screen: handleVideo(sb)
        case .audio: handleAudio(sb)
        default: break
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        err("stream stopped: \(error.localizedDescription)")
        exit(1)
    }

    private func handleVideo(_ sb: CMSampleBuffer) {
        guard let pb = CMSampleBufferGetImageBuffer(sb) else { return }
        // SCK sends "idle" frames with no image data when nothing changed; skip those.
        if let attachments = CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
           let status = attachments.first?[.status] as? Int, status != SCFrameStatus.complete.rawValue {
            return
        }
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard CVPixelBufferGetPlaneCount(pb) == 2 else { return }
        let w = CVPixelBufferGetWidthOfPlane(pb, 0), h = CVPixelBufferGetHeightOfPlane(pb, 0)
        guard w == width, h == height else { return }
        var out = Data(capacity: w * h * 3 / 2)
        for plane in 0..<2 {
            let base = CVPixelBufferGetBaseAddressOfPlane(pb, plane)!
            let stride = CVPixelBufferGetBytesPerRowOfPlane(pb, plane)
            let rows = CVPixelBufferGetHeightOfPlane(pb, plane)
            let rowBytes = CVPixelBufferGetWidthOfPlane(pb, plane) * (plane == 0 ? 1 : 2)
            for r in 0..<rows {
                out.append(base.advanced(by: r * stride).assumingMemoryBound(to: UInt8.self), count: rowBytes)
            }
        }
        store.set(out)
    }

    private func handleAudio(_ sb: CMSampleBuffer) {
        audioLock.lock(); let fh = audio; audioLock.unlock()
        guard let fh = fh else { return }
        guard let fmt = CMSampleBufferGetFormatDescription(sb),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmt)?.pointee else { return }
        let channels = Int(asbd.mChannelsPerFrame)
        let frames = CMSampleBufferGetNumSamples(sb)
        var out = [Float](repeating: 0, count: frames * 2)
        do {
            try sb.withAudioBufferList { abl, _ in
                let buffers = Array(abl)
                if buffers.count >= 2 {  // non-interleaved: one buffer per channel
                    let l = buffers[0].mData!.assumingMemoryBound(to: Float.self)
                    let r = buffers[1].mData!.assumingMemoryBound(to: Float.self)
                    for i in 0..<frames { out[2 * i] = l[i]; out[2 * i + 1] = r[i] }
                } else if let b = buffers.first, let p = b.mData?.assumingMemoryBound(to: Float.self) {
                    if channels >= 2 {
                        for i in 0..<frames { out[2 * i] = p[i * channels]; out[2 * i + 1] = p[i * channels + 1] }
                    } else {
                        for i in 0..<frames { out[2 * i] = p[i]; out[2 * i + 1] = p[i] }
                    }
                }
            }
        } catch { return }
        out.withUnsafeBufferPointer { buf in
            fh.write(Data(buffer: buf))
        }
    }
}

let opts = parseOptions()
signal(SIGPIPE, SIG_IGN)

let store = FrameStore(black: opts.width, height: opts.height)
let output = Output(store: store, width: opts.width, height: opts.height)

if let fifo = opts.audioFifo {
    // Opening a FIFO for writing blocks until ffmpeg opens it for reading; do it off the main thread.
    Thread {
        if let fh = FileHandle(forWritingAtPath: fifo) {
            output.audioLock.lock(); output.audio = fh; output.audioLock.unlock()
            err("audio fifo open")
        } else {
            err("cannot open audio fifo \(fifo)")
        }
    }.start()
}

// Constant-rate video writer.
let stdoutHandle = FileHandle.standardOutput
let timer = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "sckcap.video"))
timer.schedule(deadline: .now(), repeating: 1.0 / Double(opts.fps), leeway: .milliseconds(2))
timer.setEventHandler {
    let frame = store.get()
    frame.withUnsafeBytes { raw in
        var off = 0
        while off < raw.count {
            let n = write(1, raw.baseAddress!.advanced(by: off), raw.count - off)
            if n <= 0 { err("stdout closed, exiting"); exit(0) }
            off += n
        }
    }
}

Task {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard opts.displayIndex < content.displays.count else { err("no display \(opts.displayIndex)"); exit(1) }
        let display = content.displays[opts.displayIndex]
        let filter = SCContentFilter(display: display, excludingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.width = opts.width
        cfg.height = opts.height
        cfg.pixelFormat = kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(opts.fps))
        cfg.showsCursor = true
        cfg.queueDepth = 5
        if opts.audioFifo != nil {
            cfg.capturesAudio = true
            cfg.sampleRate = 48000
            cfg.channelCount = 2
            cfg.excludesCurrentProcessAudio = true
        }
        let stream = SCStream(filter: filter, configuration: cfg, delegate: output)
        try stream.addStreamOutput(output, type: .screen, sampleHandlerQueue: DispatchQueue(label: "sckcap.screen"))
        if opts.audioFifo != nil {
            try stream.addStreamOutput(output, type: .audio, sampleHandlerQueue: DispatchQueue(label: "sckcap.audio"))
        }
        try await stream.startCapture()
        err("capturing display \(display.width)x\(display.height) -> \(opts.width)x\(opts.height) @ \(opts.fps)")
        timer.resume()
    } catch {
        err("cannot start capture: \(error.localizedDescription)")
        exit(1)
    }
}
dispatchMain()
```

- [ ] **Step 4: Implement sckcap.py**

```python
# tvcast/cast/sckcap.py
"""Build and locate the ScreenCaptureKit helper that gives us video plus system audio."""
import ctypes
import hashlib
import os
import platform
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def source_path():
    return os.path.join(os.path.dirname(HERE), "helpers", "sckcap", "main.swift")


def cache_dir():
    return os.path.expanduser("~/Library/Caches/tvcast")


def supported():
    if platform.system() != "Darwin":
        return False
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return False
    return major >= 13


def fit_size(display_w, display_h, max_w, max_h):
    scale = min(max_w / display_w, max_h / display_h)
    w = int(display_w * scale) // 2 * 2
    h = int(display_h * scale) // 2 * 2
    return w, h


def display_size():
    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGMainDisplayID.restype = ctypes.c_uint32
    cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
    cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
    cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
    cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
    d = cg.CGMainDisplayID()
    return int(cg.CGDisplayPixelsWide(d)), int(cg.CGDisplayPixelsHigh(d))


def ensure_helper(log=lambda m: None):
    """Return the path of a built helper, compiling it if the source changed. None if unavailable."""
    if not supported():
        return None
    src = source_path()
    if not os.path.exists(src):
        return None
    with open(src, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:12]
    out = os.path.join(cache_dir(), f"sckcap-{digest}")
    if os.path.exists(out):
        return out
    swiftc = shutil.which("swiftc")
    if not swiftc:
        log("swiftc not found (install Xcode Command Line Tools for system audio capture)")
        return None
    os.makedirs(cache_dir(), exist_ok=True)
    log("→ building ScreenCaptureKit helper (first run only)…")
    proc = subprocess.run([swiftc, "-O", "-o", out, src], capture_output=True, text=True)
    if proc.returncode != 0:
        log("helper build failed:\n" + proc.stderr[-2000:])
        return None
    return out
```

- [ ] **Step 5: Add `make_sck_factory` to capture.py**

```python
import os
import tempfile


def make_sck_factory(ffmpeg, helper, spec, capture_size):
    cw, ch = capture_size

    def factory():
        tmp = tempfile.mkdtemp(prefix="tvcast-")
        fifo = os.path.join(tmp, "audio.fifo")
        os.mkfifo(fifo)
        helper_proc = subprocess.Popen(
            [helper, "--width", str(cw), "--height", str(ch), "--fps", str(spec.fps), "--audio-fifo", fifo],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        argv = ff.build_argv(ffmpeg, ff.rawpipe_inputs(cw, ch, spec.fps, fifo), spec, has_audio=True)
        cap = start_ffmpeg(argv, stdin=helper_proc.stdout, extra_procs=[helper_proc])
        helper_proc.stdout.close()  # ffmpeg owns the read end now
        orig_stop = cap.stop

        def stop():
            orig_stop()
            shutil.rmtree(tmp, ignore_errors=True)
        cap.stop = stop
        return cap
    factory.description = f"ScreenCaptureKit {cw}x{ch} with system audio"
    return factory
```

(add `import shutil` at the top of capture.py).

- [ ] **Step 6: Wire into cli.py**

Replace the body of `main` between `audio_idx, audio_desc = choose_audio(...)` and `server = StreamServer(...)` with:

```python
    w, h = QUALITY[args.quality]
    spec = ff.VideoSpec(width=w, height=h, fps=args.fps, bitrate=args.bitrate)
    factory = None
    if args.audio == "auto":
        helper = sckcap.ensure_helper(log)
        if helper:
            size = sckcap.fit_size(*sckcap.display_size(), w, h)
            factory = capture.make_sck_factory(ffmpeg, helper, spec, size)
            log(f"→ {factory.description}")
    if factory is None:
        audio_idx, audio_desc = choose_audio(args, devices)
        log(f"→ {audio_desc}")
        factory = capture.make_avfoundation_factory(ffmpeg, screen, audio_idx, spec)
```

and `from . import capture, discovery, ffmpeg as ff, sckcap`. Add `--audio sck` as an explicit way to force the helper (treat `"sck"` like `"auto"` but error instead of falling back when the helper is unavailable).

- [ ] **Step 7: Run tests and compile the helper**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: PASS.
Run: `python3 -c "from tvcast.cast import sckcap; print(sckcap.ensure_helper(print))"`
Expected: prints the build line and a path under `~/Library/Caches/tvcast/`.

- [ ] **Step 8: Verify the helper alone**

Run (5 seconds, 10 frames, then check the ffmpeg-decoded output has both streams and non-silent audio while something plays sound on the Mac, e.g. `say "testing one two three" &`):

```bash
mkfifo /tmp/a.fifo
HELPER=$(python3 -c "from tvcast.cast import sckcap; print(sckcap.ensure_helper())")
( say "testing testing one two three four five six seven eight nine ten" & )
"$HELPER" --width 1108 --height 720 --fps 30 --audio-fifo /tmp/a.fifo 2>/tmp/sck.err | \
  ffmpeg -hide_banner -y -f rawvideo -pix_fmt nv12 -video_size 1108x720 -framerate 30 -i pipe:0 \
  -f f32le -ar 48000 -ac 2 -i /tmp/a.fifo -t 5 -c:v h264_videotoolbox -c:a aac /tmp/sck-test.mp4
ffprobe -hide_banner /tmp/sck-test.mp4 2>&1 | grep Stream
ffmpeg -hide_banner -i /tmp/sck-test.mp4 -af volumedetect -vn -f null - 2>&1 | grep -E 'mean_volume|max_volume'
```

Expected: one h264 stream and one aac stream; `max_volume` well above -91 dB (silence) because `say` was playing.

- [ ] **Step 9: Real run with audio**

Run: `timeout 60 python3 -m tvcast.cast` while a video with sound plays in a browser.
Expected: `→ ScreenCaptureKit ... with system audio`, `TV: PLAYING`, picture and sound on the TV.

- [ ] **Step 10: Commit**

```bash
git add tvcast tests/test_sckcap.py
git commit -m "Add ScreenCaptureKit helper for system audio capture

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write it**

Sections: what it is (two commands), install (`brew install ffmpeg`, `pip install -e .` or `python3 -m tvcast.cast`), quick start (`tvprobe`, then `tvcast`), how it works (probe → capture → serve → launch → watch; the DLNA trick; why Miracast from a Mac is impossible; latency expectations; DRM note), audio (ScreenCaptureKit helper, BlackHole fallback, `--audio`), troubleshooting (Screen Recording permission, TV not found, TV fetches but never plays, firewall/client isolation), tested TVs table (Weier / HiSilicon Hi3751V350, Android 9, DLNA, works, ~2 s), roadmap (Cast, Roku, ADB, browser fallback, Linux), licence MIT. Keep the tvprobe usage table from the original README.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add README

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review

- Spec coverage: pipeline stages 1–5 → Tasks 4–7; audio selection and helper → Task 8; probe fixes → Task 2; error handling (ffmpeg missing, selection, SOAP fault, timeout explanation) → Tasks 6–7; tests per spec section → each task; manual acceptance → Task 8 step 9.
- Placeholders: none. README content is enumerated by section.
- Type consistency: `Target(ip, name, control_url)` used in Tasks 6 and 7; `Capture.read/stop` used by server; `VideoSpec` fields used in Tasks 3, 4, 7, 8; `ensure_helper(log)` signature matches Task 8 usage.
