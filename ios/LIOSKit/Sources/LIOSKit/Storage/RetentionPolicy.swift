import Foundation

/// The retention policy, shared by both clients: keep the last N items for M days, then
/// expire. Configurable in the app.
public struct RetentionPolicy: Codable, Sendable, Equatable {
    public var maxItems: Int
    public var maxAge: TimeInterval

    public static let `default` = RetentionPolicy(maxItems: 50, maxAge: 7 * 24 * 60 * 60)

    public init(maxItems: Int, maxAge: TimeInterval) {
        self.maxItems = maxItems
        self.maxAge = maxAge
    }
}
