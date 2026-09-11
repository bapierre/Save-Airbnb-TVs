import Foundation

/// What a TV controller must do. DlnaLauncher conforms; tests use a fake.
public protocol Launcher {
    func play(url: String, title: String) throws
    func stop() throws
    func nudge() throws
    func state() -> TransportState
}

extension DlnaLauncher: Launcher {}

/// Pure policy: given the TV state and the time, decide whether to relaunch or give up.
/// Direct port of the Python Watcher so behaviour matches.
public struct Watcher {
    let startTimeout: TimeInterval
    let relaunchWindow: TimeInterval
    var startedAt: TimeInterval?
    var seenPlaying = false
    var lastRelaunch: TimeInterval?

    public enum Action { case none, relaunch, timeout }

    public init(startTimeout: TimeInterval = 15, relaunchWindow: TimeInterval = 30) {
        self.startTimeout = startTimeout
        self.relaunchWindow = relaunchWindow
    }

    public mutating func tick(state: TransportState, now: TimeInterval) -> Action {
        if startedAt == nil { startedAt = now }
        if state == .playing { seenPlaying = true; return .none }
        if !seenPlaying {
            return (now - startedAt!) > startTimeout ? .timeout : .none
        }
        if state == .stopped {
            if lastRelaunch == nil || (now - lastRelaunch!) > relaunchWindow {
                lastRelaunch = now
                seenPlaying = false
                startedAt = now
                return .relaunch
            }
        }
        return .none
    }
}

/// Drives playback: start, keep alive, resync on demand, tear down. Port of session.py.
/// Injectable clock/sleep and flags so it is testable without a TV or real time.
public final class Session {
    public var launcher: Launcher
    public let url: String
    public let log: (String) -> Void

    // Signals (thread-safe via the atomics below).
    public let shouldStop: () -> Bool
    public var shouldResync: () -> Bool = { false }
    public var clearResync: () -> Void = {}
    public var rediscover: (() -> Launcher?)?

    public var startRetries = 2
    public var nudgeInterval: TimeInterval = 0
    public var pollInterval: TimeInterval = 2

    private let sleep: (TimeInterval) -> Void
    private let clock: () -> TimeInterval
    private let onServerStop: () -> Void

    public init(launcher: Launcher, url: String, log: @escaping (String) -> Void,
                shouldStop: @escaping () -> Bool,
                sleep: @escaping (TimeInterval) -> Void = { Foundation.Thread.sleep(forTimeInterval: $0) },
                clock: @escaping () -> TimeInterval = { Date().timeIntervalSinceReferenceDate },
                onServerStop: @escaping () -> Void = {}) {
        self.launcher = launcher
        self.url = url
        self.log = log
        self.shouldStop = shouldStop
        self.sleep = sleep
        self.clock = clock
        self.onServerStop = onServerStop
    }

    private func play() -> Bool {
        do { try launcher.play(url: url, title: "Mac screen"); return true }
        catch let e as UPnPError {
            if e.code != nil || !doRediscover() { log("TV refused the stream: \(e)"); return false }
        } catch { log("TV refused the stream: \(error)"); return false }
        do { try launcher.play(url: url, title: "Mac screen"); return true }
        catch { log("TV refused the stream after rediscovery: \(error)"); return false }
    }

    private func doRediscover() -> Bool {
        guard let rediscover else { return false }
        log("TV stopped answering; looking for it again…")
        guard let fresh = rediscover() else { log("TV not found. Is it still on the Wi-Fi?"); return false }
        launcher = fresh
        log("TV found again")
        return true
    }

    /// Returns 0 on clean stop, 1 on give-up.
    @discardableResult
    public func run() -> Int {
        var watcher = Watcher()
        if !play() { onServerStop(); return 1 }
        var code = 0
        var last: TransportState?
        var lastNudge: TimeInterval?
        var unknownStreak = 0
        var retriesLeft = startRetries

        while !shouldStop() {
            sleep(pollInterval)
            if shouldStop() { break }

            if shouldResync() {
                clearResync()
                log("resyncing: flushing the TV buffer and jumping to live…")
                watcher = Watcher()
                lastNudge = nil
                last = nil
                _ = play()
                continue
            }

            let state = launcher.state()
            let now = clock()
            if state != last { log("TV: \(state.rawValue)"); last = state }

            if nudgeInterval > 0 && state == .playing {
                if lastNudge == nil { lastNudge = now }
                else if now - lastNudge! >= nudgeInterval {
                    lastNudge = now
                    do { try launcher.nudge(); log("nudged the TV to keep it awake") }
                    catch { log("nudge failed (ignored): \(error)") }
                }
            }

            unknownStreak = (state == .unknown) ? unknownStreak + 1 : 0
            if unknownStreak >= 3 && doRediscover() {
                unknownStreak = 0
                watcher = Watcher()
                _ = play()
                continue
            }

            switch watcher.tick(state: state, now: now) {
            case .timeout:
                if retriesLeft > 0 {
                    retriesLeft -= 1
                    log("TV did not start playing. If it is asleep, press a button on its remote. "
                        + "Retrying (\(startRetries - retriesLeft)/\(startRetries))…")
                    watcher = Watcher()
                    _ = play()
                    continue
                }
                log("TV never reported PLAYING; giving up.")
                code = 1
            case .relaunch:
                log("TV stopped; relaunching")
                _ = play()
            case .none:
                break
            }
            if code == 1 { break }
        }
        try? launcher.stop()
        onServerStop()
        return code
    }
}
