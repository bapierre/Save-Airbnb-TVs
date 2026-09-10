import io
import unittest
import urllib.error

from tvcast.cast import launcher as L

CONTROL = "http://192.168.0.115:25826/upnp/service/AVTransport/Control"
OK_BODY = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
           '<s:Body><u:XResponse xmlns:u="x"/></s:Body></s:Envelope>')
FAULT = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault>'
         '<detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>716</errorCode>'
         '<errorDescription>Resource not found</errorDescription></UPnPError></detail>'
         '</s:Fault></s:Body></s:Envelope>')


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_opener(body, status=200):
    calls = []

    def opener(req, timeout=10):
        calls.append(req)
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(body.encode()))
        return FakeResponse(body.encode())
    opener.calls = calls
    return opener


class TestEnvelopes(unittest.TestCase):
    def test_envelope_contains_action_and_escaped_args(self):
        env = L.soap_envelope("AVTransport", "SetAVTransportURI",
                              {"InstanceID": 0, "CurrentURI": "http://x/a?b=1&c=2"})
        self.assertIn('<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">', env)
        self.assertIn("<CurrentURI>http://x/a?b=1&amp;c=2</CurrentURI>", env)
        self.assertIn("<InstanceID>0</InstanceID>", env)

    def test_didl_lite_has_video_item_and_protocol_info(self):
        d = L.didl_lite("http://1.2.3.4:8090/screen.ts", "Mac screen")
        self.assertIn("object.item.videoItem", d)
        self.assertIn('protocolInfo="http-get:*:video/mpeg:', d)
        self.assertIn("<dc:title>Mac screen</dc:title>", d)
        self.assertIn("http://1.2.3.4:8090/screen.ts</res>", d)

    def test_parse_response_and_fault(self):
        body = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                '<u:GetTransportInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
                '<CurrentTransportState>PLAYING</CurrentTransportState>'
                '<CurrentTransportStatus>OK</CurrentTransportStatus>'
                '</u:GetTransportInfoResponse></s:Body></s:Envelope>')
        self.assertEqual(L.parse_soap_response(body)["CurrentTransportState"], "PLAYING")
        self.assertEqual(L.parse_upnp_fault(FAULT), (716, "Resource not found"))
        self.assertEqual(L.parse_soap_response("not xml"), {})


class TestLauncher(unittest.TestCase):
    def test_play_sends_stop_seturi_play(self):
        opener = make_opener(OK_BODY)
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=opener))
        launcher.play("http://1.2.3.4:8090/screen.ts")
        actions = [c.get_header("Soapaction") for c in opener.calls]
        self.assertEqual(actions, ['"urn:schemas-upnp-org:service:AVTransport:1#Stop"',
                                   '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"',
                                   '"urn:schemas-upnp-org:service:AVTransport:1#Play"'])
        self.assertEqual(opener.calls[0].full_url, CONTROL)
        self.assertIn(b"&lt;DIDL-Lite", opener.calls[1].data)

    def test_state_maps_transport_state(self):
        body = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                '<u:GetTransportInfoResponse xmlns:u="u"><CurrentTransportState>STOPPED'
                '</CurrentTransportState></u:GetTransportInfoResponse></s:Body></s:Envelope>')
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=make_opener(body)))
        self.assertEqual(launcher.state(), "STOPPED")

    def test_unknown_state_and_unreachable_tv(self):
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=make_opener(OK_BODY)))
        self.assertEqual(launcher.state(), "UNKNOWN")

        def down(req, timeout=10):
            raise urllib.error.URLError("no route")
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=down))
        self.assertEqual(launcher.state(), "UNKNOWN")
        with self.assertRaises(L.UpnpError):
            launcher.play("http://x/screen.ts")

    def test_fault_raises_upnp_error(self):
        launcher = L.DlnaLauncher(CONTROL, client=L.SoapClient(CONTROL, opener=make_opener(FAULT, status=500)))
        with self.assertRaises(L.UpnpError) as ctx:
            launcher.play("http://x/screen.ts")
        self.assertEqual(ctx.exception.code, 716)
        self.assertIn("Resource not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
