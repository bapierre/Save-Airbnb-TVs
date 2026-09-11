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

/// Session/Watcher logic checks with a fake launcher (no TV, no real time).
public func runSessionSelfTest() -> Int {
    var failures = 0
    func check(_ cond: Bool, _ name: String) {
        if cond { print("ok   - \(name)") } else { failures += 1; print("FAIL - \(name)") }
    }

    final class FakeLauncher: Launcher {
        var states: [TransportState]
        var plays = 0
        var nudges = 0
        init(_ s: [TransportState]) { states = s }
        func play(url: String, title: String) throws { plays += 1 }
        func stop() throws {}
        func nudge() throws { nudges += 1 }
        func state() -> TransportState { states.count > 1 ? states.removeFirst() : states[0] }
    }

    // Watcher: never plays -> timeout after the window.
    var w = Watcher(startTimeout: 15)
    check(w.tick(state: .transitioning, now: 0) == .none, "watcher tolerates early transitioning")
    check(w.tick(state: .stopped, now: 16) == .timeout, "watcher times out when never playing")

    // Watcher: relaunch once per window after playing.
    var w2 = Watcher(startTimeout: 15, relaunchWindow: 30)
    _ = w2.tick(state: .playing, now: 1)
    check(w2.tick(state: .stopped, now: 60) == .relaunch, "watcher relaunches after a stop")
    check(w2.tick(state: .stopped, now: 70) == .none, "watcher waits out the relaunch window")

    // Session: plays, sees PLAYING, stops on the stop flag.
    var polls = 0
    var stop = false
    let clockBox = Box(0.0)
    let launcher = FakeLauncher([.transitioning, .playing, .playing])
    let session = Session(
        launcher: launcher, url: "http://m/screen.ts", log: { _ in },
        shouldStop: { stop },
        sleep: { _ in polls += 1; if polls >= 3 { stop = true } },
        clock: { clockBox.value += 2; return clockBox.value })
    let rc = session.run()
    check(rc == 0, "session returns 0 on clean stop")
    check(launcher.plays >= 1, "session issued play")

    // Session: resync triggers a re-play.
    var polls2 = 0
    var stop2 = false
    var resync = true
    let l2 = FakeLauncher([.playing])
    let clock2 = Box(0.0)
    let s2 = Session(
        launcher: l2, url: "http://m/screen.ts", log: { _ in },
        shouldStop: { stop2 },
        sleep: { _ in polls2 += 1; if polls2 >= 4 { stop2 = true } },
        clock: { clock2.value += 2; return clock2.value })
    s2.shouldResync = { resync }
    s2.clearResync = { resync = false }
    _ = s2.run()
    check(l2.plays >= 2, "session re-plays on resync (initial + resync)")

    print(failures == 0 ? "\nSESSION PASS" : "\n\(failures) SESSION FAILURE(S)")
    return failures
}

/// Tiny reference box so injected closures can mutate a captured value.
final class Box<T> { var value: T; init(_ v: T) { value = v } }

/// Pure capture-config checks (no screen, no ffmpeg run) so they pass anywhere.
public func runCaptureSelfTest() -> Int {
    var failures = 0
    func check(_ cond: Bool, _ name: String) {
        if cond { print("ok   - \(name)") } else { failures += 1; print("FAIL - \(name)") }
    }
    check(fitSize(displayW: 3024, displayH: 1964, maxW: 1280, maxH: 720) == (1108, 720), "fitSize wide display")
    check(fitSize(displayW: 1920, displayH: 1080, maxW: 1280, maxH: 720) == (1280, 720), "fitSize 16:9 fills")
    let (w, h) = fitSize(displayW: 1512, displayH: 982, maxW: 1280, maxH: 720)
    check(w % 2 == 0 && h % 2 == 0 && h <= 720, "fitSize dimensions even and bounded")

    let argv = ffmpegRawpipeArgv(width: 1108, height: 720, spec: VideoSpec(), audioFifo: "/tmp/a.fifo")
    check(argv.contains("h264_videotoolbox"), "argv uses hardware encoder")
    check(argv.contains("-maxrate") && argv.contains("-flush_packets"), "argv caps bursts and flushes")
    check(argv.contains("pipe:0") && argv.contains("/tmp/a.fifo"), "argv reads video pipe and audio fifo")
    check(argv.contains("aac"), "argv encodes audio when a fifo is given")
    let videoOnly = ffmpegRawpipeArgv(width: 1108, height: 720, spec: VideoSpec(), audioFifo: nil)
    check(videoOnly.contains("-an") && !videoOnly.contains("aac"), "argv is video-only without a fifo")

    print(failures == 0 ? "\nCAPTURE PASS" : "\n\(failures) CAPTURE FAILURE(S)")
    return failures
}
