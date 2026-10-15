import SwiftUI

struct AccountRowView: View {
    let account: StoredAccount
    let displayName: String
    let state: AccountRuntimeState
    let tokenUsage: AccountTokenUsageSnapshot?
    let isDuplicateLogin: Bool
    let isActive: Bool
    let canSwitch: Bool
    let isSelected: Bool
    let isReauthenticating: Bool
    let onSelect: () -> Void
    let onSaveNickname: (String) -> Void
    let onRefresh: () -> Void
    let onSwitch: () -> Void
    let onReauthenticate: () -> Void
    let onOpenFolder: () -> Void
    let onRemove: () -> Void

    @State private var draftNickname = ""

    var body: some View {
        VStack(alignment: .leading, spacing: self.isSelected ? 10 : 7) {
            self.headerRow
            self.summaryContent
                .contentShape(Rectangle())
                .onTapGesture(perform: self.onSelect)

            if self.isSelected {
                Divider()
                    .overlay(Color.primary.opacity(0.08))

                if !self.isDuplicateLogin {
                    TokenUsageDetailPanel(usage: self.tokenUsage)
                        .id(self.isActive)
                }

                HStack(spacing: 6) {
                    if !self.isDuplicateLogin {
                        RowActionButton(systemName: "arrow.clockwise", action: self.onRefresh)
                            .help(self.state.isLoading ? "Refreshing account…" : "Refresh")
                            .disabled(self.state.isLoading)
                    }
                    if self.canSwitch {
                        RowActionButton(systemName: "arrow.left.arrow.right.circle", action: self.onSwitch)
                            .help("Switch active account")
                    }
                    RowActionButton(systemName: "person.crop.circle.badge.checkmark", action: self.onReauthenticate)
                        .help("Reauthenticate")
                        .disabled(self.isReauthenticating)
                    RowActionButton(systemName: "folder", action: self.onOpenFolder)
                        .help("Open folder")
                    RowActionButton(systemName: "trash", role: .destructive, action: self.onRemove)
                        .help("Remove")

                    Spacer()

                    if let updatedAt = self.state.snapshot?.updatedAt {
                        Text("Updated \(updatedAt.formatted(date: .omitted, time: .shortened))")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }

                HStack(spacing: 8) {
                    TextField("Label", text: self.$draftNickname)
                        .accessibilityLabel("Account label")
                        .textFieldStyle(.plain)
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(Color(NSColor.windowBackgroundColor)))
                        .onSubmit(self.saveNickname)

                    Button("Save", action: self.saveNickname)
                    .buttonStyle(.plain)
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        Capsule(style: .continuous)
                            .fill(Color.accentColor.opacity(0.12)))
                    .disabled(!self.hasNicknameChanges)
                    .opacity(self.hasNicknameChanges ? 1 : 0.45)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, self.isSelected ? 11 : 9)
        .background(
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .fill(Color(NSColor.controlBackgroundColor)))
        .overlay(
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(self.isSelected ? Color.accentColor.opacity(0.38) : Color.primary.opacity(0.09), lineWidth: self.isSelected ? 1.2 : 1))
        .onAppear {
            self.draftNickname = self.account.nickname ?? ""
        }
        .onChange(of: self.account.id) {
            self.draftNickname = self.account.nickname ?? ""
        }
    }

    private var hasNicknameChanges: Bool {
        self.draftNickname.trimmingCharacters(in: .whitespacesAndNewlines)
            != (self.account.nickname ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func saveNickname() {
        guard self.hasNicknameChanges else { return }
        let nickname = self.draftNickname.trimmingCharacters(in: .whitespacesAndNewlines)
        self.onSaveNickname(nickname)
        self.draftNickname = nickname
    }

    private var headerRow: some View {
        HStack(alignment: .top, spacing: 8) {
            Button(action: self.onSelect) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(self.displayName)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .truncationMode(.middle)

                    if self.secondaryLine != self.displayName && !self.isDuplicateLogin {
                        Text(self.secondaryLine)
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }

                    HStack(spacing: 7) {
                        if self.isActive {
                            Label("Active", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(Color.accentColor)
                        }
                        if let snapshot = self.state.snapshot {
                            Text(snapshot.planDisplayName)
                                .foregroundStyle(.secondary)
                        }
                        if self.isDuplicateLogin {
                            Label("Duplicate login", systemImage: "exclamationmark.circle")
                                .foregroundStyle(.orange)
                        }
                    }
                    .font(.system(size: 10, weight: .medium))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(self.isSelected ? "Collapse account details" : "Show account details")

            if self.state.isLoading || self.isReauthenticating {
                ProgressView()
                    .controlSize(.small)
                    .frame(width: 24, height: 24)
            } else if self.canSwitch && !self.isSelected {
                HeaderActionPill(
                    title: "Switch",
                    systemName: "arrow.left.arrow.right",
                    action: self.onSwitch)
                    .help("Switch active account")
            } else {
                Image(systemName: self.isSelected ? "chevron.up" : "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.tertiary)
                    .padding(.top, 4)
                    .onTapGesture(perform: self.onSelect)
                    .accessibilityHidden(true)
            }
        }
    }

    @ViewBuilder
    private var summaryContent: some View {
        VStack(spacing: 7) {
            if self.isDuplicateLogin {
                InlineStatePill(
                    text: "Same credentials as another account. Reauthenticate this slot to restore the missing login.",
                    systemName: "person.crop.circle.badge.exclamationmark",
                    tint: .orange,
                    lineLimit: self.isSelected ? 3 : 2)
            } else if let snapshot = self.state.snapshot {
                if snapshot.hasQuotaWindows {
                    HStack(alignment: .top, spacing: 7) {
                        if let primaryWindow = snapshot.primaryWindow {
                            CompactQuotaPill(
                                title: primaryWindow.shortLabel,
                                window: primaryWindow,
                                tint: self.tint(for: primaryWindow))
                        }
                        if let secondaryWindow = snapshot.secondaryWindow {
                            CompactQuotaPill(
                                title: secondaryWindow.shortLabel,
                                window: secondaryWindow,
                                tint: self.tint(for: secondaryWindow))
                        }
                    }
                } else if snapshot.isQuotaBlocked {
                    InlineStatePill(
                        text: "Quota reached",
                        systemName: "exclamationmark.circle.fill",
                        tint: .red)
                } else {
                    InlineStatePill(
                        text: "No quota data",
                        systemName: "chart.bar.xaxis",
                        tint: .secondary)
                }
            } else if let errorMessage = self.state.errorMessage {
                InlineStatePill(
                    text: errorMessage,
                    systemName: "exclamationmark.triangle.fill",
                    tint: .orange,
                    lineLimit: self.isSelected ? 4 : 2)
            } else {
                InlineStatePill(
                    text: "Waiting for data",
                    systemName: "clock",
                    tint: .secondary)
            }

            if self.state.snapshot != nil, let errorMessage = self.state.errorMessage {
                Label("Refresh failed · showing saved quota", systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.orange)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .help(errorMessage)
                    .accessibilityHint(errorMessage)
            }
        }
    }

    private var secondaryLine: String {
        if self.isDuplicateLogin {
            return "Duplicate credentials — reauthenticate"
        }
        return self.account.emailHint ?? self.account.source.displayName
    }

    private func tint(for window: UsageWindowSnapshot) -> Color {
        let remaining = window.remainingPercent
        if remaining <= 10 {
            return .red
        }
        if remaining <= 20 {
            return .orange
        }
        return .green
    }
}

private struct TokenInlineMetric: View {
    let title: String
    let value: Int64?
    var fontSize: CGFloat = 10

    var body: some View {
        HStack(spacing: 4) {
            Text(self.title)
                .foregroundStyle(.secondary)
            Text(self.value.map(TokenCountFormatter.compact) ?? "—")
                .fontWeight(.semibold)
                .foregroundStyle(.primary)
        }
        .font(.system(size: self.fontSize, design: .rounded).monospacedDigit())
    }
}

private struct TokenUsageDetailPanel: View {
    let usage: AccountTokenUsageSnapshot?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Label("Token usage", systemImage: "chart.bar.fill")
                    .font(.system(size: 12, weight: .semibold))
                Spacer()
                if let usage {
                    Text(self.dateRangeText(for: usage.daily))
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            }

            if let usage {
                TokenContributionHeatmap(points: usage.daily)
                    .padding(.top, 7)

                HStack(spacing: 8) {
                    TokenInlineMetric(title: "Today", value: usage.today.totalTokens, fontSize: 11)
                    Spacer(minLength: 4)
                    TokenInlineMetric(title: "7 days", value: usage.lastSevenDays.totalTokens, fontSize: 11)
                    Spacer(minLength: 4)
                    TokenInlineMetric(title: "All time", value: usage.allTime.totalTokens, fontSize: 11)
                }
                .padding(.top, 9)

                HStack(spacing: 12) {
                    TokenCompositionMetric(title: "Today · Input", value: usage.today.inputTokens)
                    TokenCompositionMetric(title: "Cached", value: usage.today.cachedInputTokens)
                    TokenCompositionMetric(title: "Output", value: usage.today.outputTokens)
                    TokenCompositionMetric(title: "Reasoning", value: usage.today.reasoningOutputTokens)
                }
                .padding(.top, 7)
            } else {
                HStack(spacing: 7) {
                    Image(systemName: "clock.badge.checkmark")
                    Text("Tracking begins the next time this account is active.")
                }
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .padding(.top, 7)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .fill(Color(NSColor.windowBackgroundColor).opacity(0.55)))
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke(Color.primary.opacity(0.06), lineWidth: 1))
    }

    private func dateRangeText(for points: [DailyTokenUsagePoint]) -> String {
        guard let firstDate = points.first?.date,
              let lastDate = points.last?.date
        else {
            return "Last 7 days"
        }

        let formatter = DateIntervalFormatter()
        formatter.locale = .autoupdatingCurrent
        formatter.calendar = .autoupdatingCurrent
        formatter.timeZone = .autoupdatingCurrent
        formatter.dateTemplate = "MMM d, yyyy"
        return formatter.string(from: firstDate, to: lastDate)
    }
}

private struct TokenCompositionMetric: View {
    let title: String
    let value: Int64

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(self.title)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.secondary)
            Text(TokenCountFormatter.compact(self.value))
                .font(.system(size: 11, weight: .semibold, design: .rounded).monospacedDigit())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct CompactQuotaPill: View {
    let title: String
    let window: UsageWindowSnapshot
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(self.title.uppercased())
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(self.tint)

                Spacer(minLength: 4)

                Text("\(Int(self.window.remainingPercent.rounded()))% remaining")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
            }

            GeometryReader { geometry in
                Capsule()
                    .fill(self.tint.opacity(0.12))
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(self.tint)
                            .frame(width: geometry.size.width * min(1, max(0, self.window.remainingPercent / 100)))
                    }
            }
            .frame(height: 4)
            .padding(.vertical, 3)
            .accessibilityHidden(true)

            if let resetAt = self.window.compactResetAtDisplay {
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.system(size: 9, weight: .semibold))
                    Text("Resets \(resetAt)")
                        .lineLimit(1)
                }
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(self.tint.opacity(0.045)))
    }
}

private struct InlineStatePill: View {
    let text: String
    let systemName: String
    let tint: Color
    var lineLimit = 1

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: self.systemName)
                .font(.system(size: 10, weight: .semibold))
            Text(self.text)
                .lineLimit(self.lineLimit)
                .multilineTextAlignment(.leading)
        }
        .font(.system(size: 11, weight: .medium))
        .foregroundStyle(self.tint)
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(self.tint.opacity(0.08)))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(self.tint.opacity(0.14), lineWidth: 1))
    }
}

private struct RowActionButton: View {
    let systemName: String
    var role: ButtonRole?
    let action: () -> Void

    var body: some View {
        Button(role: self.role, action: self.action) {
            Image(systemName: self.systemName)
                .font(.system(size: 12, weight: .semibold))
                .frame(width: 24, height: 24)
                .background(
                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                        .fill(Color(NSColor.windowBackgroundColor)))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(self.accessibilityTitle)
    }

    private var accessibilityTitle: String {
        switch self.systemName {
        case "arrow.clockwise": "Refresh account"
        case "arrow.left.arrow.right.circle": "Switch active account"
        case "person.crop.circle.badge.checkmark": "Reauthenticate account"
        case "folder": "Open account folder"
        case "trash": "Remove account"
        default: self.systemName
        }
    }
}

private struct HeaderActionPill: View {
    let title: String
    let systemName: String
    let action: () -> Void

    var body: some View {
        Button(action: self.action) {
            HStack(spacing: 5) {
                Image(systemName: self.systemName)
                    .font(.system(size: 9, weight: .semibold))
                Text(self.title)
                    .font(.system(size: 10, weight: .semibold, design: .rounded))
            }
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(
                Capsule(style: .continuous)
                    .fill(Color(NSColor.windowBackgroundColor)))
        }
        .buttonStyle(.plain)
    }
}
