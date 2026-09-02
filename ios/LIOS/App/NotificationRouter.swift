import LIOSKit
import UIKit

/// What happens the moment the user taps a LIOS banner — the interaction he actually asked for,
/// and the only place in this app that is allowed to touch `UIPasteboard.general`.
///
/// 🚨 Never call anything here except in direct response to a notification tap or an explicit
/// pull. KDE Connect's iOS client re-syncs on every foreground-resume and overwrites whatever the
/// user copied in the meantime — an open bug for over a year (KDE#494853). Foregrounding alone
/// must never write the pasteboard.
@MainActor
final class NotificationRouter {
    static let shared = NotificationRouter()

    private init() {}

    private lazy var history = HistoryStore(directory: HistoryStore.defaultDirectory())

    func handleTap(userInfo: [AnyHashable: Any]) async {
        guard let decoded = PushPayload.decode(userInfo: userInfo) else {
            LogBuffer.shared.log(
                .warning, "tapped notification carried no recognisable LIOS payload", category: "receive")
            return
        }
        guard let session = LiosSession.loadFromKeychain() else {
            LogBuffer.shared.log(
                .error, "notification tapped while unpaired — dropping item \(decoded.itemId)", category: "receive")
            AppState.shared.receiveOutcome = .failed(message: "Not paired with a relay.")
            return
        }

        do {
            let client = session.makeRelayClient()
            let blob = try await client.fetchItemBlob(id: decoded.itemId)
            // The relay only ever measures the bytes it was handed — `blob.count` here is
            // exactly what it would report from `GET /api/items?since=` too, so building the
            // summary from what was just fetched avoids a second round trip to look it up.
            let summary = ItemSummary(
                id: decoded.itemId, senderDeviceId: decoded.senderDeviceId, targetDeviceId: nil,
                sizeBytes: blob.count, createdAt: Date())
            let item = try LiosItem.open(summary: summary, sealedBlob: blob, groupKey: session.groupKey)

            try? history.record(item)
            try? await client.deleteItem(id: item.id)

            switch item.type {
            case .text:
                let text = String(decoding: item.payload, as: UTF8.self)
                UIPasteboard.general.string = text
                LogBuffer.shared.log(.info, "text item \(item.id) copied to pasteboard", category: "receive")
                AppState.shared.receiveOutcome = .textCopied(preview: String(text.prefix(200)))
            case .image, .file:
                if let fileURL = ShareSheetFile.write(
                    data: item.payload, suggestedFilename: item.filename, mimeType: item.mimeType)
                {
                    AppState.shared.receiveOutcome = .shareItem(fileURL: fileURL)
                } else {
                    AppState.shared.receiveOutcome = .failed(message: "Couldn't prepare that item for sharing.")
                }
            }
        } catch {
            LogBuffer.shared.log(.error, "failed to receive item \(decoded.itemId): \(error)", category: "receive")
            AppState.shared.receiveOutcome = .failed(message: "Couldn't retrieve that item.")
        }
    }
}
