import XCTest

@testable import LIOSKit

/// A `SentItemsFetching` double with no networking at all — canned summaries and blobs, and a
/// recorded call log so a test can assert on exactly what `SentHistorySync` did without spinning
/// up a relay.
private final class FakeSentItemsClient: SentItemsFetching, @unchecked Sendable {
    var summariesToReturn: [ItemSummary] = []
    var fetchError: Error?
    /// Blobs keyed by item id; an id with no entry here fails to fetch, standing in for a blob
    /// the relay can no longer serve.
    var blobs: [UUID: Data] = [:]

    private(set) var sinceArgumentsSeen: [Date?] = []
    private(set) var fetchedBlobIds: [UUID] = []
    private(set) var ackedIds: [UUID] = []

    struct FetchError: Error {}

    func fetchSentItems(since: Date?) async throws -> [ItemSummary] {
        sinceArgumentsSeen.append(since)
        if let fetchError { throw fetchError }
        return summariesToReturn
    }

    func fetchItemBlob(id: UUID) async throws -> Data {
        fetchedBlobIds.append(id)
        guard let blob = blobs[id] else { throw FetchError() }
        return blob
    }

    func deleteItem(id: UUID) async throws {
        ackedIds.append(id)
    }
}

final class SentHistorySyncTests: XCTestCase {
    private var directory: URL!
    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        suiteName = "SentHistorySyncTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
        defaults.removePersistentDomain(forName: suiteName)
    }

    private func sealedSummary(payload: Data, groupKey: Data) throws -> (ItemSummary, Data) {
        let sealed = try LiosItem.seal(
            id: UUID(), type: .text, filename: nil, mimeType: nil, payload: payload, groupKey: groupKey)
        let summary = ItemSummary(
            id: sealed.id, senderDeviceId: UUID(), targetDeviceId: nil, sizeBytes: sealed.sizeBytes,
            createdAt: Date())
        return (summary, sealed.blob)
    }

    func testRecordsAndAcksEverySentItemTheRelayReports() async throws {
        let groupKey = Sealing.generateGroupKey()
        let (summaryA, blobA) = try sealedSummary(payload: Data("first".utf8), groupKey: groupKey)
        let (summaryB, blobB) = try sealedSummary(payload: Data("second".utf8), groupKey: groupKey)

        let client = FakeSentItemsClient()
        client.summariesToReturn = [summaryA, summaryB]
        client.blobs = [summaryA.id: blobA, summaryB.id: blobB]

        let history = HistoryStore(directory: directory)
        let sync = SentHistorySync(
            client: client, groupKey: groupKey, history: history, cursor: SentSyncCursor(defaults: defaults))

        let recorded = await sync.run()

        XCTAssertEqual(recorded, 2)
        let entries = try history.list()
        XCTAssertEqual(Set(entries.map(\.id)), [summaryA.id, summaryB.id])
        XCTAssertTrue(entries.allSatisfy { $0.direction == .sent })
        XCTAssertEqual(Set(client.ackedIds), [summaryA.id, summaryB.id])
    }

    /// One item that cannot be decrypted (a blob the relay can no longer serve, standing in for
    /// any local failure to make sense of it) must not stop the rest of the batch from being
    /// recorded, and must still be acked -- this device has already fetched it and gains nothing
    /// from the relay holding it any longer.
    func testAnItemThatFailsToFetchIsSkippedButStillAckedAndDoesNotBlockOthers() async throws {
        let groupKey = Sealing.generateGroupKey()
        let (goodSummary, goodBlob) = try sealedSummary(payload: Data("fine".utf8), groupKey: groupKey)
        let badSummary = ItemSummary(
            id: UUID(), senderDeviceId: UUID(), targetDeviceId: nil, sizeBytes: 1, createdAt: Date())

        let client = FakeSentItemsClient()
        client.summariesToReturn = [badSummary, goodSummary]
        client.blobs = [goodSummary.id: goodBlob]

        let history = HistoryStore(directory: directory)
        let sync = SentHistorySync(
            client: client, groupKey: groupKey, history: history, cursor: SentSyncCursor(defaults: defaults))

        let recorded = await sync.run()

        XCTAssertEqual(recorded, 1)
        XCTAssertEqual(try history.list().map(\.id), [goodSummary.id])
        XCTAssertEqual(Set(client.ackedIds), [badSummary.id, goodSummary.id])
    }

    /// A fetch that fails outright (the relay unreachable) must not crash and must not advance
    /// the cursor -- the next run should still ask for everything since the last real success.
    func testAFailedListFetchRecordsNothingAndLeavesTheCursorWhereItWas() async throws {
        let groupKey = Sealing.generateGroupKey()
        let client = FakeSentItemsClient()
        client.fetchError = FakeSentItemsClient.FetchError()
        let cursor = SentSyncCursor(defaults: defaults)
        let history = HistoryStore(directory: directory)
        let sync = SentHistorySync(client: client, groupKey: groupKey, history: history, cursor: cursor)

        let recorded = await sync.run()

        XCTAssertEqual(recorded, 0)
        XCTAssertTrue(try history.list().isEmpty)
        XCTAssertNil(cursor.load())
    }

    /// A run passes whatever the cursor already holds as `since`, and updates it afterwards --
    /// the shape a second, later run relies on to only ask for what is new.
    func testASuccessfulRunAdvancesTheCursorPastWhatItAlreadyHeld() async throws {
        let groupKey = Sealing.generateGroupKey()
        let cursor = SentSyncCursor(defaults: defaults)
        let priorCursor = Date(timeIntervalSinceNow: -3600)
        cursor.save(priorCursor)

        let client = FakeSentItemsClient()
        let history = HistoryStore(directory: directory)
        let sync = SentHistorySync(client: client, groupKey: groupKey, history: history, cursor: cursor)

        _ = await sync.run()

        XCTAssertEqual(client.sinceArgumentsSeen, [priorCursor])
        let newCursor = try XCTUnwrap(cursor.load())
        XCTAssertGreaterThan(newCursor, priorCursor)
    }
}
