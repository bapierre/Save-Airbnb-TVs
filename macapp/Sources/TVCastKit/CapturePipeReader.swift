import Foundation

/// A capture-output pipe whose blocked reader can be cancelled from another thread.
/// A read retains its handle until it returns, preventing close/reuse races during Stop.
final class CapturePipeReader {
    private let lock = NSLock()
    private var handle: FileHandle?
    private var closed = false

    func open(_ handle: FileHandle) throws {
        lock.lock(); defer { lock.unlock() }
        guard !closed, self.handle == nil else { throw POSIXError(.EBADF) }
        let copy = dup(handle.fileDescriptor)
        guard copy >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EBADF) }
        self.handle = FileHandle(fileDescriptor: copy, closeOnDealloc: true)
    }

    func read(_ maxBytes: Int) -> Data {
        guard maxBytes > 0, let reader = lock.withLock({ handle }) else { return Data() }
        defer { withExtendedLifetime(reader) {} }
        var pollFD = pollfd(fd: reader.fileDescriptor, events: Int16(POLLIN), revents: 0)
        while !lock.withLock({ closed }) {
            let ready = poll(&pollFD, 1, 100)
            if ready < 0 {
                if errno == EINTR { continue }
                return Data()
            }
            if ready == 0 { continue }
            if lock.withLock({ closed }) { return Data() }
            var bytes = [UInt8](repeating: 0, count: maxBytes)
            let count = Darwin.read(reader.fileDescriptor, &bytes, bytes.count)
            if count < 0 && errno == EINTR { continue }
            return count > 0 ? Data(bytes.prefix(count)) : Data()
        }
        return Data()
    }

    func close() {
        lock.withLock {
            closed = true
            handle = nil
        }
    }
}
