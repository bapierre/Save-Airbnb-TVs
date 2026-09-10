"""Regressions found on the first real network run."""
import unittest
from unittest import mock

from tvcast.probe import hosts, ssdp, verdict, wifi


class TestHostFilters(unittest.TestCase):
    def test_multicast_and_broadcast_are_excluded(self):
        self.assertTrue(hosts.is_multicast_or_broadcast("224.0.0.251"))
        self.assertTrue(hosts.is_multicast_or_broadcast("239.255.255.250"))
        self.assertTrue(hosts.is_multicast_or_broadcast("192.168.0.255"))
        self.assertFalse(hosts.is_multicast_or_broadcast("192.168.0.115"))

    def test_own_addresses_parses_ifconfig(self):
        out = "en0: flags=8863\n\tinet 192.168.0.190 netmask 0xffffff00 broadcast 192.168.0.255\n"
        with mock.patch.object(hosts.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout=out)
            with mock.patch.object(hosts.platform, "system", return_value="Darwin"):
                self.assertEqual(hosts.own_addresses(), {"192.168.0.190"})


class TestRanking(unittest.TestCase):
    def test_router_with_only_stable_mac_is_not_a_candidate(self):
        router = {"ip": "192.168.0.1", "mac": "00:11:22:33:44:55", "mac_randomized": False,
                  "open_ports": [1900], "friendly_name": "Generic Router", "model": "Generic Router"}
        report = verdict.build_report([router], [], False, "")
        self.assertEqual(report["candidates"], [])

    def test_dlna_tv_is_a_candidate(self):
        tv = {"ip": "192.168.0.115", "mac": "3c:5a:b4:aa:bb:cc", "mac_randomized": False,
              "open_ports": [], "has_avtransport": True,
              "avtransport_control": "http://192.168.0.115:25826/upnp/service/AVTransport/Control",
              "friendly_name": "HiDPTAndroid Hi3751V350_DMR", "model": "Hisilicon MediaRenderer"}
        report = verdict.build_report([tv], [], False, "")
        self.assertEqual(report["candidates"][0]["ip"], "192.168.0.115")
        self.assertIn("dlna", report["candidates"][0]["transports"])
        self.assertEqual(report["candidates"][0]["avtransport_control"], tv["avtransport_control"])
        self.assertTrue(report["actions"])

    def test_model_without_letters_is_ignored(self):
        host = {"ip": "1.2.3.4", "airplay_info": {"model": "0,1,2"}, "model": "Mac14,5"}
        self.assertEqual(verdict.best_model(host), "Mac14,5")

    def test_dial_is_a_transport(self):
        host = {"ip": "1.2.3.4", "open_ports": [], "has_dial": True}
        self.assertIn("dial", verdict.classify_host(host))

    def test_every_transport_has_advice(self):
        for t in verdict.TRANSPORTS:
            if t != "miracast":
                self.assertIn(t, verdict.ADVICE)


class TestSsdpDial(unittest.TestCase):
    def test_description_records_avtransport_control_url(self):
        xml = b"""<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0">
        <device><friendlyName>TV</friendlyName><deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
        <serviceList><service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
        <controlURL>/upnp/service/AVTransport/Control</controlURL></service></serviceList></device>
        <URLBase>http://192.168.0.115:25826/</URLBase></root>"""
        with mock.patch.object(ssdp.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = xml
            info = ssdp.fetch_description("http://192.168.0.115:25826/description.xml")
        self.assertEqual(info["avtransport_control"],
                         "http://192.168.0.115:25826/upnp/service/AVTransport/Control")
        self.assertTrue(info["has_avtransport"])
        self.assertEqual(info["services"].count("urn:schemas-upnp-org:service:AVTransport:1"), 1)

    def test_control_url_falls_back_to_location(self):
        xml = b"""<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
        <serviceList><service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
        <controlURL>AVTransport/ctrl</controlURL></service></serviceList></device></root>"""
        with mock.patch.object(ssdp.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = xml
            info = ssdp.fetch_description("http://10.0.0.5:8080/dmr/desc.xml")
        self.assertEqual(info["avtransport_control"], "http://10.0.0.5:8080/dmr/AVTransport/ctrl")

    def test_dial_flag_from_search_target(self):
        found = {"1.2.3.4": {"ip": "1.2.3.4", "headers": {}, "locations": set(),
                             "search_targets": {"urn:dial-multiscreen-org:service:dial:1"}}}
        ssdp.describe_all(found)
        self.assertTrue(found["1.2.3.4"]["dial"])
        self.assertIsNone(found["1.2.3.4"]["avtransport_control"])


class TestWifiRedaction(unittest.TestCase):
    def test_redacted_ssids_are_reported(self):
        out = ("      Other Local Wi-Fi Networks:\n        <redacted>:\n          PHY Mode: 802.11\n"
               "        <redacted>:\n")
        with mock.patch.object(wifi.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout=out)
            with mock.patch.object(wifi.platform, "system", return_value="Darwin"):
                ssids = wifi.scan_ssids()
        self.assertEqual(ssids, [])
        self.assertTrue(wifi.LAST_SCAN_REDACTED)

    def test_visible_ssids_are_not_flagged(self):
        out = "      Other Local Wi-Fi Networks:\n        DIRECT-ab-TV:\n          PHY Mode: 802.11\n"
        with mock.patch.object(wifi.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout=out)
            with mock.patch.object(wifi.platform, "system", return_value="Darwin"):
                ssids = wifi.scan_ssids()
        self.assertEqual(ssids, ["DIRECT-ab-TV"])
        self.assertFalse(wifi.LAST_SCAN_REDACTED)


if __name__ == "__main__":
    unittest.main()
