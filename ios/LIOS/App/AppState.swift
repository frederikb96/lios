import Foundation
import LIOSKit

/// The app's own runtime state — pairing status and whatever the receive path just did — shared
/// between the push delegate that drives it and the views that reflect it.
///
/// Deliberately holds nothing that belongs in `HistoryStore` or the Keychain: this is transient,
/// in-memory, gone on relaunch, which is exactly right for "what just happened" state.
@MainActor
@Observable
final class AppState {
    /// Reached from non-view code (`NotificationRouter`, the pairing flow) that has no SwiftUI
    /// `@Environment` to be handed an instance through. Views may still prefer environment
    /// injection for testability; both point at the same instance either way.
    static let shared = AppState()
    enum PairingStatus: Equatable {
        case notPaired
        case paired(relayURL: URL, deviceId: UUID)
    }

    /// What the receive path does once an item is decrypted, for `RootView` to act on. Two
    /// branches: text confirms and writes straight to the pasteboard; an image or file
    /// opens the share sheet on it. Never set except in direct response to a notification tap or
    /// an explicit pull — see `NotificationRouter`'s own warning about why.
    enum ReceiveOutcome: Equatable {
        case textCopied(preview: String)
        case shareItem(fileURL: URL)
        case failed(message: String)
    }

    var pairingStatus: PairingStatus = .notPaired
    var receiveOutcome: ReceiveOutcome?

    func markPaired(relayURL: URL, deviceId: UUID) {
        pairingStatus = .paired(relayURL: relayURL, deviceId: deviceId)
    }

    func markUnpaired() {
        pairingStatus = .notPaired
    }
}
