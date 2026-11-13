import Foundation

/// The small, separately-sealed blob a sender attaches to `POST /api/items` so the Notification
/// Service Extension can rewrite a generic push into a useful banner without ever fetching the
/// item's own payload.
///
/// 🚨 Not yet part of `lios_protocol.wire` — the relay only has clear metadata (`ItemSummary`)
/// and the sealed item blob to work with, and it cannot compose a preview itself because it
/// never holds the group key, which is the whole point of it. This is this app's proposed
/// extension to the wire contract: the sender seals a `PushPreview` under the same group key,
/// sends it alongside the item as opaque bytes the relay stores and forwards verbatim inside the
/// push blob's `sealed_preview` field (see `PushPayload`), and the relay never has to
/// understand it to relay it. If the relay does not yet carry this field, `PushPayload.decode`
/// simply finds no preview and the NSE falls back to a generic banner — nothing breaks, but the
/// point of it — seeing what arrived without opening the app — needs the relay and the Linux
/// sender to carry the field too.
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

/// What a push carries and how to read it. Kept as one place so the NSE, `NotificationRouter` and
/// any future debug tooling agree on the names.
///
/// The push relay delivers `{"v": 1, "b": "<blob>"}` under `payloadKey`; the blob is base64 of a
/// JSON object holding the three keys below, built by `lios_protocol.push.build_push_blob`.
public enum PushPayload {
    /// Mirrors `lios_protocol.headers.PUSH_RELAY_APP`: the app name at the push relay, which is
    /// also the key the push relay files the blob under.
    public static let appName = "lios"
    public static let itemIdKey = "item_id"
    public static let senderDeviceIdKey = "sender_device_id"
    public static let sealedPreviewKey = "sealed_preview"

    /// The only envelope version this build understands.
    private static let envelopeVersion = 1

    public struct Decoded: Sendable {
        public let itemId: UUID
        /// `sender_device_id` is clear, relay-visible metadata already (`ItemSummary` carries
        /// it) — including it on the push costs the relay nothing to forward and saves the app
        /// a round trip to look it up before it can even open the blob's associated data.
        public let senderDeviceId: UUID
        public let sealedPreview: Data
    }

    /// Pull the push blob out of a raw userInfo dictionary. Returns `nil` when the envelope or
    /// the blob is missing or malformed, or `item_id` / `sender_device_id` is not a valid UUID —
    /// a foreign push, which the NSE and the router should both pass through unmodified rather
    /// than crash on.
    public static func decode(userInfo: [AnyHashable: Any]) -> Decoded? {
        guard
            let envelope = userInfo[appName] as? [String: Any],
            (envelope["v"] as? Int) == envelopeVersion,
            let blobB64 = envelope["b"] as? String,
            let blob = Data(base64Encoded: blobB64),
            let fields = try? JSONSerialization.jsonObject(with: blob) as? [String: Any],
            let idString = fields[itemIdKey] as? String, let itemId = UUID(uuidString: idString),
            let senderString = fields[senderDeviceIdKey] as? String,
            let senderDeviceId = UUID(uuidString: senderString)
        else {
            return nil
        }
        let sealedPreview: Data
        if let previewB64 = fields[sealedPreviewKey] as? String, let decoded = Data(base64Encoded: previewB64) {
            sealedPreview = decoded
        } else {
            sealedPreview = Data()
        }
        return Decoded(itemId: itemId, senderDeviceId: senderDeviceId, sealedPreview: sealedPreview)
    }
}
