import Foundation
#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// The REST surface `lios-relay` exposes, as far as this app needs it.
///
/// 🚨 The relay (`relay/`) is being built in parallel and had no HTTP routes yet when this was
/// written — only `lios_protocol.wire`'s request/response *shapes* exist. Everything below that
/// is not a wire model field (endpoint paths, HTTP methods, which parts are headers versus JSON
/// versus a raw body) is this app's own proposal, chosen to keep large payloads off base64 and
/// out of JSON. Treat every path and header name here as provisional until it is checked against
/// the relay's actual routes — they are all named as constants below for exactly that reason.
///
/// iOS never opens `GET /api/stream` — that is the Linux client's long-lived connection. This
/// app instead learns about new items from an APNs push and fetches on demand, which is also why
/// this client has no WebSocket or SSE transport: everything here is a single request/response,
/// which is also what keeps it buildable and testable on Linux.
public final class RelayClient: Sendable {

    public enum Endpoint {
        static func pair(base: URL) -> URL { base.appendingPathComponent("api/devices/pair") }
        static func pushToken(base: URL, deviceId: UUID) -> URL {
            base.appendingPathComponent("api/devices/\(deviceId.uuidString)/push-token")
        }
        static func items(base: URL) -> URL { base.appendingPathComponent("api/items") }
        static func item(base: URL, id: UUID) -> URL { base.appendingPathComponent("api/items/\(id.uuidString)") }
    }

    /// Custom request headers this client sends alongside the standard ones, for the parts of a
    /// create-item request that are not JSON (the body is the raw sealed blob, to avoid a
    /// base64 blow-up on an image or a video).
    private enum Header {
        static let itemId = "X-Item-Id"
        static let targetDeviceId = "X-Target-Device-Id"
        static let sealedPreview = "X-Sealed-Preview"
    }

    public struct HTTPError: Error, Sendable {
        public let statusCode: Int
        public let body: Data
    }

    private let baseURL: URL
    private let deviceToken: String?
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    public init(relayURL: URL, deviceToken: String?, session: URLSession = .shared) {
        self.baseURL = relayURL
        self.deviceToken = deviceToken
        self.session = session

        // The relay's Pydantic models serialise with their declared (snake_case) field names —
        // this conversion is what lets `WireModels.swift` stay idiomatic Swift on both sides of
        // the wire without a `CodingKeys` block per type.
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder
    }

    /// `POST /api/devices/pair` — redeem a pairing code minted by an already-paired device for
    /// this device's own credential. No `Authorization` header: this call is what obtains one.
    public func redeemPairing(code: String, platform: LiosPlatform, displayName: String) async throws -> DevicePaired {
        var request = URLRequest(url: Endpoint.pair(base: baseURL))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(
            PairingRedeem(pairingCode: code, platform: platform, displayName: displayName))
        return try await send(request, decoding: DevicePaired.self)
    }

    /// `POST /api/devices/{id}/push-token` — register (or replace) this device's APNs token.
    public func updatePushToken(deviceId: UUID, apnsToken: String) async throws {
        var request = authenticatedRequest(url: Endpoint.pushToken(base: baseURL, deviceId: deviceId))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(PushTokenUpdate(apnsToken: apnsToken))
        _ = try await send(request)
    }

    /// `POST /api/items` — upload one sealed item. The body is the raw sealed blob
    /// (`application/octet-stream`), never base64-embedded in JSON, so an image or a video costs
    /// no encoding overhead on top of AES-GCM's fixed 28 bytes. `targetDeviceId` narrows delivery
    /// to one device; omitted, the item broadcasts to every other paired device.
    public func createItem(_ sealed: LiosItem.Sealed, targetDeviceId: UUID?, sealedPreview: Data?) async throws
        -> ItemCreated
    {
        var request = authenticatedRequest(url: Endpoint.items(base: baseURL))
        request.httpMethod = "POST"
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue(sealed.id.uuidString, forHTTPHeaderField: Header.itemId)
        if let targetDeviceId {
            request.setValue(targetDeviceId.uuidString, forHTTPHeaderField: Header.targetDeviceId)
        }
        if let sealedPreview, !sealedPreview.isEmpty {
            request.setValue(sealedPreview.base64EncodedString(), forHTTPHeaderField: Header.sealedPreview)
        }
        request.httpBody = sealed.blob
        return try await send(request, decoding: ItemCreated.self)
    }

    /// `GET /api/items?since=` — the catch-up list, for reconnect and for the initial history
    /// fill. `since` is inclusive-after: omit it for everything the relay still holds.
    public func fetchItems(since: Date?) async throws -> [ItemSummary] {
        var components = URLComponents(url: Endpoint.items(base: baseURL), resolvingAgainstBaseURL: false)!
        if let since {
            let formatter = ISO8601DateFormatter()
            components.queryItems = [URLQueryItem(name: "since", value: formatter.string(from: since))]
        }
        let request = authenticatedRequest(url: components.url!)
        return try await send(request, decoding: [ItemSummary].self)
    }

    /// `GET /api/items/{id}` — the raw sealed blob. Unlike every other call here this response is
    /// not JSON at all, by design: base64-wrapping it would cost a third of a large image's size
    /// for nothing.
    public func fetchItemBlob(id: UUID) async throws -> Data {
        let request = authenticatedRequest(url: Endpoint.item(base: baseURL, id: id))
        let (data, response) = try await session.data(for: request)
        try Self.assertSuccess(response, body: data)
        return data
    }

    /// `DELETE /api/items/{id}` — acknowledge this device has taken the item, triggering the
    /// relay's retention pruning for it.
    public func deleteItem(id: UUID) async throws {
        var request = authenticatedRequest(url: Endpoint.item(base: baseURL, id: id))
        request.httpMethod = "DELETE"
        _ = try await send(request)
    }

    private func authenticatedRequest(url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        if let deviceToken {
            request.setValue("Bearer \(deviceToken)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    @discardableResult
    private func send(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        try Self.assertSuccess(response, body: data)
        return data
    }

    private func send<T: Decodable>(_ request: URLRequest, decoding type: T.Type) async throws -> T {
        let data = try await send(request)
        return try decoder.decode(T.self, from: data)
    }

    private static func assertSuccess(_ response: URLResponse, body: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            throw HTTPError(statusCode: http.statusCode, body: body)
        }
    }
}
