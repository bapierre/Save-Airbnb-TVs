import SwiftUI
import TVCastKit

@main
struct TVCastApp: App {
    @StateObject private var controller = CastController()

    var body: some Scene {
        MenuBarExtra("tvcast", systemImage: controller.isCasting ? "tv.fill" : "tv") {
            ContentView(controller: controller)
        }
        .menuBarExtraStyle(.window)
    }
}

struct ContentView: View {
    @ObservedObject var controller: CastController

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Cast this Mac to a TV").font(.headline)

            HStack {
                Picker("TV", selection: $controller.selected) {
                    if controller.renderers.isEmpty {
                        Text("No TV found").tag(Renderer?.none)
                    }
                    ForEach(controller.renderers) { r in
                        Text(r.name).tag(Renderer?.some(r))
                    }
                }
                .labelsHidden()
                .disabled(controller.isCasting)
                Button {
                    controller.refresh()
                } label: { Image(systemName: "arrow.clockwise") }
                .disabled(controller.isBusy || controller.isCasting)
                .help("Search again")
            }

            Text(controller.status)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                if controller.isCasting {
                    Button("Resync") { controller.resync() }
                        .help("Drop the delay and jump to live, e.g. between episodes")
                    Button("Stop") { controller.stop() }
                        .keyboardShortcut(".")
                } else {
                    Button("Play") { controller.start() }
                        .disabled(controller.selected == nil)
                        .keyboardShortcut(.defaultAction)
                }
                Spacer()
                Button("Quit") { NSApplication.shared.terminate(nil) }
            }
        }
        .padding(14)
        .frame(width: 300)
        .onAppear { if controller.renderers.isEmpty { controller.refresh() } }
    }
}
