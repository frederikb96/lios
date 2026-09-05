// swift-tools-version: 6.2
import PackageDescription

// The app target (LIOS/) is Apple-only and lives outside this package; everything worth testing
// without an app host lives here instead, so it builds and tests on any Linux runner for free.
//
// swift-crypto is Apple's own drop-in for CryptoKit: on Apple platforms it re-exports CryptoKit
// itself, and on Linux it ships the same AES.GCM API over BoringSSL. That is what keeps
// `Sources/LIOSKit/Crypto/Sealing.swift` free of a `#if canImport(CryptoKit)` split — it is one
// file, proven by the same test on every platform, matching lios_protocol.crypto byte for byte.
//
// The Debug bridge and the Keychain-backed stores are Apple-only (Network.framework, Security),
// guarded with `#if canImport(...)` rather than excluded here — they still parse under
// `swiftc -parse` on Linux, which is what `Tooling/parse-swift.sh` checks.
let package = Package(
    name: "LIOSKit",
    platforms: [.iOS(.v26), .macOS(.v26)],
    products: [
        .library(name: "LIOSKit", targets: ["LIOSKit"])
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-crypto.git", from: "4.5.1")
    ],
    targets: [
        .target(
            name: "LIOSKit",
            dependencies: [
                .product(name: "Crypto", package: "swift-crypto")
            ]
        ),
        .testTarget(
            name: "LIOSKitTests",
            dependencies: ["LIOSKit"]
        ),
    ]
)
