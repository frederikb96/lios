import LIOSKit
import SwiftUI

/// the design's requirement: a log view with one-tap export from the first version. A
/// TestFlight build has no debugger attached, so this is the only way an item that silently
/// failed to arrive is ever diagnosable.
struct LogView: View {
    @State private var entries: [LogBuffer.Entry] = []
    @State private var isSharingExport = false

    var body: some View {
        NavigationStack {
            List(entries.reversed()) { entry in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(entry.level.rawValue.uppercased())
                            .font(.caption2.bold())
                            .foregroundStyle(color(for: entry.level))
                        Text(entry.category)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(entry.timestamp, style: .time)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Text(entry.message)
                        .font(.footnote)
                }
            }
            .navigationTitle("Log")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button("Share", systemImage: "square.and.arrow.up") {
                        isSharingExport = true
                    }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button("Clear", role: .destructive) {
                        LogBuffer.shared.clear()
                        refresh()
                    }
                }
            }
            .onAppear { refresh() }
            .refreshable { refresh() }
            .sheet(isPresented: $isSharingExport) {
                ActivityView(items: [LogBuffer.shared.exportText()])
            }
        }
    }

    private func refresh() {
        entries = LogBuffer.shared.snapshot()
    }

    private func color(for level: LogBuffer.Level) -> Color {
        switch level {
        case .debug: .secondary
        case .info: .primary
        case .warning: .orange
        case .error: .red
        }
    }
}
