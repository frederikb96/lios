import Foundation

/// Where `SentHistorySync` remembers how far it has already caught up, so a run only asks the
/// relay for what changed since the last one rather than this device's whole sent history every
/// time. Takes its `UserDefaults` by injection, same reasoning as `HistoryStore`'s directory
/// injection: a test gets an isolated suite instead of polluting `.standard`.
public final class SentSyncCursor: @unchecked Sendable {
    private let defaults: UserDefaults
    private let key = "com.frederikberg.lios.sentSyncCursor"
    private let lock = NSLock()

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    public func load() -> Date? {
        lock.lock()
        defer { lock.unlock() }
        return defaults.object(forKey: key) as? Date
    }

    public func save(_ date: Date) {
        lock.lock()
        defer { lock.unlock() }
        defaults.set(date, forKey: key)
    }
}

/// Rebuilds the "what did I send" half of history from the relay. The share extension that
/// actually uploads an item is a separate process with no access to this app's storage, so this
/// is the only way the app ever learns something was sent.
///
/// Meant to run once per foreground: fetch everything this device has uploaded since the last
/// run, decrypt each with the group key, record it into `HistoryStore` marked `.sent`, then ack
/// it. The relay keeps a sent item around specifically until its own sender acks it — see
/// `docs/api.md` — so acking here is what stops an already-recorded item being handed back on
/// every future run, and what lets the relay prune it.
public struct SentHistorySync: Sendable {
    private let client: any SentItemsFetching
    private let groupKey: Data
    private let history: HistoryStore
    private let cursor: SentSyncCursor

    public init(client: any SentItemsFetching, groupKey: Data, history: HistoryStore, cursor: SentSyncCursor) {
        self.client = client
        self.groupKey = groupKey
        self.history = history
        self.cursor = cursor
    }

    /// Runs one catch-up pass. Returns the number of items newly recorded, so a caller can decide
    /// whether it is worth refreshing anything already on screen.
    ///
    /// A single item that fails to decrypt or fails to write to disk is logged and skipped rather
    /// than aborting the whole batch — a phone that comes back online after a while away gets
    /// everything else in the same run, and a batch is never wedged by its one bad item. That
    /// item is still acked afterwards: this device has already fetched it and cannot make any
    /// more sense of it on a later run either, so leaving it un-acked would only occupy a slot the
    /// relay's retention counts against, never actually recover it.
    @discardableResult
    public func run() async -> Int {
        let since = cursor.load()
        // Recorded before the fetch, not after: an item created while this call is in flight has
        // a `createdAt` later than this timestamp and is simply picked up by the next run, rather
        // than silently skipped by advancing the cursor past it.
        let startedAt = Date()

        let summaries: [ItemSummary]
        do {
            summaries = try await client.fetchSentItems(since: since)
        } catch {
            LogBuffer.shared.log(.error, "sent-history fetch failed: \(error)", category: "sent-sync")
            return 0
        }

        var recorded = 0
        for summary in summaries {
            do {
                let blob = try await client.fetchItemBlob(id: summary.id)
                let item = try LiosItem.open(summary: summary, sealedBlob: blob, groupKey: groupKey, direction: .sent)
                try history.record(item)
                recorded += 1
            } catch {
                LogBuffer.shared.log(
                    .error, "failed to record sent item \(summary.id): \(error)", category: "sent-sync")
            }
            do {
                try await client.deleteItem(id: summary.id)
            } catch {
                LogBuffer.shared.log(.error, "failed to ack sent item \(summary.id): \(error)", category: "sent-sync")
            }
        }

        cursor.save(startedAt)
        return recorded
    }
}
