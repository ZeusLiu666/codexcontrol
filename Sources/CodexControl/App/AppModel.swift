import AppKit
import Foundation

enum MenuBarQuotaState {
    case available
    case unavailable
    case unresolved
    case empty
}

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var accounts: [StoredAccount] = []
    @Published private(set) var runtimeStates: [UUID: AccountRuntimeState] = [:]
    @Published private(set) var tokenUsageStates: [UUID: AccountTokenUsageSnapshot] = [:]
    @Published private(set) var remoteTokenStatuses: [RemoteTokenUsageStatus] = []
    @Published private(set) var activeIdentity: AuthBackedIdentity?
    @Published var selectedAccountID: UUID?
    @Published var searchText = ""
    @Published private(set) var isRefreshingAll = false
    @Published private(set) var isAddingAccount = false
    @Published private(set) var reauthenticatingAccountID: UUID?
    @Published var pendingRemovalAccount: StoredAccount?
    @Published var statusMessage: String?

    private let accountStore = AccountStore()
    private let snapshotStore = SnapshotStore()
    private let accountManager = CodexAccountManager()
    private let desktopController = CodexDesktopControl()
    private let tokenUsageTracker = TokenUsageTracker()
    private let remoteTokenUsageMirror = RemoteTokenUsageMirror()
    private let widgetSnapshotStore = WidgetSnapshotStore()
    private let refreshConcurrencyLimit = 2
    private var removedAccounts: [RemovedAccountIdentity] = []
    private let autoRefreshInterval: TimeInterval = 5 * 60
    private let tokenRefreshInterval: TimeInterval = 30
    private var autoRefreshTask: Task<Void, Never>?
    private var tokenRefreshTask: Task<Void, Never>?
    private var addAccountTask: Task<Void, Never>?

    init() {
        self.loadInitialAccounts()
        self.autoRefreshTask = Task { [weak self] in
            await self?.autoRefreshLoop()
        }
        self.tokenRefreshTask = Task { [weak self] in
            await self?.tokenRefreshLoop()
        }
        Task { [weak self] in
            await self?.refreshAll()
        }
    }

    deinit {
        self.autoRefreshTask?.cancel()
        self.tokenRefreshTask?.cancel()
        self.addAccountTask?.cancel()
    }

    var filteredAccounts: [StoredAccount] {
        let trimmedQuery = self.accountCount > 5
            ? self.searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            : ""

        let filtered = self.accounts.filter { account in
            guard !trimmedQuery.isEmpty else { return true }
            let haystacks = [
                account.displayName,
                account.emailHint ?? "",
                account.authSubject ?? "",
                account.providerAccountID ?? "",
                account.codexHomePath,
            ]
            return haystacks.contains { $0.lowercased().contains(trimmedQuery) }
        }

        return filtered.sorted { left, right in
            let leftSnapshot = self.runtimeStates[left.id]?.snapshot
            let rightSnapshot = self.runtimeStates[right.id]?.snapshot

            let leftPriority = leftSnapshot?.sortPriority ?? 2
            let rightPriority = rightSnapshot?.sortPriority ?? 2
            if leftPriority != rightPriority {
                return leftPriority < rightPriority
            }

            switch (leftSnapshot, rightSnapshot) {
            case let (.some(leftSnapshot), .some(rightSnapshot)):
                if leftSnapshot.hasUsableQuotaNow && rightSnapshot.hasUsableQuotaNow {
                    let leftRemaining = leftSnapshot.lowestRemainingPercent
                    let rightRemaining = rightSnapshot.lowestRemainingPercent
                    if leftRemaining != rightRemaining {
                        return leftRemaining > rightRemaining
                    }

                    let leftReset = leftSnapshot.nextResetAt ?? .distantFuture
                    let rightReset = rightSnapshot.nextResetAt ?? .distantFuture
                    if leftReset != rightReset {
                        return leftReset < rightReset
                    }
                } else {
                    let leftReset = leftSnapshot.nextResetAt ?? .distantFuture
                    let rightReset = rightSnapshot.nextResetAt ?? .distantFuture
                    if leftReset != rightReset {
                        return leftReset < rightReset
                    }
                }
            case (.some, .none):
                return true
            case (.none, .some):
                return false
            case (.none, .none):
                break
            }

            return left.displayName.localizedCaseInsensitiveCompare(right.displayName) == .orderedAscending
        }
    }

    var selectedAccount: StoredAccount? {
        guard let selectedAccountID else {
            return self.filteredAccounts.first ?? self.accounts.first
        }
        return self.accounts.first(where: { $0.id == selectedAccountID })
    }

    var accountCount: Int {
        self.accounts.count
    }

    var lowQuotaCount: Int {
        self.accounts.filter {
            (self.runtimeStates[$0.id]?.snapshot?.lowestRemainingPercent ?? 101) <= 20
        }.count
    }

    var usableQuotaCount: Int {
        self.accounts.filter {
            self.runtimeStates[$0.id]?.snapshot?.hasUsableQuotaNow == true
        }.count
    }

    var activeAccountID: UUID? {
        self.identityPresentation.activeAccountID(for: self.activeIdentity)
    }

    var duplicateLoginCount: Int {
        self.identityPresentation.duplicateCount
    }

    var todayTokenCount: Int64 {
        self.tokenUsageStates.values.reduce(0) { $0 + $1.today.totalTokens }
    }

    var sevenDayTokenCount: Int64 {
        self.tokenUsageStates.values.reduce(0) { $0 + $1.lastSevenDays.totalTokens }
    }

    var remoteTokenStatusText: String? {
        let visibleStatuses = self.remoteTokenStatuses.filter { !$0.isOptional || $0.isAvailable }
        guard !visibleStatuses.isEmpty else { return nil }
        return visibleStatuses.map { status in
            if status.isAvailable {
                return "\(status.host) ✓"
            }
            return "\(status.host) ⚠ \(status.detail)"
        }.joined(separator: " • ")
    }

    var menuBarQuotaState: MenuBarQuotaState {
        guard !self.accounts.isEmpty else {
            return .empty
        }

        let menuBarUsableCount = self.accounts.filter {
            self.runtimeStates[$0.id]?.snapshot?.hasUsableMenuBarQuotaNow == true
        }.count

        if menuBarUsableCount > 0 {
            return .available
        }

        let exhaustedCount = self.accounts.filter {
            if let snapshot = self.runtimeStates[$0.id]?.snapshot {
                return !snapshot.hasUsableMenuBarQuotaNow
            }
            return false
        }.count

        if exhaustedCount == self.accountCount {
            return .unavailable
        }

        return .unresolved
    }

    var menuBarSymbol: String {
        switch self.menuBarQuotaState {
        case .available:
            return "checkmark.circle.fill"
        case .unavailable:
            return "exclamationmark.triangle.fill"
        case .unresolved:
            return self.isRefreshingAll ? "arrow.triangle.2.circlepath" : "ellipsis.circle.fill"
        case .empty:
            return "circle.grid.2x1.fill"
        }
    }

    var menuBarSymbolColor: NSColor {
        switch self.menuBarQuotaState {
        case .available:
            return .systemGreen
        case .unavailable:
            return .systemRed
        case .unresolved, .empty:
            return .secondaryLabelColor
        }
    }

    func runtimeState(for accountID: UUID) -> AccountRuntimeState {
        self.runtimeStates[accountID] ?? AccountRuntimeState()
    }

    func tokenUsage(for accountID: UUID) -> AccountTokenUsageSnapshot? {
        self.tokenUsageStates[accountID]
    }

    func isDuplicateAccount(_ account: StoredAccount) -> Bool {
        self.identityPresentation.isDuplicate(account)
    }

    func displayName(for account: StoredAccount) -> String {
        self.identityPresentation.displayName(for: account)
    }

    func refreshAll() async {
        guard !self.accounts.isEmpty, !self.isRefreshingAll else {
            return
        }

        let snapshot = self.accounts.filter {
            !self.requiresReauthentication(accountID: $0.id) && !self.isDuplicateAccount($0)
        }
        guard !snapshot.isEmpty else {
            return
        }

        self.isRefreshingAll = true
        for account in snapshot {
            var state = self.runtimeStates[account.id] ?? AccountRuntimeState()
            state.isLoading = true
            self.runtimeStates[account.id] = state
        }

        defer {
            self.isRefreshingAll = false
        }

        let concurrencyLimit = min(self.refreshConcurrencyLimit, snapshot.count)
        await withTaskGroup(of: (UUID, Result<AccountUsageSnapshot, Error>).self) { group in
            var iterator = snapshot.makeIterator()
            var inFlightCount = 0

            func enqueueNextRefresh() {
                guard let account = iterator.next() else {
                    return
                }
                inFlightCount += 1
                group.addTask {
                    do {
                        return (account.id, .success(try await CodexAPI.fetchSnapshot(for: account)))
                    } catch {
                        return (account.id, .failure(error))
                    }
                }
            }

            for _ in 0 ..< concurrencyLimit {
                enqueueNextRefresh()
            }

            while inFlightCount > 0 {
                guard let (accountID, result) = await group.next() else {
                    break
                }
                inFlightCount -= 1
                self.applyRefreshResult(result, to: accountID)
                enqueueNextRefresh()
            }
        }
        self.persistWidgetSnapshotSilently()
    }

    func refresh(account: StoredAccount) async {
        guard !self.isDuplicateAccount(account) else {
            self.statusMessage = "This account slot contains a duplicate login. Reauthenticate it to restore the missing account."
            return
        }
        var state = self.runtimeStates[account.id] ?? AccountRuntimeState()
        guard !state.isLoading else {
            return
        }

        state.isLoading = true
        self.runtimeStates[account.id] = state

        do {
            let snapshot = try await CodexAPI.fetchSnapshot(for: account)
            self.applyRefreshResult(.success(snapshot), to: account.id)
        } catch {
            self.applyRefreshResult(.failure(error), to: account.id)
        }
        self.persistWidgetSnapshotSilently()
    }

    func startAddAccount() {
        guard !self.isAddingAccount, self.addAccountTask == nil else {
            return
        }

        self.addAccountTask = Task { [weak self] in
            await self?.addAccount()
        }
    }

    func cancelAddAccount() {
        guard self.isAddingAccount else {
            return
        }

        self.statusMessage = "Cancelling account setup."
        self.addAccountTask?.cancel()
    }

    private func addAccount() async {
        self.isAddingAccount = true
        self.statusMessage = "Complete or cancel the Codex sign-in flow in your browser."
        defer {
            self.isAddingAccount = false
            self.addAccountTask = nil
        }

        do {
            let account = try await self.accountManager.addManagedAccount()
            self.restoreRemovedAccount(account)
            self.accounts = self.accountStore.merge(existing: self.accounts, incoming: [account])
            try self.accountStore.saveAccounts(self.accounts, removedAccounts: self.removedAccounts)
            self.selectedAccountID = self.accounts.first(where: { $0.matches(account) })?.id ?? account.id
            self.statusMessage = "\(account.displayName) added."
            if let selectedAccount = self.selectedAccount {
                await self.refresh(account: selectedAccount)
            }
        } catch is CancellationError {
            self.statusMessage = "Account setup cancelled."
        } catch {
            self.statusMessage = error.localizedDescription
        }
    }

    func reauthenticate(_ account: StoredAccount) async {
        guard self.reauthenticatingAccountID == nil else {
            return
        }

        self.reauthenticatingAccountID = account.id
        self.statusMessage = "Waiting for \(account.displayName) to sign in again."
        defer {
            self.reauthenticatingAccountID = nil
        }

        do {
            let updated = try await self.accountManager.reauthenticate(account)
            self.restoreRemovedAccount(updated)
            self.mergeAccount(updated)
            try self.accountStore.saveAccounts(self.accounts, removedAccounts: self.removedAccounts)
            self.statusMessage = "\(updated.displayName) reauthenticated."
            if let refreshed = self.accounts.first(where: { $0.id == account.id }) {
                await self.refresh(account: refreshed)
            }
        } catch {
            self.statusMessage = error.localizedDescription
        }
    }

    func switchAccount(_ account: StoredAccount) async {
        guard !self.isDuplicateAccount(account) else {
            self.statusMessage = "This account slot contains a duplicate login. Reauthenticate it before switching."
            return
        }
        guard !self.isActiveAccount(account) else {
            self.statusMessage = "\(account.displayName) is already the active Codex account."
            return
        }

        do {
            await self.refreshTokenUsage()
            let result = try self.accountManager.switchActiveAccount(account, existing: self.accounts)
            if let materializedAccount = result.materializedAccount {
                self.mergeAccount(materializedAccount)
                try self.accountStore.saveAccounts(self.accounts, removedAccounts: self.removedAccounts)
            }

            self.loadInitialAccounts()
            self.refreshActiveIdentity()
            await self.refreshTokenUsage()
            self.selectedAccountID = self.accounts.first(where: { $0.matches(account) })?.id ?? self.selectedAccountID
            self.statusMessage = "Switched to \(account.displayName). Restarting Codex Desktop."

            if let refreshed = self.accounts.first(where: { $0.matches(account) }) {
                await self.refresh(account: refreshed)
            }

            do {
                try await self.desktopController.restartCodexDesktop()
                // The switch/restart message is a progress notification.  Once
                // Desktop is back, let the header return to its normal state
                // (including the current SSH/remote status) instead of leaving
                // the one-off message permanently in front of it.
                self.statusMessage = nil
                await self.refreshTokenUsage()
            } catch {
                self.statusMessage = "Switched to \(account.displayName), but \(error.localizedDescription)"
            }
        } catch {
            self.statusMessage = error.localizedDescription
        }
    }

    func updateNickname(for accountID: UUID, nickname: String) {
        guard let index = self.accounts.firstIndex(where: { $0.id == accountID }) else {
            return
        }

        self.accounts[index].nickname = nickname.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? nil
            : nickname.trimmingCharacters(in: .whitespacesAndNewlines)
        self.accounts[index].updatedAt = Date()
        self.persistAccountsSilently()
        self.persistWidgetSnapshotSilently()
    }

    func requestRemoval(of account: StoredAccount) {
        self.pendingRemovalAccount = account
    }

    func confirmPendingRemoval() {
        guard let account = self.pendingRemovalAccount else {
            return
        }
        self.pendingRemovalAccount = nil
        self.remove(account)
    }

    func cancelPendingRemoval() {
        self.pendingRemovalAccount = nil
    }

    func openFolder(for account: StoredAccount) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: account.codexHomePath, isDirectory: true)])
    }

    func isActiveAccount(_ account: StoredAccount) -> Bool {
        self.activeAccountID == account.id
    }

    func canSwitchAccount(_ account: StoredAccount) -> Bool {
        guard !self.isActiveAccount(account), !self.isDuplicateAccount(account) else {
            return false
        }

        let authURL = URL(fileURLWithPath: account.codexHomePath, isDirectory: true)
            .appendingPathComponent("auth.json", isDirectory: false)
        return FileManager.default.fileExists(atPath: authURL.path)
    }

    private func loadInitialAccounts() {
        do {
            let stored = try self.accountStore.loadAccountList()
            self.removedAccounts = stored.removedAccounts
            let loadedAccounts = stored.accounts.filter { !self.isRemoved($0) }
            let storedAccounts = loadedAccounts.filter { $0.source != .ambient }
            let discoveredManagedAccounts = try self.accountManager.discoverManagedAccounts(existing: loadedAccounts)
            var incomingAccounts = discoveredManagedAccounts
            if let ambientAccount = try self.accountManager.discoverAmbientAccount(existing: loadedAccounts) {
                incomingAccounts.insert(ambientAccount, at: 0)
            }
            incomingAccounts.removeAll { self.isRemoved($0) }

            self.accounts = self.accountStore.merge(existing: storedAccounts, incoming: incomingAccounts)
            if self.accounts != stored.accounts {
                try self.accountStore.saveAccounts(self.accounts, removedAccounts: self.removedAccounts)
            }
            self.ensureSelection()
            self.refreshActiveIdentity()
        } catch {
            self.statusMessage = error.localizedDescription
        }
    }

    private func mergeAccount(_ account: StoredAccount) {
        self.accounts = self.accountStore.merge(existing: self.accounts, incoming: [account])
        self.ensureSelection()
    }

    private func remove(_ account: StoredAccount) {
        let removedIdentity = RemovedAccountIdentity(account: account)
        self.removedAccounts.removeAll { $0.matches(account) }
        self.removedAccounts.append(removedIdentity)

        self.accounts.removeAll { $0.id == account.id || removedIdentity.matches($0) }
        self.runtimeStates.removeValue(forKey: account.id)
        self.tokenUsageStates.removeValue(forKey: account.id)

        do {
            try self.accountManager.removeManagedFilesIfOwned(account)
            try self.accountStore.saveAccounts(self.accounts, removedAccounts: self.removedAccounts)
            self.ensureSelection()
            self.statusMessage = "\(account.displayName) removed."
            Task { [weak self] in
                guard let self else { return }
                do {
                    self.tokenUsageStates = try await self.tokenUsageTracker.removeAccount(account.id)
                    self.persistWidgetSnapshotSilently()
                } catch {
                    self.statusMessage = error.localizedDescription
                }
            }
        } catch {
            self.statusMessage = error.localizedDescription
        }
    }

    private func applyRefreshResult(_ result: Result<AccountUsageSnapshot, Error>, to accountID: UUID) {
        var state = self.runtimeStates[accountID] ?? AccountRuntimeState()
        state.isLoading = false

        switch result {
        case let .success(snapshot):
            state.snapshot = snapshot
            state.errorMessage = nil
            self.runtimeStates[accountID] = state
            self.updateAccountMetadata(accountID: accountID, snapshot: snapshot)
            self.persistSnapshotsSilently()
        case let .failure(error):
            if !self.shouldPreserveSnapshot(after: error) {
                state.snapshot = nil
            }
            state.errorMessage = error.localizedDescription
            self.runtimeStates[accountID] = state
            self.persistSnapshotsSilently()
        }
    }

    private func shouldPreserveSnapshot(after error: Error) -> Bool {
        if let apiError = error as? CodexAPIError {
            return apiError.preservesExistingSnapshot
        }
        return false
    }

    private func updateAccountMetadata(accountID: UUID, snapshot: AccountUsageSnapshot) {
        guard let index = self.accounts.firstIndex(where: { $0.id == accountID }) else {
            return
        }

        let normalizedEmail = StoredAccount.normalizeEmail(snapshot.email)
        var didChange = false

        if self.accounts[index].emailHint != normalizedEmail, let normalizedEmail {
            self.accounts[index].emailHint = normalizedEmail
            didChange = true
        }
        if self.accounts[index].providerAccountID != snapshot.providerAccountID,
           let providerAccountID = snapshot.providerAccountID
        {
            self.accounts[index].providerAccountID = providerAccountID
            didChange = true
        }
        if didChange {
            self.accounts[index].updatedAt = Date()
            self.persistAccountsSilently()
        }
    }

    private func persistAccountsSilently() {
        do {
            try self.accountStore.saveAccounts(self.accounts, removedAccounts: self.removedAccounts)
        } catch {
            self.statusMessage = error.localizedDescription
        }
    }

    private func isRemoved(_ account: StoredAccount) -> Bool {
        self.removedAccounts.contains { $0.matches(account) }
    }

    private func restoreRemovedAccount(_ account: StoredAccount) {
        self.removedAccounts.removeAll { $0.matches(account) }
    }

    private func requiresReauthentication(accountID: UUID) -> Bool {
        guard let message = self.runtimeStates[accountID]?.errorMessage?.lowercased() else {
            return false
        }

        return message.contains("refresh token")
            && message.contains("sign in again")
    }

    private func persistSnapshotsSilently() {
        let snapshots = self.runtimeStates.compactMapValues(\.snapshot)
        do {
            try self.snapshotStore.save(snapshots)
        } catch {
            self.statusMessage = error.localizedDescription
        }
    }

    private func persistWidgetSnapshotSilently() {
        do {
            try self.widgetSnapshotStore.save(
                accounts: self.accounts,
                runtimeStates: self.runtimeStates,
                tokenUsage: self.tokenUsageStates,
                activeAccountID: self.activeAccountID)
        } catch {
            if self.statusMessage == nil {
                self.statusMessage = "Widget data could not be updated: \(error.localizedDescription)"
            }
        }
    }

    private func refreshTokenUsage(initial: Bool = false) async {
        do {
            if initial {
                self.tokenUsageStates = try await self.tokenUsageTracker.start(activeAccountID: self.activeAccountID)
            } else {
                self.refreshActiveIdentity()
            }

            self.remoteTokenStatuses = await self.remoteTokenUsageMirror.sync(
                accounts: self.accounts,
                fallbackAccountID: self.activeAccountID)
            self.tokenUsageStates = try await self.tokenUsageTracker.scan(activeAccountID: self.activeAccountID)
            self.persistWidgetSnapshotSilently()
        } catch {
            if self.statusMessage == nil {
                self.statusMessage = "Token statistics could not be updated: \(error.localizedDescription)"
            }
        }
    }

    private func ensureSelection() {
        if let selectedAccountID, self.accounts.contains(where: { $0.id == selectedAccountID }) {
            return
        }
        self.selectedAccountID = self.filteredAccounts.first?.id ?? self.accounts.first?.id
    }

    private func refreshActiveIdentity() {
        self.activeIdentity = self.accountManager.loadActiveIdentity()
    }

    private var identityPresentation: AccountIdentityPresentation {
        AccountIdentityPresentation(accounts: self.accounts)
    }

    private func autoRefreshLoop() async {
        while !Task.isCancelled {
            let nanoseconds = UInt64(self.autoRefreshInterval * 1_000_000_000)
            try? await Task.sleep(nanoseconds: nanoseconds)
            await self.refreshAll()
        }
    }

    private func tokenRefreshLoop() async {
        await self.refreshTokenUsage(initial: true)
        while !Task.isCancelled {
            let nanoseconds = UInt64(self.tokenRefreshInterval * 1_000_000_000)
            try? await Task.sleep(nanoseconds: nanoseconds)
            guard !Task.isCancelled else { return }
            await self.refreshTokenUsage()
        }
    }
}
