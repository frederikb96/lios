import SwiftUI

/// Owns nothing but *whether* `SettingsViewModel` exists yet — construction (a Keychain read
/// among other things, see `SettingsViewModel.init`) happens exactly once, from `.task`, never
/// from this view's own initialiser.
///
/// 🚨 An eager `@State private var viewModel = SettingsViewModel()` looks like it constructs once,
/// but the default-value expression is an ordinary argument to `SettingsView.init()` — it runs
/// every time something constructs a fresh `SettingsView()` value (every re-evaluation of
/// whichever parent body places one, `RootView`'s `TabView` here), and only the *storage* `@State`
/// preserves is exempt from being discarded. The construction itself, Keychain read included,
/// still happens and is thrown away. Row 95's crash log caught exactly that: `SettingsViewModel.
/// init()` on the main thread, blocked in `SecItemCopyMatching`, called from `SettingsView.init()`
/// inside `RootView.body.getter`. An optional `@State` plus a `.task` guard is the standard fix —
/// `.task` runs once per view identity, not once per parent body pass.
struct SettingsView: View {
    @State private var viewModel: SettingsViewModel?

    var body: some View {
        Group {
            if let viewModel {
                SettingsForm(viewModel: viewModel)
            } else {
                ProgressView()
            }
        }
        .task {
            if viewModel == nil {
                viewModel = SettingsViewModel()
            }
        }
    }
}

private struct SettingsForm: View {
    @Bindable var viewModel: SettingsViewModel
    @State private var showForgetConfirmation = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Relay") {
                    if let relayURL = viewModel.relayURL {
                        LabeledContent("Address", value: relayURL.absoluteString)
                    }
                    Button("Invite Another Device", action: viewModel.inviteAnotherDevice)
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
            .sheet(isPresented: inviteSheetBinding) {
                InviteDeviceSheet(state: viewModel.inviteState, dismiss: viewModel.dismissInvite)
            }
        }
    }

    private var inviteSheetBinding: Binding<Bool> {
        Binding(
            get: { viewModel.inviteState != .idle },
            set: { isPresented in
                if !isPresented { viewModel.dismissInvite() }
            }
        )
    }
}

private struct InviteDeviceSheet: View {
    let state: SettingsViewModel.InviteState
    let dismiss: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            switch state {
            case .idle:
                EmptyView()
            case .creating:
                ProgressView("Preparing invite…")
            case .ready(let qrUri):
                if let image = QRCodeImage.render(qrUri) {
                    image
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .frame(maxWidth: 280)
                    Text("Scan this from the new device")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Couldn't render the QR code.")
                }
            case .failed(let message):
                Text(message)
                    .multilineTextAlignment(.center)
            }
            Button("Close", action: dismiss)
        }
        .padding()
    }
}
