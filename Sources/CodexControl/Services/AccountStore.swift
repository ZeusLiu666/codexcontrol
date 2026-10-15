import Foundation

struct AccountStore {
    private static let currentVersion = 2

    func loadAccounts() throws -> [StoredAccount] {
        try self.loadAccountList().accounts
    }

    func loadRemovedAccounts() throws -> [RemovedAccountIdentity] {
        try self.loadAccountList().removedAccounts
    }

    func loadAccountList() throws -> StoredAccountList {
        guard FileManager.default.fileExists(atPath: FileLocations.accountsFile.path) else {
            return StoredAccountList(version: Self.currentVersion, accounts: [])
        }

        let data = try Data(contentsOf: FileLocations.accountsFile)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let stored = try decoder.decode(StoredAccountList.self, from: data)
        return StoredAccountList(
            version: stored.version,
            accounts: self.sorted(stored.accounts),
            removedAccounts: stored.removedAccounts)
    }

    func saveAccounts(_ accounts: [StoredAccount], removedAccounts: [RemovedAccountIdentity]? = nil) throws {
        try FileLocations.ensureDirectories()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        let preservedRemovedAccounts = try removedAccounts ?? self.loadRemovedAccountsIfPresent()
        let data = try encoder.encode(StoredAccountList(
            version: Self.currentVersion,
            accounts: self.sorted(accounts),
            removedAccounts: preservedRemovedAccounts))
        try data.write(to: FileLocations.accountsFile, options: .atomic)
    }

    func merge(existing: [StoredAccount], incoming: [StoredAccount]) -> [StoredAccount] {
        var result = existing

        for candidate in incoming {
            if let index = result.firstIndex(where: { $0.matches(candidate) }) {
                var merged = result[index]
                merged.merge(from: candidate)
                result[index] = merged
            } else {
                result.append(candidate)
            }
        }

        return self.sorted(result)
    }

    private func sorted(_ accounts: [StoredAccount]) -> [StoredAccount] {
        accounts.sorted {
            let left = $0.displayName.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
            let right = $1.displayName.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
            return left < right
        }
    }

    private func loadRemovedAccountsIfPresent() throws -> [RemovedAccountIdentity] {
        guard FileManager.default.fileExists(atPath: FileLocations.accountsFile.path) else {
            return []
        }
        return try self.loadRemovedAccounts()
    }
}
