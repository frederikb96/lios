import LIOSKit
import SwiftUI

struct HistoryView: View {
    @State private var viewModel = HistoryViewModel()
    @State private var shareTarget: ShareTarget?

    var body: some View {
        NavigationStack {
            List(viewModel.entries) { entry in
                HistoryRow(entry: entry)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        switch entry.type {
                        case .text:
                            viewModel.copyText(for: entry)
                        case .image, .file:
                            if let url = viewModel.shareFileURL(for: entry) {
                                shareTarget = ShareTarget(url: url)
                            }
                        }
                    }
            }
            .navigationTitle("History")
            .overlay {
                if viewModel.entries.isEmpty {
                    ContentUnavailableView(
                        "No items yet", systemImage: "tray",
                        description: Text("Items shared between your devices show up here for 7 days."))
                }
            }
            .onAppear { viewModel.refresh() }
            .refreshable { viewModel.refresh() }
            .sheet(item: $shareTarget) { target in
                ActivityView(items: [target.url])
            }
        }
    }
}

/// `.sheet(item:)` needs `Identifiable`; wrapping rather than conforming `URL` itself avoids
/// colliding with any conformance a future SDK adds.
private struct ShareTarget: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

private struct HistoryRow: View {
    let entry: HistoryStore.Entry

    var body: some View {
        HStack {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading) {
                Text(entry.filename ?? label)
                Text(entry.createdAt, style: .relative)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var icon: String {
        switch entry.type {
        case .text: "doc.plaintext"
        case .image: "photo"
        case .file: "doc"
        }
    }

    private var label: String {
        switch entry.type {
        case .text: "Text"
        case .image: "Image"
        case .file: "File"
        }
    }
}
