import Foundation
import WidgetKit

struct CodexControlWidgetAccount: Codable, Sendable {
    let id: UUID
    let displayName: String
    let isActive: Bool
    let todayTokens: Int64
    let sevenDayTokens: Int64
    let allTimeTokens: Int64
    let quotaRemainingPercent: Double?
    let quotaLabel: String?
}

struct CodexControlWidgetSnapshot: Codable, Sendable {
    let version: Int
    let accounts: [CodexControlWidgetAccount]
    let trackingStartedAt: Date?
    let updatedAt: Date
}

struct WidgetSnapshotStore {
    static let widgetKind = "CodexControlTokenWidget"

    func save(
        accounts: [StoredAccount],
        runtimeStates: [UUID: AccountRuntimeState],
        tokenUsage: [UUID: AccountTokenUsageSnapshot],
        activeAccountID: UUID?) throws
    {
        try FileLocations.ensureDirectories()

        let summaries = accounts.enumerated().map { index, account in
            let quotaSnapshot = runtimeStates[account.id]?.snapshot
            let usage = tokenUsage[account.id]
            return CodexControlWidgetAccount(
                id: account.id,
                displayName: self.privateDisplayName(for: account, fallbackIndex: index + 1),
                isActive: account.id == activeAccountID,
                todayTokens: usage?.today.totalTokens ?? 0,
                sevenDayTokens: usage?.lastSevenDays.totalTokens ?? 0,
                allTimeTokens: usage?.allTime.totalTokens ?? 0,
                quotaRemainingPercent: quotaSnapshot?.hasQuotaWindows == true
                    ? quotaSnapshot?.lowestRemainingPercent
                    : nil,
                quotaLabel: quotaSnapshot?.primaryWindow?.shortLabel ?? quotaSnapshot?.secondaryWindow?.shortLabel)
        }
        .sorted { left, right in
            if left.isActive != right.isActive { return left.isActive }
            if left.todayTokens != right.todayTokens { return left.todayTokens > right.todayTokens }
            return left.displayName.localizedCaseInsensitiveCompare(right.displayName) == .orderedAscending
        }

        let snapshot = CodexControlWidgetSnapshot(
            version: 1,
            accounts: summaries,
            trackingStartedAt: tokenUsage.values.map(\.trackingStartedAt).min(),
            updatedAt: Date())
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(snapshot)
        for destination in [FileLocations.widgetSnapshotFile, FileLocations.widgetExtensionSnapshotFile] {
            try FileManager.default.createDirectory(
                at: destination.deletingLastPathComponent(),
                withIntermediateDirectories: true)
            try data.write(to: destination, options: .atomic)
        }
        WidgetCenter.shared.reloadTimelines(ofKind: Self.widgetKind)
    }

    private func privateDisplayName(for account: StoredAccount, fallbackIndex: Int) -> String {
        if let nickname = account.nickname?.trimmingCharacters(in: .whitespacesAndNewlines), !nickname.isEmpty {
            return nickname
        }

        if let email = account.emailHint,
           let atIndex = email.firstIndex(of: "@")
        {
            let localPart = String(email[..<atIndex])
            let domain = String(email[email.index(after: atIndex)...])
            if let first = localPart.first {
                return "\(first)***@\(domain)"
            }
        }

        return "Account \(fallbackIndex)"
    }
}
