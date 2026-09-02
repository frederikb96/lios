import LIOSKit
import SwiftUI
import UIKit

@MainActor
@Observable
final class PairingViewModel {
    enum PairingState: Equatable {
        case scanning
        case redeeming
        case failed(String)
    }

    var state: PairingState = .scanning

    func handleScannedCode(_ code: String) {
        state = .redeeming
        Task {
            await redeem(code)
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
        state = .scanning
    }
}
