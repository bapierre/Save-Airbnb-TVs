import json
import unittest

from tvcast.probe import report


class TestRedact(unittest.TestCase):
    def sample(self):
        return {
            "candidates": [{"ip": "192.168.0.115", "mac": "3c:5a:b4:aa:bb:cc", "name": "TV",
                            "model": "Hisilicon MediaRenderer", "transports": ["dlna"],
                            "avtransport_control": "http://192.168.0.115:25826/c",
                            "open_ports": [], "score": 4, "reasons": ["speaks dlna"]}],
            "hosts": [{"ip": "192.168.0.115", "mac": "3c:5a:b4:aa:bb:cc", "open_ports": []},
                      {"ip": "192.168.0.141", "mac": "2e:00:11:22:33:44", "mac_randomized": True,
                       "open_ports": []},
                      {"ip": "192.168.0.1", "mac": "00:11:22:33:44:55", "open_ports": [1900],
                       "friendly_name": "My Home Router"}],
            "direct_groups": [{"ssid": "DIRECT-ab-Weier TV", "model_hint": "Weier TV"}],
            "own_addresses": ["192.168.0.190"],
            "p2p_supported": False, "p2p_reason": "macOS", "actions": [], "wifi_redacted": False,
        }

    def test_macs_keep_only_the_vendor_prefix(self):
        out = report.redact(self.sample())
        self.assertEqual(out["candidates"][0]["mac"], "3c:5a:b4:xx:xx:xx")
        self.assertEqual(out["hosts"][0]["mac"], "3c:5a:b4:xx:xx:xx")

    def test_randomized_macs_and_own_addresses_are_dropped(self):
        self.assertEqual(report._mask_mac("2e:00:11:22:33:44", randomized=True), "(randomized)")
        self.assertIsNone(report._mask_mac(None))
        out = report.redact(self.sample())
        self.assertNotIn("own_addresses", out)

    def test_non_tv_hosts_are_summarized_not_listed(self):
        out = report.redact(self.sample())
        names = [h.get("friendly_name") for h in out["hosts"]]
        self.assertNotIn("My Home Router", names)
        self.assertEqual(out["other_hosts"], 2)

    def test_direct_group_ssid_keeps_model_hint_only(self):
        out = report.redact(self.sample())
        self.assertEqual(out["direct_groups"][0], {"ssid": "DIRECT-xx-Weier TV", "model_hint": "Weier TV"})

    def test_report_has_tool_metadata_and_is_json(self):
        out = report.redact(self.sample())
        self.assertIn("tvcast_version", out)
        self.assertIn("platform", out)
        json.dumps(out)


if __name__ == "__main__":
    unittest.main()
