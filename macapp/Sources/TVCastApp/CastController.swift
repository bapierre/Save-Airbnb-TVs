import Foundation
import SwiftUI
import CoreGraphics
import TVCastKit

/// Ties the engine together for the UI: discover TVs, start/stop casting, resync. Runs the
/// blocking session on a background thread and publishes state for SwiftUI.
/// Bandwidth presets. Lower ones give a weak or congested Wi-Fi more headroom, trading
/// sharpness for a stream that does not stall.
enum Quality: String, CaseIterable, Identifiable {
    case smooth = "Smooth (480p)"
    case balanced = "Balanced (720p)"
    case sharp = "Sharp (1080p)"
    var id: String { rawValue }
    var spec: VideoSpec {
        switch self {
        case .smooth: return VideoSpec(width: 854, height: 480, fps: 30, bitrate: "1500k")
        case .balanced: return VideoSpec(width: 1280, height: 720, fps: 30, bitrate: "3M")
        case .sharp: return VideoSpec(width: 1920, height: 1080, fps: 30, bitrate: "6M")
        }
    }
}

@MainActor
final class CastController: ObservableObject {
    @Published var quality: Quality = .balanced
    @Published var renderers: [Renderer] = []
    @Published var selected: Renderer?
    @Published var status = "Idle"
    @Published var isCasting = false
    @Published var isBusy = false

    private let stopFlag = AtomicFlag()
    private let resyncFlag = AtomicFlag()
    private var server: StreamServer?
    private var wasMuted = false

    func refresh() {
        isBusy = true
        status = "Searching for TVs…"
        Task.detached { [weak self] in
            let found = SSDP.discover(timeout: 4)
            await MainActor.run {
                guard let self else { return }
                self.renderers = found
                if self.selected == nil || !found.contains(self.selected!) {
                    self.selected = found.first
                }
                self.status = found.isEmpty ? "No TV found. Is it on this Wi-Fi, on its home screen?"
                                            : "\(found.count) TV(s) found"
                self.isBusy = false
            }
        }
    }

    func start() {
        guard let target = selected, !isCasting else { return }
        guard let ffmpeg = locateFFmpeg(bundledDir: Bundle.main.resourceURL) else {
            status = "ffmpeg not found (install it or bundle it in the app)"; return
        }
        guard let myIP = localIP(reaching: target.ip) else { status = "no route to \(target.ip)"; return }

        stopFlag.set(false)
        resyncFlag.set(false)
        isCasting = true
        status = "Starting…"

        let spec = quality.spec
        let d = CGMainDisplayID()
        let size = fitSize(displayW: CGDisplayPixelsWide(d), displayH: CGDisplayPixelsHigh(d),
                           maxW: spec.width, maxH: spec.height)
        let server = StreamServer(makeSource: {
            let s = ScreenCaptureSource(ffmpegPath: ffmpeg, spec: spec, captureSize: size)
            try? s.start()
            return s
        })
        self.server = server

        // Mute the Mac speakers so the show does not play twice.
        wasMuted = MacAudio.isMuted()
        if !wasMuted { MacAudio.setMuted(true) }

        Task.detached { [weak self] in
            guard let self else { return }
            let port: UInt16
            do { port = try server.start(port: 0) }
            catch { await self.finish(status: "cannot open a local port"); return }
            let url = "http://\(myIP):\(port)\(server.path)"
            await MainActor.run { self.status = "Casting to \(target.name)" }

            let session = Session(
                launcher: DlnaLauncher(controlURL: target.controlURL),
                url: url,
                log: { line in Task { @MainActor in self.status = line } },
                shouldStop: { self.stopFlag.get() },
                onServerStop: { server.stop() })
            session.shouldResync = { self.resyncFlag.get() }
            session.clearResync = { self.resyncFlag.set(false) }
            session.rediscover = {
                SSDP.discover(timeout: 4).first { $0.ip == target.ip }
                    .map { DlnaLauncher(controlURL: $0.controlURL) }
            }
            _ = session.run()
            await self.finish(status: "Stopped")
        }
    }

    func resync() {
        guard isCasting else { return }
        resyncFlag.set(true)
        status = "Resyncing…"
    }

    func stop() {
        guard isCasting else { return }
        status = "Stopping…"
        stopFlag.set(true)
    }

    private func finish(status: String) {
        self.status = status
        self.isCasting = false
        self.server = nil
        if !wasMuted { MacAudio.setMuted(false) }
    }

}

enum MacAudio {
    static func run(_ script: String) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        p.arguments = ["-e", script]
        let pipe = Pipe(); p.standardOutput = pipe
        try? p.run(); p.waitUntilExit()
        return String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
    static func isMuted() -> Bool { run("output muted of (get volume settings)") == "true" }
    static func setMuted(_ m: Bool) { _ = run(m ? "set volume with output muted" : "set volume without output muted") }
}
