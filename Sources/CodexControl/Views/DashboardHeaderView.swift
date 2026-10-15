import SwiftUI

struct DashboardHeaderView: View {
    @ObservedObject var model: AppModel
    @State private var isMessageExpanded = false
    @State private var isRemoteExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Codex")
                        .font(.system(size: 14, weight: .semibold))
                    Text("\(self.model.accountCount) accounts · \(TokenCountFormatter.compact(self.model.todayTokenCount)) tokens today")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)

                    if let attentionSummary = self.attentionSummary {
                        Text(attentionSummary)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.orange)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                HStack(spacing: 7) {
                    Button {
                        if self.model.isAddingAccount {
                            self.model.cancelAddAccount()
                        } else {
                            self.model.startAddAccount()
                        }
                    } label: {
                        Image(systemName: self.model.isAddingAccount ? "xmark" : "plus")
                            .font(.system(size: 13, weight: .semibold))
                            .frame(width: 28, height: 28)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(self.model.isAddingAccount ? Color.accentColor.opacity(0.14) : Color(NSColor.controlBackgroundColor)))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(self.model.isAddingAccount ? "Cancel account setup" : "Add account")
                    .help(self.model.isAddingAccount ? "Cancel account setup" : "Add account")

                    Button {
                        Task { await self.model.refreshAll() }
                    } label: {
                        Group {
                            if self.model.isRefreshingAll {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Image(systemName: "arrow.clockwise")
                                    .font(.system(size: 13, weight: .semibold))
                            }
                        }
                        .frame(width: 28, height: 28)
                        .background(RoundedRectangle(cornerRadius: 8).fill(Color(NSColor.controlBackgroundColor)))
                    }
                    .buttonStyle(.plain)
                    .disabled(self.model.isRefreshingAll)
                    .accessibilityLabel(self.model.isRefreshingAll ? "Refreshing all accounts" : "Refresh all accounts")
                    .help(self.model.isRefreshingAll ? "Refreshing all accounts…" : "Refresh all accounts")
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

    private var attentionSummary: String? {
        var parts: [String] = []
        if self.model.duplicateLoginCount > 0 {
            parts.append("\(self.model.duplicateLoginCount) duplicate login")
        }
        if self.model.lowQuotaCount > 0 {
            parts.append("\(self.model.lowQuotaCount) low quota")
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
                    Text(self.isRemoteExpanded ? "Remote status" : "Remote: \(text)")
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
            .help("Remote: \(text)")
            .accessibilityLabel("Remote: \(text)")
            .accessibilityHint(self.isRemoteExpanded ? "Collapse remote status" : "Expand full remote status")

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
                        Text(self.isMessageExpanded ? "Status message" : message)
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
                .accessibilityHint(self.isMessageExpanded ? "Collapse status message" : "Expand full status message")

                Button {
                    self.model.statusMessage = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 9, weight: .semibold))
                        .frame(width: 20, height: 20)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Dismiss status message")
                .help("Dismiss status message")
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
