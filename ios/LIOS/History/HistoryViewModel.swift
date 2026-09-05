import LIOSKit
import SwiftUI

@MainActor
@Observable
final class HistoryViewModel {
    private let store = HistoryStore(directory: HistoryStore.defaultDirectory())
    var entries: [HistoryStore.Entry] = []

    func refresh() {
        entries = (try? store.list()) ?? []
    }

    func payload(for id: UUID) -> Data? {
        store.payload(for: id)
    }

    /// The share sheet takes a `String` for a text item rather than a staged file, so its
    /// first offer is Copy and everything after it (Messages, Notes, a translation action)
    /// receives real text instead of a `.bin` attachment.
    func shareText(for entry: HistoryStore.Entry) -> String? {
        guard entry.type == .text, let data = store.payload(for: entry.id) else { return nil }
        return String(decoding: data, as: UTF8.self)
    }

    func shareFileURL(for entry: HistoryStore.Entry) -> URL? {
        guard let data = store.payload(for: entry.id) else { return nil }
        return ShareSheetFile.write(data: data, suggestedFilename: entry.filename, mimeType: entry.mimeType)
    }
}
