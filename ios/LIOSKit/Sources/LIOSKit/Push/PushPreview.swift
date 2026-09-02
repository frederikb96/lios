import Foundation

/// The small, separately-sealed blob a sender attaches to `POST /api/items` so the Notification
/// Service Extension can rewrite a generic push into a useful banner without ever fetching the
/// item's own payload.
///
/// 🚨 Not yet part of `lios_protocol.wire` — the relay only has clear metadata (`ItemSummary`)
/// and the sealed item blob to work with, and it cannot compose a preview itself because it
/// never holds the group key (the design's whole point). This is this app's proposed
/// extension to the wire contract: the sender seals a `PushPreview` under the same group key,
/// sends it alongside the item as opaque bytes the relay stores and forwards verbatim inside the
/// APNs payload's `sealed_preview` field (see `PushPayload`), and the relay never has to
/// understand it to relay it. If the relay does not yet carry this field, `PushPayload.decode`
/// simply finds no preview and the NSE falls back to a generic banner — nothing breaks, but the
/// zero-open-taps-for-context experience the user asked for needs the relay and the Linux sender to
/// pick this up too.
public struct PushPreview: Codable, Sendable {
    public let type: ItemType
    /// A short prefix of the text, for a text item only. Never set for image or file, so a
    /// truncation bug cannot leak more than the sender intended.
    public let preview: String?
    public let filename: String?

    public init(type: ItemType, preview: String?, filename: String?) {
        self.type = type
        self.preview = preview
        self.filename = filename
    }

    /// How much of a text item's content the sender includes in the clear-after-decryption
    /// banner. Deliberately short: this is a notification banner, not a reading surface.
    public static let previewCharacterLimit = 120

    /// Seal this preview under the group key. The associated data is the item's own id, so a
    /// preview cannot be replayed against a different item's push.
    public func seal(itemId: UUID, groupKey: Data) throws -> Data {
        let json = try JSONEncoder().encode(self)
        return try Sealing.seal(key: groupKey, plaintext: json, associatedData: Self.associatedData(itemId: itemId))
    }

    /// Lowercased to match Python's `str(uuid.UUID(...))` — see `LiosItem`'s own note on the
    /// same trap. Only matters here because these bytes are authenticated, never parsed back
    /// into a `UUID`; the wire paths and headers elsewhere in this package are case-insensitive
    /// on both sides and need no such care.
    private static func associatedData(itemId: UUID) -> Data {
        Data(itemId.uuidString.lowercased().utf8)
    }

    /// Reverse `seal`. Returns `nil` rather than throwing when `sealedBlob` is empty — the
    /// caller's signal that the sender (or an older relay) attached no preview at all, which is
    /// the expected degrade, not a tamper attempt.
    public static func open(sealedBlob: Data, itemId: UUID, groupKey: Data) throws -> PushPreview? {
        guard !sealedBlob.isEmpty else { return nil }
        let json = try Sealing.open(
            key: groupKey, blob: sealedBlob, associatedData: Self.associatedData(itemId: itemId))
        return try JSONDecoder().decode(PushPreview.self, from: json)
    }
}

/// The custom (non-`aps`) fields this app expects on an APNs payload, and how to read them.
/// Kept as one place so the NSE, `NotificationRouter` and any future debug tooling agree on the
/// field names.
public enum PushPayload {
    public static let itemIdKey = "item_id"
    public static let senderDeviceIdKey = "sender_device_id"
    public static let sealedPreviewKey = "sealed_preview"

    public struct Decoded: Sendable {
        public let itemId: UUID
        /// `sender_device_id` is clear, relay-visible metadata already (`ItemSummary` carries
        /// it) — including it on the push costs the relay nothing to forward and saves the app
        /// a round trip to look it up before it can even open the blob's associated data.
        public let senderDeviceId: UUID
        public let sealedPreview: Data
    }

    /// Pull the push's custom fields out of a raw userInfo dictionary. Returns `nil` when
    /// `item_id` or `sender_device_id` is missing or not a valid UUID — a malformed or foreign
    /// push, which the NSE and the router should both pass through unmodified rather than crash
    /// on.
    public static func decode(userInfo: [AnyHashable: Any]) -> Decoded? {
        guard
            let idString = userInfo[itemIdKey] as? String, let itemId = UUID(uuidString: idString),
            let senderString = userInfo[senderDeviceIdKey] as? String,
            let senderDeviceId = UUID(uuidString: senderString)
        else {
            return nil
        }
        let sealedPreview: Data
        if let previewB64 = userInfo[sealedPreviewKey] as? String, let decoded = Data(base64Encoded: previewB64) {
            sealedPreview = decoded
        } else {
            sealedPreview = Data()
        }
        return Decoded(itemId: itemId, senderDeviceId: senderDeviceId, sealedPreview: sealedPreview)
    }
}
