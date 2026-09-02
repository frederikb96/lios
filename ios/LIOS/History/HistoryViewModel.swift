import LIOSKit
import SwiftUI
import UIKit

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

    func copyText(for entry: HistoryStore.Entry) {
        guard entry.type == .text, let data = store.payload(for: entry.id) else { return }
        UIPasteboard.general.string = String(decoding: data, as: UTF8.self)
    }

    func shareFileURL(for entry: HistoryStore.Entry) -> URL? {
        guard let data = store.payload(for: entry.id) else { return nil }
        return ShareSheetFile.write(data: data, suggestedFilename: entry.filename, mimeType: entry.mimeType)
    }
}
