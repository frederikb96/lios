import LIOSKit
import UIKit
import UserNotifications

/// Requests notification permission, registers for remote notifications, captures the APNs
/// device token and routes a tapped banner into `NotificationRouter`.
///
/// A `UIApplicationDelegateAdaptor` rather than anything SwiftUI-native: the APNs token callback
/// is delivered to an app delegate or nowhere, and SwiftUI has no equivalent entry point.
final class PushRegistrar: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            LogBuffer.shared.log(
                .info, "notification authorization granted=\(granted) error=\(String(describing: error))",
                category: "push")
            guard granted else { return }
            Task { @MainActor in
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
        return true
    }

    // `Data` is `Sendable`, so this hop needs nothing extracted first — the parameter itself is
    // safe to carry across the actor boundary.
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let tokenHex = deviceToken.map { String(format: "%02x", $0) }.joined()
        LogBuffer.shared.log(.info, "APNs token registered (\(tokenHex.count) hex chars)", category: "push")
        Task {
            await Self.uploadPushToken(tokenHex: tokenHex)
        }
    }

    // `nonisolated` because `UIApplicationDelegate`'s requirement is nonisolated and `Error` is
    // not `Sendable` — extract the one thing worth logging (its description, a `String`, which
    // is `Sendable`) before doing anything actor-isolated.
    nonisolated func application(
        _ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        let description = error.localizedDescription
        LogBuffer.shared.log(.error, "APNs registration failed: \(description)", category: "push")
    }

    /// A push arrives while the app is in the foreground — still shown as a banner, per row
    /// order 8: the write only happens on the explicit tap in `didReceive`, never here.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound, .list]
    }

    /// The one moment this app is allowed to write the pasteboard or open a share sheet: an
    /// explicit tap brought the app to the foreground, which is a real UI context.
    ///
    /// `userInfo` (`[AnyHashable: Any]`) is not `Sendable`, so it is decoded right here, on this
    /// nonisolated method's own thread, into `PushPayload.Decoded` — plain `UUID`s and `Data` —
    /// before anything hops to `NotificationRouter`'s `@MainActor`. Sending the raw dictionary
    /// across that boundary instead is exactly what Swift 6 rejects.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse
    ) async {
        let userInfo = response.notification.request.content.userInfo
        guard let decoded = PushPayload.decode(userInfo: userInfo) else {
            LogBuffer.shared.log(
                .warning, "tapped notification carried no recognisable LIOS payload", category: "push")
            return
        }
        await NotificationRouter.shared.handleTap(decoded: decoded)
    }

    private static func uploadPushToken(tokenHex: String) async {
        guard let session = LiosSession.loadFromKeychain() else {
            LogBuffer.shared.log(.warning, "APNs token arrived before pairing; dropped", category: "push")
            return
        }
        do {
            try await session.makeRelayClient().updatePushToken(deviceId: session.deviceId, apnsToken: tokenHex)
            LogBuffer.shared.log(.info, "APNs token uploaded to relay", category: "push")
        } catch {
            LogBuffer.shared.log(.error, "APNs token upload failed: \(error)", category: "push")
        }
    }
}
