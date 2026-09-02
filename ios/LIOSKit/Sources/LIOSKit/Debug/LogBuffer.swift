import Foundation

/// The in-app log every screen and background path writes to, and the log view reads and
/// exports from with one tap.
///
/// A TestFlight build has no debugger attached, so this ring buffer is the only way an item that
/// silently failed to arrive is ever diagnosable — you see the buffer, not a console. Kept as
/// a lock-guarded singleton rather than an actor: nearly every call site is a synchronous log
/// statement inside non-async code (a Keychain read, a decode failure), and awaiting each one
/// would be friction with no benefit — the lock is held only for an array append.
public final class LogBuffer: @unchecked Sendable {
    public static let shared = LogBuffer()

    public enum Level: String, Codable, Sendable, Comparable {
        case debug, info, warning, error

        private var rank: Int {
            switch self {
            case .debug: 0
            case .info: 1
            case .warning: 2
            case .error: 3
            }
        }

        public static func < (lhs: Level, rhs: Level) -> Bool { lhs.rank < rhs.rank }
    }

    public struct Entry: Codable, Sendable, Identifiable {
        public let id: UUID
        public let timestamp: Date
        public let level: Level
        public let category: String
        public let message: String

        public init(timestamp: Date, level: Level, category: String, message: String) {
            id = UUID()
            self.timestamp = timestamp
            self.level = level
            self.category = category
            self.message = message
        }
    }

    /// Bounded so a runaway loop cannot grow this without limit — old entries drop silently
    /// once full, which is the correct failure mode for a diagnostic aid, not a data store.
    private let capacity: Int
    private var entries: [Entry] = []
    private let lock = NSLock()

    public init(capacity: Int = 2000) {
        self.capacity = capacity
    }

    public func log(_ level: Level, _ message: String, category: String = "app") {
        lock.lock()
        defer { lock.unlock() }
        entries.append(Entry(timestamp: Date(), level: level, category: category, message: message))
        if entries.count > capacity {
            entries.removeFirst(entries.count - capacity)
        }
    }

    public func snapshot(minimumLevel: Level = .debug) -> [Entry] {
        lock.lock()
        defer { lock.unlock() }
        return entries.filter { $0.level >= minimumLevel }
    }

    public func clear() {
        lock.lock()
        defer { lock.unlock() }
        entries.removeAll()
    }

    /// Plain text, newest-last, for the one-tap share sheet export — the format a human reads
    /// and pastes, not JSON a tool would parse.
    public func exportText() -> String {
        let formatter = ISO8601DateFormatter()
        return snapshot().map { entry in
            "\(formatter.string(from: entry.timestamp)) [\(entry.level.rawValue)] \(entry.category): \(entry.message)"
        }.joined(separator: "\n")
    }
}
