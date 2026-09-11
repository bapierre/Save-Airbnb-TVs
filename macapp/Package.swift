// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "TVCast",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "TVCastKit"),
        .executableTarget(name: "sckcap"),
        .executableTarget(name: "TVCastApp", dependencies: ["TVCastKit"]),
        .executableTarget(name: "tvcast-native", dependencies: ["TVCastKit"]),
        .executableTarget(name: "tvcast-selftest", dependencies: ["TVCastKit"]),
    ]
)
