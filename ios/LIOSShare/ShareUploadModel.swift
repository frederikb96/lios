import Foundation
import LIOSKit

@MainActor
@Observable
final class ShareUploadModel {
    enum UploadState: Equatable {
        case loading
        case uploading
        case done
        case failed(String)
    }

    var state: UploadState = .loading

    /// Runs the whole send path for one shared item: load the attachment, seal it under the
    /// paired group key, upload directly from this process (no App Group staging — see the
    /// entitlements note on why), and report the result. Never throws; every failure becomes a
    /// user-facing `UploadState.failed` message instead, since there is no caller above this to catch
    /// one.
    func send(provider: NSItemProvider) async {
        guard let session = LiosSession.loadFromKeychain() else {
            state = .failed("LIOS isn't paired with a device yet. Open the app to scan a pairing code.")
            return
        }

        let loaded: AttachmentLoader.Loaded
        do {
            loaded = try await AttachmentLoader.load(provider)
        } catch AttachmentLoader.LoadError.tooLarge(let bytes) {
            let megabytes = Double(bytes) / 1_000_000
            state = .failed(String(format: "That's %.0f MB — too large for LIOS to share directly.", megabytes))
            return
        } catch {
            state = .failed("Couldn't read that item.")
            return
        }

        state = .uploading
        do {
            let sealed = try LiosItem.seal(
                id: UUID(), type: loaded.type, filename: loaded.filename, mimeType: loaded.mimeType,
                payload: loaded.payload, groupKey: session.groupKey)

            let preview = ShareUploadModel.buildPreview(loaded: loaded)
            let sealedPreview = try? preview.seal(itemId: sealed.id, groupKey: session.groupKey)

            _ = try await session.makeRelayClient().createItem(
                sealed, targetDeviceId: nil, sealedPreview: sealedPreview)
            state = .done
        } catch {
            state = .failed("Couldn't upload to the relay. Check your connection and try again.")
        }
    }

    private static func buildPreview(loaded: AttachmentLoader.Loaded) -> PushPreview {
        switch loaded.type {
        case .text:
            let text = String(decoding: loaded.payload, as: UTF8.self)
            return PushPreview(
                type: .text, preview: String(text.prefix(PushPreview.previewCharacterLimit)), filename: nil)
        case .image:
            return PushPreview(type: .image, preview: nil, filename: loaded.filename)
        case .file:
            return PushPreview(type: .file, preview: nil, filename: loaded.filename)
        }
    }
}
