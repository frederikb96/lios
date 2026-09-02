import LIOSKit
import SwiftUI
import UIKit

/// Wraps `UIActivityViewController` for SwiftUI — there is no first-party SwiftUI share sheet.
/// Used for both the receive path (row order 8: image or file opens on the item so it can be
/// saved or forwarded) and the log export (row order 2.8).
struct ActivityView: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

enum ShareSheetFile {
    /// Writes `data` to a temp file so the share sheet has something with a sensible name and
    /// extension to offer — sharing raw `Data` directly gives every target app a meaningless
    /// generic name. Callers own cleanup; nothing here schedules deletion, since the file only
    /// needs to outlive the activity view controller's own lifetime.
    static func write(data: Data, suggestedFilename: String?, mimeType: String?) -> URL? {
        let filename = suggestedFilename ?? "lios-item.\(fileExtension(forMimeType: mimeType))"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(filename)
        do {
            try data.write(to: url)
            return url
        } catch {
            LogBuffer.shared.log(.error, "failed to stage share-sheet file: \(error)", category: "share")
            return nil
        }
    }

    private static func fileExtension(forMimeType mimeType: String?) -> String {
        switch mimeType {
        case "image/jpeg": "jpg"
        case "image/png": "png"
        case "image/heic": "heic"
        case "application/pdf": "pdf"
        default: "bin"
        }
    }
}
