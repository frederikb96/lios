import XCTest

@testable import LIOSKit

final class PushTests: XCTestCase {

    /// A blob produced by `lios_protocol.push.build_push_blob` — the Python side's own output, so
    /// a change to either end of the format fails here rather than as a silent generic banner.
    private let pythonBlob =
        "eyJpdGVtX2lkIjoiMTExMTExMTEtMjIyMi0zMzMzLTQ0NDQtNTU1NTU1NTU1NTU1Iiwic2VuZGVyX2RldmljZV9pZCI6ImFhYWFhYWFhLWJiYmItY2NjYy1kZGRkLWVlZWVlZWVlZWVlZSIsInNlYWxlZF9wcmV2aWV3IjoiQUFFPSJ9"

    func testDecodesTheBlobLiosProtocolBuilds() throws {
        let userInfo: [AnyHashable: Any] = ["aps": [:], "lios": ["v": 1, "b": pythonBlob]]
        let decoded = try XCTUnwrap(PushPayload.decode(userInfo: userInfo))
        XCTAssertEqual(decoded.itemId, UUID(uuidString: "11111111-2222-3333-4444-555555555555"))
        XCTAssertEqual(decoded.senderDeviceId, UUID(uuidString: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
        XCTAssertEqual(decoded.sealedPreview, Data([0, 1]))
    }

    func testABlobWithoutAPreviewDecodesToAnEmptyPreview() throws {
        let json = """
            {"item_id":"11111111-2222-3333-4444-555555555555",\
            "sender_device_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            """
        let userInfo: [AnyHashable: Any] = ["lios": ["v": 1, "b": Data(json.utf8).base64EncodedString()]]
        let decoded = try XCTUnwrap(PushPayload.decode(userInfo: userInfo))
        XCTAssertTrue(decoded.sealedPreview.isEmpty)
    }

    func testForeignOrMalformedPushesDecodeToNil() {
        XCTAssertNil(PushPayload.decode(userInfo: [:]))
        XCTAssertNil(PushPayload.decode(userInfo: ["lios": ["v": 2, "b": pythonBlob]]))
        XCTAssertNil(PushPayload.decode(userInfo: ["lios": ["v": 1, "b": "not base64!"]]))
        XCTAssertNil(PushPayload.decode(userInfo: ["lios": ["v": 1]]))
        // The previous payload shape, with the ids at the top level, is no longer read.
        XCTAssertNil(
            PushPayload.decode(userInfo: [
                "item_id": "11111111-2222-3333-4444-555555555555",
                "sender_device_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            ]))
    }

    func testRegisterRequestNamesTheAppAndTheToken() throws {
        let base = URL(string: "https://push.example.test")!
        let request = try PushRelayClient.registerRequest(baseURL: base, apnsToken: "abcd")
        XCTAssertEqual(request.url?.absoluteString, "https://push.example.test/v1/register")
        XCTAssertEqual(request.httpMethod, "POST")
        let body = try XCTUnwrap(request.httpBody)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: String])
        XCTAssertEqual(object, ["app": "lios", "apns_token": "abcd"])
    }

    func testDecodesTheTicketFromARegisterResponse() throws {
        let json = #"{"ticket":"opaque","ticket_id":"0123456789abcdef","expires_at":"2027-02-11T00:00:00Z"}"#
        XCTAssertEqual(try PushRelayClient.decodeTicket(Data(json.utf8)), "opaque")
    }
}
