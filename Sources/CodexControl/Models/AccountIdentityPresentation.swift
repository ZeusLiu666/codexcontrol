import Foundation

struct AccountIdentityPresentation {
    let accounts: [StoredAccount]

    var duplicateAccountIDs: Set<UUID> {
        var accountsByIdentity: [String: [StoredAccount]] = [:]
        for account in self.accounts {
            guard let identityKey = self.identityKey(for: account) else { continue }
            accountsByIdentity[identityKey, default: []].append(account)
        }

        return accountsByIdentity.values.reduce(into: Set<UUID>()) { result, matchingAccounts in
            let ordered = self.preferredOrder(matchingAccounts)
            guard ordered.count > 1 else { return }
            result.formUnion(ordered.dropFirst().map(\.id))
        }
    }

    var duplicateCount: Int {
        self.duplicateAccountIDs.count
    }

    func isDuplicate(_ account: StoredAccount) -> Bool {
        self.duplicateAccountIDs.contains(account.id)
    }

    func activeAccountID(for identity: AuthBackedIdentity?) -> UUID? {
        guard let identity else { return nil }

        let exactMatches = self.accounts.filter {
            $0.matchesIdentity(
                email: identity.email,
                authSubject: identity.authSubject,
                providerAccountID: identity.providerAccountID)
        }
        return self.preferredOrder(exactMatches).first?.id
    }

    func displayName(for account: StoredAccount) -> String {
        let baseName = account.displayName
        let matchingNames = self.accounts.filter {
            $0.displayName.localizedCaseInsensitiveCompare(baseName) == .orderedSame
        }
        guard matchingNames.count > 1 else { return baseName }

        if let providerID = account.providerAccountID?.trimmingCharacters(in: .whitespacesAndNewlines),
           !providerID.isEmpty
        {
            let sameProvider = matchingNames.filter {
                $0.normalizedProviderAccountID == account.normalizedProviderAccountID
            }
            if sameProvider.count == 1 {
                return "\(baseName) · \(providerID.suffix(4).uppercased())"
            }
        }

        if let subject = account.authSubject?.trimmingCharacters(in: .whitespacesAndNewlines),
           !subject.isEmpty
        {
            return "\(baseName) · \(subject.suffix(4).uppercased())"
        }

        let ordered = self.preferredOrder(matchingNames)
        let position = (ordered.firstIndex(where: { $0.id == account.id }) ?? 0) + 1
        return "\(baseName) · \(position)"
    }

    private func preferredOrder(_ accounts: [StoredAccount]) -> [StoredAccount] {
        accounts.sorted { left, right in
            let leftIsAmbient = left.standardizedHomePath == FileLocations.ambientCodexHome.standardizedFileURL.path
            let rightIsAmbient = right.standardizedHomePath == FileLocations.ambientCodexHome.standardizedFileURL.path
            if leftIsAmbient != rightIsAmbient {
                return leftIsAmbient
            }
            return left.id.uuidString < right.id.uuidString
        }
    }

    private func identityKey(for account: StoredAccount) -> String? {
        let provider = account.normalizedProviderAccountID
        let subject = account.normalizedAuthSubject
        if provider != nil || subject != nil {
            return "provider:\(provider ?? "-")|subject:\(subject ?? "-")"
        }
        return account.normalizedEmailHint.map { "email:\($0)" }
    }
}
