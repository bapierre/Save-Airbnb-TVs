"""Fixture-driven tests. No network required."""

import socket
import struct
import unittest
from unittest import mock


from tvcast.probe import hosts, mdns, ssdp, verdict, wifi


# ---------------------------------------------------------------- mDNS

class TestMdnsWire(unittest.TestCase):
    def test_name_roundtrip(self):
        encoded = mdns.encode_name("_googlecast._tcp.local.")
        name, offset = mdns.decode_name(encoded, 0)
        self.assertEqual(name, "_googlecast._tcp.local")
        self.assertEqual(offset, len(encoded))

    def test_compression_pointer(self):
        # "local" at offset 0, then a name that points back at it
        base = mdns.encode_name("local")
        data = base + b"\x03abc" + struct.pack("!H", 0xC000)
        name, _ = mdns.decode_name(data, len(base))
        self.assertEqual(name, "abc.local")

    def test_pointer_loop_terminates(self):
        # A name that points at itself must not hang
        data = struct.pack("!H", 0xC000)
        name, _ = mdns.decode_name(data, 0)
        self.assertIsInstance(name, str)

    def test_query_structure(self):
        q = mdns.build_query(["_airplay._tcp.local.", "_raop._tcp.local."])
        qdcount = struct.unpack("!H", q[4:6])[0]
        self.assertEqual(qdcount, 2)

    def test_parse_full_response(self):
        """Build a realistic Cast response and parse it back."""
        service = "_googlecast._tcp.local."
        instance = "Chromecast-abc._googlecast._tcp.local."
        target = "abc.local."

        def rr(name, rtype, rdata):
            return (mdns.encode_name(name)
                    + struct.pack("!HHIH", rtype, 1, 120, len(rdata)) + rdata)

        body = b""
        body += rr(service, mdns.T_PTR, mdns.encode_name(instance))
        body += rr(instance, mdns.T_SRV,
                   struct.pack("!HHH", 0, 0, 8009) + mdns.encode_name(target))
        txt = b"\x0amd=Chromecast\x0dfn=Living Room"
        txt = b"".join(bytes([len(x)]) + x for x in
                       [b"md=Chromecast", b"fn=Living Room"])
        body += rr(instance, mdns.T_TXT, txt)
        body += rr(target, mdns.T_A, socket.inet_aton("192.168.0.42"))

        header = struct.pack("!HHHHHH", 0, 0x8400, 0, 4, 0, 0)
        records = mdns.parse_message(header + body)

        types = {r[1] for r in records}
        self.assertEqual(types, {mdns.T_PTR, mdns.T_SRV, mdns.T_TXT, mdns.T_A})

        srv = [r for r in records if r[1] == mdns.T_SRV][0]
        self.assertEqual(srv[2]["port"], 8009)

        txt_rec = [r for r in records if r[1] == mdns.T_TXT][0]
        self.assertEqual(txt_rec[2]["fn"], "Living Room")
        self.assertEqual(txt_rec[2]["md"], "Chromecast")

        a = [r for r in records if r[1] == mdns.T_A][0]
        self.assertEqual(a[2], "192.168.0.42")

    def test_truncated_message_is_safe(self):
        self.assertEqual(mdns.parse_message(b"\x00\x01"), [])
        self.assertEqual(mdns.parse_message(b""), [])


# ---------------------------------------------------------------- SSDP

DESC_XML = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
    <friendlyName>Living Room TV</friendlyName>
    <manufacturer>Sony</manufacturer>
    <modelName>BRAVIA KJ-43</modelName>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
      </service>
      <service>
        <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
      </service>
    </serviceList>
  </device>
</root>"""

ROUTER_XML = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType>
    <friendlyName>Generic Router</friendlyName>
    <manufacturer>TP-Link</manufacturer>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
      </service>
    </serviceList>
  </device>
</root>"""


class TestSsdpDescription(unittest.TestCase):
    def test_media_renderer_has_avtransport(self):
        with mock.patch("urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = \
                DESC_XML.encode()
            info = ssdp.fetch_description("http://192.168.0.42:8080/desc.xml")
        self.assertTrue(info["has_avtransport"])
        self.assertEqual(info["friendly_name"], "Living Room TV")
        self.assertEqual(info["model"], "BRAVIA KJ-43")
        self.assertEqual(info["manufacturer"], "Sony")

    def test_router_is_not_a_renderer(self):
        """The TP-Link router must not be mistaken for a cast target."""
        with mock.patch("urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = \
                ROUTER_XML.encode()
            info = ssdp.fetch_description("http://192.168.0.1:1900/rootDesc.xml")
        self.assertFalse(info["has_avtransport"])

    def test_malformed_xml_returns_none(self):
        with mock.patch("urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = b"<not xml"
            self.assertIsNone(ssdp.fetch_description("http://x/y.xml"))

    def test_unreachable_location_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError):
            self.assertIsNone(ssdp.fetch_description("http://192.0.2.1/y.xml"))


# ---------------------------------------------------------------- ARP

REAL_ARP = """? (169.254.169.254) at (incomplete) on en0 [ethernet]
router (192.168.0.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]
? (192.168.0.115) at 3c:5a:b4:aa:bb:cc on en0 ifscope [ethernet]
? (192.168.0.124) at fa:00:11:22:33:44 on en0 ifscope [ethernet]
? (192.168.0.141) at 2e:00:11:22:33:44 on en0 ifscope [ethernet]
? (192.168.0.167) at 86:00:11:22:33:44 on en0 ifscope [ethernet]
? (192.168.0.208) at 9a:00:11:22:33:44 on en0 ifscope permanent [ethernet]
? (192.168.0.255) at ff:ff:ff:ff:ff:ff on en0 ifscope [ethernet]
mdns.mcast.net (224.0.0.251) at 1:0:5e:0:0:fb on en0 ifscope permanent [ethernet]
"""


class TestArpParsing(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("subprocess.run")
        self.run = patcher.start()
        self.addCleanup(patcher.stop)
        self.run.return_value = mock.Mock(stdout=REAL_ARP)

    def test_parses_real_output(self):
        table = hosts.arp_table()
        self.assertEqual(table["192.168.0.115"], "3c:5a:b4:aa:bb:cc")
        # Short octets must be zero-padded
        self.assertEqual(table["192.168.0.1"], "00:11:22:33:44:55")
        self.assertNotIn("169.254.169.254", table)

    def test_randomized_mac_detection(self):
        """Locally-administered bit set means phone or laptop, not a TV."""
        self.assertFalse(hosts.is_randomized_mac("3c:5a:b4:aa:bb:cc"))
        self.assertFalse(hosts.is_randomized_mac("00:11:22:33:44:55"))
        for randomized in ("2e:00:11:22:33:44", "86:00:11:22:33:44",
                           "9a:00:11:22:33:44", "fa:00:11:22:33:44"):
            self.assertTrue(hosts.is_randomized_mac(randomized), randomized)

    def test_malformed_mac_is_safe(self):
        self.assertFalse(hosts.is_randomized_mac("garbage"))
        self.assertFalse(hosts.is_randomized_mac(""))


# ---------------------------------------------------- macOS interfaces

IFCONFIG = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
	inet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
	inet 192.168.0.208 netmask 0xffffff00 broadcast 192.168.0.255
awdl0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> mtu 1500
	inet 169.254.12.3 netmask 0xffff0000 broadcast 169.254.255.255
"""


class TestNetworkDetection(unittest.TestCase):
    def test_macos_ifconfig(self):
        with mock.patch("platform.system", return_value="Darwin"), \
             mock.patch("subprocess.run",
                        return_value=mock.Mock(stdout=IFCONFIG)):
            nets = hosts.local_networks()
        cidrs = {str(n) for n in nets}
        self.assertIn("192.168.0.0/24", cidrs)
        self.assertNotIn("127.0.0.0/8", cidrs)


# ------------------------------------------------------------ Wi-Fi

AIRPORT_OUTPUT = """      Software Versions:
      Interfaces:
        en0:
          Card Type: AirPort Extreme
          Status: Connected
          Current Network Information:
            TP-Link_65D5_5G:
              PHY Mode: 802.11ax
          Other Local Wi-Fi Networks:
            DIRECT-4gMSM-AndroidTV:
              PHY Mode: 802.11n
              Channel: 6
            Neighbour Wifi:
              PHY Mode: 802.11ac
            aterm-3f2a-g:
              PHY Mode: 802.11n
        awdl0:
          Status: Connected
"""

NO_DIRECT_OUTPUT = """      Interfaces:
        en0:
          Other Local Wi-Fi Networks:
            Neighbour Wifi:
              PHY Mode: 802.11ac
            aterm-3f2a-g:
              PHY Mode: 802.11n
        awdl0:
          Status: Connected
"""


class TestWifiDirect(unittest.TestCase):
    def test_finds_direct_group_and_model_hint(self):
        with mock.patch("platform.system", return_value="Darwin"), \
             mock.patch("subprocess.run",
                        return_value=mock.Mock(stdout=AIRPORT_OUTPUT)):
            ssids = wifi.scan_ssids()
            groups = wifi.find_direct_groups(ssids)
        self.assertIn("DIRECT-4gMSM-AndroidTV", ssids)
        self.assertEqual(len(groups), 1)
        self.assertIn("AndroidTV", groups[0]["model_hint"])

    def test_no_false_positive(self):
        with mock.patch("platform.system", return_value="Darwin"), \
             mock.patch("subprocess.run",
                        return_value=mock.Mock(stdout=NO_DIRECT_OUTPUT)):
            groups = wifi.find_direct_groups(wifi.scan_ssids())
        self.assertEqual(groups, [])

    def test_ezcast_style_names_caught(self):
        groups = wifi.find_direct_groups(["EZCast-A2B3", "MiraScreen_1122"])
        self.assertEqual(len(groups), 2)

    def test_macos_never_claims_p2p(self):
        with mock.patch("platform.system", return_value="Darwin"):
            ok, reason = wifi.p2p_supported()
        self.assertFalse(ok)
        self.assertIn("no Wi-Fi Direct", reason)


# ---------------------------------------------------------- verdict

class TestVerdict(unittest.TestCase):
    def test_cast_device_classified(self):
        host = {"ip": "192.168.0.42", "open_ports": [8008, 8009],
                "cast_info": {"name": "Living Room TV", "model": "Chromecast"}}
        self.assertIn("cast", verdict.classify_host(host))
        self.assertEqual(verdict.best_name(host), "Living Room TV")

    def test_adb_device_classified(self):
        host = {"ip": "192.168.0.50", "open_ports": [5555]}
        self.assertIn("adb", verdict.classify_host(host))

    def test_dlna_requires_avtransport(self):
        renderer = {"ip": "1.2.3.4", "open_ports": [1900], "has_avtransport": True}
        router = {"ip": "1.2.3.1", "open_ports": [1900], "has_avtransport": False}
        self.assertIn("dlna", verdict.classify_host(renderer))
        self.assertNotIn("dlna", verdict.classify_host(router))

    def test_tv_outranks_phone(self):
        tv = {"ip": "192.168.0.42", "mac": "3c:5a:b4:aa:bb:cc",
              "mac_randomized": False, "open_ports": [8008],
              "cast_info": {"name": "Bedroom TV", "model": "Chromecast"}}
        phone = {"ip": "192.168.0.141", "mac": "2e:00:11:22:33:44",
                 "mac_randomized": True, "open_ports": []}
        report = verdict.build_report([tv, phone], [], False, "macOS")
        self.assertEqual(report["candidates"][0]["ip"], "192.168.0.42")

    def test_empty_network_gives_useful_advice(self):
        report = verdict.build_report([], [], False, "macOS")
        self.assertEqual(report["candidates"], [])
        self.assertIn("Nothing found", report["actions"][0]["title"])

    def test_direct_group_produces_miracast_warning(self):
        report = verdict.build_report(
            [], [{"ssid": "DIRECT-xx-TV", "model_hint": "TV"}], False, "macOS")
        titles = " ".join(a["title"] for a in report["actions"])
        detail = " ".join(a["detail"] for a in report["actions"])
        self.assertIn("Wi-Fi Direct", titles)
        self.assertIn("macOS cannot join", detail)

    def test_advice_interpolates_ip(self):
        host = {"ip": "192.168.0.50", "open_ports": [5555],
                "mac": "3c:5a:b4:aa:bb:cc", "mac_randomized": False}
        report = verdict.build_report([host], [], False, "macOS")
        adb_action = [a for a in report["actions"] if a["transport"] == "adb"][0]
        self.assertIn("192.168.0.50:5555", adb_action["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
