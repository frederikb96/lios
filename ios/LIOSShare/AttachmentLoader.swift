import LIOSKit
import UniformTypeIdentifiers

/// Turns one `NSItemProvider` from the share sheet into the shape `LiosItem.seal` wants.
///
/// Checked in this order because a single provider often conforms to more than one type — a
/// Nautilus-style file share and an image share both offer `public.file-url`, so file is checked
/// last among the "this could be a document" cases and image first, matching what a person means
/// by "share this photo" versus "share this PDF".
///
/// `NSItemProvider` is not `Sendable`, so this stays on the same actor as its caller
/// (`ShareUploadModel`, `@MainActor`) rather than hopping off to load — the provider is never
/// sent anywhere, only read from in place. The completion-handler calls inside each `load*`
/// function still run on whatever queue `NSItemProvider` itself chooses; only the `async`
/// function wrapping them is pinned here, and resuming a `CheckedContinuation` from another
/// thread is the one part of this pattern Swift Concurrency explicitly allows.
@MainActor
enum AttachmentLoader {

    struct Loaded {
        let type: ItemType
        let filename: String?
        let mimeType: String?
        let payload: Data
    }

    /// The share extension's own memory ceiling is undocumented but real — naive handling of a
    /// full-resolution camera roll image has been reported to exceed it. Conservative on
    /// purpose: better to reject clearly than to be silently jetsam-killed mid-upload.
    static let maxPayloadBytes = 80_000_000

    enum LoadError: Error {
        case unsupportedType
        case tooLarge(bytes: Int)
        case loadFailed
    }

    static func load(_ provider: NSItemProvider) async throws -> Loaded {
        if provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
            return try await loadFile(provider, preferredType: .image, fallbackTypeIdentifier: UTType.image.identifier)
        }
        if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier),
            !provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier)
        {
            return try await loadText(provider)
        }
        if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier),
            !provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier)
        {
            return try await loadURL(provider)
        }
        if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier)
            || provider.hasItemConformingToTypeIdentifier(UTType.data.identifier)
        {
            return try await loadFile(provider, preferredType: .file, fallbackTypeIdentifier: UTType.data.identifier)
        }
        throw LoadError.unsupportedType
    }

    private static func loadText(_ provider: NSItemProvider) async throws -> Loaded {
        let text = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String, Error>) in
            provider.loadItem(forTypeIdentifier: UTType.plainText.identifier) { item, error in
                if let error { continuation.resume(throwing: error); return }
                switch item {
                case let string as String: continuation.resume(returning: string)
                case let data as Data: continuation.resume(returning: String(decoding: data, as: UTF8.self))
                default: continuation.resume(throwing: LoadError.loadFailed)
                }
            }
        }
        let payload = Data(text.utf8)
        try assertSize(payload.count)
        return Loaded(type: .text, filename: nil, mimeType: nil, payload: payload)
    }

    private static func loadURL(_ provider: NSItemProvider) async throws -> Loaded {
        let url = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
            provider.loadItem(forTypeIdentifier: UTType.url.identifier) { item, error in
                if let error { continuation.resume(throwing: error); return }
                guard let url = item as? URL else { continuation.resume(throwing: LoadError.loadFailed); return }
                continuation.resume(returning: url)
            }
        }
        let payload = Data(url.absoluteString.utf8)
        try assertSize(payload.count)
        return Loaded(type: .text, filename: nil, mimeType: nil, payload: payload)
    }

    /// Images and generic files both arrive as a file URL (or, for some providers, raw `Data`)
    /// — loading through the file URL when one is offered means this reads the bytes once,
    /// straight off disk, rather than the provider materialising a second in-memory copy first.
    private static func loadFile(_ provider: NSItemProvider, preferredType: ItemType, fallbackTypeIdentifier: String)
        async throws -> Loaded
    {
        let typeIdentifier = provider.registeredTypeIdentifiers.first ?? fallbackTypeIdentifier

        if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            let fileURL = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier) { item, error in
                    if let error { continuation.resume(throwing: error); return }
                    guard let url = item as? URL else { continuation.resume(throwing: LoadError.loadFailed); return }
                    continuation.resume(returning: url)
                }
            }
            let sizeAttribute = try fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            try assertSize(sizeAttribute)
            let payload = try Data(contentsOf: fileURL)
            let mimeType = UTType(filenameExtension: fileURL.pathExtension)?.preferredMIMEType
            return Loaded(
                type: preferredType, filename: fileURL.lastPathComponent, mimeType: mimeType, payload: payload)
        }

        let payload = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Data, Error>) in
            provider.loadItem(forTypeIdentifier: typeIdentifier) { item, error in
                if let error { continuation.resume(throwing: error); return }
                switch item {
                case let data as Data: continuation.resume(returning: data)
                case let url as URL: continuation.resume(returning: (try? Data(contentsOf: url)) ?? Data())
                default: continuation.resume(throwing: LoadError.loadFailed)
                }
            }
        }
        try assertSize(payload.count)
        let mimeType = UTType(typeIdentifier)?.preferredMIMEType
        return Loaded(type: preferredType, filename: nil, mimeType: mimeType, payload: payload)
    }

    private static func assertSize(_ bytes: Int) throws {
        guard bytes <= maxPayloadBytes else { throw LoadError.tooLarge(bytes: bytes) }
    }
}
