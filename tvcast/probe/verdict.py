"""Turn raw probe results into a transport verdict and a next action.

The point of tvprobe is not the scan, it is this file: given whatever
came back, say which streaming path is actually available and what to
run next.
"""

TRANSPORTS = ["cast", "airplay", "dlna", "adb", "roku", "samsung", "miracast"]


def classify_host(host):
    """Given an aggregated host record, return a list of available transports."""
    found = []
    ports = set(host.get("open_ports", []))
    services = set()
    for s in host.get("mdns_services", []):
        services.add(s)

    if 8008 in ports or 8009 in ports or any("googlecast" in s for s in services) \
            or host.get("cast_info"):
        found.append("cast")
    if 7000 in ports or any("airplay" in s or "raop" in s for s in services) \
            or host.get("airplay_info"):
        found.append("airplay")
    if host.get("has_avtransport"):
        found.append("dlna")
    if 5555 in ports:
        found.append("adb")
    if 8060 in ports or host.get("roku_info"):
        found.append("roku")
    if 8001 in ports or host.get("samsung_info"):
        found.append("samsung")
    return found


def best_name(host):
    for key in ("cast_info", "roku_info", "samsung_info"):
        info = host.get(key)
        if info and info.get("name"):
            return info["name"]
    if host.get("friendly_name"):
        return host["friendly_name"]
    for inst in host.get("mdns_instances", []):
        return inst.split(".")[0]
    return None


def best_model(host):
    for key in ("cast_info", "roku_info", "samsung_info", "airplay_info"):
        info = host.get(key)
        if info and info.get("model"):
            return info["model"]
    return host.get("model")


def looks_like_tv(host):
    """Heuristic: is this host plausibly a TV rather than a phone or laptop?"""
    score = 0
    reasons = []
    transports = classify_host(host)
    for t in ("cast", "roku", "samsung", "dlna", "adb"):
        if t in transports:
            score += 3
            reasons.append(f"speaks {t}")
    if host.get("mac") and not host.get("mac_randomized", False):
        score += 1
        reasons.append("stable (non-randomized) MAC")
    name = (best_name(host) or "") + " " + (best_model(host) or "")
    lowered = name.lower()
    for kw in ("tv", "bravia", "aquos", "regza", "viera", "roku", "fire",
               "shield", "chromecast", "display", "projector", "monitor"):
        if kw in lowered:
            score += 3
            reasons.append(f"name mentions '{kw}'")
            break
    return score, reasons


ADVICE = {
    "cast": (
        "Google Cast available",
        "Play files with `catt -d {ip} cast video.mp4`, or use VLC's renderer "
        "menu. Full desktop mirroring only works from Chrome's Cast menu."
    ),
    "airplay": (
        "AirPlay available",
        "Mirror natively from the macOS Control Center. This is the lowest "
        "latency option and needs no extra software."
    ),
    "dlna": (
        "DLNA with AVTransport available",
        "Push a live MPEG-TS stream and advertise it as a file. Expect several "
        "seconds of latency. Good for playback, useless for interactive use."
    ),
    "adb": (
        "ADB over network is open",
        "Run `adb connect {ip}:5555` then `adb shell getprop ro.product.model`. "
        "You can install your own receiver APK, which is the most flexible path."
    ),
    "roku": (
        "Roku ECP available",
        "Roku has no ADB and no true mirroring API. Use ECP to launch a channel, "
        "or side-load a private channel for custom playback."
    ),
    "samsung": (
        "Samsung SmartTV websocket available",
        "Tizen, not Android. Use the websocket remote API or DLNA; ADB is not "
        "available without developer mode over port 26101."
    ),
}


def build_report(hosts, direct_groups, p2p_ok, p2p_reason):
    """Assemble the final structured verdict."""
    candidates = []
    for host in hosts:
        score, reasons = looks_like_tv(host)
        transports = classify_host(host)
        if score <= 0 and not transports:
            continue
        candidates.append({
            "ip": host.get("ip"),
            "mac": host.get("mac"),
            "name": best_name(host),
            "model": best_model(host),
            "transports": transports,
            "open_ports": host.get("open_ports", []),
            "score": score,
            "reasons": reasons,
        })
    candidates.sort(key=lambda c: (-c["score"], c["ip"] or ""))

    actions = []
    if candidates:
        top = candidates[0]
        for t in top["transports"]:
            title, detail = ADVICE[t]
            actions.append({
                "transport": t,
                "title": title,
                "detail": detail.format(ip=top["ip"]),
            })

    if direct_groups:
        actions.append({
            "transport": "miracast",
            "title": f"Wi-Fi Direct group visible ({len(direct_groups)} found)",
            "detail": ("The TV is advertising a Miracast group. Note that macOS "
                       "cannot join it: there is no P2P client mode. Use a Linux "
                       "box running gnome-network-displays as a bridge, or join "
                       "the TV to normal Wi-Fi instead."),
        })

    if not candidates and not direct_groups:
        actions.append({
            "transport": None,
            "title": "Nothing found",
            "detail": ("No cast-capable device answered. Most likely the TV is "
                       "asleep, on a different network, or has never been joined "
                       "to Wi-Fi at all. Wake it, open its network settings, and "
                       "confirm it has an IP on this subnet."),
        })

    return {
        "candidates": candidates,
        "direct_groups": direct_groups,
        "p2p_supported": p2p_ok,
        "p2p_reason": p2p_reason,
        "actions": actions,
    }
