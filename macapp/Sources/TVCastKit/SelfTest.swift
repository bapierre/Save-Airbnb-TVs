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

/// Live-server check: start the server with a fixed-bytes source, GET over loopback,
/// verify the DLNA headers and that the whole payload streams through. Returns failures.
public func runServerSelfTest() -> Int {
    var failures = 0
    func check(_ cond: Bool, _ name: String) {
        if cond { print("ok   - \(name)") } else { failures += 1; print("FAIL - \(name)") }
    }

    final class FixedSource: MediaSource {
        var buf: Data
        var stopped = false
        init(_ d: Data) { buf = d }
        func read(_ maxBytes: Int) -> Data {
            if buf.isEmpty { return Data() }
            let n = min(maxBytes, buf.count)
            let head = buf.prefix(n)
            buf.removeFirst(n)
            return Data(head)
        }
        func stop() { stopped = true }
    }

    let payload = Data(repeating: 0x47, count: 188 * 100)
    var made: [FixedSource] = []
    let server = StreamServer(makeSource: { let s = FixedSource(payload); made.append(s); return s })
    guard let port = try? server.start(port: 0) else {
        print("FAIL - server did not start"); return 1
    }
    defer { server.stop() }

    let sem = DispatchSemaphore(value: 0)
    var body: Data?
    var contentType: String?
    var transferMode: String?
    var url = URLRequest(url: URL(string: "http://127.0.0.1:\(port)/screen.ts")!)
    url.timeoutInterval = 5
    URLSession.shared.dataTask(with: url) { data, resp, _ in
        body = data
        if let http = resp as? HTTPURLResponse {
            contentType = http.value(forHTTPHeaderField: "Content-Type")
            transferMode = http.value(forHTTPHeaderField: "transferMode.dlna.org")
        }
        sem.signal()
    }.resume()
    _ = sem.wait(timeout: .now() + 6)

    check(contentType == "video/mpeg", "server Content-Type is video/mpeg")
    check(transferMode == "Streaming", "server sends DLNA transferMode header")
    check(body?.count == payload.count, "server streamed the full payload")
    check(made.first?.stopped == true, "server stopped the source on disconnect")

    // 404 for an unknown path
    let sem2 = DispatchSemaphore(value: 0)
    var status = 0
    URLSession.shared.dataTask(with: URL(string: "http://127.0.0.1:\(port)/nope")!) { _, resp, _ in
        status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        sem2.signal()
    }.resume()
    _ = sem2.wait(timeout: .now() + 6)
    check(status == 404, "server 404s unknown path")

    print(failures == 0 ? "\nSERVER PASS" : "\n\(failures) SERVER FAILURE(S)")
    return failures
}
