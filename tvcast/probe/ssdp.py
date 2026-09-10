"""SSDP discovery plus UPnP device-description parsing. Stdlib only.

The important question for casting is not 'does it answer SSDP' but
'does it expose an AVTransport service', which is what actually lets
you push a stream at it. So we fetch and parse the description XML.
"""

import re
import socket
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900

SEARCH_TARGETS = [
    "urn:schemas-upnp-org:device:MediaRenderer:1",
    "urn:schemas-upnp-org:service:AVTransport:1",
    "urn:dial-multiscreen-org:service:dial:1",
    "ssdp:all",
]


def discover(timeout=5.0, targets=None):
    """Send M-SEARCH for each target. Returns {ip: {headers...}}."""
    targets = targets or SEARCH_TARGETS
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.4)

    for st in targets:
        msg = "\r\n".join([
            "M-SEARCH * HTTP/1.1",
            f"HOST: {SSDP_ADDR}:{SSDP_PORT}",
            'MAN: "ssdp:discover"',
            "MX: 2",
            f"ST: {st}",
            "", "",
        ]).encode()
        try:
            sock.sendto(msg, (SSDP_ADDR, SSDP_PORT))
        except OSError:
            pass
        time.sleep(0.1)

    found = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65507)
        except socket.timeout:
            continue
        except OSError:
            break
        headers = {}
        for line in data.decode("utf-8", "replace").split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        ip = addr[0]
        entry = found.setdefault(ip, {"ip": ip, "headers": {}, "locations": set()})
        entry["headers"].update(headers)
        if headers.get("location"):
            entry["locations"].add(headers["location"])
    sock.close()
    return found


def _strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def fetch_description(location, timeout=4.0):
    """Fetch and parse a UPnP device description XML."""
    try:
        req = urllib.request.Request(location, headers={"User-Agent": "tvprobe/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(200000)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    info = {"services": [], "location": location}
    for elem in root.iter():
        tag = _strip_ns(elem.tag)
        if tag == "friendlyName" and "friendly_name" not in info:
            info["friendly_name"] = (elem.text or "").strip()
        elif tag == "manufacturer" and "manufacturer" not in info:
            info["manufacturer"] = (elem.text or "").strip()
        elif tag == "modelName" and "model" not in info:
            info["model"] = (elem.text or "").strip()
        elif tag == "modelNumber" and "model_number" not in info:
            info["model_number"] = (elem.text or "").strip()
        elif tag == "deviceType" and "device_type" not in info:
            info["device_type"] = (elem.text or "").strip()
        elif tag == "serviceType":
            st = (elem.text or "").strip()
            if st:
                info["services"].append(st)

    info["has_avtransport"] = any("AVTransport" in s for s in info["services"])
    info["has_rendering_control"] = any("RenderingControl" in s for s in info["services"])
    return info


def describe_all(found, timeout=4.0):
    """Enrich SSDP hits with parsed description data."""
    for ip, entry in found.items():
        descriptions = []
        for loc in list(entry["locations"])[:4]:
            desc = fetch_description(loc, timeout=timeout)
            if desc:
                descriptions.append(desc)
        entry["descriptions"] = descriptions
        entry["has_avtransport"] = any(d.get("has_avtransport") for d in descriptions)
        names = [d.get("friendly_name") for d in descriptions if d.get("friendly_name")]
        entry["friendly_name"] = names[0] if names else None
        models = [d.get("model") for d in descriptions if d.get("model")]
        entry["model"] = models[0] if models else None
        mfrs = [d.get("manufacturer") for d in descriptions if d.get("manufacturer")]
        entry["manufacturer"] = mfrs[0] if mfrs else None
        if not entry["model"]:
            server = entry["headers"].get("server", "")
            m = re.search(r"([A-Za-z0-9_\-]+/[0-9.]+)", server)
            if m:
                entry["model"] = server.strip()
    return found
