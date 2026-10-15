import XCTest
@testable import CodexControl

final class AccountIdentityTests: XCTestCase {
    func testPresentationSupportsEmptyAndLargeAccountCollections() {
        XCTAssertEqual(AccountIdentityPresentation(accounts: []).duplicateCount, 0)

        let accounts = (0 ..< 25).map { index in
            StoredAccount(
                id: UUID(),
                nickname: "Account \(index + 1)",
                emailHint: "user\(index)@example.com",
                authSubject: "subject-\(index)",
                providerAccountID: "provider-\(index)",
                codexHomePath: "/tmp/unlimited-account-\(index)",
                source: .managedByApp,
                createdAt: Date(timeIntervalSince1970: 1_766_534_400),
                updatedAt: Date(timeIntervalSince1970: 1_766_534_400))
        }
        let presentation = AccountIdentityPresentation(accounts: accounts)

        XCTAssertEqual(accounts.map { presentation.displayName(for: $0) }.count, 25)
        XCTAssertEqual(presentation.duplicateCount, 0)
    }

    func testMatchesKeepsDifferentProviderAccountsSeparate() {
        let createdAt = Date(timeIntervalSince1970: 1_766_534_400)
        let first = StoredAccount(
            id: UUID(),
            nickname: nil,
            emailHint: "user@example.com",
            authSubject: "auth0|same-user",
            providerAccountID: "account-1",
            codexHomePath: "/tmp/a",
            source: .managedByApp,
            createdAt: createdAt,
            updatedAt: createdAt)
        let second = StoredAccount(
            id: UUID(),
            nickname: nil,
            emailHint: "user@example.com",
            authSubject: "auth0|same-user",
            providerAccountID: "account-2",
            codexHomePath: "/tmp/b",
            source: .managedByApp,
            createdAt: createdAt,
            updatedAt: createdAt)

        XCTAssertFalse(first.matches(second))
    }

    func testMatchesKeepsDifferentUsersInTheSameProviderWorkspaceSeparate() {
        let accounts = self.sameProviderAccounts(authSubjects: ["auth0|user-one", "auth0|user-two"])

        XCTAssertFalse(accounts[0].matches(accounts[1]))
    }

    func testRemovedIdentityMatchesProviderNotSharedEmail() {
        let createdAt = Date(timeIntervalSince1970: 1_766_534_400)
        let removedAccount = StoredAccount(
            id: UUID(),
            nickname: nil,
            emailHint: "user@example.com",
            authSubject: "auth0|same-user",
            providerAccountID: "account-1",
            codexHomePath: "/tmp/a",
            source: .managedByApp,
            createdAt: createdAt,
            updatedAt: createdAt)
        let otherAccount = StoredAccount(
            id: UUID(),
            nickname: nil,
            emailHint: "user@example.com",
            authSubject: "auth0|same-user",
            providerAccountID: "account-2",
            codexHomePath: "/tmp/b",
            source: .managedByApp,
            createdAt: createdAt,
            updatedAt: createdAt)

        let removed = RemovedAccountIdentity(account: removedAccount, removedAt: createdAt)

        XCTAssertTrue(removed.matches(removedAccount))
        XCTAssertFalse(removed.matches(otherAccount))
    }

    func testActiveAccountUsesProviderIDBeforeSharedEmail() {
        let accounts = self.sameEmailAccounts(providerIDs: ["account-1", "account-2"])
        let presentation = AccountIdentityPresentation(accounts: accounts)
        let identity = AuthBackedIdentity(
            email: "user@example.com",
            authSubject: "auth0|same-user",
            plan: "team",
            providerAccountID: "account-2")

        XCTAssertEqual(presentation.activeAccountID(for: identity), accounts[1].id)
        XCTAssertNotEqual(presentation.activeAccountID(for: identity), accounts[0].id)
    }

    func testActiveAccountUsesSubjectWithinSharedProviderWorkspace() {
        let accounts = self.sameProviderAccounts(authSubjects: ["auth0|user-one", "auth0|user-two"])
        let presentation = AccountIdentityPresentation(accounts: accounts)
        let identity = AuthBackedIdentity(
            email: "user-two@example.com",
            authSubject: "auth0|user-two",
            plan: "team",
            providerAccountID: "shared-workspace")

        XCTAssertEqual(presentation.activeAccountID(for: identity), accounts[1].id)
        XCTAssertNotEqual(presentation.activeAccountID(for: identity), accounts[0].id)
        XCTAssertEqual(presentation.duplicateCount, 0)
    }

    func testDuplicateProviderMarksOnlyOneRepairSlot() {
        let accounts = self.sameEmailAccounts(providerIDs: ["same-account", "same-account"])
        let presentation = AccountIdentityPresentation(accounts: accounts)
        let duplicateIDs = presentation.duplicateAccountIDs

        XCTAssertEqual(duplicateIDs.count, 1)
        XCTAssertEqual(accounts.filter { presentation.isDuplicate($0) }.count, 1)
        XCTAssertFalse(accounts.map { presentation.displayName(for: $0) }.contains { $0.contains("Primary") })
    }

    func testSameEmailDifferentProvidersGetsDistinctDisplayNames() {
        let accounts = self.sameEmailAccounts(providerIDs: ["workspace-1234", "workspace-5678"])
        let presentation = AccountIdentityPresentation(accounts: accounts)

        XCTAssertEqual(Set(accounts.map { presentation.displayName(for: $0) }).count, 2)
        XCTAssertTrue(presentation.displayName(for: accounts[0]).contains("1234"))
        XCTAssertTrue(presentation.displayName(for: accounts[1]).contains("5678"))
    }

    private func sameEmailAccounts(providerIDs: [String]) -> [StoredAccount] {
        let createdAt = Date(timeIntervalSince1970: 1_766_534_400)
        return providerIDs.enumerated().map { index, providerID in
            StoredAccount(
                id: UUID(uuidString: String(format: "00000000-0000-0000-0000-%012d", index + 1))!,
                nickname: nil,
                emailHint: "user@example.com",
                authSubject: "auth0|same-user",
                providerAccountID: providerID,
                codexHomePath: "/tmp/account-\(index)",
                source: .managedByApp,
                createdAt: createdAt,
                updatedAt: createdAt)
        }
    }

    private func sameProviderAccounts(authSubjects: [String]) -> [StoredAccount] {
        let createdAt = Date(timeIntervalSince1970: 1_766_534_400)
        return authSubjects.enumerated().map { index, authSubject in
            StoredAccount(
                id: UUID(uuidString: String(format: "10000000-0000-0000-0000-%012d", index + 1))!,
                nickname: nil,
                emailHint: "user-\(index + 1)@example.com",
                authSubject: authSubject,
                providerAccountID: "shared-workspace",
                codexHomePath: "/tmp/shared-workspace-account-\(index)",
                source: .managedByApp,
                createdAt: createdAt,
                updatedAt: createdAt)
        }
    }
}
