"""Wi-Fi Direct (P2P) group detection.

A Miracast sink advertises a Wi-Fi Direct group that looks like an
ordinary SSID, conventionally named DIRECT-xx-<ModelName>. It usually
only exists while the TV is sitting on its mirroring screen, so a
negative result here means very little unless the TV is waiting.
"""

import platform
import re
import subprocess

DIRECT_RE = re.compile(r"\bDIRECT[-_][A-Za-z0-9]{0,4}[-_]?([A-Za-z0-9 _\-]*)")


def scan_ssids():
    """Return a list of visible SSIDs. macOS and Linux."""
    system = platform.system()
    ssids = []
    if system == "Darwin":
        try:
            out = subprocess.run(
                ["system_profiler", "SPAirPortDataType"],
                capture_output=True, text=True, timeout=45).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        in_other = False
        for line in out.splitlines():
            stripped = line.strip()
            if "Other Local Wi-Fi Networks" in stripped:
                in_other = True
                continue
            if in_other:
                # SSID entries are indented keys ending in a colon
                if stripped.endswith(":") and not stripped.startswith("PHY"):
                    name = stripped[:-1].strip()
                    lowered = name.lower()
                    skip = ("current network information", "awdl0", "en0", "en1",
                            "supported", "interfaces", "software versions",
                            "wi-fi", "status")
                    if name and not any(s in lowered for s in skip):
                        ssids.append(name)
    else:
        for cmd in (["nmcli", "-t", "-f", "SSID", "dev", "wifi"],
                    ["iwlist", "scanning"]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=30).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            if cmd[0] == "nmcli":
                ssids = [l.strip() for l in out.splitlines() if l.strip()]
            else:
                ssids = re.findall(r'ESSID:"(.*?)"', out)
            if ssids:
                break
    return ssids


def find_direct_groups(ssids=None):
    """Filter SSIDs down to plausible Wi-Fi Direct groups."""
    ssids = ssids if ssids is not None else scan_ssids()
    hits = []
    for s in ssids:
        upper = s.upper()
        if upper.startswith("DIRECT-") or upper.startswith("DIRECT_"):
            m = DIRECT_RE.search(s)
            model = (m.group(1).strip() if m and m.group(1) else "")
            hits.append({"ssid": s, "model_hint": model})
        elif any(k in upper for k in ("MIRACAST", "SCREENCAST", "ANYCAST",
                                      "EZCAST", "MIRASCREEN")):
            hits.append({"ssid": s, "model_hint": ""})
    return hits


def p2p_supported():
    """On Linux we can actually check the adapter. On macOS the answer is no."""
    if platform.system() == "Darwin":
        return False, ("macOS exposes no Wi-Fi Direct client mode; a Miracast "
                       "sender cannot be implemented on the Mac itself")
    try:
        out = subprocess.run(["iw", "phy"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None, "could not run `iw phy` to check P2P support"
    has_go = "P2P-GO" in out
    has_client = "P2P-client" in out
    if has_go and has_client:
        return True, "adapter reports P2P-GO and P2P-client modes"
    return False, "adapter does not report P2P-GO/P2P-client modes"
