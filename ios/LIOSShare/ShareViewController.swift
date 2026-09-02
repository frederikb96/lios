import SwiftUI
import UIKit

/// `NSExtensionPrincipalClass` for the share extension. Hosts a SwiftUI view rather than a
/// storyboard scene — this target has no `NSExtensionMainStoryboard` key, so the system
/// instantiates this class directly and expects it to build its own UI.
final class ShareViewController: UIViewController {

    override func viewDidLoad() {
        super.viewDidLoad()

        let provider = firstAttachment()
        let root = ShareRootView(provider: provider) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil)
        }
        let hosting = UIHostingController(rootView: root)
        addChild(hosting)
        view.addSubview(hosting.view)
        hosting.view.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            hosting.view.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            hosting.view.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            hosting.view.topAnchor.constraint(equalTo: view.topAnchor),
            hosting.view.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
        hosting.didMove(toParent: self)
    }

    /// LIOS sends one item per share, even when the share sheet offers several attachments
    /// (a multi-photo selection, say) — simplest correct behaviour for a first version, and
    /// consistent with the activation rule's max counts existing only to make those items
    /// eligible to share at all, not to promise every one is sent.
    private func firstAttachment() -> NSItemProvider? {
        let items = extensionContext?.inputItems as? [NSExtensionItem] ?? []
        return items.first?.attachments?.first
    }
}
