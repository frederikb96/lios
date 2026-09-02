import XCTest

@testable import LIOSKit

final class PairingTests: XCTestCase {

    func testRoundTripThroughQrUri() throws {
        let groupKey = Sealing.generateGroupKey()
        let payload = try Pairing.buildPayload(
            relayUrl: "https://lios.frederikberg.net", pairingCode: "ABCD2345", groupKey: groupKey)
        let uri = try Pairing.encodeQrUri(payload)
        XCTAssertTrue(uri.hasPrefix("lios://pair/"))

        let decoded = try Pairing.decodeQrUri(uri)
        XCTAssertEqual(decoded.relayUrl, payload.relayUrl)
        XCTAssertEqual(decoded.pairingCode, payload.pairingCode)
        XCTAssertEqual(try decoded.groupKey(), groupKey)
    }

    func testUriWithoutTheLiosSchemeIsRejected() {
        XCTAssertThrowsError(try Pairing.decodeQrUri("https://example.com/not-a-pairing-link")) {
            XCTAssertTrue($0 is Pairing.InvalidUriError)
        }
    }

    /// A payload built by `lios_protocol.pairing.encode_qr_uri` on the Linux side is what this
    /// app actually has to read. Constructed by hand here from the Python module's own
    /// documented shape (URL-safe base64 of the JSON, `lios://pair/` prefix, snake_case field
    /// names) rather than round-tripped through this app's own encoder, so this test would catch
    /// a drift the round-trip test above cannot.
    func testDecodesAPayloadShapedLikeThePythonEncoderProduces() throws {
        let json = """
            {"relay_url":"https://lios.frederikberg.net","pairing_code":"WXYZ9876",\
            "group_key_b64":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}
            """
        let encoded = Data(json.utf8).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
        let payload = try Pairing.decodeQrUri("lios://pair/\(encoded)")
        XCTAssertEqual(payload.relayUrl, "https://lios.frederikberg.net")
        XCTAssertEqual(payload.pairingCode, "WXYZ9876")
        XCTAssertEqual(try payload.groupKey().count, Sealing.keySize)
    }

    func testGeneratedPairingCodeAvoidsAmbiguousGlyphs() {
        let code = Pairing.generatePairingCode()
        XCTAssertEqual(code.count, 8)
        for glyph in "0O1IL" {
            XCTAssertFalse(code.contains(glyph))
        }
    }

    func testBuildPayloadRejectsAWrongSizedKey() {
        XCTAssertThrowsError(
            try Pairing.buildPayload(relayUrl: "https://x", pairingCode: "X", groupKey: Data(repeating: 0, count: 10)))
    }
}
