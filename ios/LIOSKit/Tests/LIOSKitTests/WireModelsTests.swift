import XCTest

@testable import LIOSKit

final class WireModelsTests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    private func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }

    /// Shaped exactly like `lios_protocol.wire.ItemSummary.model_dump_json()` would emit —
    /// snake_case field names, a `null` for the broadcast case, ISO-8601 timestamps. If the
    /// relay's actual JSON ever differs from this, this test is the one that should fail, not a
    /// live request.
    func testDecodesAnItemSummaryShapedLikeThePydanticModel() throws {
        let json = """
            {"id":"5b1b6f1a-9c1e-4b0a-9c1e-4b0a9c1e4b0a",
             "sender_device_id":"5b1b6f1a-9c1e-4b0a-9c1e-4b0a9c1e4b0b",
             "target_device_id":null,
             "size_bytes":1234,
             "created_at":"2026-09-02T21:00:00Z"}
            """
        let summary = try makeDecoder().decode(ItemSummary.self, from: Data(json.utf8))
        XCTAssertEqual(summary.sizeBytes, 1234)
        XCTAssertNil(summary.targetDeviceId)
    }

    func testEncodesPairingRedeemWithSnakeCaseFieldNames() throws {
        let redeem = PairingRedeem(pairingCode: "ABCD1234", platform: .ios, displayName: "the user's iPhone")
        let data = try makeEncoder().encode(redeem)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["pairing_code"] as? String, "ABCD1234")
        XCTAssertEqual(object["display_name"] as? String, "the user's iPhone")
        XCTAssertEqual(object["platform"] as? String, "ios")
    }

    func testDevicePairedRoundTrips() throws {
        let json = """
            {"device_id":"5b1b6f1a-9c1e-4b0a-9c1e-4b0a9c1e4b0a","device_token":"tok_abc"}
            """
        let paired = try makeDecoder().decode(DevicePaired.self, from: Data(json.utf8))
        XCTAssertEqual(paired.deviceToken, "tok_abc")
    }
}
