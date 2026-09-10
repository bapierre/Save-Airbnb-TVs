"""tvprobe CLI: fingerprint an unknown TV on the local network."""

import argparse
import concurrent.futures
import ipaddress
import json
import sys

from . import hosts as hostmod
from . import mdns
from . import ssdp
from . import verdict as verdictmod
from . import wifi

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def c(text, color, enabled=True):
    return f"{color}{text}{RESET}" if enabled else text


def log(msg, quiet=False):
    if not quiet:
        print(msg, file=sys.stderr)


def gather(args):
    color = not args.no_color and sys.stdout.isatty()
    quiet = args.json

    # 1. Which subnet are we on
    networks = hostmod.local_networks()
    networks = [n for n in networks if n.version == 4 and not n.is_loopback
                and n.num_addresses <= 65536]
    if args.network:
        try:
            networks = [ipaddress.ip_network(args.network, strict=False)]
        except ValueError:
            print(f"invalid network: {args.network}", file=sys.stderr)
            sys.exit(2)
    if not networks:
        log("could not determine a local IPv4 network", quiet)

    # 2. mDNS
    log(c("→ browsing mDNS…", DIM, color), quiet)
    instances = mdns.browse(timeout=args.timeout)

    # 3. SSDP
    log(c("→ searching SSDP…", DIM, color), quiet)
    ssdp_hits = ssdp.discover(timeout=args.timeout)
    ssdp.describe_all(ssdp_hits)

    # 4. Host discovery
    log(c("→ collecting hosts…", DIM, color), quiet)
    for net in networks:
        hostmod.broadcast_ping(net)
    arp = hostmod.arp_table()

    known_ips = set(arp.keys())
    for entry in instances.values():
        known_ips.update(entry["addresses"])
    known_ips.update(ssdp_hits.keys())

    if args.sweep:
        for net in networks:
            log(c(f"→ sweeping {net}…", DIM, color), quiet)
            known_ips.update(hostmod.sweep(net))
        arp = hostmod.arp_table()

    known_ips = {ip for ip in known_ips
                 if not ip.startswith("127.") and not ip.startswith("169.254.")
                 and not ip.endswith(".255")}

    # 5. Port scan + HTTP fingerprints, in parallel across hosts
    log(c(f"→ probing {len(known_ips)} host(s)…", DIM, color), quiet)
    records = []

    def probe(ip):
        rec = {"ip": ip, "mac": arp.get(ip)}
        if rec["mac"]:
            rec["mac_randomized"] = hostmod.is_randomized_mac(rec["mac"])
        rec["open_ports"] = hostmod.scan_ports(ip, timeout=args.port_timeout)
        ports = set(rec["open_ports"])
        if 8008 in ports:
            rec["cast_info"] = hostmod.fingerprint_cast(ip)
        if 8060 in ports:
            rec["roku_info"] = hostmod.fingerprint_roku(ip)
        if 7000 in ports or 5000 in ports:
            rec["airplay_info"] = hostmod.fingerprint_airplay(ip)
        if 8001 in ports:
            rec["samsung_info"] = hostmod.fingerprint_samsung(ip)
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for rec in pool.map(probe, sorted(known_ips)):
            records.append(rec)

    # 6. Stitch mDNS and SSDP data onto host records
    by_ip = {r["ip"]: r for r in records}
    for entry in instances.values():
        for addr in entry["addresses"]:
            rec = by_ip.setdefault(addr, {"ip": addr, "open_ports": []})
            rec.setdefault("mdns_instances", []).append(entry["instance"])
            rec.setdefault("mdns_services", []).extend(entry["services"])
            txt = entry.get("txt") or {}
            if txt.get("md") and not rec.get("model"):
                rec["model"] = txt["md"]
            if txt.get("fn") and not rec.get("friendly_name"):
                rec["friendly_name"] = txt["fn"]
    for ip, entry in ssdp_hits.items():
        rec = by_ip.setdefault(ip, {"ip": ip, "open_ports": []})
        rec["has_avtransport"] = entry.get("has_avtransport", False)
        if entry.get("friendly_name"):
            rec.setdefault("friendly_name", entry["friendly_name"])
        if entry.get("model"):
            rec.setdefault("model", entry["model"])
        if entry.get("manufacturer"):
            rec.setdefault("manufacturer", entry["manufacturer"])

    records = list(by_ip.values())

    if args.vendor:
        log(c("→ looking up MAC vendors…", DIM, color), quiet)
        for rec in records:
            if rec.get("mac") and not rec.get("mac_randomized"):
                rec["vendor"] = hostmod.mac_vendor(rec["mac"])

    # 7. Wi-Fi Direct
    direct_groups = []
    if not args.no_wifi:
        log(c("→ scanning for Wi-Fi Direct groups…", DIM, color), quiet)
        direct_groups = wifi.find_direct_groups()
    p2p_ok, p2p_reason = wifi.p2p_supported()

    report = verdictmod.build_report(records, direct_groups, p2p_ok, p2p_reason)
    report["hosts"] = records
    return report, color


def render(report, color):
    def col(t, x):
        return c(t, x, color)

    print()
    print(col("TV PROBE REPORT", BOLD))
    print("=" * 60)

    candidates = report["candidates"]
    if candidates:
        print()
        print(col("Candidates", BOLD))
        for i, cand in enumerate(candidates):
            marker = col("★", GREEN) if i == 0 else " "
            name = cand["name"] or col("(unnamed)", DIM)
            print(f"\n {marker} {col(cand['ip'], CYAN)}  {name}")
            if cand["model"]:
                print(f"     model:      {cand['model']}")
            if cand["mac"]:
                print(f"     mac:        {cand['mac']}")
            if cand["transports"]:
                print(f"     transports: {col(', '.join(cand['transports']), GREEN)}")
            if cand["open_ports"]:
                ports = ", ".join(
                    f"{p} ({hostmod.PORTS.get(p, '?')})" for p in cand["open_ports"])
                print(f"     ports:      {ports}")
            if cand["reasons"]:
                print(col(f"     why:        {'; '.join(cand['reasons'])}", DIM))
    else:
        print()
        print(col("No cast-capable candidates found.", YELLOW))

    if report["direct_groups"]:
        print()
        print(col("Wi-Fi Direct groups", BOLD))
        for g in report["direct_groups"]:
            hint = f"  → model hint: {g['model_hint']}" if g["model_hint"] else ""
            print(f"   {col(g['ssid'], YELLOW)}{hint}")

    print()
    print(col("Wi-Fi Direct / Miracast capability", BOLD))
    state = {True: col("yes", GREEN), False: col("no", RED),
             None: col("unknown", YELLOW)}[report["p2p_supported"]]
    print(f"   this machine can act as a Miracast sender: {state}")
    print(col(f"   {report['p2p_reason']}", DIM))

    print()
    print(col("What to do next", BOLD))
    for action in report["actions"]:
        print(f"\n   {col('▸ ' + action['title'], BOLD)}")
        for line in _wrap(action["detail"], 66):
            print(f"     {line}")
    print()


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="tvprobe",
        description="Fingerprint an unknown TV on the local network and report "
                    "which streaming transports it actually supports.")
    p.add_argument("-t", "--timeout", type=float, default=5.0,
                   help="seconds to listen for mDNS and SSDP replies (default 5)")
    p.add_argument("-n", "--network", help="CIDR to scan, e.g. 192.168.0.0/24")
    p.add_argument("-s", "--sweep", action="store_true",
                   help="ping every address in the subnet (slower, finds more)")
    p.add_argument("--port-timeout", type=float, default=1.0,
                   help="TCP connect timeout per port (default 1.0)")
    p.add_argument("--vendor", action="store_true",
                   help="look up MAC vendors online (needs internet)")
    p.add_argument("--no-wifi", action="store_true",
                   help="skip the Wi-Fi Direct scan (it is slow on macOS)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args(argv)

    report, color = gather(args)

    if args.json:
        print(json.dumps(report, indent=2, default=list))
    else:
        render(report, color)
    return 0


if __name__ == "__main__":
    sys.exit(main())
