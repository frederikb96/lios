import XCTest

@testable import LIOSKit

final class SealingTests: XCTestCase {

    func testRoundTripReturnsOriginalPlaintext() throws {
        let key = Sealing.generateGroupKey()
        let plaintext = Data("hello from the linux laptop".utf8)
        let aad = Data("item-1|100".utf8)
        let blob = try Sealing.seal(key: key, plaintext: plaintext, associatedData: aad)
        let opened = try Sealing.open(key: key, blob: blob, associatedData: aad)
        XCTAssertEqual(opened, plaintext)
    }

    /// Mirrors `crypto.py`'s own layout comment: the blob this produces must be byte-for-byte
    /// the same shape the Python side builds by hand, so the relay's stored byte count and this
    /// app's `LiosItem.seal`-computed `sizeBytes` agree without either side asking the other.
    func testBlobLayoutMatchesLiosProtocolCrypto() throws {
        let key = Sealing.generateGroupKey()
        let plaintext = Data("x".utf8)
        let blob = try Sealing.seal(key: key, plaintext: plaintext)
        XCTAssertEqual(blob.count, 12 + plaintext.count + 16)
    }

    func testWrongKeyFailsToOpen() throws {
        let key = Sealing.generateGroupKey()
        let otherKey = Sealing.generateGroupKey()
        let blob = try Sealing.seal(key: key, plaintext: Data("secret".utf8))
        XCTAssertThrowsError(try Sealing.open(key: otherKey, blob: blob)) {
            XCTAssertTrue($0 is Sealing.TamperError)
        }
    }

    func testTamperedCiphertextFailsToOpen() throws {
        let key = Sealing.generateGroupKey()
        var blob = try Sealing.seal(key: key, plaintext: Data("secret".utf8))
        blob[blob.count - 1] ^= 0xFF
        XCTAssertThrowsError(try Sealing.open(key: key, blob: blob)) {
            XCTAssertTrue($0 is Sealing.TamperError)
        }
    }

    func testMismatchedAssociatedDataFailsToOpen() throws {
        let key = Sealing.generateGroupKey()
        let blob = try Sealing.seal(key: key, plaintext: Data("secret".utf8), associatedData: Data("item-1".utf8))
        XCTAssertThrowsError(try Sealing.open(key: key, blob: blob, associatedData: Data("item-2".utf8))) {
            XCTAssertTrue($0 is Sealing.TamperError)
        }
    }

    func testWrongKeyLengthIsRejectedBeforeTouchingTheCryptoPrimitive() {
        XCTAssertThrowsError(try Sealing.seal(key: Data(repeating: 0, count: 16), plaintext: Data())) {
            XCTAssertTrue($0 is Sealing.InvalidInputError)
        }
    }
}
