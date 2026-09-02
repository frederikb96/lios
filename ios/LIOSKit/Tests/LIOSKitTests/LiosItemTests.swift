import XCTest

@testable import LIOSKit

final class LiosItemTests: XCTestCase {

    func testSealThenOpenRoundTripsATextItem() throws {
        let groupKey = Sealing.generateGroupKey()
        let payload = Data("copy this to the clipboard".utf8)

        let sealed = try LiosItem.seal(
            id: UUID(), type: .text, filename: nil, mimeType: nil, payload: payload, groupKey: groupKey)

        // Stands in for what the relay reports back after storing the blob — it never sees
        // plaintext, so `sizeBytes` here is only ever a measurement of `sealed.blob.count`.
        let summary = ItemSummary(
            id: sealed.id, senderDeviceId: UUID(), targetDeviceId: nil, sizeBytes: sealed.sizeBytes,
            createdAt: Date())

        let opened = try LiosItem.open(summary: summary, sealedBlob: sealed.blob, groupKey: groupKey)
        XCTAssertEqual(opened.type, .text)
        XCTAssertEqual(opened.payload, payload)
        XCTAssertNil(opened.filename)
    }

    func testSealThenOpenRoundTripsAFileItemWithMetadata() throws {
        let groupKey = Sealing.generateGroupKey()
        let payload = Data("fake pdf bytes".utf8)

        let sealed = try LiosItem.seal(
            id: UUID(), type: .file, filename: "notes.pdf", mimeType: "application/pdf", payload: payload,
            groupKey: groupKey)
        let summary = ItemSummary(
            id: sealed.id, senderDeviceId: UUID(), targetDeviceId: nil, sizeBytes: sealed.sizeBytes,
            createdAt: Date())

        let opened = try LiosItem.open(summary: summary, sealedBlob: sealed.blob, groupKey: groupKey)
        XCTAssertEqual(opened.filename, "notes.pdf")
        XCTAssertEqual(opened.mimeType, "application/pdf")
        XCTAssertEqual(opened.payload, payload)
    }

    /// The associated data binds a blob to one specific id and size — opening it against a
    /// summary claiming a different id must fail rather than quietly return the wrong content.
    func testOpeningAgainstAMismatchedSummaryFailsAuthentication() throws {
        let groupKey = Sealing.generateGroupKey()
        let sealed = try LiosItem.seal(
            id: UUID(), type: .text, filename: nil, mimeType: nil, payload: Data("x".utf8), groupKey: groupKey)
        let wrongSummary = ItemSummary(
            id: UUID(), senderDeviceId: UUID(), targetDeviceId: nil, sizeBytes: sealed.sizeBytes, createdAt: Date())

        XCTAssertThrowsError(try LiosItem.open(summary: wrongSummary, sealedBlob: sealed.blob, groupKey: groupKey)) {
            XCTAssertTrue($0 is Sealing.TamperError)
        }
    }
}
