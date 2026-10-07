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

    // Lifecycle regressions use idle clients and a source blocked in read.
    final class WaitingSource: MediaSource {
        let reading = DispatchSemaphore(value: 0)
        let stopped = DispatchSemaphore(value: 0)
        private let condition = NSCondition()
        private var ended = false
        private var stops = 0
        private var reads = 0
        var counts: (stops: Int, reads: Int) {
            condition.lock(); defer { condition.unlock() }
            return (stops, reads)
        }
        func read(_ maxBytes: Int) -> Data {
            condition.lock(); defer { condition.unlock() }
            reads += 1
            reading.signal()
            while !ended { condition.wait() }
            return Data()
        }
        func stop() {
            condition.lock()
            stops += 1
            ended = true
            condition.broadcast()
            condition.unlock()
            stopped.signal()
        }
    }
    func connectClient(_ port: UInt16, request: String) -> Int32? {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        var timeout = timeval(tv_sec: 1, tv_usec: 0)
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian
        inet_pton(AF_INET, "127.0.0.1", &address.sin_addr)
        let result = withUnsafePointer(to: &address) { p in
            p.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard result == 0 else { close(fd); return nil }
        let bytes = Array(request.utf8)
        let sent = bytes.withUnsafeBytes { Darwin.send(fd, $0.baseAddress, $0.count, 0) }
        guard sent == bytes.count else { close(fd); return nil }
        return fd
    }
    func connectionClosed(_ fd: Int32) -> Bool {
        var bytes = [UInt8](repeating: 0, count: 1024)
        while true {
            let count = recv(fd, &bytes, bytes.count, 0)
            if count == 0 { return true }
            if count < 0 { return errno == ECONNRESET }
        }
    }

    let source = WaitingSource()
    let blockingServer = StreamServer(makeSource: { source })
    guard let blockingPort = try? blockingServer.start(),
          let idleClient = connectClient(blockingPort, request: "GET /screen.ts HTTP/1.0\r\n"),
          let client = connectClient(blockingPort, request: "GET \(blockingServer.path) HTTP/1.0\r\n\r\n") else {
        print("FAIL - loopback fixture failed to connect"); blockingServer.stop(); return 1
    }
    check(source.reading.wait(timeout: .now() + 2) == .success, "client has an active source")
    blockingServer.stop()
    check(source.stopped.wait(timeout: .now() + 1) == .success, "Stop releases a source blocked in read")
    blockingServer.stop()
    check(source.counts.stops == 1, "repeated Stop disposes the source once")
    check(connectionClosed(client), "Stop closes an established streaming connection")
    check(connectionClosed(idleClient), "Stop releases clients with unfinished headers")
    source.stop() // also release the fixture when running against the unfixed implementation
    close(client)
    close(idleClient)

    let cancelled = StreamServer(makeSource: { WaitingSource() })
    cancelled.stop()
    check((try? cancelled.start()) == nil, "Stop before start cannot reopen a listener")
    cancelled.stop()

    let factoryEntered = DispatchSemaphore(value: 0)
    let factoryMayReturn = DispatchSemaphore(value: 0)
    let lateSource = WaitingSource()
    let late = StreamServer(makeSource: {
        factoryEntered.signal()
        _ = factoryMayReturn.wait(timeout: .now() + 5)
        return lateSource
    })
    if let latePort = try? late.start(),
       let lateClient = connectClient(latePort, request: "GET \(late.path) HTTP/1.0\r\n\r\n") {
        check(factoryEntered.wait(timeout: .now() + 2) == .success, "source factory is in progress")
        let stopReturned = DispatchSemaphore(value: 0)
        DispatchQueue.global().async { late.stop(); stopReturned.signal() }
        check(stopReturned.wait(timeout: .now() + 1) == .success, "Stop does not wait for the source factory")
        factoryMayReturn.signal()
        check(lateSource.stopped.wait(timeout: .now() + 2) == .success, "a source returned after Stop is disposed")
        check(lateSource.counts.reads == 0, "a source returned after Stop is never streamed")
        lateSource.stop()
        close(lateClient)
    } else { check(false, "late-source fixture connects"); factoryMayReturn.signal() }
    late.stop()

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

    // Cancellation before run must not send the initial Play command.
    let cancelledLauncher = FakeLauncher([.playing])
    var serverStopped = false
    let cancelledSession = Session(
        launcher: cancelledLauncher, url: "http://127.0.0.1/screen.ts", log: { _ in },
        shouldStop: { true }, onServerStop: { serverStopped = true })
    check(cancelledSession.run() == 0 && cancelledLauncher.plays == 0 && serverStopped,
          "a cancelled session stops its server without telling the TV to play")

    print(failures == 0 ? "\nSESSION PASS" : "\n\(failures) SESSION FAILURE(S)")
    return failures
}

/// Tiny reference box so injected closures can mutate a captured value.
final class Box<T> { var value: T; init(_ v: T) { value = v } }

/// Capture configuration and output checks (no screen or ffmpeg process).
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

    // A real pipe checks cancellation without launching FFmpeg.
    let pipe = Pipe()
    let reader = CapturePipeReader()
    do {
        try reader.open(pipe.fileHandleForReading)
        try pipe.fileHandleForReading.close()
        try pipe.fileHandleForWriting.write(contentsOf: Data([1, 2, 3, 4]))
    } catch { print("FAIL - pipe fixture: \(error)"); return 1 }
    defer { reader.close(); try? pipe.fileHandleForWriting.close() }
    check(reader.read(2) == Data([1, 2]), "capture read respects its byte limit")
    check(reader.read(2) == Data([3, 4]), "capture reader owns its descriptor")

    let entered = DispatchSemaphore(value: 0)
    let returned = DispatchSemaphore(value: 0)
    let empty = AtomicFlag()
    DispatchQueue.global().async {
        entered.signal()
        empty.set(reader.read(188).isEmpty)
        returned.signal()
    }
    check(entered.wait(timeout: .now() + 1) == .success, "pipe reader starts")
    check(returned.wait(timeout: .now() + 0.1) == .timedOut, "pipe read waits for bytes")
    reader.close()
    // Keep the writer open: cancellation must not depend on FFmpeg exiting.
    check(returned.wait(timeout: .now() + 1) == .success && empty.get(),
          "closing capture output cancels a blocked read")
    reader.close()
    check(reader.read(188).isEmpty, "reads after close return EOF")
    do {
        let other = Pipe()
        try reader.open(other.fileHandleForReading)
        check(false, "closed capture output cannot reopen")
    } catch { check(true, "closed capture output cannot reopen") }

    print(failures == 0 ? "\nCAPTURE PASS" : "\n\(failures) CAPTURE FAILURE(S)")
    return failures
}
