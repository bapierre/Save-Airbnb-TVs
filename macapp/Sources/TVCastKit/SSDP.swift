import Foundation

/// A DLNA MediaRenderer we can cast to: its address, friendly name, and the AVTransport
/// control URL we POST SOAP commands to.
public struct Renderer: Equatable, Hashable, Identifiable, Sendable {
    public let ip: String
    public let name: String
    public let controlURL: URL
    public var id: String { controlURL.absoluteString }

    public init(ip: String, name: String, controlURL: URL) {
        self.ip = ip
        self.name = name
        self.controlURL = controlURL
    }
}

public enum SSDP {
    static let address = "239.255.255.250"
    static let port: UInt16 = 1900
    static let searchTargets = [
        "urn:schemas-upnp-org:device:MediaRenderer:1",
        "urn:schemas-upnp-org:service:AVTransport:1",
    ]

    /// Broadcast an M-SEARCH, collect replies for `timeout` seconds, then fetch and parse
    /// each device description. Returns the renderers that expose an AVTransport service.
    public static func discover(timeout: TimeInterval = 4) -> [Renderer] {
        let locations = search(timeout: timeout)
        var renderers: [String: Renderer] = [:]  // keyed by ip, first win
        for location in locations {
            guard let desc = fetchDescription(location) else { continue }
            guard let control = desc.avTransportControlURL else { continue }
            let ip = location.host ?? control.host ?? "?"
            if renderers[ip] == nil {
                renderers[ip] = Renderer(ip: ip, name: desc.friendlyName ?? "(unnamed renderer)",
                                         controlURL: control)
            }
        }
        return renderers.values.sorted { $0.ip < $1.ip }
    }

    /// Send the M-SEARCH bursts and gather unique LOCATION URLs from the replies.
    static func search(timeout: TimeInterval) -> [URL] {
        let fd = socket(AF_INET, SOCK_DGRAM, 0)
        guard fd >= 0 else { return [] }
        defer { close(fd) }

        var ttl: UInt8 = 2
        setsockopt(fd, IPPROTO_IP, IP_MULTICAST_TTL, &ttl, socklen_t(MemoryLayout<UInt8>.size))
        var tv = timeval(tv_sec: 0, tv_usec: 400_000)
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))

        var dest = sockaddr_in()
        dest.sin_family = sa_family_t(AF_INET)
        dest.sin_port = SSDP.port.bigEndian
        inet_pton(AF_INET, SSDP.address, &dest.sin_addr)

        func sendSearch() {
            for st in searchTargets {
                let msg = """
                M-SEARCH * HTTP/1.1\r
                HOST: \(address):\(port)\r
                MAN: "ssdp:discover"\r
                MX: 2\r
                ST: \(st)\r
                \r

                """
                let bytes = Array(msg.utf8)
                withUnsafePointer(to: &dest) { ptr in
                    ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                        _ = bytes.withUnsafeBytes { raw in
                            sendto(fd, raw.baseAddress, raw.count, 0, sa,
                                   socklen_t(MemoryLayout<sockaddr_in>.size))
                        }
                    }
                }
            }
        }

        sendSearch()
        let deadline = Date().addingTimeInterval(timeout)
        let resendAt = Date().addingTimeInterval(min(1.5, timeout / 2))
        var resent = false
        var locations: [URL] = []
        var seen = Set<String>()
        var buf = [UInt8](repeating: 0, count: 65536)

        while Date() < deadline {
            if !resent && Date() >= resendAt {
                sendSearch()  // a single burst is easy for a busy TV to miss
                resent = true
            }
            let n = recv(fd, &buf, buf.count, 0)
            if n <= 0 { continue }
            let text = String(decoding: buf[0..<n], as: UTF8.self)
            if let loc = Self.header(text, "location"), let url = URL(string: loc),
               !seen.contains(loc) {
                seen.insert(loc)
                locations.append(url)
            }
        }
        return locations
    }

    static func header(_ message: String, _ name: String) -> String? {
        for line in message.split(separator: "\r\n") {
            let parts = line.split(separator: ":", maxSplits: 1)
            if parts.count == 2, parts[0].trimmingCharacters(in: .whitespaces).lowercased() == name {
                return parts[1].trimmingCharacters(in: .whitespaces)
            }
        }
        return nil
    }

    struct Description {
        var friendlyName: String?
        var avTransportControlURL: URL?
    }

    static func fetchDescription(_ location: URL, timeout: TimeInterval = 4) -> Description? {
        guard let data = syncGET(location, timeout: timeout) else { return nil }
        let parser = DescriptionParser(base: location)
        guard parser.parse(data) else { return nil }
        var d = Description()
        d.friendlyName = parser.friendlyName
        if let raw = parser.avTransportControlURL {
            d.avTransportControlURL = URL(string: raw, relativeTo: parser.urlBase ?? location)?.absoluteURL
        }
        return d.avTransportControlURL == nil ? nil : d
    }

    /// Minimal synchronous HTTP GET (device descriptions are tiny and on the LAN).
    static func syncGET(_ url: URL, timeout: TimeInterval) -> Data? {
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.setValue("tvcast/0.1", forHTTPHeaderField: "User-Agent")
        let sem = DispatchSemaphore(value: 0)
        var out: Data?
        URLSession.shared.dataTask(with: req) { data, _, _ in
            out = data
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + timeout + 1)
        return out
    }
}

/// Parses a UPnP device description: friendlyName, URLBase, and the AVTransport controlURL.
final class DescriptionParser: NSObject, XMLParserDelegate {
    let base: URL
    var friendlyName: String?
    var urlBase: URL?
    var avTransportControlURL: String?

    private var path: [String] = []
    private var text = ""
    private var currentServiceType: String?
    private var currentControlURL: String?

    init(base: URL) { self.base = base }

    func parse(_ data: Data) -> Bool {
        let parser = XMLParser(data: data)
        parser.delegate = self
        return parser.parse()
    }

    private func local(_ name: String) -> String {
        name.contains(":") ? String(name.split(separator: ":").last!) : name
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?, attributes attributeDict: [String: String]) {
        let tag = local(elementName)
        path.append(tag)
        text = ""
        if tag == "service" {
            currentServiceType = nil
            currentControlURL = nil
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        text += string
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?) {
        let tag = local(elementName)
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        switch tag {
        case "friendlyName": if friendlyName == nil { friendlyName = value }
        case "URLBase": if !value.isEmpty { urlBase = URL(string: value) }
        case "serviceType": currentServiceType = value
        case "controlURL": currentControlURL = value
        case "service":
            if let st = currentServiceType, st.contains("AVTransport"),
               let ctl = currentControlURL, avTransportControlURL == nil {
                avTransportControlURL = ctl
            }
        default: break
        }
        if !path.isEmpty { path.removeLast() }
        text = ""
    }
}
