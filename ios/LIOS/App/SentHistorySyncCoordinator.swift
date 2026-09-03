import Foundation
import LIOSKit

/// Runs `SentHistorySync` once per foreground. Unlike `NotificationRouter`, nothing here ever
/// touches the pasteboard — it only writes to `HistoryStore` and acks the relay — so it is safe
/// to run on every foreground rather than only in direct response to a user action.
@MainActor
enum SentHistorySyncCoordinator {
    private static var isRunning = false

    /// No-op while unpaired, or while a previous run is still in flight — the app can go
    /// foreground several times in quick succession (a notification banner tapped away from,
    /// then the app itself opened) and only one pass over the same catch-up window is useful.
    static func runIfPaired() {
        guard !isRunning, let session = LiosSession.loadFromKeychain() else { return }
        isRunning = true
        Task {
            defer { isRunning = false }
            let history = HistoryStore(directory: HistoryStore.defaultDirectory())
            let sync = SentHistorySync(
                client: session.makeRelayClient(), groupKey: session.groupKey, history: history,
                cursor: SentSyncCursor())
            let recorded = await sync.run()
            if recorded > 0 {
                LogBuffer.shared.log(
                    .info, "recorded \(recorded) sent item(s) from history sync", category: "sent-sync")
            }
        }
    }
}
