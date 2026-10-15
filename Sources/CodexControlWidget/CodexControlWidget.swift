import Darwin
import Foundation
import SwiftUI
import WidgetKit

private struct WidgetAccount: Codable, Identifiable {
    let id: UUID
    let displayName: String
    let isActive: Bool
    let todayTokens: Int64
    let sevenDayTokens: Int64
    let allTimeTokens: Int64
    let quotaRemainingPercent: Double?
    let quotaLabel: String?
}

private struct WidgetSnapshot: Codable {
    let version: Int
    let accounts: [WidgetAccount]
    let trackingStartedAt: Date?
    let updatedAt: Date

    static let placeholder = WidgetSnapshot(
        version: 1,
        accounts: [
            WidgetAccount(
                id: UUID(),
                displayName: "Work",
                isActive: true,
                todayTokens: 128_400,
                sevenDayTokens: 742_100,
                allTimeTokens: 2_840_000,
                quotaRemainingPercent: 68,
                quotaLabel: "5h"),
            WidgetAccount(
                id: UUID(),
                displayName: "Personal",
                isActive: false,
                todayTokens: 42_800,
                sevenDayTokens: 296_000,
                allTimeTokens: 1_120_000,
                quotaRemainingPercent: 91,
                quotaLabel: "5h"),
        ],
        trackingStartedAt: Date().addingTimeInterval(-86400 * 30),
        updatedAt: Date())

    var activeAccount: WidgetAccount? {
        self.accounts.first(where: \.isActive) ?? self.accounts.first
    }

    var todayTokens: Int64 {
        self.accounts.reduce(0) { $0 + $1.todayTokens }
    }

    var sevenDayTokens: Int64 {
        self.accounts.reduce(0) { $0 + $1.sevenDayTokens }
    }
}

private enum WidgetSnapshotReader {
    static func load() -> WidgetSnapshot? {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        for url in self.candidateURLs() where FileManager.default.fileExists(atPath: url.path) {
            if let data = try? Data(contentsOf: url),
               let snapshot = try? decoder.decode(WidgetSnapshot.self, from: data)
            {
                return snapshot
            }
        }
        return nil
    }

    private static func candidateURLs() -> [URL] {
        var homes: [URL] = [FileManager.default.homeDirectoryForCurrentUser]
        if let user = getpwuid(getuid()), let home = user.pointee.pw_dir {
            homes.insert(URL(fileURLWithPath: String(cString: home), isDirectory: true), at: 0)
        }

        return Array(Set(homes.map(\.standardizedFileURL))).map {
            $0.appendingPathComponent("Library/Application Support/CodexControl/widget-snapshot.json")
        }
    }
}

private struct TokenWidgetEntry: TimelineEntry {
    let date: Date
    let snapshot: WidgetSnapshot
    let isPlaceholder: Bool
}

private struct TokenWidgetProvider: TimelineProvider {
    func placeholder(in context: Context) -> TokenWidgetEntry {
        TokenWidgetEntry(date: Date(), snapshot: .placeholder, isPlaceholder: true)
    }

    func getSnapshot(in context: Context, completion: @escaping (TokenWidgetEntry) -> Void) {
        completion(TokenWidgetEntry(
            date: Date(),
            snapshot: context.isPreview ? .placeholder : (WidgetSnapshotReader.load() ?? .placeholder),
            isPlaceholder: context.isPreview))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<TokenWidgetEntry>) -> Void) {
        let now = Date()
        let snapshot = WidgetSnapshotReader.load() ?? WidgetSnapshot(
            version: 1,
            accounts: [],
            trackingStartedAt: nil,
            updatedAt: now)
        let entry = TokenWidgetEntry(date: now, snapshot: snapshot, isPlaceholder: false)
        completion(Timeline(
            entries: [entry],
            policy: .after(now.addingTimeInterval(15 * 60))))
    }
}

private struct CodexControlWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: TokenWidgetEntry

    var body: some View {
        Group {
            switch self.family {
            case .systemSmall:
                self.smallView
            case .systemLarge:
                self.largeView
            default:
                self.mediumView
            }
        }
        .containerBackground(for: .widget) {
            LinearGradient(
                colors: [Color(nsColor: .windowBackgroundColor), Color.accentColor.opacity(0.09)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing)
        }
        .redacted(reason: self.entry.isPlaceholder ? .placeholder : [])
    }

    private var smallView: some View {
        VStack(alignment: .leading, spacing: 8) {
            self.brandHeader

            Spacer(minLength: 0)

            if let account = self.entry.snapshot.activeAccount {
                Text(account.displayName)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Text(TokenWidgetFormatter.compact(account.todayTokens))
                    .font(.system(size: 28, weight: .bold, design: .rounded).monospacedDigit())
                    .minimumScaleFactor(0.65)
                    .lineLimit(1)
                Text("tokens today")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Spacer(minLength: 0)
                QuotaBadge(account: account)
            } else {
                self.emptyState
            }
        }
        .padding(14)
    }

    private var mediumView: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 7) {
                self.brandHeader
                Spacer(minLength: 0)
                Text("Today")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(TokenWidgetFormatter.compact(self.entry.snapshot.todayTokens))
                    .font(.system(size: 26, weight: .bold, design: .rounded).monospacedDigit())
                Text("\(TokenWidgetFormatter.compact(self.entry.snapshot.sevenDayTokens)) in 7 days")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .frame(width: 116, alignment: .leading)

            Divider()

            VStack(spacing: 7) {
                if self.entry.snapshot.accounts.isEmpty {
                    self.emptyState
                } else {
                    ForEach(Array(self.entry.snapshot.accounts.prefix(3))) { account in
                        AccountUsageRow(account: account)
                    }
                }
            }
            .frame(maxWidth: .infinity)
        }
        .padding(14)
    }

    private var largeView: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                self.brandHeader
                Spacer()
                VStack(alignment: .trailing, spacing: 1) {
                    Text(TokenWidgetFormatter.compact(self.entry.snapshot.todayTokens))
                        .font(.title2.bold().monospacedDigit())
                    Text("tokens today")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 8) {
                WidgetMetricCard(
                    title: "Today",
                    value: self.entry.snapshot.todayTokens,
                    systemName: "sun.max.fill",
                    tint: .blue)
                WidgetMetricCard(
                    title: "7 days",
                    value: self.entry.snapshot.sevenDayTokens,
                    systemName: "calendar",
                    tint: .purple)
            }

            Text("Accounts")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            if self.entry.snapshot.accounts.isEmpty {
                self.emptyState
            } else {
                VStack(spacing: 8) {
                    ForEach(Array(self.entry.snapshot.accounts.prefix(6))) { account in
                        AccountUsageRow(account: account, expanded: true)
                    }
                }
            }

            Spacer(minLength: 0)
            Text("Updated \(self.entry.snapshot.updatedAt.formatted(date: .omitted, time: .shortened))")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(16)
    }

    private var brandHeader: some View {
        HStack(spacing: 6) {
            Image(systemName: "number.circle.fill")
                .foregroundStyle(Color.accentColor)
            Text("Codex Tokens")
                .font(.caption.weight(.semibold))
                .lineLimit(1)
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 5) {
            Image(systemName: "chart.bar.xaxis")
                .foregroundStyle(.secondary)
            Text("Open CodexControl to begin tracking.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

private struct AccountUsageRow: View {
    let account: WidgetAccount
    var expanded = false

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(self.account.isActive ? Color.green : Color.secondary.opacity(0.3))
                .frame(width: 7, height: 7)

            VStack(alignment: .leading, spacing: 2) {
                Text(self.account.displayName)
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                if self.expanded {
                    Text("\(TokenWidgetFormatter.compact(self.account.sevenDayTokens)) / 7d")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            Spacer(minLength: 4)

            Text(TokenWidgetFormatter.compact(self.account.todayTokens))
                .font(.caption.weight(.bold).monospacedDigit())

            QuotaBadge(account: self.account, compact: true)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, self.expanded ? 7 : 6)
        .background(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(self.account.isActive ? Color.green.opacity(0.09) : Color.primary.opacity(0.045)))
    }
}

private struct QuotaBadge: View {
    let account: WidgetAccount
    var compact = false

    var body: some View {
        if let remaining = self.account.quotaRemainingPercent {
            HStack(spacing: 3) {
                if !self.compact {
                    Text(self.account.quotaLabel?.uppercased() ?? "QUOTA")
                }
                Text("\(Int(remaining.rounded()))%")
                    .monospacedDigit()
            }
            .font(.system(size: self.compact ? 9 : 10, weight: .semibold, design: .rounded))
            .foregroundStyle(self.tint(for: remaining))
            .padding(.horizontal, self.compact ? 5 : 7)
            .padding(.vertical, 3)
            .background(Capsule().fill(self.tint(for: remaining).opacity(0.11)))
        }
    }

    private func tint(for remaining: Double) -> Color {
        if remaining <= 10 { return .red }
        if remaining <= 20 { return .orange }
        return .green
    }
}

private struct WidgetMetricCard: View {
    let title: String
    let value: Int64
    let systemName: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Label(self.title, systemImage: self.systemName)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(self.tint)
            Text(TokenWidgetFormatter.compact(self.value))
                .font(.title3.bold().monospacedDigit())
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 11).fill(self.tint.opacity(0.08)))
    }
}

private enum TokenWidgetFormatter {
    static func compact(_ value: Int64) -> String {
        let magnitude = abs(Double(value))
        let divisor: Double
        let suffix: String
        switch magnitude {
        case 1_000_000_000...:
            divisor = 1_000_000_000
            suffix = "B"
        case 1_000_000...:
            divisor = 1_000_000
            suffix = "M"
        case 1_000...:
            divisor = 1_000
            suffix = "K"
        default:
            return value.formatted(.number.grouping(.automatic))
        }
        let scaled = Double(value) / divisor
        return scaled.formatted(.number.precision(.fractionLength(0 ... (scaled.magnitude >= 100 ? 0 : 1)))) + suffix
    }
}

struct CodexControlTokenWidget: Widget {
    let kind = "CodexControlTokenWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: self.kind, provider: TokenWidgetProvider()) { entry in
            CodexControlWidgetView(entry: entry)
        }
        .configurationDisplayName("Codex Tokens")
        .description("Track daily Token usage and remaining Codex quota for your accounts.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

@main
struct CodexControlWidgetBundle: WidgetBundle {
    var body: some Widget {
        CodexControlTokenWidget()
    }
}
