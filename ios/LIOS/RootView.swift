import LIOSKit
import SwiftUI

struct RootView: View {
    @Bindable private var appState = AppState.shared

    var body: some View {
        Group {
            switch appState.pairingStatus {
            case .notPaired:
                PairingView()
            case .paired:
                TabView {
                    HistoryView()
                        .tabItem { Label("History", systemImage: "clock") }
                    LogView()
                        .tabItem { Label("Log", systemImage: "doc.text") }
                    SettingsView()
                        .tabItem { Label("Settings", systemImage: "gear") }
                }
            }
        }
        .overlay(alignment: .top) {
            if case .textCopied(let preview) = appState.receiveOutcome {
                ReceiveConfirmationBanner(text: "Copied: \(preview)") {
                    appState.receiveOutcome = nil
                }
            } else if case .failed(let message) = appState.receiveOutcome {
                ReceiveConfirmationBanner(text: message, isError: true) {
                    appState.receiveOutcome = nil
                }
            }
        }
        .sheet(isPresented: shareSheetBinding) {
            if case .shareItem(let fileURL) = appState.receiveOutcome {
                ActivityView(items: [fileURL])
            }
        }
    }

    private var shareSheetBinding: Binding<Bool> {
        Binding(
            get: {
                if case .shareItem = appState.receiveOutcome { return true }
                return false
            },
            set: { isPresented in
                if !isPresented { appState.receiveOutcome = nil }
            }
        )
    }
}

private struct ReceiveConfirmationBanner: View {
    let text: String
    var isError: Bool = false
    let dismiss: () -> Void

    var body: some View {
        Text(text)
            .font(.subheadline)
            .padding()
            .background(isError ? Color.red.opacity(0.9) : Color.green.opacity(0.9))
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .padding()
            .task {
                try? await Task.sleep(for: .seconds(3))
                dismiss()
            }
    }
}
