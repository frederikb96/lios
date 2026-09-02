import Foundation

/// The Codable mirror of `lios_protocol.wire` — the relay's Pydantic models are the authority on
/// field names and shapes; this file must be kept in exact correspondence with them rather than
/// re-derived from prose. `RelayClient` is the only place that encodes or decodes these, and it
/// configures `JSONDecoder`/`JSONEncoder` with snake_case conversion so every type below can stay
/// idiomatic Swift (camelCase) while the wire form matches Pydantic's default field names.
///
/// These describe clear (relay-visible) metadata only. What travels inside a sealed blob is
/// `PushMetadata` and the framed payload, defined alongside `Sealing` and `Framing` — the relay
/// never constructs or reads either.

/// Mirrors `lios_protocol.wire.Platform`.
public enum LiosPlatform: String, Codable, Sendable {
    case ios
    case linux
}

/// Mirrors `lios_protocol.wire.ItemSummary`.
///
/// `targetDeviceId` is `nil` for a broadcast item — delivered to every paired device other than
/// the sender. Set, it narrows delivery (and the ack that triggers pruning) to that one device.
public struct ItemSummary: Codable, Sendable, Identifiable {
    public let id: UUID
    public let senderDeviceId: UUID
    public let targetDeviceId: UUID?
    public let sizeBytes: Int
    public let createdAt: Date

    public init(id: UUID, senderDeviceId: UUID, targetDeviceId: UUID?, sizeBytes: Int, createdAt: Date) {
        self.id = id
        self.senderDeviceId = senderDeviceId
        self.targetDeviceId = targetDeviceId
        self.sizeBytes = sizeBytes
        self.createdAt = createdAt
    }
}

/// Mirrors `lios_protocol.wire.ItemCreated` — the response to `POST /api/items`.
public struct ItemCreated: Codable, Sendable {
    public let id: UUID
    public let createdAt: Date

    public init(id: UUID, createdAt: Date) {
        self.id = id
        self.createdAt = createdAt
    }
}

/// Mirrors `lios_protocol.wire.StreamEvent`. iOS never opens `GET /api/stream` itself — that is
/// the Linux client's long-lived connection — but the shape is kept here so a future debug route
/// or a shared decode path has no second definition to drift from the relay's.
public struct StreamEvent: Codable, Sendable {
    public let type: String
    public let item: ItemSummary

    public init(item: ItemSummary) {
        self.type = "item.new"
        self.item = item
    }
}

/// Mirrors `lios_protocol.wire.DeviceInfo`.
public struct DeviceInfo: Codable, Sendable, Identifiable {
    public let id: UUID
    public let displayName: String
    public let platform: LiosPlatform
    public let createdAt: Date
    public let hasPushToken: Bool
}

/// Mirrors `lios_protocol.wire.PairingSessionCreated` — the response to
/// `POST /api/devices/pairing-sessions`.
public struct PairingSessionCreated: Codable, Sendable {
    public let pairingCode: String
    public let expiresAt: Date
}

/// Mirrors `lios_protocol.wire.PairingRedeem` — the request body for `POST /api/devices/pair`.
public struct PairingRedeem: Codable, Sendable {
    public let pairingCode: String
    public let platform: LiosPlatform
    public let displayName: String

    public init(pairingCode: String, platform: LiosPlatform, displayName: String) {
        self.pairingCode = pairingCode
        self.platform = platform
        self.displayName = displayName
    }
}

/// Mirrors `lios_protocol.wire.DevicePaired` — the response to `POST /api/devices/pair`.
///
/// `deviceToken` is shown exactly once, here — the relay stores only its hash and cannot display
/// it again afterwards, so the caller must persist it (Keychain) immediately on receipt.
public struct DevicePaired: Codable, Sendable {
    public let deviceId: UUID
    public let deviceToken: String
}

/// Mirrors `lios_protocol.wire.PushTokenUpdate` — the request body for
/// `POST /api/devices/{id}/push-token`.
public struct PushTokenUpdate: Codable, Sendable {
    public let apnsToken: String

    public init(apnsToken: String) {
        self.apnsToken = apnsToken
    }
}
