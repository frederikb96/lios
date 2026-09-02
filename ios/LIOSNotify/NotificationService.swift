import LIOSKit
import UserNotifications

/// Decrypts only the small sealed preview attached to the push and rewrites the banner — it
/// never fetches the item's own payload, which is the whole reason a preview travels inside the
/// push in the first place (see `PushPreview`'s own note on why the relay cannot build one).
///
/// This is also, per the spec's verified platform research, a real UI context: it may decrypt
/// and rewrite its own notification content, even though `UIPasteboard.general` is unavailable
/// to it — those are different capabilities, and only the pasteboard write is blocked.
final class NotificationService: UNNotificationServiceExtension {
    private var contentHandler: ((UNNotificationContent) -> Void)?
    private var bestAttemptContent: UNMutableNotificationContent?

    override func didReceive(
        _ request: UNNotificationRequest, withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
    ) {
        self.contentHandler = contentHandler
        let content = (request.content.mutableCopy() as? UNMutableNotificationContent) ?? UNMutableNotificationContent()
        bestAttemptContent = content

        guard
            let decoded = PushPayload.decode(userInfo: request.content.userInfo),
            let session = LiosSession.loadFromKeychain()
        else {
            // Not a recognisable LIOS push, or the device has since been unpaired — deliver the
            // relay's own generic banner unmodified rather than failing loudly.
            deliver(content)
            return
        }

        do {
            guard
                let preview = try PushPreview.open(
                    sealedBlob: decoded.sealedPreview, itemId: decoded.itemId, groupKey: session.groupKey)
            else {
                deliver(content)
                return
            }
            content.title = "LIOS"
            content.body = Self.body(for: preview)
        } catch {
            // A preview that fails to decrypt (stale group key, tampered payload) is not a
            // reason to show nothing — fall back to whatever generic body the relay sent.
        }
        deliver(content)
    }

    override func serviceExtensionTimeWillExpire() {
        // Apple's own deadline arrived before this finished — hand back whatever was built so
        // far rather than nothing at all.
        if let bestAttemptContent {
            deliver(bestAttemptContent)
        }
    }

    private func deliver(_ content: UNNotificationContent) {
        contentHandler?(content)
        contentHandler = nil
    }

    private static func body(for preview: PushPreview) -> String {
        switch preview.type {
        case .text:
            preview.preview ?? "New text item"
        case .image:
            "New image"
        case .file:
            preview.filename.map { "New file: \($0)" } ?? "New file"
        }
    }
}
