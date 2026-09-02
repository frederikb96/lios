Ready-to-use GitHub Actions workflows for the iOS component, staged here rather than in
`.github/workflows/` because that directory belongs to the relay/protocol/charts work happening
in this same checkout at the same time.

Move each file into `.github/workflows/` (dropping the `ios-` prefix is fine, or keep it if the
repo's other workflows are named without a component prefix — match whatever convention the
relay/Linux workflows use) once that directory exists and is not mid-edit elsewhere. Each is
self-contained and path-filtered to `ios/**` (or, for the release workflow, its own tag prefix
`ios-v*.*.*`) so it only ever runs for iOS changes:

- `ios-free-checks.yml` — Linux, free, every push/PR touching `ios/**`.
- `ios-mac.yml` — macOS, PR and manual dispatch only.
- `ios-release.yml` — macOS, on an `ios-v*.*.*` tag, a bimonthly cron (TestFlight expiry), or
  manual dispatch.

Needed once, before `ios-release.yml` can run: the repo secrets `ASC_KEY_ID`, `ASC_ISSUER_ID`,
`ASC_KEY_P8_BASE64`, `IOS_TEAM_ID`, `IOS_BUILD_CERTIFICATE_BASE64`, `IOS_P12_PASSWORD` (all
account-wide and reusable from `the secret store` as-is), plus three new
per-target ones — `IOS_PROVISIONING_PROFILE_BASE64` (host app), `IOS_PROVISIONING_PROFILE_SHARE_BASE64`,
`IOS_PROVISIONING_PROFILE_NOTIFY_BASE64` — mirrored the same way, from the three provisioning
profiles already minted (see the report this shipped with).
