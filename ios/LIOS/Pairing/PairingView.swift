import SwiftUI

struct PairingView: View {
    @State private var viewModel = PairingViewModel()

    var body: some View {
        VStack(spacing: 16) {
            switch viewModel.state {
            case .scanning:
                QRScannerView(onCode: viewModel.handleScannedCode)
                    .ignoresSafeArea()
                    .overlay(alignment: .bottom) {
                        Text("Scan the QR code shown by the Linux client")
                            .font(.subheadline)
                            .foregroundStyle(.white)
                            .padding()
                            .background(.black.opacity(0.6), in: Capsule())
                            .padding(.bottom, 40)
                    }
            case .redeeming:
                ProgressView("Pairing…")
            case .failed(let message):
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.orange)
                    Text(message)
                        .multilineTextAlignment(.center)
                    Button("Try again", action: viewModel.retry)
                        .buttonStyle(.borderedProminent)
                }
                .padding()
            }
        }
    }
}
