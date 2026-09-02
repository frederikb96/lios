import LIOSKit
import SwiftUI

@MainActor
@Observable
final class SettingsViewModel {
    private let store = HistoryStore(directory: HistoryStore.defaultDirectory())

    var relayURL: URL?
    var maxItems: Double
    var maxAgeDays: Double

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
