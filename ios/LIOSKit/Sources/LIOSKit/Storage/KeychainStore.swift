#if canImport(Security)
    import Foundation
    import Security

    /// Everything the pairing model keeps secret, stored in the Keychain access group shared by
    /// all three targets — the app, the share extension and the notification service extension.
    ///
    /// This is the substitute for an App Group: none exists for `com.frederikberg.lios` (Apple's
    /// `POST /v1/appGroups` does not exist as an endpoint at all — see the spec's row order 2.95),
    /// but a Keychain access group needs only a shared team, which every target here already has.
    /// The three targets' entitlements must each list the same
    /// `$(AppIdentifierPrefix)com.frederikberg.lios` group, or every read here returns `nil` with
    /// no error — Keychain access-group mismatches fail silently rather than throwing.
    ///
    /// Apple-only (`Security` has no Linux implementation), so this whole file compiles to
    /// nothing on the free Linux runner — `swift build` proves the rest of the package instead.
    /// `swiftc -parse` via `Tooling/parse-swift.sh` still catches a syntax error here for free.
    public enum KeychainStore {

        /// The resolved access group string a Keychain query needs — the app identifier prefix
        /// resolves to the team id at runtime, so this must be written out rather than left as
        /// the `$(AppIdentifierPrefix)` build-setting macro the entitlements file uses.
        public static let accessGroup = "CSHG4AV9YH.com.frederikberg.lios"

        private static let service = "net.frederikberg.lios"

        private enum Account {
            static let groupKey = "group-key"
            static let deviceId = "device-id"
            static let deviceToken = "device-token"
            static let relayURL = "relay-url"
        }

        /// Thrown when a Keychain call reports something other than "not found" — a genuine I/O
        /// or entitlement problem worth surfacing, rather than the ordinary "nothing paired yet".
        public struct KeychainError: Error, Sendable {
            public let status: OSStatus
        }

        public static func saveGroupKey(_ key: Data) throws { try save(key, account: Account.groupKey) }
        public static func loadGroupKey() throws -> Data? { try load(account: Account.groupKey) }

        public static func saveDeviceId(_ id: UUID) throws {
            try save(Data(id.uuidString.utf8), account: Account.deviceId)
        }
        public static func loadDeviceId() throws -> UUID? {
            guard let data = try load(account: Account.deviceId), let string = String(data: data, encoding: .utf8)
            else {
                return nil
            }
            return UUID(uuidString: string)
        }

        public static func saveDeviceToken(_ token: String) throws {
            try save(Data(token.utf8), account: Account.deviceToken)
        }
        public static func loadDeviceToken() throws -> String? {
            guard let data = try load(account: Account.deviceToken) else { return nil }
            return String(data: data, encoding: .utf8)
        }

        public static func saveRelayURL(_ url: URL) throws {
            try save(Data(url.absoluteString.utf8), account: Account.relayURL)
        }
        public static func loadRelayURL() throws -> URL? {
            guard let data = try load(account: Account.relayURL), let string = String(data: data, encoding: .utf8)
            else {
                return nil
            }
            return URL(string: string)
        }

        /// Erase every credential — the "forget this fleet" action a re-pair starts from.
        public static func eraseAll() throws {
            for account in [Account.groupKey, Account.deviceId, Account.deviceToken, Account.relayURL] {
                let status = SecItemDelete(query(account: account) as CFDictionary)
                guard status == errSecSuccess || status == errSecItemNotFound else {
                    throw KeychainError(status: status)
                }
            }
        }

        private static func query(account: String) -> [String: Any] {
            [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: account,
                kSecAttrAccessGroup as String: accessGroup,
            ]
        }

        private static func save(_ data: Data, account: String) throws {
            // Delete-then-add rather than an update, so this is one code path whether or not a
            // value already exists — a Keychain "update" call fails outright when there is
            // nothing to update, which would make every first save a special case.
            SecItemDelete(query(account: account) as CFDictionary)
            var attributes = query(account: account)
            attributes[kSecValueData as String] = data
            attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            let status = SecItemAdd(attributes as CFDictionary, nil)
            guard status == errSecSuccess else { throw KeychainError(status: status) }
        }

        private static func load(account: String) throws -> Data? {
            var attributes = query(account: account)
            attributes[kSecReturnData as String] = true
            attributes[kSecMatchLimit as String] = kSecMatchLimitOne
            var result: AnyObject?
            let status = SecItemCopyMatching(attributes as CFDictionary, &result)
            if status == errSecItemNotFound { return nil }
            guard status == errSecSuccess else { throw KeychainError(status: status) }
            return result as? Data
        }
    }
#endif
