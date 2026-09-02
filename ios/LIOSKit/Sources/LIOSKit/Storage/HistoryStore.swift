import Foundation

/// The last N items for M days, in the app's own storage, auto-expiring —
/// row 2.8's requirement. Dismissing a notification is never destructive: the item stays here,
/// browsable, until the retention policy prunes it.
///
/// Built on plain files under one directory rather than a database: history is small, bounded by
/// the retention policy itself, and a directory of `<id>.json` index entries plus `<id>.blob`
/// payloads needs no schema migration story. Takes its directory by injection (rather than
/// resolving `.applicationSupportDirectory` itself) so it is testable on Linux, where that
/// directory does not exist.
public final class HistoryStore: @unchecked Sendable {
    private let directory: URL
    private let fileManager = FileManager.default
    private let lock = NSLock()

    /// One history entry's clear metadata — never the payload itself, so listing history never
    /// has to decrypt or load anything but this small index. `payload(for:)` reads the matching
    /// blob file only when a caller actually needs it.
    public struct Entry: Codable, Sendable, Identifiable {
        public let id: UUID
        public let senderDeviceId: UUID
        public let type: ItemType
        public let filename: String?
        public let mimeType: String?
        public let createdAt: Date

        public init(item: LiosItem) {
            id = item.id
            senderDeviceId = item.senderDeviceId
            type = item.type
            filename = item.filename
            mimeType = item.mimeType
            createdAt = item.createdAt
        }
    }

    public init(directory: URL) {
        self.directory = directory
        try? fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    /// The app's own sandboxed storage for history — never a shared container, since the share
    /// extension and the notification service extension have no need to browse history and this
    /// app has no App Group to share it through anyway.
    public static func defaultDirectory() -> URL {
        let base =
            FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("History", isDirectory: true)
    }

    private func indexURL(for id: UUID) -> URL { directory.appendingPathComponent("\(id.uuidString).json") }
    private func blobURL(for id: UUID) -> URL { directory.appendingPathComponent("\(id.uuidString).blob") }

    /// Record one item and its payload, then prune to `policy`. The payload is written
    /// unencrypted to the app's own sandboxed storage — the item has already been decrypted by
    /// the time anything reaches history, and nothing here is shared with another app.
    public func record(_ item: LiosItem, policy: RetentionPolicy = .default) throws {
        lock.lock()
        defer { lock.unlock() }
        let entry = Entry(item: item)
        try JSONEncoder.lios.encode(entry).write(to: indexURL(for: item.id))
        try item.payload.write(to: blobURL(for: item.id))
        try prune(policy: policy)
    }

    /// Every entry still within the retention policy, newest first.
    public func list() throws -> [Entry] {
        lock.lock()
        defer { lock.unlock() }
        return try loadAllEntries().sorted { $0.createdAt > $1.createdAt }
    }

    /// The payload bytes for one entry, or `nil` if it has already been pruned.
    public func payload(for id: UUID) -> Data? {
        try? Data(contentsOf: blobURL(for: id))
    }

    /// Remove one entry immediately, regardless of policy — used when a device acks an item it
    /// no longer needs to keep locally.
    public func remove(id: UUID) throws {
        lock.lock()
        defer { lock.unlock() }
        try? fileManager.removeItem(at: indexURL(for: id))
        try? fileManager.removeItem(at: blobURL(for: id))
    }

    /// Apply `policy` to what is already on disk — count first (oldest beyond the cap go), then
    /// age. Exposed so a settings change re-prunes immediately rather than waiting for the next
    /// `record`.
    public func applyRetention(policy: RetentionPolicy) throws {
        lock.lock()
        defer { lock.unlock() }
        try prune(policy: policy)
    }

    private func prune(policy: RetentionPolicy) throws {
        let cutoff = Date().addingTimeInterval(-policy.maxAge)
        var entries = try loadAllEntries().sorted { $0.createdAt > $1.createdAt }
        var toRemove: [UUID] = []
        if entries.count > policy.maxItems {
            toRemove.append(contentsOf: entries[policy.maxItems...].map(\.id))
            entries = Array(entries.prefix(policy.maxItems))
        }
        toRemove.append(contentsOf: entries.filter { $0.createdAt < cutoff }.map(\.id))
        for id in toRemove {
            try? fileManager.removeItem(at: indexURL(for: id))
            try? fileManager.removeItem(at: blobURL(for: id))
        }
    }

    private func loadAllEntries() throws -> [Entry] {
        let files = try fileManager.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        return files.filter { $0.pathExtension == "json" }.compactMap { url in
            guard let data = try? Data(contentsOf: url) else { return nil }
            return try? JSONDecoder.lios.decode(Entry.self, from: data)
        }
    }
}

extension JSONEncoder {
    /// Shared, ISO-8601-dated encoder for everything this package persists to disk — one place
    /// so a store and its own tests cannot silently use different date strategies.
    static let lios: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}

extension JSONDecoder {
    static let lios: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}
