import LIOSKit
import SwiftUI
import UIKit

@MainActor
@Observable
final class SettingsViewModel {
    private let store = HistoryStore(directory: HistoryStore.defaultDirectory())

    var relayURL: URL?
    var maxItems: Double
    var maxAgeDays: Double

    enum InviteState: Equatable {
        case idle
        case creating
        case ready(qrUri: String)
        case failed(String)
    }

    var inviteState: InviteState = .idle

    init() {
        let policy = SettingsViewModel.loadPolicy()
        maxItems = Double(policy.maxItems)
        maxAgeDays = policy.maxAge / (24 * 60 * 60)
        relayURL = try? KeychainStore.loadRelayURL()
    }

    var policy: RetentionPolicy {
        RetentionPolicy(maxItems: Int(maxItems), maxAge: maxAgeDays * 24 * 60 * 60)
    }

    func applyRetentionChange() {
        SettingsViewModel.savePolicy(policy)
        try? store.applyRetention(policy: policy)
    }

    func forgetThisDevice() {
        try? KeychainStore.eraseAll()
        AppState.shared.markUnpaired()
    }

    /// Mints a fresh pairing code for a new device to redeem, and packages it — together with
    /// the group key this device already holds — into the same QR payload shape
    /// `PairingViewModel` reads. The key never reaches the relay; only the code does.
    func inviteAnotherDevice() {
        inviteState = .creating
        Task {
            guard let session = LiosSession.loadFromKeychain() else {
                inviteState = .failed("Not paired.")
                return
            }
            do {
                let created = try await session.makeRelayClient().createPairingSession()
                let payload = try Pairing.buildPayload(
                    relayUrl: session.relayURL.absoluteString, pairingCode: created.pairingCode,
                    groupKey: session.groupKey)
                let uri = try Pairing.encodeQrUri(payload)
                inviteState = .ready(qrUri: uri)
            } catch {
                inviteState = .failed("Couldn't reach the relay.")
                LogBuffer.shared.log(.error, "invite failed: \(error)", category: "pairing")
            }
        }
    }

    func dismissInvite() {
        inviteState = .idle
    }

    func copyInviteLink(_ uri: String) {
        UIPasteboard.general.string = uri
    }

    /// The retention policy is a device-local preference, not a secret, so it lives in
    /// `UserDefaults` rather than the Keychain — that reservation is for the pairing model.
    private static let defaultsKey = "net.frederikberg.lios.retentionPolicy"

    private static func loadPolicy() -> RetentionPolicy {
        guard let data = UserDefaults.standard.data(forKey: defaultsKey),
            let policy = try? JSONDecoder().decode(RetentionPolicy.self, from: data)
        else {
            return .default
        }
        return policy
    }

    private static func savePolicy(_ policy: RetentionPolicy) {
        guard let data = try? JSONEncoder().encode(policy) else { return }
        UserDefaults.standard.set(data, forKey: defaultsKey)
    }
}
