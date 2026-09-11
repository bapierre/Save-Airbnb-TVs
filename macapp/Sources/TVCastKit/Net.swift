import Foundation

/// The local IP of the interface that routes to `targetIP` (no packets are sent). Used to
/// build the stream URL the TV fetches from this Mac.
public func localIP(reaching targetIP: String) -> String? {
    let fd = socket(AF_INET, SOCK_DGRAM, 0)
    guard fd >= 0 else { return nil }
    defer { close(fd) }
    var dest = sockaddr_in()
    dest.sin_family = sa_family_t(AF_INET)
    dest.sin_port = UInt16(9).bigEndian
    inet_pton(AF_INET, targetIP, &dest.sin_addr)
    let ok = withUnsafePointer(to: &dest) { ptr in
        ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    guard ok == 0 else { return nil }
    var local = sockaddr_in()
    var len = socklen_t(MemoryLayout<sockaddr_in>.size)
    let got = withUnsafeMutablePointer(to: &local) { ptr in
        ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &len) }
    }
    guard got == 0 else { return nil }
    var buf = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
    inet_ntop(AF_INET, &local.sin_addr, &buf, socklen_t(INET_ADDRSTRLEN))
    return String(cString: buf)
}

/// A tiny thread-safe boolean for cross-thread signals (stop, resync).
public final class AtomicFlag: @unchecked Sendable {
    private var value: Bool
    private let lock = NSLock()
    public init(_ v: Bool = false) { value = v }
    public func set(_ v: Bool) { lock.lock(); value = v; lock.unlock() }
    public func get() -> Bool { lock.lock(); defer { lock.unlock() }; return value }
}
