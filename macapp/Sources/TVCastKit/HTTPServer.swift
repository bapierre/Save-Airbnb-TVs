import Foundation

/// A live byte source for one HTTP client: `read` blocks until data is ready or the stream
/// ends (returns empty), `stop` tears down the underlying capture.
public protocol MediaSource: AnyObject {
    func read(_ maxBytes: Int) -> Data
    func stop()
}

/// Serves a live MPEG-TS stream to a DLNA renderer. The TV sends HEAD, then a ranged GET;
/// it tolerates no Content-Length and no range support as long as the DLNA transfer headers
/// are present. Each GET spawns a fresh MediaSource via the factory.
public final class StreamServer {
    public let path = "/screen.ts"
    public private(set) var port: UInt16 = 0

    private let makeSource: () -> MediaSource
    private let log: (String) -> Void
    private var listenFD: Int32 = -1
    private var accepting = false
    private let chunk = 188 * 64

    static let dlnaHeaders = [
        "transferMode.dlna.org": "Streaming",
        "contentFeatures.dlna.org": "DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=8D500000000000000000000000000000",
        "Accept-Ranges": "none",
    ]

    public init(makeSource: @escaping () -> MediaSource, log: @escaping (String) -> Void = { _ in }) {
        self.makeSource = makeSource
        self.log = log
    }

    /// Bind and start accepting. Returns the bound port (pass port 0 for any free port).
    @discardableResult
    public func start(port requested: UInt16 = 0) throws -> UInt16 {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { throw ServerError.socket }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))

        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = INADDR_ANY  // 0.0.0.0
        addr.sin_port = requested.bigEndian
        let bound = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bound == 0 else { close(fd); throw ServerError.bind }
        guard listen(fd, 4) == 0 else { close(fd); throw ServerError.bind }

        var actual = sockaddr_in()
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        withUnsafeMutablePointer(to: &actual) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { _ = getsockname(fd, $0, &len) }
        }
        port = UInt16(bigEndian: actual.sin_port)
        listenFD = fd
        accepting = true

        Thread.detachNewThread { [weak self] in self?.acceptLoop(fd) }
        return port
    }

    public func stop() {
        accepting = false
        if listenFD >= 0 { close(listenFD); listenFD = -1 }
    }

    private func acceptLoop(_ fd: Int32) {
        while accepting {
            let client = accept(fd, nil, nil)
            if client < 0 { break }
            // A disconnected TV must not raise SIGPIPE and kill the app when we write.
            var on: Int32 = 1
            setsockopt(client, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
            Thread.detachNewThread { [weak self] in self?.handle(client) }
        }
    }

    private func handle(_ client: Int32) {
        defer { close(client) }
        guard let request = readRequestLine(client) else { return }
        let (method, target) = request
        let wantsStream = target.split(separator: "?").first.map(String.init) == path
        log("\(method) \(target)")

        if !wantsStream {
            send(client, "HTTP/1.0 404 Not Found\r\nConnection: close\r\n\r\n")
            return
        }
        var head = "HTTP/1.0 200 OK\r\nContent-Type: video/mpeg\r\n"
        for (k, v) in Self.dlnaHeaders { head += "\(k): \(v)\r\n" }
        head += "Connection: close\r\n\r\n"
        send(client, head)
        if method == "HEAD" { return }

        let source = makeSource()
        var sent = 0
        while true {
            let data = source.read(chunk)
            if data.isEmpty { break }
            if !sendData(client, data) { break }
            sent += data.count
        }
        source.stop()
        log("client disconnected after \(sent) bytes")
    }

    private func readRequestLine(_ client: Int32) -> (String, String)? {
        var bytes = [UInt8]()
        var b: UInt8 = 0
        // Read until end of headers; we only need the request line.
        while bytes.count < 8192 {
            let n = recv(client, &b, 1, 0)
            if n <= 0 { break }
            bytes.append(b)
            if bytes.count >= 4, bytes.suffix(4) == [13, 10, 13, 10] { break }
        }
        let text = String(decoding: bytes, as: UTF8.self)
        guard let first = text.split(separator: "\r\n").first else { return nil }
        let parts = first.split(separator: " ")
        guard parts.count >= 2 else { return nil }
        return (String(parts[0]), String(parts[1]))
    }

    private func send(_ client: Int32, _ s: String) {
        sendData(client, Data(s.utf8))
    }

    @discardableResult
    private func sendData(_ client: Int32, _ data: Data) -> Bool {
        var ok = true
        data.withUnsafeBytes { raw in
            var off = 0
            let base = raw.baseAddress!
            while off < raw.count {
                let n = Darwin.send(client, base + off, raw.count - off, 0)
                if n <= 0 { ok = false; break }
                off += n
            }
        }
        return ok
    }

    public enum ServerError: Error { case socket, bind }
}
