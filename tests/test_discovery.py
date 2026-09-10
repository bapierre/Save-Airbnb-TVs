import unittest
from unittest import mock

from tvcast.cast import discovery
from tvcast.cast.session import Target


class TestFindRenderers(unittest.TestCase):
    def test_only_entries_with_control_url_become_targets(self):
        found = {
            "192.168.0.115": {"ip": "192.168.0.115", "friendly_name": "HiDPTAndroid",
                              "avtransport_control": "http://192.168.0.115:25826/c"},
            "192.168.0.1": {"ip": "192.168.0.1", "friendly_name": "Router",
                            "avtransport_control": None},
        }
        with mock.patch.object(discovery.ssdp, "discover", return_value=found), \
             mock.patch.object(discovery.ssdp, "describe_all", return_value=found):
            targets = discovery.find_renderers(timeout=0)
        self.assertEqual(targets, [Target("192.168.0.115", "HiDPTAndroid",
                                          "http://192.168.0.115:25826/c")])

    def test_unnamed_renderer_gets_placeholder(self):
        found = {"1.2.3.4": {"ip": "1.2.3.4", "avtransport_control": "http://1.2.3.4/c"}}
        with mock.patch.object(discovery.ssdp, "discover", return_value=found), \
             mock.patch.object(discovery.ssdp, "describe_all", return_value=found):
            self.assertEqual(discovery.find_renderers(timeout=0)[0].name, "(unnamed renderer)")

    def test_local_ip_for_returns_dotted_quad(self):
        ip = discovery.local_ip_for("127.0.0.1")
        self.assertEqual(ip.count("."), 3)


if __name__ == "__main__":
    unittest.main()
