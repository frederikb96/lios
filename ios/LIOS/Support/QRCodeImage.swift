import CoreImage.CIFilterBuiltins
import SwiftUI

/// Renders a string as a QR code image — used for inviting a second device, the reverse
/// direction of `QRScannerView`.
enum QRCodeImage {
    static func render(_ string: String) -> Image? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        // The generator's native output is a handful of pixels across; scaling up in CoreImage
        // keeps the edges crisp, which scaling a SwiftUI `Image` up later would not.
        guard let ciImage = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 10, y: 10)) else {
            return nil
        }
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else { return nil }
        return Image(decorative: cgImage, scale: 1, orientation: .up)
    }
}
