"""Find DLNA renderers via the probe's SSDP code, and pick the local IP the TV can reach."""
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
    """The address of the interface that routes to the TV (no packets are sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 9))
        return s.getsockname()[0]
    finally:
        s.close()
