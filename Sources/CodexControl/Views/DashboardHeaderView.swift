import SwiftUI

struct DashboardHeaderView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var gemini: GeminiAppQuotaModel
    let onConnectGemini: () -> Void
    @State private var isMessageExpanded = false
    @State private var isRemoteExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("UsageControl")
                        .font(.system(size: 19, weight: .semibold, design: .rounded))
                        .accessibilityAddTraits(.isHeader)
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text("Codex 今日用量")
                        Text(TokenCountFormatter.compact(model.todayTokenCount))
                            .fontWeight(.semibold)
                            .foregroundStyle(.primary)
                            .monospacedDigit()
                        Text("tokens")
                    }
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .accessibilityElement(children: .combine)

                    if let attentionSummary {
                        Text(attentionSummary)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.orange)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                HStack(spacing: 7) {
                    Menu {
                        Button(model.isAddingAccount ? "取消 Codex 登录" : "添加 Codex 账号") {
                            model.searchText = ""
                            if model.isAddingAccount { model.cancelAddAccount() }
                            else { model.startAddAccount() }
                        }
                        Button("连接 Gemini App 并后台更新", action: onConnectGemini)
                            .disabled(gemini.isRefreshing)
                        Button("在 Gemini 中添加或切换账号") {
                            Task { await gemini.manageAccounts() }
                        }
                        .disabled(gemini.isRefreshing)
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 13, weight: .semibold))
                            .frame(width: 28, height: 28)
                            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                    }
                    .menuStyle(.button)
                    .buttonStyle(.plain)
                    .menuIndicator(.hidden)
                    .fixedSize()
                    .accessibilityLabel("添加账号")
                    .help("添加账号")

                    Button {
                        Task {
                            async let codex: Void = model.refreshAll()
                            async let chat: Void = gemini.refreshOpenPanel()
                            _ = await (codex, chat)
                        }
                    } label: {
                        HStack(spacing: 5) {
                            if isRefreshing {
                                ProgressView().controlSize(.mini)
                            } else {
                                Image(systemName: "arrow.clockwise")
                            }
                            Text("刷新")
                        }
                        .font(.system(size: 12, weight: .medium))
                        .padding(.horizontal, 9)
                        .frame(height: 28)
                        .background(RoundedRectangle(cornerRadius: 8).fill(Color(nsColor: .controlBackgroundColor)))
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut("r", modifiers: .command)
                    .disabled(isRefreshing)
                    .accessibilityLabel("刷新 Codex 账号和已打开的 Gemini 额度面板")
                    .help("刷新 Codex 账号和已打开的 Gemini 额度面板")
                }
            }

            if let remote = self.model.remoteTokenStatusText, !remote.isEmpty {
                self.remoteStatus(remote)
            }

            if let message = self.model.statusMessage, !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                self.statusBanner(message)
            }
        }
        .padding(.horizontal, 2)
        .onChange(of: self.model.statusMessage) { _, _ in
            self.isMessageExpanded = false
        }
    }

    private var isRefreshing: Bool { model.isRefreshingAll || gemini.isRefreshing }

    private var attentionSummary: String? {
        var parts: [String] = []
        if self.model.duplicateLoginCount > 0 {
            parts.append("\(self.model.duplicateLoginCount) 个重复登录")
        }
        if self.model.lowQuotaCount > 0 {
            parts.append("\(self.model.lowQuotaCount) 个账号额度偏低")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private func remoteStatus(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Button {
                self.isRemoteExpanded.toggle()
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "network")
                    Text(self.isRemoteExpanded ? "远程用量状态" : "远程用量 · \(text)")
                        .lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Image(systemName: self.isRemoteExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                }
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("远程用量 · \(text)")
            .accessibilityLabel("远程用量 · \(text)")
            .accessibilityHint(self.isRemoteExpanded ? "收起远程状态" : "展开远程状态")

            if self.isRemoteExpanded {
                CappedStatusText(text: text, fontSize: 10, maximumHeight: 45)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func statusBanner(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Button {
                    self.isMessageExpanded.toggle()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "info.circle")
                        Text(self.isMessageExpanded ? "状态信息" : message)
                            .lineLimit(1)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: self.isMessageExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 8, weight: .semibold))
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help(message)
                .accessibilityLabel(message)
                .accessibilityHint(self.isMessageExpanded ? "收起状态信息" : "展开状态信息")

                Button {
                    self.model.statusMessage = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 9, weight: .semibold))
                        .frame(width: 20, height: 20)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭状态信息")
                .help("关闭状态信息")
            }

            if self.isMessageExpanded {
                CappedStatusText(text: message, fontSize: 11, maximumHeight: 65)
            }
        }
        .font(.system(size: 11))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(RoundedRectangle(cornerRadius: 9).fill(Color.accentColor.opacity(0.07)))
    }
}

private struct CappedStatusText: View {
    let text: String
    let fontSize: CGFloat
    let maximumHeight: CGFloat
    @State private var contentHeight: CGFloat = 0

    var body: some View {
        ScrollView {
            Text(self.text)
                .font(.system(size: self.fontSize))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background {
                    GeometryReader { geometry in
                        Color.clear.preference(key: StatusTextHeightKey.self, value: geometry.size.height)
                    }
                }
        }
        .frame(height: min(self.contentHeight > 0 ? self.contentHeight : self.fontSize * 1.5, self.maximumHeight))
        .onPreferenceChange(StatusTextHeightKey.self) { height in
            if abs(self.contentHeight - height) > 0.5 {
                self.contentHeight = height
            }
        }
    }
}

private struct StatusTextHeightKey: PreferenceKey {
    static var defaultValue: CGFloat { 0 }

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}
