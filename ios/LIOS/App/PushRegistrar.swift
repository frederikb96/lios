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
    ///
    /// The completion-handler form, not `async` — see the note on `didReceive` below for why:
    /// both `willPresent` and `didReceive` were `nonisolated async`, and the completion Swift
    /// synthesises around an `async` delegate method fires wherever the method's *last* hop
    /// left it, not on whatever thread the system called in on. This body never awaits anything,
    /// so that never bit here in practice, but it has the identical shape and costs nothing to
    /// close the same way.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping @Sendable (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .list])
    }

    /// The one moment this app is allowed to write the pasteboard or open a share sheet: an
    /// explicit tap brought the app to the foreground, which is a real UI context.
    ///
    /// `userInfo` (`[AnyHashable: Any]`) is not `Sendable`, so it is decoded right here, on
    /// whatever thread the system calls this nonisolated method on, into `PushPayload.Decoded`
    /// — plain `UUID`s and `Data` — before anything hops to `NotificationRouter`'s `@MainActor`.
    /// Sending the raw dictionary across that boundary instead is exactly what Swift 6 rejects.
    ///
    /// 🚨 The completion-handler form, not `async` (row 94's crash): `UNUserNotificationCenterDelegate`
    /// requires this method nonisolated, so the async version's body ends up back on a
    /// nonisolated (cooperative-pool) thread the instant `await NotificationRouter.shared.handleTap`
    /// returns — the enclosing function's own isolation, not the callee's, governs where control
    /// resumes. Swift's ObjC completion shim then calls the real completion handler from exactly
    /// there, and UIKit's own bookkeeping right after that call is main-thread-only and asserts,
    /// aborting on every tap. Apple declares this completion handler `@escaping @Sendable`
    /// specifically so it can be carried into a `Task { @MainActor in }` and invoked from there —
    /// that pins the call, and everything UIKit does as a direct consequence of it, to the main
    /// actor regardless of which thread the system invoked this method from.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping @Sendable () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        guard let decoded = PushPayload.decode(userInfo: userInfo) else {
            LogBuffer.shared.log(
                .warning, "tapped notification carried no recognisable LIOS payload", category: "push")
            Task { @MainActor in
                completionHandler()
            }
            return
        }
        Task { @MainActor in
            await NotificationRouter.shared.handleTap(decoded: decoded)
            completionHandler()
        }
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
