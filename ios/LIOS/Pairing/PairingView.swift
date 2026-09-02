import SwiftUI

struct PairingView: View {
    @State private var viewModel = PairingViewModel()

    var body: some View {
        VStack(spacing: 16) {
            switch viewModel.state {
            case .choosing:
                VStack(spacing: 20) {
                    Image(systemName: "bolt.horizontal.circle")
                        .font(.system(size: 56))
                        .foregroundStyle(.tint)
                    Text("Connect LIOS")
                        .font(.title2.bold())
                    Button("Scan a Pairing QR Code", action: viewModel.chooseScan)
                        .buttonStyle(.borderedProminent)
                    Button("Set Up a New Relay", action: viewModel.chooseSetUpNewRelay)
                        .buttonStyle(.bordered)
                    Text(
                        "Scan the code if the Linux client already shows one. Set up a new relay only if this is the very first device to connect to it."
                    )
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
                }
                .padding()
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
            case .enteringRelayURL:
                VStack(spacing: 16) {
                    Text("Relay address")
                        .font(.headline)
                    TextField("https://lios.example.net", text: $viewModel.relayURLText)
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .padding(.horizontal)
                    Button("Continue", action: viewModel.submitRelayURL)
                        .buttonStyle(.borderedProminent)
                        .disabled(viewModel.relayURLText.isEmpty)
                }
                .padding()
            case .bootstrapping, .redeeming:
                ProgressView("Connecting…")
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
