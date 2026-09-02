import SwiftUI

struct ShareRootView: View {
    let provider: NSItemProvider?
    let onFinished: () -> Void

    @State private var model = ShareUploadModel()

    var body: some View {
        VStack(spacing: 16) {
            switch model.state {
            case .loading, .uploading:
                ProgressView(model.state == .loading ? "Reading…" : "Sending to LIOS…")
            case .done:
                Label("Sent", systemImage: "checkmark.circle.fill")
                    .font(.title2)
                    .foregroundStyle(.green)
            case .failed(let message):
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.orange)
                    Text(message)
                        .multilineTextAlignment(.center)
                    Button("Close", action: onFinished)
                }
            }
        }
        .padding()
        .task {
            guard let provider else {
                model.state = .failed("Nothing to share.")
                return
            }
            await model.send(provider: provider)
            if model.state == .done {
                try? await Task.sleep(for: .seconds(1))
                onFinished()
            }
        }
    }
}
