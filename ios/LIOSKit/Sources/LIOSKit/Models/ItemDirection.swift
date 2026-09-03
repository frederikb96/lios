import Foundation

/// Which way an item travelled relative to this device — the one piece of information
/// `LiosItem` had no notion of at all until sent-item history existed, since every screen until
/// then only ever showed items this device received.
public enum ItemDirection: String, Codable, Sendable {
    case sent
    case received
}
