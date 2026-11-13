import Foundation
#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// The one call this app makes to the shared push relay: trade the APNs device token for a
/// ticket. The ticket — never the token — is what the app hands its own LIOS relay, so a
/// self-hosted relay can push to this device without ever holding an Apple credential or a raw
/// token. See the push relay's own API documentation for the contract.
public final class PushRelayClient: Sendable {

    /// The push relay this build registers with. Compiled in on purpose: the APNs credential
    /// and topic belong to this app's signed bundle, so only the relay that holds them can push
    /// to it. A fork with its own bundle id points this at its own push relay.
    public static let defaultURL = URL(string: "https://push.frederikberg.net")!

    struct RegisterRequest: Encodable {
        let app: String
        let apnsToken: String
    }

    struct RegisterResponse: Decodable {
        let ticket: String
    }

    private let baseURL: URL
    private let session: URLSession

    public init(baseURL: URL = PushRelayClient.defaultURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    /// `POST /v1/register` — returns the opaque ticket for `apnsToken`, valid for the relay's
    /// ticket lifetime. Registering again on every launch keeps it fresh.
    public func register(apnsToken: String) async throws -> String {
        let request = try Self.registerRequest(baseURL: baseURL, apnsToken: apnsToken)
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw RelayClient.HTTPError(statusCode: http.statusCode, body: data)
        }
        return try Self.decodeTicket(data)
    }

    static func registerRequest(baseURL: URL, apnsToken: String) throws -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/register"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        request.httpBody = try encoder.encode(RegisterRequest(app: PushPayload.appName, apnsToken: apnsToken))
        return request
    }

    static func decodeTicket(_ data: Data) throws -> String {
        try JSONDecoder().decode(RegisterResponse.self, from: data).ticket
    }
}
