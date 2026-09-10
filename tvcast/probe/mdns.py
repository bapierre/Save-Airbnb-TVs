"""Minimal mDNS/DNS-SD browser. Stdlib only.

We speak just enough of the DNS wire format to send PTR questions to
224.0.0.251:5353 and parse PTR/SRV/A/TXT answers back out.
"""

import socket
import struct
import time

MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353

# Record types we care about
T_A = 1
T_PTR = 12
T_TXT = 16
T_SRV = 33

# Services worth asking about when hunting for a TV.
SERVICES = {
    "_googlecast._tcp.local.": "Google Cast",
    "_airplay._tcp.local.": "AirPlay",
    "_raop._tcp.local.": "AirPlay audio (RAOP)",
    "_androidtvremote2._tcp.local.": "Android TV remote",
    "_amzn-wplay._tcp.local.": "Fire TV",
    "_viziocast._tcp.local.": "Vizio Cast",
    "_spotify-connect._tcp.local.": "Spotify Connect",
    "_dlna._tcp.local.": "DLNA",
    "_http._tcp.local.": "HTTP (generic)",
    "_workstation._tcp.local.": "Workstation",
}


def encode_name(name):
    out = b""
    for label in name.rstrip(".").split("."):
        b = label.encode("utf-8")
        out += bytes([len(b)]) + b
    return out + b"\x00"


def decode_name(data, offset):
    """Decode a (possibly compressed) DNS name. Returns (name, new_offset)."""
    labels = []
    jumped = False
    end_offset = offset
    hops = 0
    while True:
        if offset >= len(data):
            break
        length = data[offset]
        if length == 0:
            offset += 1
            if not jumped:
                end_offset = offset
            break
        if length & 0xC0 == 0xC0:
            # compression pointer
            if offset + 1 >= len(data):
                break
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumped:
                end_offset = offset + 2
            offset = pointer
            jumped = True
            hops += 1
            if hops > 20:
                break
            continue
        offset += 1
        labels.append(data[offset:offset + length].decode("utf-8", "replace"))
        offset += length
        if not jumped:
            end_offset = offset
    return ".".join(labels), end_offset


def build_query(names, unicast_response=True):
    """Build a single DNS query packet carrying one PTR question per name."""
    header = struct.pack("!HHHHHH", 0, 0, len(names), 0, 0, 0)
    body = b""
    for n in names:
        qclass = 1 | (0x8000 if unicast_response else 0)
        body += encode_name(n) + struct.pack("!HH", T_PTR, qclass)
    return header + body


def parse_message(data):
    """Parse a DNS message into a list of (name, rtype, rdata_parsed)."""
    try:
        (_, _, qdcount, ancount, nscount, arcount) = struct.unpack("!HHHHHH", data[:12])
    except struct.error:
        return []
    offset = 12
    for _ in range(qdcount):
        _, offset = decode_name(data, offset)
        offset += 4
    records = []
    total = ancount + nscount + arcount
    for _ in range(total):
        if offset >= len(data):
            break
        name, offset = decode_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, _rclass, _ttl, rdlength = struct.unpack("!HHIH", data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + rdlength]
        rdata_end = offset + rdlength
        parsed = None
        try:
            if rtype == T_A and rdlength == 4:
                parsed = socket.inet_ntoa(rdata)
            elif rtype == T_PTR:
                parsed, _ = decode_name(data, offset)
            elif rtype == T_SRV and rdlength >= 6:
                priority, weight, port = struct.unpack("!HHH", rdata[:6])
                target, _ = decode_name(data, offset + 6)
                parsed = {"port": port, "target": target}
            elif rtype == T_TXT:
                txt = {}
                i = 0
                while i < len(rdata):
                    ln = rdata[i]
                    i += 1
                    chunk = rdata[i:i + ln].decode("utf-8", "replace")
                    i += ln
                    if "=" in chunk:
                        k, v = chunk.split("=", 1)
                        txt[k] = v
                parsed = txt
        except Exception:
            parsed = None
        records.append((name, rtype, parsed))
        offset = rdata_end
    return records


def _make_socket():
    """Bind to 5353 so we catch multicast replies; fall back to ephemeral."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    bound_multicast = False
    try:
        s.bind(("", MDNS_PORT))
        mreq = struct.pack("4sl", socket.inet_aton(MDNS_ADDR), socket.INADDR_ANY)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        bound_multicast = True
    except OSError:
        try:
            s.bind(("", 0))
        except OSError:
            pass
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    return s, bound_multicast


def browse(timeout=4.0, services=None):
    """Browse for services. Returns {instance_name: {...details...}}."""
    names = list(services or SERVICES.keys())
    sock, bound_multicast = _make_socket()
    sock.settimeout(0.4)

    query = build_query(names, unicast_response=not bound_multicast)
    for _ in range(2):
        try:
            sock.sendto(query, (MDNS_ADDR, MDNS_PORT))
        except OSError:
            pass
        time.sleep(0.15)

    instances = {}
    srv_map = {}
    txt_map = {}
    a_map = {}

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(9000)
        except socket.timeout:
            continue
        except OSError:
            break
        for name, rtype, parsed in parse_message(data):
            if parsed is None:
                continue
            if rtype == T_PTR:
                service = name
                instance = parsed
                entry = instances.setdefault(instance, {
                    "instance": instance,
                    "services": set(),
                    "addresses": set(),
                    "port": None,
                    "txt": {},
                    "responder": addr[0],
                })
                entry["services"].add(service)
            elif rtype == T_SRV:
                srv_map[name] = parsed
            elif rtype == T_TXT:
                txt_map[name] = parsed
            elif rtype == T_A:
                a_map.setdefault(name, set()).add(parsed)

    sock.close()

    # Stitch SRV/TXT/A onto the instances
    for instance, entry in instances.items():
        srv = srv_map.get(instance)
        if srv:
            entry["port"] = srv["port"]
            for addr in a_map.get(srv["target"], set()):
                entry["addresses"].add(addr)
            entry["host"] = srv["target"]
        if instance in txt_map:
            entry["txt"] = txt_map[instance]
        if not entry["addresses"] and entry.get("responder"):
            entry["addresses"].add(entry["responder"])

    # SRV records we saw without a matching PTR are still worth reporting
    for name, srv in srv_map.items():
        if name in instances:
            continue
        instances[name] = {
            "instance": name,
            "services": {name.split(".", 1)[1] if "." in name else name},
            "addresses": a_map.get(srv["target"], set()),
            "port": srv["port"],
            "txt": txt_map.get(name, {}),
            "host": srv["target"],
            "responder": None,
        }

    return instances
