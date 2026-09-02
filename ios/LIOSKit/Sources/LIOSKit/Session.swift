#if canImport(Security)
    import Foundation

    /// Everything the app, the share extension and the notification service extension each need
    /// to read from the shared Keychain access group before they can talk to the relay or open a
    /// sealed item — one place so the three targets cannot each grow a slightly different read
    /// path.
    public struct LiosSession: Sendable {
        public let relayURL: URL
        public let deviceId: UUID
        public let deviceToken: String
        public let groupKey: Data

        /// Loads every credential from `KeychainStore`. Returns `nil` — never throws — when
        /// pairing has not happened yet or was erased, since "not paired" is the ordinary state
        /// for a fresh install, not an error.
        public static func loadFromKeychain() -> LiosSession? {
            guard
                let relayURL = try? KeychainStore.loadRelayURL(),
                let deviceId = try? KeychainStore.loadDeviceId(),
                let deviceToken = try? KeychainStore.loadDeviceToken(),
                let groupKey = try? KeychainStore.loadGroupKey()
            else {
                return nil
            }
            return LiosSession(relayURL: relayURL, deviceId: deviceId, deviceToken: deviceToken, groupKey: groupKey)
        }

        public func makeRelayClient() -> RelayClient {
            RelayClient(relayURL: relayURL, deviceToken: deviceToken)
        }
    }
#endif
