# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project uses Semantic Versioning.

## [1.2.8] - 2026-10-15

### Cross-platform release

- Unified the macOS and Windows project introduction, download guidance, and privacy documentation.
- Added a per-user Windows x64 installer, portable package, and SHA-256 checksums.
- Disabled remote Token collection until the user explicitly configures their own SSH targets.
- Removed private infrastructure descriptions and unverified screenshots from the public source tree.
- Rebuilt macOS installers without build-machine provenance metadata; disabled extended attributes in future macOS archives.

### Added

- Per-account local Token analytics for today, the last 7 days, and all tracked time
- Optional incremental SSH collection of Token events from user-configured hosts, with provider-account mapping and pending unknown-account records
- Input, cached input, output, and reasoning Token breakdowns sourced from local Codex session events
- A native macOS WidgetKit extension with small, medium, and large desktop widgets
- Widget snapshots with masked account identifiers and no authentication data; masked labels are not a guarantee of anonymity
- A GitHub-style 7-day Token contribution heatmap with per-day hover details
- An unbounded main account list with explicit empty-state support and no artificial account-count limit
- Compact 14-point daily cells and a rolling date range for the 7-day Token view
- A compact inline Less-to-More legend that removes excess vertical space from the weekly heatmap
- Full-width, evenly distributed weekly cells enlarged to 20 points with more readable Token analytics typography
- An adaptive account search bar that appears only when more than five accounts are present
- Rebalanced weekly heatmap spacing so the cells sit visually centered between the legend and Token totals
- Matched the weekly heatmap's lower visual gap to its upper gap by tightening the Token totals spacing

### Fixed

- Prevent removed accounts from reappearing after managed-home discovery on macOS and Windows
- Recover stale managed account credentials from newer matching auth homes before surfacing refresh-token errors
- Decode Plus account credit balances when the Codex usage API returns `credits.balance` as a string
- Match accounts by the complete auth-subject and provider-account identity so different users in one workspace remain separate
- Resolve the active account only from the exact composite login identity
- Detect exact duplicated credentials, keep one canonical active row, and mark the repair slot for reauthentication
- Remove the account-level Primary label so only the current login is marked Active
- Remove duplicated full-width quota progress bars from expanded account rows
- Build the macOS widget as a real app extension with the standard `NSExtensionMain` entry point so WidgetKit can discover it

## [1.1.3] - 2026-04-23

### Added

- Windows account switching now syncs `.codex-global-state.json` and `.codex-global-state.json.bak` creator IDs when replacing the active account
- Windows restart flow now backs up and restores Codex Desktop MSIX session state under `%LOCALAPPDATA%\Packages\OpenAI.Codex*`
- Regression coverage for Windows account switching, global state rewrites, and desktop session handoff
- Windows account-switching fix notes under `windows/ACCOUNT_SWITCH_FIX.md`

### Changed

- Replaced the repository Windows implementation with the validated fixed Windows source from the working build
- Updated release metadata, landing page references, and documentation for `1.1.3`

### Fixed

- Windows account switching after recent Codex Desktop updates, where copying only `auth.json` could leave Codex Desktop on a stale session or login screen

## [1.1.2] - 2026-04-19

### Fixed

- Windows packaged account switching so the hidden PowerShell restart helper no longer uses `DETACHED_PROCESS`, which previously prevented Codex Desktop from relaunching after a switch
 
## [1.1.1] - 2026-04-19

### Added

- Windows-side presentation logic tests covering active account detection and practical quota sorting
- Tracked Windows build assets for the packaged tray application icon and preview image

### Changed

- Synced the Windows app from the latest stable `CodexControl-dev` implementation
- Updated release metadata and direct download references to `1.1.1`

### Removed

- Sparkle-based macOS update plumbing, appcast generation, and the in-app update action

### Fixed

- Windows active-account logic so shared provider IDs do not incorrectly mark multiple accounts as active
- Windows restart command path normalization for a consistent PowerShell launch path
- Windows quota presentation flow with the newer sorting and filtering layer from the stable dev copy

## [1.1.0] - 2026-04-19

### Added

- Sparkle updater integration for the macOS app with an in-app "Check for Updates" action
- Sparkle bootstrap and appcast generation scripts for local signed release preparation
- Windows release packaging script and GitHub Release asset upload workflow
- Notarization helper script and CI hooks for optional Apple credential-based signing
- Updated website iconography, install cards, and release metadata for the new distribution flow

### Changed

- Replaced the previous blue Orbit Dial mark with the dark, green, and red production brand
- Updated direct download references from `1.0.0` to `1.1.0`
- Embedded Sparkle.framework into the packaged macOS app bundle

### Fixed

- macOS packaging so Sparkle's framework and helper bundle are copied into the app
- Website CTA and navigation affordances so external destinations use explicit icons

## [1.0.0] - 2026-04-19

### Added

- Native macOS menu bar app for Codex quota tracking and account switching
- Windows tray app with quota reads, account management, and switching support
- Static website source and upstream distribution tooling
- GitHub Actions CI and tag-driven release automation
- Release and deployment scripts for macOS packaging and site publishing

### Changed

- Established CodexControl branding, website assets, and project release structure
- Adopted the Orbit Dial brand mark across the website, app packaging, and release assets
- Professionalized repository surface, documentation, and release readiness

### Fixed

- Weekly quota window handling for paid and Team accounts
- Active account switching behavior on macOS
- Account removal confirmation flow on macOS
- Window-specific quota coloring and account sorting logic
