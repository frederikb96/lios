import Foundation

/// Device pairing: reading (and, for symmetry, building) the QR payload that carries the group
/// key from an already-paired device to a new one.
///
/// Mirrors `lios_protocol.pairing` exactly — the group key travels only inside this payload,
/// never as a bare value logged or sent to the relay, and this module never makes an HTTP call.
/// LIOS's first release only ever *decodes* a QR the Linux client displays, but `encode` is kept
/// so an iPhone can one day be the first-paired device without a second implementation appearing.
public enum Pairing {

    /// URI scheme a QR code carries. Mirrors `lios_protocol.pairing._SCHEME`. Chosen over a bare
    /// JSON string so a general-purpose QR scanner shows a recognisable, non-executable link.
    static let scheme = "lios"

    /// Everything a new device needs to join the fleet, exactly as carried by the QR code.
    /// Mirrors `lios_protocol.pairing.PairingPayload`.
    public struct Payload: Codable, Sendable {
        public let relayUrl: String
        public let pairingCode: String
        /// Base64-encoded 32-byte AES-256-GCM group key.
        public let groupKeyB64: String

        private enum CodingKeys: String, CodingKey {
            case relayUrl = "relay_url"
            case pairingCode = "pairing_code"
            case groupKeyB64 = "group_key_b64"
        }

        public init(relayUrl: String, pairingCode: String, groupKeyB64: String) {
            self.relayUrl = relayUrl
            self.pairingCode = pairingCode
            self.groupKeyB64 = groupKeyB64
        }

        /// Decode the embedded group key back to raw bytes.
        ///
        /// - Throws: `Sealing.InvalidInputError` if the decoded key is not exactly
        ///   `Sealing.keySize` bytes, or the base64 itself does not decode.
        public func groupKey() throws -> Data {
            guard let key = Data(base64Encoded: groupKeyB64) else {
                throw Sealing.InvalidInputError(message: "pairing payload's group key is not valid base64")
            }
            guard key.count == Sealing.keySize else {
                throw Sealing.InvalidInputError(
                    message: "pairing payload's group key is \(key.count) bytes, expected \(Sealing.keySize)")
            }
            return key
        }
    }

    /// Assemble the payload an already-paired device encodes into a QR code. Mirrors
    /// `lios_protocol.pairing.build_pairing_payload`.
    ///
    /// - Throws: `Sealing.InvalidInputError` if `groupKey` is not exactly `Sealing.keySize` bytes.
    public static func buildPayload(relayUrl: String, pairingCode: String, groupKey: Data) throws -> Payload {
        guard groupKey.count == Sealing.keySize else {
            throw Sealing.InvalidInputError(
                message: "group key must be \(Sealing.keySize) bytes, got \(groupKey.count)")
        }
        return Payload(relayUrl: relayUrl, pairingCode: pairingCode, groupKeyB64: groupKey.base64EncodedString())
    }

    /// Malformed URI error thrown by `decodeQrUri`. Mirrors the `ValueError`
    /// `lios_protocol.pairing.decode_qr_uri` raises.
    public struct InvalidUriError: Error, Sendable {
        public let message: String
    }

    /// Render a `Payload` as the URI a QR code image encodes. Mirrors
    /// `lios_protocol.pairing.encode_qr_uri`. Rendering the actual QR image (CoreImage's
    /// `CIQRCodeGenerator` on iOS) is a caller concern; this only produces the string both sides
    /// agree on.
    public static func encodeQrUri(_ payload: Payload) throws -> String {
        let json = try JSONEncoder().encode(payload)
        let encoded = urlSafeBase64(json)
        return "\(scheme)://pair/\(encoded)"
    }

    /// Reverse `encodeQrUri`. Mirrors `lios_protocol.pairing.decode_qr_uri`.
    ///
    /// - Throws: `InvalidUriError` if `uri` does not carry the expected scheme, or its payload
    ///   does not decode as base64 or parse as JSON.
    public static func decodeQrUri(_ uri: String) throws -> Payload {
        let prefix = "\(scheme)://pair/"
        guard uri.hasPrefix(prefix) else {
            throw InvalidUriError(message: "not a LIOS pairing URI: expected a \"\(prefix)\" prefix")
        }
        let encoded = String(uri.dropFirst(prefix.count))
        guard let data = dataFromUrlSafeBase64(encoded) else {
            throw InvalidUriError(message: "pairing URI's payload does not decode as base64")
        }
        do {
            return try JSONDecoder().decode(Payload.self, from: data)
        } catch {
            throw InvalidUriError(message: "pairing URI's payload does not parse: \(error)")
        }
    }

    /// A short-lived, single-use code a redeeming device types or scans. iOS only ever redeems
    /// one minted by the relay (via the Linux client's pairing session) rather than generating
    /// its own, so this mirrors `lios_protocol.pairing.generate_pairing_code` for parity and for
    /// any future path where the phone is the first-paired device.
    public static func generatePairingCode(length: Int = 8) -> String {
        // No ambiguous glyphs (0/O, 1/I/L) -- mirrors `lios_protocol.pairing._CODE_ALPHABET` --
        // since a code may need to be read off a screen and typed by hand as a fallback to
        // scanning.
        let alphabet = Array("23456789ABCDEFGHJKMNPQRSTUVWXYZ")
        return String((0..<length).map { _ in alphabet.randomElement()! })
    }

    private static func urlSafeBase64(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
    }

    private static func dataFromUrlSafeBase64(_ string: String) -> Data? {
        var standard =
            string
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        let remainder = standard.count % 4
        if remainder > 0 {
            standard += String(repeating: "=", count: 4 - remainder)
        }
        return Data(base64Encoded: standard)
    }
}
