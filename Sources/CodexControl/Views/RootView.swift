import SwiftUI

struct RootView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ZStack {
            VStack(spacing: 10) {
                DashboardHeaderView(model: self.model)
                if self.model.accountCount > 5 {
                    self.searchBar
                }
                self.accountList
            }
            .allowsHitTesting(self.model.pendingRemovalAccount == nil)

            if let pendingRemovalAccount = self.model.pendingRemovalAccount {
                self.removalOverlay(for: pendingRemovalAccount)
            }
        }
        .padding(12)
        .frame(width: 430, height: 580)
        .background(Color(NSColor.windowBackgroundColor))
        .overlayPreferenceValue(TokenDayDetailPreferenceKey.self) { selection in
            if let selection, self.model.pendingRemovalAccount == nil {
                TokenDayDetailOverlay(selection: selection)
            }
        }
        .onChange(of: self.model.accountCount) { _, accountCount in
            if accountCount <= 5 {
                self.model.searchText = ""
            }
        }
    }

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)

            TextField("Search accounts", text: self.$model.searchText)
                .textFieldStyle(.plain)

            if !self.model.searchText.isEmpty {
                Button {
                    self.model.searchText = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(NSColor.controlBackgroundColor)))
    }

    @ViewBuilder
    private var accountList: some View {
        if self.model.filteredAccounts.isEmpty {
            if self.model.accountCount > 0 {
                ContentUnavailableView {
                    Label("No matching accounts", systemImage: "magnifyingglass")
                } description: {
                    Text("Try another name or email.")
                } actions: {
                    Button("Clear search") {
                        self.model.searchText = ""
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView(
                    "No Accounts",
                    systemImage: "tray",
                    description: Text("Add a Codex account to start tracking quota."))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
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
                .padding(.vertical, 4)
            }
            .transformAnchorPreference(key: TokenDayDetailPreferenceKey.self, value: .bounds) { selection, viewport in
                selection?.viewport = viewport
            }
        }
    }

    private func removalOverlay(for account: StoredAccount) -> some View {
        ZStack {
            Color.black.opacity(0.16)
                .ignoresSafeArea()
                .onTapGesture {
                    self.model.cancelPendingRemoval()
                }

            VStack(alignment: .leading, spacing: 12) {
                Text("Remove Account")
                    .font(.system(size: 14, weight: .semibold))

                Text("\(account.displayName) will be removed from CodexControl.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)

                HStack(spacing: 8) {
                    Spacer()

                    Button("Cancel") {
                        self.model.cancelPendingRemoval()
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        Capsule(style: .continuous)
                            .fill(Color(NSColor.controlBackgroundColor)))

                    Button("Remove") {
                        self.model.confirmPendingRemoval()
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        Capsule(style: .continuous)
                            .fill(Color.red))
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

