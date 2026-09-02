import Foundation

/// Packing an item's metadata and payload into one buffer before it is sealed.
///
/// Mirrors `lios_protocol.framing` exactly: a 4-byte big-endian length prefix, then the metadata
/// as UTF-8 JSON, then the raw payload appended unencoded. Kept separate from `Sealing`, which
/// operates on arbitrary bytes and knows nothing about what is inside them — this defines what
/// those bytes mean. Metadata that would leak content if left in the clear (filename, MIME type,
/// a text preview) lives here, inside the sealed envelope, never as a clear relay-visible field.
public enum Framing {

    /// Thrown when `unpack` is handed a frame shorter than the length prefix, or whose prefix
    /// claims more metadata bytes than the frame actually holds. Mirrors the `ValueError`s
    /// `lios_protocol.framing.unpack` raises.
    public struct MalformedFrameError: Error, Sendable {
        public let message: String
    }

    /// Concatenate `metadata` (as length-prefixed JSON) and `payload` into one buffer.
    ///
    /// The payload is appended raw, never base64-encoded — avoiding that overhead is the whole
    /// reason this is a length-prefixed binary frame rather than one JSON document with the
    /// payload embedded as a string field. Mirrors `lios_protocol.framing.pack`.
    public static func pack(metadata: [String: String], payload: Data) -> Data {
        let metadataBytes = (try? JSONEncoder().encode(metadata)) ?? Data()
        var prefix = UInt32(metadataBytes.count).bigEndian
        var frame = Data(bytes: &prefix, count: 4)
        frame.append(metadataBytes)
        frame.append(payload)
        return frame
    }

    /// Reverse `pack`, returning the metadata dict and the raw payload. Mirrors
    /// `lios_protocol.framing.unpack`.
    public static func unpack(frame: Data) throws -> (metadata: [String: String], payload: Data) {
        guard frame.count >= 4 else {
            throw MalformedFrameError(message: "frame shorter than the metadata length prefix")
        }
        let prefixRange = frame.startIndex..<frame.startIndex.advanced(by: 4)
        let metadataLength = Int(frame[prefixRange].withUnsafeBytes { $0.load(as: UInt32.self) }.bigEndian)
        let metadataStart = frame.startIndex.advanced(by: 4)
        guard let metadataEnd = frame.index(metadataStart, offsetBy: metadataLength, limitedBy: frame.endIndex) else {
            throw MalformedFrameError(message: "frame's metadata length prefix exceeds the frame's own size")
        }
        let metadataBytes = frame[metadataStart..<metadataEnd]
        let metadata = try JSONDecoder().decode([String: String].self, from: metadataBytes)
        let payload = frame[metadataEnd...]
        return (metadata, Data(payload))
    }
}
