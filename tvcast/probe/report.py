"""Turn a probe result into a shareable report with identifying details removed.

Contributors paste this into TV reports. It keeps what helps compare TVs (vendor prefix
of the MAC, model strings, ports, services) and drops what identifies a home (full MACs,
the Mac's own addresses, routers and phones, Wi-Fi Direct group suffixes).
"""
import platform
import re

from .. import __version__


def _mask_mac(mac, randomized=False):
    if not mac:
        return None
    if randomized:
        return "(randomized)"
    parts = mac.split(":")
    if len(parts) != 6:
        return "(invalid)"
    return ":".join(parts[:3] + ["xx", "xx", "xx"])


def _mask_ssid(ssid):
    return re.sub(r"^(DIRECT[-_])[A-Za-z0-9]{1,4}([-_])", r"\1xx\2", ssid)


def redact(report):
    candidate_ips = {c["ip"] for c in report.get("candidates", [])}
    out = {
        "tvcast_version": __version__,
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "candidates": [],
        "hosts": [],
        "direct_groups": [],
        "p2p_supported": report.get("p2p_supported"),
        "wifi_redacted": report.get("wifi_redacted", False),
        "actions": [a.get("transport") for a in report.get("actions", [])],
    }
    for c in report.get("candidates", []):
        c = dict(c)
        c["mac"] = _mask_mac(c.get("mac"))
        out["candidates"].append(c)
    other = 0
    for h in report.get("hosts", []):
        if h.get("ip") in candidate_ips:
            h = dict(h)
            h["mac"] = _mask_mac(h.get("mac"), h.get("mac_randomized", False))
            out["hosts"].append(h)
        else:
            other += 1
    out["other_hosts"] = other
    for g in report.get("direct_groups", []):
        out["direct_groups"].append({"ssid": _mask_ssid(g.get("ssid", "")),
                                     "model_hint": g.get("model_hint", "")})
    return out
