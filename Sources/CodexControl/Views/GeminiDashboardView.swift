import SwiftUI

struct GeminiDashboardView: View {
    @ObservedObject var model: GeminiAppQuotaModel
    let search: String

    @Environment(\.openURL) private var openURL

    private func matches(_ email: String?) -> Bool {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        return query.isEmpty || "Gemini App".localizedCaseInsensitiveContains(query)
            || (email?.localizedCaseInsensitiveContains(query) == true)
    }

    var body: some View {
        let current = model.snapshot
        let showReader = matches(current?.accountEmail)
        let saved = model.accountSnapshots.filter { item in
            guard let email = item.accountEmail else { return false }
            return email.caseInsensitiveCompare(current?.accountEmail ?? "") != .orderedSame && matches(email)
        }

        VStack(alignment: .leading, spacing: 8) {
            if showReader {
                DashboardAccountCard(isExpanded: false) {
                    header(for: current, canRefresh: true)
                    if let current {
                        windows(for: current)
                        lastRead(current, isLive: model.isCurrent)
                    } else if model.error == nil {
                        Text("连接后，额度窗口会最小化并在后台更新。")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let error = model.error {
                        InlineStatePill(text: error, systemName: "exclamationmark.circle",
                                        tint: .orange, lineLimit: 5)
                            .help(error)
                        if model.errorCode == "accessibilityDenied" {
                            Button("打开辅助功能设置") {
                                if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
                                    openURL(url)
                                }
                            }
                            .controlSize(.small)
                        }
                    }
                }
            }
            ForEach(saved, id: \.accountEmail) { snapshot in
                DashboardAccountCard(isExpanded: false) {
                    header(for: snapshot, canRefresh: false)
                    windows(for: snapshot)
                    lastRead(snapshot, isLive: false)
                }
            }
            if !showReader && saved.isEmpty {
                Text("没有匹配的 Gemini App 账号")
                    .font(.callout).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(10)
            }
        }
    }

    private func header(for snapshot: GeminiAppQuotaSnapshot?, canRefresh: Bool) -> some View {
        let name = snapshot?.accountEmail ?? (snapshot == nil ? "连接 Gemini App" : "Gemini App")
        let status = snapshot == nil ? nil : (canRefresh && model.isCurrent ? "已连接" : "已保存的额度")
        return HStack(spacing: 8) {
            DashboardAccountTitle(name: name, subtitle: status)
                .frame(maxWidth: .infinity, alignment: .leading)
            if canRefresh {
                if model.isRefreshing {
                    ProgressView().controlSize(.small)
                        .accessibilityLabel("正在读取 Gemini App 额度")
                } else {
                    HeaderActionPill(title: model.isCurrent ? "刷新" : (snapshot == nil ? "连接" : "重新连接"),
                                     systemName: model.isCurrent ? "arrow.clockwise" : "link") {
                        Task {
                            if model.isCurrent {
                                await model.refreshOpenPanel()
                            } else {
                                await model.connectForBackgroundUpdates()
                            }
                        }
                    }
                    .help("读取 Gemini App 当前账号的聊天额度。切换账号后，可再次读取。")
                }
            }
        }
    }

    private func windows(for snapshot: GeminiAppQuotaSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            ForEach(snapshot.buckets.sorted { $0.id < $1.id }) { bucket in
                DashboardQuotaTile(title: bucket.id == "fiveHour" ? "5 小时额度" : "每周额度",
                                   value: "剩余 \(bucket.remainingPercent)%",
                                   remainingPercent: Double(bucket.remainingPercent),
                                   reset: bucket.resetText, showsRawResetText: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func lastRead(_ snapshot: GeminiAppQuotaSnapshot, isLive: Bool) -> some View {
        let readDate = snapshot.updatedAt.formatted(date: .abbreviated, time: .shortened)
        let readTime = (isLive ? "读取于 " : "上次读取 ") + readDate
        return VStack(alignment: .leading, spacing: 3) {
            if let updated = snapshot.sourceUpdatedAt {
                Label("Gemini 更新于 " + updated.formatted(date: .abbreviated, time: .shortened),
                      systemImage: "clock")
            }
            Text(readTime)
        }
        .font(.caption2.monospacedDigit())
        .foregroundStyle(.secondary)
    }
}
