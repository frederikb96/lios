import SwiftUI

struct SettingsView: View {
    @State private var viewModel = SettingsViewModel()
    @State private var showForgetConfirmation = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Relay") {
                    if let relayURL = viewModel.relayURL {
                        LabeledContent("Address", value: relayURL.absoluteString)
                    }
                }

                Section("History") {
                    Stepper(
                        "Keep last \(Int(viewModel.maxItems)) items", value: $viewModel.maxItems, in: 10...200, step: 10
                    )
                    .onChange(of: viewModel.maxItems) { _, _ in viewModel.applyRetentionChange() }

                    Stepper(
                        "Keep for \(Int(viewModel.maxAgeDays)) days", value: $viewModel.maxAgeDays, in: 1...30
                    )
                    .onChange(of: viewModel.maxAgeDays) { _, _ in viewModel.applyRetentionChange() }
                }

                Section {
                    Button("Forget this device", role: .destructive) {
                        showForgetConfirmation = true
                    }
                } footer: {
                    Text("Removes this device's pairing. You'll need to scan a new QR code to reconnect.")
                }
            }
            .navigationTitle("Settings")
            .confirmationDialog(
                "Forget this device?", isPresented: $showForgetConfirmation, titleVisibility: .visible
            ) {
                Button("Forget", role: .destructive, action: viewModel.forgetThisDevice)
                Button("Cancel", role: .cancel) {}
            }
        }
    }
}
