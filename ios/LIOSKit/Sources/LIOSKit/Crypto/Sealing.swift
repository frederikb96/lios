import Crypto
import Foundation

/// AES-256-GCM sealing of one opaque blob under the shared group key.
///
/// Mirrors `lios_protocol.crypto` byte for byte: `AES.GCM.SealedBox.combined` is defined as
/// `nonce (12 bytes) || ciphertext || tag (16 bytes)`, exactly the layout `crypto.py` builds by
/// hand with `cryptography`'s `AESGCM`. That correspondence is asserted in `SealingTests`, not
/// just assumed — a blob sealed on one side must open on the other, or the two ends have quietly
/// diverged. The relay stores and forwards exactly this blob and can never open it: the group key
/// never reaches it (see `PairingPayload`).
public enum Sealing {

    /// AES-256 key size in bytes. Mirrors `lios_protocol.crypto.KEY_SIZE`.
    public static let keySize = 32

    /// Thrown when a sealed blob's authentication tag does not verify: wrong key, or the bytes
    /// were altered. Mirrors `lios_protocol.crypto.TamperError`.
    public struct TamperError: Error, Sendable {}

    /// The group key or blob was malformed before decryption was even attempted — mirrors the
    /// `ValueError`s `crypto.py` raises for a wrong key length or too-short blob.
    public struct InvalidInputError: Error, Sendable {
        public let message: String
    }

    /// Generate a fresh 256-bit key for a new device fleet, from the platform CSPRNG.
    /// Mirrors `lios_protocol.crypto.generate_group_key`.
    public static func generateGroupKey() -> Data {
        Data(SymmetricKey(size: .bits256).withUnsafeBytes { Array($0) })
    }

    /// Encrypt `plaintext` under `key`, returning `nonce || ciphertext || tag` as one blob.
    ///
    /// `associatedData` is authenticated but not encrypted — pass the item's clear-text metadata
    /// (id, size, timestamps) here so a swapped envelope on a genuine item is rejected even
    /// though the relay never inspects the blob's contents. Mirrors `lios_protocol.crypto.seal`.
    ///
    /// - Throws: `InvalidInputError` if `key` is not exactly `keySize` bytes.
    public static func seal(key: Data, plaintext: Data, associatedData: Data = Data()) throws -> Data {
        guard key.count == keySize else {
            throw InvalidInputError(message: "group key must be \(keySize) bytes, got \(key.count)")
        }
        let symmetricKey = SymmetricKey(data: key)
        let sealedBox: AES.GCM.SealedBox
        do {
            sealedBox = try AES.GCM.seal(plaintext, using: symmetricKey, authenticating: associatedData)
        } catch {
            // `AES.GCM.seal` only fails for reasons that cannot happen with a random nonce and a
            // correctly sized key — surfacing it as a tamper-shaped error would be misleading, so
            // this is the one place a raw CryptoKit error is allowed to propagate unwrapped.
            throw error
        }
        return sealedBox.combined ?? Data()
    }

    /// Decrypt a blob produced by `seal`, verifying its tag and `associatedData`.
    /// Mirrors `lios_protocol.crypto.open_sealed`.
    ///
    /// - Throws: `InvalidInputError` if `key` is not exactly `keySize` bytes, or `blob` is
    ///   shorter than one nonce. `TamperError` if the tag does not verify.
    public static func open(key: Data, blob: Data, associatedData: Data = Data()) throws -> Data {
        guard key.count == keySize else {
            throw InvalidInputError(message: "group key must be \(keySize) bytes, got \(key.count)")
        }
        guard blob.count >= 12 else {
            throw InvalidInputError(message: "sealed blob shorter than one nonce (12 bytes)")
        }
        let symmetricKey = SymmetricKey(data: key)
        do {
            let sealedBox = try AES.GCM.SealedBox(combined: blob)
            return try AES.GCM.open(sealedBox, using: symmetricKey, authenticating: associatedData)
        } catch {
            throw TamperError()
        }
    }
}
