import Foundation

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
    case helperMissing
    case launchFailed(String)
    public var description: String {
        switch self {
        case .ffmpegMissing: return "ffmpeg not found"
        case .helperMissing: return "the ScreenCaptureKit helper (sckcap) was not found"
        case .launchFailed(let m): return "capture failed to start: \(m)"
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

/// A live screen+audio MediaSource: the sckcap helper feeds NV12 video and PCM audio into
/// ffmpeg, which emits MPEG-TS that `read` returns. Reuses the exact pipeline proven in the
/// Python build.
public final class ScreenCaptureSource: MediaSource {
    private let ffmpegPath: String
    private let helperPath: String
    private let spec: VideoSpec
    private let captureSize: (Int, Int)
    private let withAudio: Bool

    private var helper: Process?
    private var ffmpeg: Process?
    private var out: FileHandle?
    private var tmpDir: URL?

    public init(ffmpegPath: String, helperPath: String, spec: VideoSpec,
                captureSize: (Int, Int), withAudio: Bool = true) {
        self.ffmpegPath = ffmpegPath
        self.helperPath = helperPath
        self.spec = spec
        self.captureSize = captureSize
        self.withAudio = withAudio
    }

    public func start() throws {
        let (cw, ch) = captureSize
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

        var helperArgs = ["--width", "\(cw)", "--height", "\(ch)", "--fps", "\(spec.fps)"]
        if let fifo = fifoPath { helperArgs += ["--audio-fifo", fifo] }
        let helper = Process()
        helper.executableURL = URL(fileURLWithPath: helperPath)
        helper.arguments = helperArgs
        let helperOut = Pipe()
        helper.standardOutput = helperOut
        helper.standardError = FileHandle.nullDevice

        let ffmpeg = Process()
        ffmpeg.executableURL = URL(fileURLWithPath: ffmpegPath)
        ffmpeg.arguments = ["-hide_banner", "-loglevel", "warning"]
            + ffmpegRawpipeArgv(width: cw, height: ch, spec: spec, audioFifo: fifoPath)
        ffmpeg.standardInput = helperOut       // helper NV12 -> ffmpeg stdin
        let tsOut = Pipe()
        ffmpeg.standardOutput = tsOut
        ffmpeg.standardError = FileHandle.nullDevice

        do {
            try helper.run()
            try ffmpeg.run()
        } catch {
            throw CaptureError.launchFailed(error.localizedDescription)
        }
        self.helper = helper
        self.ffmpeg = ffmpeg
        self.out = tsOut.fileHandleForReading
    }

    public func read(_ maxBytes: Int) -> Data {
        guard let out else { return Data() }
        return out.availableData  // blocks until data or EOF (empty)
    }

    public func stop() {
        ffmpeg?.terminate()
        helper?.terminate()
        ffmpeg = nil
        helper = nil
        try? out?.close()
        out = nil
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
