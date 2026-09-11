// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "TVCast",
    platforms: [.macOS(.v13)],
    targets: [
        // The engine: discovery, DLNA control, HTTP streaming, capture, session.
        .target(name: "TVCastKit"),
        // A thin CLI to exercise the engine against a real TV (parity with `tvcast`).
        .executableTarget(name: "tvcast-native", dependencies: ["TVCastKit"]),
        // Self-contained assertions (the CLT toolchain has no XCTest); run: swift run tvcast-selftest
        .executableTarget(name: "tvcast-selftest", dependencies: ["TVCastKit"]),
    ]
)
