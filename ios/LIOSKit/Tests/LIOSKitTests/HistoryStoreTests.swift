import XCTest

@testable import LIOSKit

final class HistoryStoreTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private func makeItem(createdAt: Date = Date()) -> LiosItem {
        LiosItem(
            id: UUID(), senderDeviceId: UUID(), type: .text, filename: nil, mimeType: nil,
            payload: Data("hello".utf8), createdAt: createdAt)
    }

    func testRecordedItemIsListedAndItsPayloadReadableBack() throws {
        let store = HistoryStore(directory: directory)
        let item = makeItem()
        try store.record(item)

        let entries = try store.list()
        XCTAssertEqual(entries.map(\.id), [item.id])
        XCTAssertEqual(store.payload(for: item.id), item.payload)
    }

    func testListIsNewestFirst() throws {
        let store = HistoryStore(directory: directory)
        let older = makeItem(createdAt: Date(timeIntervalSinceNow: -60))
        let newer = makeItem(createdAt: Date())
        try store.record(older)
        try store.record(newer)

        XCTAssertEqual(try store.list().map(\.id), [newer.id, older.id])
    }

    func testPruningByCountKeepsOnlyTheNewestMaxItems() throws {
        let store = HistoryStore(directory: directory)
        let policy = RetentionPolicy(maxItems: 2, maxAge: 60 * 60 * 24 * 7)
        let items = (0..<5).map { makeItem(createdAt: Date(timeIntervalSinceNow: TimeInterval($0))) }
        for item in items {
            try store.record(item, policy: policy)
        }

        let remaining = try store.list()
        XCTAssertEqual(remaining.count, 2)
        // The two most recently created survive.
        XCTAssertEqual(Set(remaining.map(\.id)), Set(items.suffix(2).map(\.id)))
    }

    func testPruningByAgeExpiresOldEntries() throws {
        let store = HistoryStore(directory: directory)
        let policy = RetentionPolicy(maxItems: 50, maxAge: 60)
        let old = makeItem(createdAt: Date(timeIntervalSinceNow: -120))
        try store.record(old, policy: policy)

        XCTAssertTrue(try store.list().isEmpty)
        XCTAssertNil(store.payload(for: old.id))
    }

    func testRemoveDeletesBothIndexAndPayload() throws {
        let store = HistoryStore(directory: directory)
        let item = makeItem()
        try store.record(item)
        try store.remove(id: item.id)

        XCTAssertTrue(try store.list().isEmpty)
        XCTAssertNil(store.payload(for: item.id))
    }
}
