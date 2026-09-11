import Foundation

/// In-module assertions. The Command Line Tools toolchain ships no XCTest, so tests live
/// here where they can see internal symbols, and run via `swift run tvcast-selftest`.
public func runSelfTests() -> Int {
    var failures = 0
    func check(_ cond: Bool, _ name: String) {
        if cond { print("ok   - \(name)") }
        else { failures += 1; print("FAIL - \(name)") }
    }

    let didl = DlnaLauncher.didlLite(url: "http://1.2.3.4:8090/screen.ts", title: "Mac screen")
    check(didl.contains("object.item.videoItem"), "didl has videoItem class")
    check(didl.contains("protocolInfo=\"http-get:*:video/mpeg:"), "didl has protocolInfo")
    check(didl.contains("<dc:title>Mac screen</dc:title>"), "didl has title")
    check(DlnaLauncher.escape("a&b<c>\"") == "a&amp;b&lt;c&gt;&quot;", "xml escaping")

    let stateBody = """
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>\
    <u:GetTransportInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">\
    <CurrentTransportState>PLAYING</CurrentTransportState></u:GetTransportInfoResponse></s:Body></s:Envelope>
    """
    check(DlnaLauncher.parseResponse(stateBody)["CurrentTransportState"] == "PLAYING", "parse transport state")

    let fault = """
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault>\
    <detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>716</errorCode>\
    <errorDescription>Resource not found</errorDescription></UPnPError></detail></s:Fault></s:Body></s:Envelope>
    """
    let f = DlnaLauncher.parseFault(fault)
    check(f.0 == 716 && f.1 == "Resource not found", "parse upnp fault")

    let msg = "HTTP/1.1 200 OK\r\nLOCATION: http://192.168.0.115:25826/desc.xml\r\nST: x\r\n"
    check(SSDP.header(msg, "location") == "http://192.168.0.115:25826/desc.xml", "ssdp header extract")
    check(SSDP.header(msg, "missing") == nil, "ssdp header missing")

    let xml = """
    <?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0">\
    <device><friendlyName>TV</friendlyName><serviceList><service>\
    <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>\
    <controlURL>/upnp/service/AVTransport/Control</controlURL></service></serviceList></device>\
    <URLBase>http://192.168.0.115:25826/</URLBase></root>
    """
    let p = DescriptionParser(base: URL(string: "http://192.168.0.115:25826/desc.xml")!)
    check(p.parse(xml.data(using: .utf8)!), "description parses")
    check(p.friendlyName == "TV", "friendlyName parsed")
    check(p.avTransportControlURL == "/upnp/service/AVTransport/Control", "controlURL parsed")

    print(failures == 0 ? "\nALL PASS" : "\n\(failures) FAILURE(S)")
    return failures
}
