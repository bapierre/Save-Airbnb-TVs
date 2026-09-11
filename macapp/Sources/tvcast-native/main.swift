import TVCastKit
import Foundation

let args = CommandLine.arguments
let cmd = args.count > 1 ? args[1] : "discover"

func firstRenderer() -> Renderer? {
    FileHandle.standardError.write("searching for renderers…\n".data(using: .utf8)!)
    return SSDP.discover(timeout: 4).first
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
default:
    print("usage: tvcast-native [discover|state]")
}
