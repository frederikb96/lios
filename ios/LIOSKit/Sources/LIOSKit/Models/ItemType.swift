import Foundation

/// The three content types the design fixed for v1: text, images and files, all of it, both
/// directions. What differs between them is what each end *offers* on delivery, not what
/// travels — see `LiosItem` for the receive-side branch.
public enum ItemType: String, Codable, Sendable {
    case text
    case image
    case file
}

/// The keys `Framing.pack`'s `[String: String]` metadata dict is built from. Not part of
/// `lios_protocol` (that module treats metadata as an opaque string dict), so this is the one
/// place both this app and the share extension read and write them — grep this file, not a
/// string literal, before adding or renaming one.
public enum FrameMetadataKey {
    public static let type = "type"
    public static let filename = "filename"
    public static let mimeType = "mime_type"
}
