"""Tell a TV to play a URL. The MVP ships the DLNA AVTransport launcher.

A launcher has three methods: play(url, title), stop(), state(). Future transports
(Cast, Roku ECP, ADB intents) implement the same three.

XML note: responses are parsed with the stdlib ElementTree. They come from a device on
the LAN that we chose to talk to, and expat does not resolve external entities, so the
usual XXE concern does not apply; a hostile renderer could at worst waste our CPU.
"""
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

SERVICE_NS = "urn:schemas-upnp-org:service:{service}:1"
STATES = {"PLAYING", "STOPPED", "TRANSITIONING", "PAUSED_PLAYBACK", "NO_MEDIA_PRESENT"}


class UpnpError(Exception):
    def __init__(self, code, description, http_status=None):
        super().__init__(f"UPnP error {code}: {description}" if code else description)
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
    """Return the child elements of the first *Response element as {name: text}."""
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
    return (int(code.group(1)) if code else None,
            desc.group(1).strip() if desc else body[:200])


def didl_lite(url, title, mime="video/mpeg"):
    """Metadata for SetAVTransportURI. Some renderers refuse to play without it."""
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
            headers={"Content-Type": 'text/xml; charset="utf-8"',
                     "SOAPAction": f'"{ns}#{action}"'})
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
        except UpnpError as e:
            if e.code is None:
                raise  # unreachable, no point continuing
            # Some renderers fault on Stop when idle; that is fine.
        self._avt("SetAVTransportURI", CurrentURI=url, CurrentURIMetaData=didl_lite(url, title))
        self._avt("Play", Speed="1")

    def stop(self):
        self._avt("Stop")

    def nudge(self):
        """Re-issue Play on an already-playing renderer: a control command with no visible
        effect that some TVs count as activity, holding off their screensaver."""
        self._avt("Play", Speed="1")

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
