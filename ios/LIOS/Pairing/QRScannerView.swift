import AVFoundation
import LIOSKit
import SwiftUI

/// A minimal QR scanner — `AVCaptureMetadataOutput` rather than VisionKit's
/// `DataScannerViewController`, since the latter needs a device-support check this app has no
/// other use for and the former is enough for one job: read a `lios://pair/...` string once.
struct QRScannerView: UIViewControllerRepresentable {
    let onCode: (String) -> Void

    func makeUIViewController(context: Context) -> ScannerViewController {
        let controller = ScannerViewController()
        controller.onCode = onCode
        return controller
    }

    func updateUIViewController(_ uiViewController: ScannerViewController, context: Context) {}
}

final class ScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onCode: ((String) -> Void)?

    private let session = AVCaptureSession()
    private var hasDelivered = false
    private var previewLayer: AVCaptureVideoPreviewLayer?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureSession()
    }

    // `CALayer.autoresizingMask` is AppKit-only and unavailable on iOS — a sublayer added
    // directly (rather than through a `UIView`) does not participate in Auto Layout or UIKit's
    // own autoresizing at all, so keeping its frame in sync is this method's job.
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.bounds
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        if !session.isRunning {
            DispatchQueue.global(qos: .userInitiated).async { [session] in
                session.startRunning()
            }
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        if session.isRunning {
            session.stopRunning()
        }
    }

    private func configureSession() {
        guard let device = AVCaptureDevice.default(for: .video), let input = try? AVCaptureDeviceInput(device: device)
        else {
            LogBuffer.shared.log(.error, "no camera available for QR scanning", category: "pairing")
            return
        }
        guard session.canAddInput(input) else { return }
        session.addInput(input)

        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else { return }
        session.addOutput(output)
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [.qr]

        let preview = AVCaptureVideoPreviewLayer(session: session)
        preview.videoGravity = .resizeAspectFill
        preview.frame = view.bounds
        view.layer.addSublayer(preview)
        previewLayer = preview
    }

    // `AVCaptureMetadataOutputObjectsDelegate`'s requirement is nonisolated in the SDK, and this
    // type is implicitly @MainActor (a `UIViewController` subclass) — providing a MainActor
    // witness for it is exactly the conformance Swift 6 rejects. `metadataObjects` itself is not
    // `Sendable`, so the fix is not just marking this `nonisolated` but extracting the one thing
    // worth keeping (a plain `String`, genuinely `Sendable`) before ever touching MainActor
    // state — the delegate is registered with `queue: .main` in `configureSession`, so
    // `assumeIsolated` states a guarantee that already holds rather than adding a hop.
    nonisolated func metadataOutput(
        _ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject],
        from connection: AVCaptureConnection
    ) {
        guard let object = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
            let value = object.stringValue
        else {
            return
        }
        MainActor.assumeIsolated {
            guard !hasDelivered else { return }
            hasDelivered = true
            onCode?(value)
        }
    }
}
