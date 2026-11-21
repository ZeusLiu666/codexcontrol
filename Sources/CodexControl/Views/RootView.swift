import SwiftUI

struct RootView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var gemini: GeminiAppQuotaModel

    private var showsSearch: Bool {
        model.accountCount + gemini.accountSnapshots.count > 5
    }

    private var screen: CGRect {
        let pointer = NSEvent.mouseLocation
        let display = NSScreen.screens.first { $0.frame.contains(pointer) } ?? NSScreen.main
        return display?.visibleFrame ?? CGRect(x: 0, y: 0, width: 1024, height: 720)
    }

    var body: some View {
        let width = min(430, screen.width - 16)
        ZStack {
            ScrollViewReader { reader in
                VStack(spacing: 10) {
                    DashboardHeaderView(model: model, gemini: gemini, onConnectGemini: {
                        model.searchText = ""
                        reader.scrollTo("geminiTop", anchor: .top)
                        Task { await gemini.connectForBackgroundUpdates() }
                    })
                    if showsSearch {
                        searchBar
                    }
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            heading("Codex", symbol: "terminal", count: model.accountCount)
                            codexContent
                            heading("Gemini App", symbol: "sparkles").padding(.top, 4).id("geminiTop")
                            GeminiDashboardView(model: gemini, search: model.searchText)
                        }
                    }
                    .transformAnchorPreference(key: TokenDayDetailPreferenceKey.self, value: .bounds) { selection, viewport in
                        selection?.viewport = viewport
                    }
                }
            }
            .disabled(model.pendingRemovalAccount != nil)
            .accessibilityHidden(model.pendingRemovalAccount != nil)

            if let account = model.pendingRemovalAccount {
                removalOverlay(for: account)
            }
        }
        .padding(12)
        .frame(width: width, height: min(580, screen.height - 18))
        .background(Color(nsColor: .windowBackgroundColor))
        .overlayPreferenceValue(TokenDayDetailPreferenceKey.self) { selection in
            if let selection, model.pendingRemovalAccount == nil {
                TokenDayDetailOverlay(selection: selection)
            }
        }
        .onChange(of: showsSearch) { _, visible in
            if !visible { model.searchText = "" }
        }
    }

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)

            TextField("搜索账号或邮箱", text: self.$model.searchText)
                .textFieldStyle(.plain)

            if !self.model.searchText.isEmpty {
                Button {
                    self.model.searchText = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("清除搜索")
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(NSColor.controlBackgroundColor)))
    }

    private func heading(_ title: String, symbol: String, count: Int? = nil) -> some View {
        HStack(spacing: 6) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(title).font(.system(size: 13, weight: .semibold))
            if let count {
                Text("\(count) 个账号")
                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }
            Rectangle()
                .fill(.separator)
                .frame(height: 0.5)
                .padding(.leading, 2)
                .accessibilityHidden(true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
        .padding(.horizontal, 2)
    }

    private var codexContent: some View {
        LazyVStack(alignment: .leading, spacing: 8) {
            if model.filteredAccounts.isEmpty {
                Text(model.accounts.isEmpty ? "尚未添加 Codex 账号" : "没有匹配的 Codex 账号")
                    .font(.callout).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(10)
            }
            ForEach(self.model.filteredAccounts) { account in
                let isSelected = self.model.selectedAccountID == account.id
                let nextSelection = isSelected ? nil : account.id

                AccountRowView(
                    account: account,
                    displayName: self.model.displayName(for: account),
                    state: self.model.runtimeState(for: account.id),
                    tokenUsage: self.model.tokenUsage(for: account.id),
                    isDuplicateLogin: self.model.isDuplicateAccount(account),
                    isActive: self.model.isActiveAccount(account),
                    canSwitch: self.model.canSwitchAccount(account),
                    isSelected: isSelected,
                    isReauthenticating: self.model.reauthenticatingAccountID == account.id,
                    onSelect: {
                        self.model.selectedAccountID = nextSelection
                    },
                    onSaveNickname: { self.model.updateNickname(for: account.id, nickname: $0) },
                    onRefresh: { Task { await self.model.refresh(account: account) } },
                    onSwitch: { Task { await self.model.switchAccount(account) } },
                    onReauthenticate: { Task { await self.model.reauthenticate(account) } },
                    onOpenFolder: { self.model.openFolder(for: account) },
                    onRemove: { self.model.requestRemoval(of: account) })
            }
        }
        .padding(.vertical, 1)
    }

    private func removalOverlay(for account: StoredAccount) -> some View {
        ZStack {
            Color.black.opacity(0.16)
                .ignoresSafeArea()
                .onTapGesture {
                    self.model.cancelPendingRemoval()
                }

            VStack(alignment: .leading, spacing: 12) {
                Text("移除账号")
                    .font(.system(size: 14, weight: .semibold))

                Text("将从 CodexControl 中移除“\(model.displayName(for: account))”。")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)

                HStack(spacing: 8) {
                    Spacer()

                    Button("取消", role: .cancel) {
                        model.cancelPendingRemoval()
                    }
                    .keyboardShortcut(.cancelAction)
                    .buttonStyle(.bordered)

                    Button("移除", role: .destructive) {
                        model.confirmPendingRemoval()
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                }
            }
            .padding(14)
            .frame(width: 300, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color(NSColor.windowBackgroundColor)))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(Color.primary.opacity(0.08), lineWidth: 1))
            .shadow(color: Color.black.opacity(0.14), radius: 18, y: 6)
        }
    }
}

