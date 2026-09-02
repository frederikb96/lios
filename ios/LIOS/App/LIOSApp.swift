import LIOSKit
import SwiftUI

@main
struct LIOSApp: App {

    /// The only way to receive an APNs device token — the callback is delivered to an app
    /// delegate or nowhere, and SwiftUI has no equivalent.
    @UIApplicationDelegateAdaptor(PushRegistrar.self) private var pushRegistrar

    init() {
        LogBuffer.shared.log(.info, "LIOS launched", category: "app")
        if let session = LiosSession.loadFromKeychain() {
            AppState.shared.markPaired(relayURL: session.relayURL, deviceId: session.deviceId)
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
