import LIOSKit
import SwiftUI

/// Owns nothing but *whether* `HistoryViewModel` exists yet — construction (which runs
/// `HistoryStore.init`'s directory-creation I/O) happens exactly once, from `.task`, never from
/// this view's own initialiser. Same shape as `SettingsView`: an eager
/// `@State private var viewModel = HistoryViewModel()` looks like a one-time construction, but
/// the default-value expression is an ordinary argument to `HistoryView.init()` and re-runs, side
/// effects included, on every re-evaluation of whichever parent body places a `HistoryView()` —
/// `RootView`'s `TabView` here.
struct HistoryView: View {
    @State private var viewModel: HistoryViewModel?
    @State private var shareTarget: ShareTarget?

    var body: some View {
        Group {
            if let viewModel {
                HistoryList(viewModel: viewModel, shareTarget: $shareTarget)
            } else {
                ProgressView()
            }
        }
        .task {
            if viewModel == nil {
                viewModel = HistoryViewModel()
            }
        }
    }
}

private struct HistoryList: View {
    @Bindable var viewModel: HistoryViewModel
    @Binding var shareTarget: ShareTarget?

    var body: some View {
        NavigationStack {
            List(viewModel.entries) { entry in
                HistoryRow(entry: entry)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        shareTarget = target(for: entry)
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
                ActivityView(items: target.activityItems)
            }
        }
    }

    /// Every kind of item opens the same share sheet -- a text one differs only in what it
    /// hands over, and `nil` here (a payload no longer on disk) simply leaves the sheet shut.
    private func target(for entry: HistoryStore.Entry) -> ShareTarget? {
        switch entry.type {
        case .text:
            guard let text = viewModel.shareText(for: entry) else { return nil }
            return ShareTarget(id: entry.id.uuidString, payload: .text(text))
        case .image, .file:
            guard let url = viewModel.shareFileURL(for: entry) else { return nil }
            return ShareTarget(id: entry.id.uuidString, payload: .file(url))
        }
    }
}

/// `.sheet(item:)` needs `Identifiable`, and `UIActivityViewController` takes `[Any]` -- so the
/// payload is an enum rather than an `Any`, keeping the two shapes the sheet can carry explicit
/// and the type checkable. The item's own id is the identity: a text item has no URL to borrow
/// one from, and re-tapping the same row should reopen the same sheet either way.
private struct ShareTarget: Identifiable {
    enum Payload {
        case text(String)
        case file(URL)
    }

    let id: String
    let payload: Payload

    var activityItems: [Any] {
        switch payload {
        case .text(let text): [text]
        case .file(let url): [url]
        }
    }
}

private struct HistoryRow: View {
    let entry: HistoryStore.Entry

    var body: some View {
        HStack {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading) {
                Text(entry.filename ?? label)
                HStack(spacing: 4) {
                    Text(directionLabel)
                    Text("·")
                    Text(entry.createdAt, style: .relative)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: directionIcon)
                .foregroundStyle(.tertiary)
                .accessibilityHidden(true)
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

    private var directionLabel: String {
        switch entry.direction {
        case .sent: "Sent"
        case .received: "Received"
        }
    }

    private var directionIcon: String {
        switch entry.direction {
        case .sent: "arrow.up.circle"
        case .received: "arrow.down.circle"
        }
    }
}
