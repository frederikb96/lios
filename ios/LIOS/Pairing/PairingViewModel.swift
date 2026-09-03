import LIOSKit
import SwiftUI
import UIKit

@MainActor
@Observable
final class PairingViewModel {
    enum PairingState: Equatable {
        case choosing
        case scanning
        case enteringRelayURL
        case pastingLink
        case bootstrapping
        case redeeming
        case failed(String)
    }

    var state: PairingState = .choosing
    var relayURLText: String = ""
    var pastedLinkText: String = ""

    func chooseScan() {
        state = .scanning
    }

    func chooseSetUpNewRelay() {
        state = .enteringRelayURL
    }

    func choosePasteLink() {
        state = .pastingLink
    }

    func handleScannedCode(_ code: String) {
        state = .redeeming
        Task {
            await redeem(code)
        }
    }

    /// Feeds the same redeem path `handleScannedCode` uses — a pasted link is just a
    /// `lios://pair/...` URI the user typed or pasted instead of a camera reading it.
    func submitPastedLink() {
        state = .redeeming
        Task {
            await redeem(pastedLinkText.trimmingCharacters(in: .whitespacesAndNewlines))
        }
    }

    /// The relay has no devices yet, so there is no QR to scan — whichever device gets here
    /// first calls `POST /api/devices/bootstrap` directly. If another device beat this one to
    /// it (the relay answers 403), that is not a hard failure: it means a QR now exists
    /// somewhere and scanning is the right next step, not a broken setup.
    func submitRelayURL() {
        state = .bootstrapping
        Task {
            await bootstrap()
        }
    }

    private func bootstrap() async {
        guard let relayURL = URL(string: relayURLText), relayURL.scheme != nil else {
            state = .failed("That doesn't look like a valid address.")
            return
        }
        do {
            let client = RelayClient(relayURL: relayURL, deviceToken: nil)
            let displayName = UIDevice.current.name
            let paired = try await client.bootstrapFirstDevice(platform: .ios, displayName: displayName)

            // Bootstrapping never hands back a group key — the relay never holds one at all.
            // This device mints the fleet's only key, right here, and becomes the root every
            // later device's QR ultimately traces back to.
            let groupKey = Sealing.generateGroupKey()

            try KeychainStore.saveRelayURL(relayURL)
            try KeychainStore.saveGroupKey(groupKey)
            try KeychainStore.saveDeviceId(paired.deviceId)
            try KeychainStore.saveDeviceToken(paired.deviceToken)

            LogBuffer.shared.log(.info, "bootstrapped as the first device \(paired.deviceId)", category: "pairing")
            AppState.shared.markPaired(relayURL: relayURL, deviceId: paired.deviceId)
            UIApplication.shared.registerForRemoteNotifications()
        } catch let error as RelayClient.HTTPError where error.statusCode == 403 {
            state = .failed("This relay already has a paired device. Scan its QR code instead of setting up a new one.")
        } catch {
            state = .failed("Couldn't reach that relay. Check the address and try again.")
            LogBuffer.shared.log(.error, "bootstrap failed: \(error)", category: "pairing")
        }
    }

    private func redeem(_ code: String) async {
        do {
            let payload = try Pairing.decodeQrUri(code)
            guard let relayURL = URL(string: payload.relayUrl) else {
                state = .failed("The scanned code's relay address is malformed.")
                return
            }
            let groupKey = try payload.groupKey()

            let client = RelayClient(relayURL: relayURL, deviceToken: nil)
            let displayName = UIDevice.current.name
            let paired = try await client.redeemPairing(
                code: payload.pairingCode, platform: .ios, displayName: displayName)

            try KeychainStore.saveRelayURL(relayURL)
            try KeychainStore.saveGroupKey(groupKey)
            try KeychainStore.saveDeviceId(paired.deviceId)
            try KeychainStore.saveDeviceToken(paired.deviceToken)

            LogBuffer.shared.log(.info, "paired as device \(paired.deviceId)", category: "pairing")
            AppState.shared.markPaired(relayURL: relayURL, deviceId: paired.deviceId)

            // A token requested before pairing finished never had anywhere to go — ask again
            // now that the Keychain actually holds a device to attach it to. Harmless if
            // already granted: `UIApplication.registerForRemoteNotifications` is idempotent.
            UIApplication.shared.registerForRemoteNotifications()
        } catch let error as Pairing.InvalidUriError {
            state = .failed("That QR code isn't a LIOS pairing code.")
            LogBuffer.shared.log(.error, "pairing failed: \(error.message)", category: "pairing")
        } catch {
            state = .failed("Couldn't reach the relay. Check the address and try again.")
            LogBuffer.shared.log(.error, "pairing failed: \(error)", category: "pairing")
        }
    }

    func retry() {
        state = .choosing
    }
}
