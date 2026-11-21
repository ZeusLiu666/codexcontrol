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
        DashboardAccountCard(isExpanded: self.isSelected) {
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
                        RowActionButton(systemName: "arrow.clockwise", title: "刷新额度", action: self.onRefresh)
                            .help(self.state.isLoading ? "正在刷新额度…" : "刷新额度")
                            .disabled(self.state.isLoading)
                    }
                    if self.canSwitch {
                        RowActionButton(systemName: "arrow.left.arrow.right.circle", title: "切换到此账号", action: self.onSwitch)
                            .help("切换到此账号")
                    }
                    RowActionButton(systemName: "person.crop.circle.badge.checkmark", title: "重新登录", action: self.onReauthenticate)
                        .disabled(self.isReauthenticating)
                    RowActionButton(systemName: "folder", title: "打开账号文件夹", action: self.onOpenFolder)
                    RowActionButton(systemName: "trash", title: "移除账号", role: .destructive, action: self.onRemove)

                    Spacer()

                    if let updatedAt = self.state.snapshot?.updatedAt {
                        Text("更新于 \(updatedAt.formatted(date: .omitted, time: .shortened))")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }

                HStack(spacing: 8) {
                    TextField("账号备注", text: self.$draftNickname)
                        .accessibilityLabel("账号备注")
                        .textFieldStyle(.plain)
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(Color(NSColor.windowBackgroundColor)))
                        .onSubmit(self.saveNickname)

                    Button("保存", action: self.saveNickname)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(!self.hasNicknameChanges)
                }
            }
        }
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
                HStack(spacing: 6) {
                    Image(systemName: self.isSelected ? "chevron.down" : "chevron.right")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .frame(width: 10)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 5) {
                        DashboardAccountTitle(
                            name: self.displayName,
                            subtitle: self.secondaryLine != self.displayName && !self.isDuplicateLogin ? self.secondaryLine : nil)

                        HStack(spacing: 7) {
                            if self.isActive {
                                Label("当前使用", systemImage: "checkmark.circle.fill")
                                    .foregroundStyle(Color.accentColor)
                            }
                            if let snapshot = self.state.snapshot {
                                Text(snapshot.planDisplayName)
                                    .foregroundStyle(.secondary)
                            }
                            if self.isDuplicateLogin {
                                Label("重复登录", systemImage: "exclamationmark.circle")
                                    .foregroundStyle(.orange)
                            }
                        }
                        .font(.system(size: 10, weight: .medium))
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityValue(self.isSelected ? "已展开" : "已收起")
            .accessibilityHint(self.isSelected ? "收起账号详情" : "展开账号详情")

            if self.state.isLoading || self.isReauthenticating {
                ProgressView()
                    .controlSize(.small)
                    .frame(width: 24, height: 24)
            } else if self.canSwitch && !self.isSelected {
                HeaderActionPill(
                    title: "切换",
                    systemName: "arrow.left.arrow.right",
                    action: self.onSwitch)
                    .help("切换到此账号")
            }
        }
    }

    @ViewBuilder
    private var summaryContent: some View {
        VStack(spacing: 7) {
            if self.isDuplicateLogin {
                InlineStatePill(
                    text: "此条目与其他账号使用相同凭据。请重新登录此条目。",
                    systemName: "person.crop.circle.badge.exclamationmark",
                    tint: .orange,
                    lineLimit: self.isSelected ? 3 : 2)
            } else if let snapshot = self.state.snapshot {
                if snapshot.hasQuotaWindows {
                    DashboardQuotaRow {
                        if let primaryWindow = snapshot.primaryWindow {
                            quotaTile(for: primaryWindow)
                        }
                        if let secondaryWindow = snapshot.secondaryWindow {
                            quotaTile(for: secondaryWindow)
                        }
                    }
                } else if snapshot.isQuotaBlocked {
                    InlineStatePill(
                        text: "额度已用尽",
                        systemName: "exclamationmark.circle.fill",
                        tint: .red)
                } else {
                    InlineStatePill(
                        text: "暂无额度数据",
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
                    text: "等待读取额度",
                    systemName: "clock",
                    tint: .secondary)
            }

            if self.state.snapshot != nil, let errorMessage = self.state.errorMessage {
                Label("刷新失败，显示上次额度", systemImage: "exclamationmark.triangle.fill")
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
            return "登录凭据重复，请重新登录"
        }
        return self.account.emailHint ?? self.account.source.displayName
    }

    private func quotaTile(for window: UsageWindowSnapshot) -> some View {
        DashboardQuotaTile(
            title: DashboardQuotaTile.windowTitle(window.shortLabel),
            value: "剩余 \(Int(window.remainingPercent.rounded()))%",
            remainingPercent: window.remainingPercent,
            reset: window.compactResetAtDisplay)
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
                Label("Token 用量", systemImage: "chart.bar.fill")
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
                    TokenInlineMetric(title: "今日", value: usage.today.totalTokens, fontSize: 11)
                    Spacer(minLength: 4)
                    TokenInlineMetric(title: "近 7 天", value: usage.lastSevenDays.totalTokens, fontSize: 11)
                    Spacer(minLength: 4)
                    TokenInlineMetric(title: "累计", value: usage.allTime.totalTokens, fontSize: 11)
                }
                .padding(.top, 9)

                HStack(spacing: 12) {
                    TokenCompositionMetric(title: "今日输入", value: usage.today.inputTokens)
                    TokenCompositionMetric(title: "缓存", value: usage.today.cachedInputTokens)
                    TokenCompositionMetric(title: "输出", value: usage.today.outputTokens)
                    TokenCompositionMetric(title: "推理", value: usage.today.reasoningOutputTokens)
                }
                .padding(.top, 7)
            } else {
                HStack(spacing: 7) {
                    Image(systemName: "clock.badge.checkmark")
                    Text("下次使用此账号时开始统计。")
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
            return "近 7 天"
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
