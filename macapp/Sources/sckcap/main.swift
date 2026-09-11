// sckcap: ScreenCaptureKit capture helper for tvcast.
//
// Emits the main display as raw NV12 frames on stdout at a constant frame rate, and
// system audio as interleaved float32 stereo 48 kHz PCM on a named pipe. ffmpeg reads
// both. No virtual audio driver needed. Requires macOS 13+ and Screen Recording
// permission for the process that launches it (the same permission ffmpeg needs).
//
// Build: swiftc -O -o sckcap main.swift
// Usage: sckcap --width W --height H --fps N [--audio-fifo PATH] [--display-index 0]
import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

struct Options {
    var width = 1280
    var height = 720
    var fps = 30
    var audioFifo: String? = nil
    var displayIndex = 0
}

func err(_ s: String) {
    FileHandle.standardError.write("sckcap: \(s)\n".data(using: .utf8)!)
}

func parseOptions() -> Options {
    var o = Options()
    var args = Array(CommandLine.arguments.dropFirst())
    func next() -> String { args.isEmpty ? "" : args.removeFirst() }
    while !args.isEmpty {
        let a = args.removeFirst()
        switch a {
        case "--width": o.width = Int(next()) ?? o.width
        case "--height": o.height = Int(next()) ?? o.height
        case "--fps": o.fps = Int(next()) ?? o.fps
        case "--audio-fifo": o.audioFifo = next()
        case "--display-index": o.displayIndex = Int(next()) ?? 0
        default:
            err("unknown option \(a)")
            exit(2)
        }
    }
    return o
}

/// Holds the most recent NV12 frame. SCK only delivers frames when the screen changes,
/// so the writer re-sends this at a fixed rate to give ffmpeg a constant frame rate.
final class FrameStore {
    private let lock = NSLock()
    private var frame: Data

    init(blackWidth width: Int, height: Int) {
        var d = Data(repeating: 16, count: width * height)          // Y: black
        d.append(Data(repeating: 128, count: width * height / 2))   // UV: neutral
        frame = d
    }

    func set(_ d: Data) { lock.lock(); frame = d; lock.unlock() }
    func get() -> Data { lock.lock(); defer { lock.unlock() }; return frame }
}

final class Output: NSObject, SCStreamOutput, SCStreamDelegate {
    let store: FrameStore
    let width: Int
    let height: Int
    private let audioLock = NSLock()
    private var audio: FileHandle?
    private var loggedAudioFormat = false

    init(store: FrameStore, width: Int, height: Int) {
        self.store = store
        self.width = width
        self.height = height
    }

    func setAudio(_ fh: FileHandle) {
        audioLock.lock(); audio = fh; audioLock.unlock()
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        switch type {
        case .screen: handleVideo(sb)
        case .audio: handleAudio(sb)
        default: break
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        err("stream stopped: \(error.localizedDescription)")
        exit(1)
    }

    private func handleVideo(_ sb: CMSampleBuffer) {
        // Skip "idle" notifications that carry no fresh image.
        if let attachments = CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
           let status = attachments.first?[.status] as? Int,
           status != SCFrameStatus.complete.rawValue {
            return
        }
        guard let pb = CMSampleBufferGetImageBuffer(sb) else { return }
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard CVPixelBufferGetPlaneCount(pb) == 2,
              CVPixelBufferGetWidthOfPlane(pb, 0) == width,
              CVPixelBufferGetHeightOfPlane(pb, 0) == height else { return }
        var out = Data(capacity: width * height * 3 / 2)
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
        audioLock.lock(); let fh = audio; audioLock.unlock()
        guard let fh = fh else { return }
        guard let fmt = CMSampleBufferGetFormatDescription(sb),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmt)?.pointee else { return }
        let channels = Int(asbd.mChannelsPerFrame)
        let interleaved = (asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved) == 0
        let frames = CMSampleBufferGetNumSamples(sb)
        if !loggedAudioFormat {
            loggedAudioFormat = true
            err("audio: \(Int(asbd.mSampleRate)) Hz, \(channels) ch, \(interleaved ? "interleaved" : "planar"), \(asbd.mBitsPerChannel)-bit")
        }
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
                        for i in 0..<frames {
                            out[2 * i] = p[i * channels]
                            out[2 * i + 1] = p[i * channels + 1]
                        }
                    } else {
                        for i in 0..<frames { out[2 * i] = p[i]; out[2 * i + 1] = p[i] }
                    }
                }
            }
        } catch {
            return
        }
        out.withUnsafeBufferPointer { buf in
            fh.write(Data(buffer: buf))
        }
    }
}

let opts = parseOptions()
signal(SIGPIPE, SIG_IGN)

let store = FrameStore(blackWidth: opts.width, height: opts.height)
let output = Output(store: store, width: opts.width, height: opts.height)
// The stream must outlive the task that starts it, or SCK silently stops delivering.
var activeStream: SCStream?

if let fifo = opts.audioFifo {
    // Opening a FIFO for writing blocks until ffmpeg opens it for reading; do it off the main thread.
    Thread {
        if let fh = FileHandle(forWritingAtPath: fifo) {
            output.setAudio(fh)
            err("audio fifo open")
        } else {
            err("cannot open audio fifo \(fifo)")
        }
    }.start()
}

// Constant-rate video writer on its own queue.
let timer = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "sckcap.video"))
timer.schedule(deadline: .now(), repeating: 1.0 / Double(opts.fps), leeway: .milliseconds(2))
timer.setEventHandler {
    let frame = store.get()
    frame.withUnsafeBytes { raw in
        var off = 0
        while off < raw.count {
            let n = write(1, raw.baseAddress!.advanced(by: off), raw.count - off)
            if n <= 0 {
                err("stdout closed, exiting")
                exit(0)
            }
            off += n
        }
    }
}

Task {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard opts.displayIndex < content.displays.count else {
            err("no display at index \(opts.displayIndex) (have \(content.displays.count))")
            exit(1)
        }
        let display = content.displays[opts.displayIndex]
        let filter = SCContentFilter(display: display, excludingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.width = opts.width
        cfg.height = opts.height
        cfg.pixelFormat = kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(opts.fps))
        cfg.showsCursor = true
        cfg.queueDepth = 5
        if opts.audioFifo != nil {
            cfg.capturesAudio = true
            cfg.sampleRate = 48000
            cfg.channelCount = 2
            cfg.excludesCurrentProcessAudio = true
        }
        let stream = SCStream(filter: filter, configuration: cfg, delegate: output)
        activeStream = stream
        try stream.addStreamOutput(output, type: .screen,
                                   sampleHandlerQueue: DispatchQueue(label: "sckcap.screen"))
        if opts.audioFifo != nil {
            try stream.addStreamOutput(output, type: .audio,
                                       sampleHandlerQueue: DispatchQueue(label: "sckcap.audio"))
        }
        try await stream.startCapture()
        err("capturing display \(display.width)x\(display.height) -> \(opts.width)x\(opts.height) @ \(opts.fps) fps")
        timer.resume()
    } catch {
        err("cannot start capture: \(error.localizedDescription)")
        exit(1)
    }
}
dispatchMain()
