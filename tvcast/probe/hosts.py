"""Host discovery and per-host TCP/HTTP fingerprinting. Stdlib only."""

import concurrent.futures
import ipaddress
import json
import platform
import re
import socket
import subprocess
import urllib.error
import urllib.request

# Ports that identify a casting-capable device, and what they mean.
PORTS = {
    5555: "ADB (Android debug bridge)",
    8008: "Google Cast setup",
    8009: "Google Cast TLS",
    8060: "Roku ECP",
    7000: "AirPlay",
    7100: "AirPlay mirroring",
    1900: "SSDP/UPnP",
    3689: "DAAP",
    8080: "HTTP alt",
    9080: "Vendor HTTP",
    10001: "Vendor control",
    5000: "HTTP alt",
    55000: "Samsung legacy remote",
    8001: "Samsung SmartTV WS",
    3000: "LG webOS",
    9741: "Fire TV / vendor",
}

def is_multicast_or_broadcast(ip):
    """True for addresses that can never be a device: multicast, broadcast, garbage."""
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


# Locally-administered bit in the first octet means a randomized MAC,
# which in practice means a phone or laptop, not a TV.
def is_randomized_mac(mac):
    try:
        first = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return False
    return bool(first & 0x02)


def normalize_mac(mac):
    parts = mac.split(":")
    if len(parts) != 6:
        return mac.lower()
    return ":".join(p.zfill(2).lower() for p in parts)


def arp_table():
    """Parse `arp -a` into {ip: mac}. Works on macOS and Linux."""
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    table = {}
    for line in out.splitlines():
        ip_m = re.search(r"\(?(\d+\.\d+\.\d+\.\d+)\)?", line)
        mac_m = re.search(r"\b((?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})\b", line)
        if ip_m and mac_m:
            table[ip_m.group(1)] = normalize_mac(mac_m.group(1))
    return table


def local_networks():
    """Return a list of IPv4Network objects for local interfaces."""
    nets = []
    system = platform.system()
    try:
        out = subprocess.run(["ifconfig"] if system == "Darwin" else ["ip", "-o", "addr"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""

    if system == "Darwin":
        for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-f]+)", out):
            ip, mask_hex = m.group(1), m.group(2)
            if ip.startswith("127."):
                continue
            mask = int(mask_hex, 16)
            prefix = bin(mask).count("1")
            try:
                nets.append(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))
            except ValueError:
                pass
    else:
        for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", out):
            cidr = m.group(1)
            if cidr.startswith("127."):
                continue
            try:
                nets.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                pass
    return nets


def _ping_cmd(target, count=1, timeout=1):
    """ping flags differ by platform: -W is ms on macOS, seconds on Linux,
    and Linux needs -b before it will ping a broadcast address at all."""
    if platform.system() == "Darwin":
        return ["ping", "-c", str(count), "-W", str(int(timeout * 1000)), target]
    return ["ping", "-c", str(count), "-W", str(max(1, int(timeout))),
            "-b", target]


def broadcast_ping(network, count=3):
    """Broadcast ping wakes up the ARP table. Many devices ignore it."""
    bcast = str(network.broadcast_address)
    try:
        subprocess.run(_ping_cmd(bcast, count=count, timeout=2),
                       capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass


def ping_host(ip, timeout=1):
    cmd = _ping_cmd(ip, count=1, timeout=timeout)
    if platform.system() != "Darwin":
        cmd = [a for a in cmd if a != "-b"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout + 2)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sweep(network, workers=128):
    """Ping every host in the subnet. Returns the set that replied."""
    hosts = [str(h) for h in network.hosts()]
    if len(hosts) > 1024:
        hosts = hosts[:1024]
    alive = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ping_host, h): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            if fut.result():
                alive.add(futures[fut])
    return alive


def check_port(ip, port, timeout=1.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def scan_ports(ip, ports=None, timeout=1.0, workers=32):
    ports = ports or list(PORTS.keys())
    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_port, ip, p, timeout): p for p in ports}
        for fut in concurrent.futures.as_completed(futures):
            if fut.result():
                open_ports.append(futures[fut])
    return sorted(open_ports)


def http_get(url, timeout=3.0, limit=100000):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tvprobe/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(limit).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def fingerprint_cast(ip):
    """Chromecast / Cast-builtin devices answer here with a friendly name."""
    body = http_get(f"http://{ip}:8008/setup/eureka_info?params=name,device_info")
    if not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    info = {"name": data.get("name")}
    di = data.get("device_info") or {}
    info["model"] = di.get("model_name")
    info["manufacturer"] = di.get("manufacturer")
    return info


def fingerprint_roku(ip):
    body = http_get(f"http://{ip}:8060/query/device-info")
    if not body or "<device-info" not in body:
        return None
    def tag(name):
        m = re.search(rf"<{name}>(.*?)</{name}>", body, re.S)
        return m.group(1).strip() if m else None
    return {
        "name": tag("friendly-device-name") or tag("user-device-name"),
        "model": tag("model-name"),
        "os": tag("software-version"),
    }


def fingerprint_airplay(ip):
    for port in (7000, 5000):
        body = http_get(f"http://{ip}:{port}/server-info", timeout=2.0)
        if body and ("<plist" in body or "model" in body):
            m = re.search(r"<key>model</key>\s*<string>(.*?)</string>", body)
            return {"model": m.group(1) if m else None, "port": port}
    return None


def fingerprint_samsung(ip):
    body = http_get(f"http://{ip}:8001/api/v2/", timeout=2.0)
    if not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    device = data.get("device") or {}
    return {"name": device.get("name"), "model": device.get("modelName"),
            "os": device.get("OS")}


def mac_vendor(mac, timeout=3.0):
    """Optional online OUI lookup. Requires network; used only with --vendor."""
    prefix = ":".join(mac.split(":")[:3])
    body = http_get(f"https://api.macvendors.com/{prefix}", timeout=timeout)
    if body and "<" not in body and len(body) < 200:
        return body.strip()
    return None
