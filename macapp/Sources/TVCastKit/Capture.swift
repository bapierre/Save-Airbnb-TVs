import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import CoreVideo

/// Video size and rate for the encoded stream.
public struct VideoSpec: Sendable {
    public var width: Int
    public var height: Int
    public var fps: Int
    public var bitrate: String
    public init(width: Int = 1280, height: Int = 720, fps: Int = 30, bitrate: String = "3M") {
        self.width = width; self.height = height; self.fps = fps; self.bitrate = bitrate
    }
}

public enum CaptureError: Error, CustomStringConvertible {
    case ffmpegMissing
    case launchFailed(String)
    case noDisplay
    public var description: String {
        switch self {
        case .ffmpegMissing: return "ffmpeg not found"
        case .launchFailed(let m): return "capture failed to start: \(m)"
        case .noDisplay: return "no display available to capture"
        }
    }
}

/// Largest even-sized box with the display's aspect that fits inside the target.
public func fitSize(displayW: Int, displayH: Int, maxW: Int, maxH: Int) -> (Int, Int) {
    let scale = min(Double(maxW) / Double(displayW), Double(maxH) / Double(displayH))
    let w = Int(Double(displayW) * scale) / 2 * 2
    let h = Int(Double(displayH) * scale) / 2 * 2
    return (w, h)
}

/// Builds the ffmpeg argv for encoding raw NV12 (stdin) + float PCM (fifo) into low-latency
/// MPEG-TS on stdout. Mirrors the Python build_argv rawpipe path (probing off, burst-capped).
public func ffmpegRawpipeArgv(width: Int, height: Int, spec: VideoSpec, audioFifo: String?) -> [String] {
    let noProbe = ["-probesize", "32", "-analyzeduration", "0", "-fflags", "nobuffer"]
    var a = [String]()
    a += noProbe + ["-f", "rawvideo", "-pix_fmt", "nv12", "-video_size", "\(width)x\(height)",
                    "-framerate", "\(spec.fps)", "-thread_queue_size", "64", "-i", "pipe:0"]
    let hasAudio = audioFifo != nil
    if let fifo = audioFifo {
        a += noProbe + ["-f", "f32le", "-ar", "48000", "-ac", "2",
                        "-thread_queue_size", "1024", "-i", fifo]
    }
    let vf = "scale=\(spec.width):\(spec.height):force_original_aspect_ratio=decrease,"
           + "pad=\(spec.width):\(spec.height):(ow-iw)/2:(oh-ih)/2,format=nv12"
    a += ["-vf", vf, "-c:v", "h264_videotoolbox", "-b:v", spec.bitrate,
          "-maxrate", spec.bitrate, "-bufsize", spec.bitrate, "-g", "\(spec.fps)",
          "-bf", "0", "-realtime", "1"]
    a += hasAudio ? ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"] : ["-an"]
    a += ["-muxdelay", "0", "-muxpreload", "0", "-max_delay", "0", "-flush_packets", "1",
          "-f", "mpegts", "pipe:1"]
    return a
}

/// Holds the latest packed NV12 frame. ScreenCaptureKit only delivers on change, so a timer
/// re-sends this at a constant rate to give ffmpeg a steady frame rate.
private final class FrameStore: @unchecked Sendable {
    private let lock = NSLock()
    private var frame: Data
    init(width: Int, height: Int) {
        var d = Data(repeating: 16, count: width * height)          // Y: black
        d.append(Data(repeating: 128, count: width * height / 2))   // UV: neutral
        frame = d
    }
    func set(_ d: Data) { lock.lock(); frame = d; lock.unlock() }
    func get() -> Data { lock.lock(); defer { lock.unlock() }; return frame }
}

/// A live screen+audio MediaSource that captures with ScreenCaptureKit **in this process**
/// (no external helper, so only one Screen Recording grant) and feeds a bundled ffmpeg,
/// whose MPEG-TS output `read` returns.
public final class ScreenCaptureSource: NSObject, MediaSource, SCStreamOutput, SCStreamDelegate {
    private let ffmpegPath: String
    private let spec: VideoSpec
    private let captureWidth: Int
    private let captureHeight: Int
    private let withAudio: Bool

    private var stream: SCStream?
    private var ffmpeg: Process?
    private var videoIn: FileHandle?      // ffmpeg stdin (raw NV12)
    private var tsOut: FileHandle?        // ffmpeg stdout (MPEG-TS)
    private var audioFifoHandle: FileHandle?
    private var tmpDir: URL?
    private let store: FrameStore
    private var timer: DispatchSourceTimer?
    private let audioLock = NSLock()

    public init(ffmpegPath: String, spec: VideoSpec, captureSize: (Int, Int), withAudio: Bool = true) {
        self.ffmpegPath = ffmpegPath
        self.spec = spec
        self.captureWidth = captureSize.0
        self.captureHeight = captureSize.1
        self.withAudio = withAudio
        self.store = FrameStore(width: captureSize.0, height: captureSize.1)
        super.init()
    }

    public func start() throws {
        signal(SIGPIPE, SIG_IGN)  // writing to a closed ffmpeg pipe must not kill the app

        var fifoPath: String?
        if withAudio {
            let dir = URL(fileURLWithPath: NSTemporaryDirectory())
                .appendingPathComponent("tvcast-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            tmpDir = dir
            let fifo = dir.appendingPathComponent("audio.fifo").path
            guard mkfifo(fifo, 0o600) == 0 else { throw CaptureError.launchFailed("mkfifo") }
            fifoPath = fifo
        }

        // Spawn ffmpeg: video on stdin (a Pipe we write to), audio on the fifo, TS on stdout.
        let ff = Process()
        ff.executableURL = URL(fileURLWithPath: ffmpegPath)
        ff.arguments = ["-hide_banner", "-loglevel", "warning"]
            + ffmpegRawpipeArgv(width: captureWidth, height: captureHeight, spec: spec, audioFifo: fifoPath)
        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        ff.standardInput = stdinPipe
        ff.standardOutput = stdoutPipe
        ff.standardError = FileHandle.nullDevice
        do { try ff.run() } catch { throw CaptureError.launchFailed(error.localizedDescription) }
        ffmpeg = ff
        videoIn = stdinPipe.fileHandleForWriting
        tsOut = stdoutPipe.fileHandleForReading

        // Opening a fifo for writing blocks until ffmpeg opens the read end; do it off-thread.
        if let fifo = fifoPath {
            Thread.detachNewThread { [weak self] in
                let fh = FileHandle(forWritingAtPath: fifo)
                self?.audioLock.lock(); self?.audioFifoHandle = fh; self?.audioLock.unlock()
            }
        }

        try startCapture()
        startVideoTimer()
    }

    private func startCapture() throws {
        let sem = DispatchSemaphore(value: 0)
        var startError: Error?
        Task {
            do {
                let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
                guard let display = content.displays.first else { startError = CaptureError.noDisplay; sem.signal(); return }
                let filter = SCContentFilter(display: display, excludingWindows: [])
                let cfg = SCStreamConfiguration()
                cfg.width = captureWidth
                cfg.height = captureHeight
                cfg.pixelFormat = kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange
                cfg.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(spec.fps))
                cfg.showsCursor = true
                cfg.queueDepth = 5
                if withAudio {
                    cfg.capturesAudio = true
                    cfg.sampleRate = 48000
                    cfg.channelCount = 2
                    cfg.excludesCurrentProcessAudio = true
                }
                let s = SCStream(filter: filter, configuration: cfg, delegate: self)
                try s.addStreamOutput(self, type: .screen, sampleHandlerQueue: DispatchQueue(label: "tvcast.screen"))
                if withAudio {
                    try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: DispatchQueue(label: "tvcast.audio"))
                }
                try await s.startCapture()
                self.stream = s
            } catch {
                startError = error
            }
            sem.signal()
        }
        _ = sem.wait(timeout: .now() + 10)
        if let e = startError { throw CaptureError.launchFailed(String(describing: e)) }
    }

    private func startVideoTimer() {
        let t = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "tvcast.videoOut"))
        t.schedule(deadline: .now(), repeating: 1.0 / Double(spec.fps), leeway: .milliseconds(2))
        t.setEventHandler { [weak self] in
            guard let self, let handle = self.videoIn else { return }
            try? handle.write(contentsOf: self.store.get())
        }
        timer = t
        t.resume()
    }

    // MARK: SCStreamOutput

    public func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        switch type {
        case .screen: handleVideo(sb)
        case .audio: handleAudio(sb)
        default: break
        }
    }

    public func stream(_ stream: SCStream, didStopWithError error: Error) {
        // Leave a black frame flowing; the session/watcher handles recovery upstream.
    }

    private func handleVideo(_ sb: CMSampleBuffer) {
        if let att = CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
           let status = att.first?[.status] as? Int, status != SCFrameStatus.complete.rawValue {
            return
        }
        guard let pb = CMSampleBufferGetImageBuffer(sb) else { return }
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard CVPixelBufferGetPlaneCount(pb) == 2,
              CVPixelBufferGetWidthOfPlane(pb, 0) == captureWidth,
              CVPixelBufferGetHeightOfPlane(pb, 0) == captureHeight else { return }
        var out = Data(capacity: captureWidth * captureHeight * 3 / 2)
        for plane in 0..<2 {
            guard let base = CVPixelBufferGetBaseAddressOfPlane(pb, plane) else { return }
            let stride = CVPixelBufferGetBytesPerRowOfPlane(pb, plane)
            let rows = CVPixelBufferGetHeightOfPlane(pb, plane)
            let rowBytes = CVPixelBufferGetWidthOfPlane(pb, plane) * (plane == 0 ? 1 : 2)
            for r in 0..<rows {
                out.append(base.advanced(by: r * stride).assumingMemoryBound(to: UInt8.self), count: rowBytes)
            }
        }
        store.set(out)
    }

    private func handleAudio(_ sb: CMSampleBuffer) {
        audioLock.lock(); let fh = audioFifoHandle; audioLock.unlock()
        guard let fh else { return }
        guard let fmt = CMSampleBufferGetFormatDescription(sb),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmt)?.pointee else { return }
        let channels = Int(asbd.mChannelsPerFrame)
        let interleaved = (asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved) == 0
        let frames = CMSampleBufferGetNumSamples(sb)
        var out = [Float](repeating: 0, count: frames * 2)
        do {
            try sb.withAudioBufferList { abl, _ in
                let buffers = Array(abl)
                if !interleaved, buffers.count >= 2,
                   let l = buffers[0].mData?.assumingMemoryBound(to: Float.self),
                   let r = buffers[1].mData?.assumingMemoryBound(to: Float.self) {
                    for i in 0..<frames { out[2 * i] = l[i]; out[2 * i + 1] = r[i] }
                } else if !interleaved, let m = buffers.first?.mData?.assumingMemoryBound(to: Float.self) {
                    for i in 0..<frames { out[2 * i] = m[i]; out[2 * i + 1] = m[i] }
                } else if let p = buffers.first?.mData?.assumingMemoryBound(to: Float.self) {
                    if channels >= 2 {
                        for i in 0..<frames { out[2 * i] = p[i * channels]; out[2 * i + 1] = p[i * channels + 1] }
                    } else {
                        for i in 0..<frames { out[2 * i] = p[i]; out[2 * i + 1] = p[i] }
                    }
                }
            }
        } catch { return }
        out.withUnsafeBytes { raw in
            try? fh.write(contentsOf: Data(bytes: raw.baseAddress!, count: raw.count))
        }
    }

    // MARK: MediaSource

    public func read(_ maxBytes: Int) -> Data {
        tsOut?.availableData ?? Data()
    }

    public func stop() {
        timer?.cancel(); timer = nil
        if let s = stream {
            let sem = DispatchSemaphore(value: 0)
            Task { try? await s.stopCapture(); sem.signal() }
            _ = sem.wait(timeout: .now() + 3)
            stream = nil
        }
        ffmpeg?.terminate(); ffmpeg = nil
        try? videoIn?.close(); videoIn = nil
        try? tsOut?.close(); tsOut = nil
        audioLock.lock(); try? audioFifoHandle?.close(); audioFifoHandle = nil; audioLock.unlock()
        if let dir = tmpDir { try? FileManager.default.removeItem(at: dir); tmpDir = nil }
    }
}

/// Locates ffmpeg: bundled in the app first, then common Homebrew/system paths.
public func locateFFmpeg(bundledDir: URL? = nil) -> String? {
    if let dir = bundledDir {
        let p = dir.appendingPathComponent("ffmpeg").path
        if FileManager.default.isExecutableFile(atPath: p) { return p }
    }
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"] {
        if FileManager.default.isExecutableFile(atPath: p) { return p }
    }
    return nil
}
