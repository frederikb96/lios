import XCTest

@testable import LIOSKit

final class FramingTests: XCTestCase {

    func testRoundTripReturnsOriginalMetadataAndPayload() throws {
        let metadata = [FrameMetadataKey.type: "file", FrameMetadataKey.filename: "notes.pdf"]
        let payload = Data("%PDF-1.4 fake".utf8)
        let frame = Framing.pack(metadata: metadata, payload: payload)
        let (unpackedMetadata, unpackedPayload) = try Framing.unpack(frame: frame)
        XCTAssertEqual(unpackedMetadata, metadata)
        XCTAssertEqual(unpackedPayload, payload)
    }

    func testEmptyMetadataAndPayloadRoundTrips() throws {
        let frame = Framing.pack(metadata: [:], payload: Data())
        let (metadata, payload) = try Framing.unpack(frame: frame)
        XCTAssertTrue(metadata.isEmpty)
        XCTAssertTrue(payload.isEmpty)
    }

    func testShorterThanPrefixIsRejected() {
        XCTAssertThrowsError(try Framing.unpack(frame: Data([0, 1, 2]))) {
            XCTAssertTrue($0 is Framing.MalformedFrameError)
        }
    }

    func testPrefixExceedingFrameSizeIsRejected() {
        // Claims 1000 bytes of metadata while carrying none.
        let frame = Data([0, 0, 0x03, 0xE8])
        XCTAssertThrowsError(try Framing.unpack(frame: frame)) {
            XCTAssertTrue($0 is Framing.MalformedFrameError)
        }
    }
}
