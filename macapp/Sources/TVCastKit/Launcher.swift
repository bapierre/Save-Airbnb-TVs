import Foundation

public enum TransportState: String, Sendable {
    case playing = "PLAYING"
    case stopped = "STOPPED"
    case transitioning = "TRANSITIONING"
    case pausedPlayback = "PAUSED_PLAYBACK"
    case noMedia = "NO_MEDIA_PRESENT"
    case unknown = "UNKNOWN"
}

public struct UPnPError: Error, CustomStringConvertible {
    public let code: Int?
    public let detail: String
    public var description: String {
        code.map { "UPnP error \($0): \(detail)" } ?? detail
    }
}

/// Speaks DLNA AVTransport to a TV: play a URL, stop, read state, nudge. Mirrors the
/// Python DlnaLauncher so behaviour against real TVs stays identical.
public struct DlnaLauncher {
    public let controlURL: URL
    let timeout: TimeInterval

    public init(controlURL: URL, timeout: TimeInterval = 10) {
        self.controlURL = controlURL
        self.timeout = timeout
    }

    static let service = "urn:schemas-upnp-org:service:AVTransport:1"

    // MARK: control

    public func play(url: String, title: String = "Mac screen") throws {
        // Some renderers fault on Stop when idle; that is fine, but a network failure is not.
        do { try call("Stop", ["InstanceID": "0"]) }
        catch let e as UPnPError where e.code == nil { throw e }
        catch {}
        try call("SetAVTransportURI", [
            "InstanceID": "0",
            "CurrentURI": url,
            "CurrentURIMetaData": Self.didlLite(url: url, title: title),
        ])
        try call("Play", ["InstanceID": "0", "Speed": "1"])
    }

    public func stop() throws {
        try call("Stop", ["InstanceID": "0"])
    }

    /// Re-issue Play on an already-playing renderer: a control command with no visible
    /// effect that some TVs count as activity, holding off their screensaver.
    public func nudge() throws {
        try call("Play", ["InstanceID": "0", "Speed": "1"])
    }

    public func state() -> TransportState {
        guard let resp = try? call("GetTransportInfo", ["InstanceID": "0"]),
              let raw = resp["CurrentTransportState"] else { return .unknown }
        return TransportState(rawValue: raw) ?? .unknown
    }

    public func position() -> String {
        (try? call("GetPositionInfo", ["InstanceID": "0"]))?["RelTime"] ?? "?"
    }

    // MARK: SOAP

    @discardableResult
    func call(_ action: String, _ args: [(String, String)]) throws -> [String: String] {
        let body = args.map { "<\($0.0)>\(Self.escape($0.1))</\($0.0)>" }.joined()
        let envelope = """
        <?xml version="1.0" encoding="utf-8"?>\
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" \
        s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>\
        <u:\(action) xmlns:u="\(Self.service)">\(body)</u:\(action)></s:Body></s:Envelope>
        """
        var req = URLRequest(url: controlURL, timeoutInterval: timeout)
        req.httpMethod = "POST"
        req.setValue("text/xml; charset=\"utf-8\"", forHTTPHeaderField: "Content-Type")
        req.setValue("\"\(Self.service)#\(action)\"", forHTTPHeaderField: "SOAPAction")
        req.httpBody = envelope.data(using: .utf8)

        let sem = DispatchSemaphore(value: 0)
        var data: Data?
        var status = 0
        var transportError: Error?
        URLSession.shared.dataTask(with: req) { d, resp, err in
            data = d
            status = (resp as? HTTPURLResponse)?.statusCode ?? 0
            transportError = err
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + timeout + 1)

        if let transportError {
            throw UPnPError(code: nil, detail: "cannot reach \(controlURL): \(transportError.localizedDescription)")
        }
        let text = data.map { String(decoding: $0, as: UTF8.self) } ?? ""
        if status >= 400 || status == 0 {
            let fault = Self.parseFault(text)
            throw UPnPError(code: fault.0, detail: fault.1)
        }
        return Self.parseResponse(text)
    }

    // MARK: helpers (overload with array so call sites can pass ordered args)

    func call(_ action: String, _ args: [String: String]) throws -> [String: String] {
        // Ordered so envelopes are stable and testable (InstanceID first).
        let order = ["InstanceID", "CurrentURI", "CurrentURIMetaData", "Speed", "Unit", "Target"]
        let sorted = args.sorted { a, b in
            (order.firstIndex(of: a.key) ?? 99) < (order.firstIndex(of: b.key) ?? 99)
        }
        return try call(action, sorted.map { ($0.key, $0.value) })
    }

    static func escape(_ s: String) -> String {
        s.replacingOccurrences(of: "&", with: "&amp;")
         .replacingOccurrences(of: "<", with: "&lt;")
         .replacingOccurrences(of: ">", with: "&gt;")
         .replacingOccurrences(of: "\"", with: "&quot;")
    }

    static func didlLite(url: String, title: String, mime: String = "video/mpeg") -> String {
        """
        <DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" \
        xmlns:dc="http://purl.org/dc/elements/1.1/" \
        xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" \
        xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">\
        <item id="0" parentID="-1" restricted="1"><dc:title>\(escape(title))</dc:title>\
        <upnp:class>object.item.videoItem</upnp:class>\
        <res protocolInfo="http-get:*:\(mime):DLNA.ORG_OP=00;DLNA.ORG_CI=0;\
        DLNA.ORG_FLAGS=01700000000000000000000000000000">\
        \(escape(url))</res></item></DIDL-Lite>
        """
    }

    static func parseResponse(_ body: String) -> [String: String] {
        let p = ResponseParser()
        return p.parse(body)
    }

    static func parseFault(_ body: String) -> (Int?, String) {
        func between(_ open: String, _ close: String) -> String? {
            guard let a = body.range(of: open), let b = body.range(of: close, range: a.upperBound..<body.endIndex)
            else { return nil }
            return String(body[a.upperBound..<b.lowerBound])
        }
        let code = between("<errorCode>", "</errorCode>").flatMap { Int($0.trimmingCharacters(in: .whitespaces)) }
        let desc = between("<errorDescription>", "</errorDescription>")?.trimmingCharacters(in: .whitespacesAndNewlines)
        return (code, desc ?? String(body.prefix(200)))
    }
}

/// Pulls the child elements of the first *Response element into a dictionary.
final class ResponseParser: NSObject, XMLParserDelegate {
    private var out: [String: String] = [:]
    private var inResponse = false
    private var key: String?
    private var text = ""

    func parse(_ body: String) -> [String: String] {
        guard let data = body.data(using: .utf8) else { return [:] }
        let parser = XMLParser(data: data)
        parser.delegate = self
        parser.parse()
        return out
    }

    private func local(_ name: String) -> String {
        name.contains(":") ? String(name.split(separator: ":").last!) : name
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?, attributes attributeDict: [String: String]) {
        let tag = local(elementName)
        if tag.hasSuffix("Response") { inResponse = true; return }
        if inResponse { key = tag; text = "" }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) { text += string }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?) {
        let tag = local(elementName)
        if tag.hasSuffix("Response") { inResponse = false; key = nil; return }
        if inResponse, let k = key, k == tag {
            out[k] = text.trimmingCharacters(in: .whitespacesAndNewlines)
            key = nil
        }
    }
}
