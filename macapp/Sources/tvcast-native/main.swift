import TVCastKit
import Foundation
import CoreGraphics

let args = CommandLine.arguments
let cmd = args.count > 1 ? args[1] : "discover"

func err(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

func firstRenderer() -> Renderer? {
    err("searching for renderers…")
    return SSDP.discover(timeout: 4).first
}

func siblingHelper() -> String {
    URL(fileURLWithPath: args[0]).deletingLastPathComponent().appendingPathComponent("sckcap").path
}

func mainDisplaySize() -> (Int, Int) {
    let d = CGMainDisplayID()
    return (CGDisplayPixelsWide(d), CGDisplayPixelsHigh(d))
}

switch cmd {
case "discover":
    let found = SSDP.discover(timeout: 4)
    if found.isEmpty { print("no DLNA renderer found") }
    for r in found { print("\(r.ip)  \(r.name)  ->  \(r.controlURL.absoluteString)") }

case "state":
    guard let r = firstRenderer() else { print("no renderer"); exit(1) }
    let l = DlnaLauncher(controlURL: r.controlURL)
    print("\(r.name): state=\(l.state().rawValue) pos=\(l.position())")

case "capture":  // capture <seconds> <outfile.ts> — local validation, no TV
    let secs = args.count > 2 ? Double(args[2]) ?? 4 : 4
    let outfile = args.count > 3 ? args[3] : "capture.ts"
    guard let ffmpeg = locateFFmpeg() else { err("ffmpeg not found"); exit(2) }
    let helper = siblingHelper()
    guard FileManager.default.isExecutableFile(atPath: helper) else { err("helper missing at \(helper)"); exit(2) }
    let spec = VideoSpec()
    let (dw, dh) = mainDisplaySize()
    let size = fitSize(displayW: dw, displayH: dh, maxW: spec.width, maxH: spec.height)
    err("capturing \(size.0)x\(size.1) for \(secs)s -> \(outfile)")
    let src = ScreenCaptureSource(ffmpegPath: ffmpeg, helperPath: helper, spec: spec, captureSize: size)
    do { try src.start() } catch { err("\(error)"); exit(2) }
    var data = Data()
    let deadline = Date().addingTimeInterval(secs)
    while Date() < deadline {
        let chunk = src.read(188 * 64)
        if chunk.isEmpty { break }
        data.append(chunk)
    }
    src.stop()
    try? data.write(to: URL(fileURLWithPath: outfile))
    print("wrote \(data.count) bytes to \(outfile)")

default:
    print("usage: tvcast-native [discover|state|capture <secs> <out.ts>]")
}
