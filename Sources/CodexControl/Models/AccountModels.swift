import Foundation

enum StoredAccountSource: String, Codable, CaseIterable, Sendable {
    case ambient
    case managedByApp

    private static let legacyImportedValue = ["imported", "Codex", "Bar"].joined()

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let rawValue = try container.decode(String.self)

        switch rawValue {
        case Self.ambient.rawValue:
            self = .ambient
        case Self.managedByApp.rawValue, Self.legacyImportedValue:
            self = .managedByApp
        default:
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unknown stored account source: \(rawValue)")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(self.rawValue)
    }

    var displayName: String {
        switch self {
        case .ambient:
            "System"
        case .managedByApp:
            "Managed"
        }
    }

    var ownsFiles: Bool {
        self == .managedByApp
    }
}

struct StoredAccount: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    var nickname: String?
    var emailHint: String?
    var authSubject: String?
    var providerAccountID: String?
    var codexHomePath: String
    var source: StoredAccountSource
    let createdAt: Date
    var updatedAt: Date
    var lastAuthenticatedAt: Date?

    var displayName: String {
        if let nickname, !nickname.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return nickname.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if let emailHint, !emailHint.isEmpty {
            return emailHint
        }
        return URL(fileURLWithPath: self.codexHomePath).lastPathComponent
    }

    var normalizedEmailHint: String? {
        Self.normalizeEmail(self.emailHint)
    }

    var normalizedAuthSubject: String? {
        Self.normalizeIdentifier(self.authSubject)
    }

    var normalizedProviderAccountID: String? {
        Self.normalizeIdentifier(self.providerAccountID)
    }

    var standardizedHomePath: String {
        URL(fileURLWithPath: self.codexHomePath, isDirectory: true).standardizedFileURL.path
    }

    func matches(_ other: StoredAccount) -> Bool {
        if self.standardizedHomePath == other.standardizedHomePath {
            return true
        }

        return self.matchesIdentity(
            email: other.emailHint,
            authSubject: other.authSubject,
            providerAccountID: other.providerAccountID)
    }

    func matchesIdentity(email: String?, authSubject: String?, providerAccountID: String?) -> Bool {
        let otherProviderAccountID = Self.normalizeIdentifier(providerAccountID)
        let otherAuthSubject = Self.normalizeIdentifier(authSubject)
        let otherEmail = Self.normalizeEmail(email)
        var comparedStrongIdentity = false

        if let normalizedProviderAccountID, let otherProviderAccountID {
            guard normalizedProviderAccountID == otherProviderAccountID else { return false }
            comparedStrongIdentity = true
        }

        if let normalizedAuthSubject, let otherAuthSubject {
            guard normalizedAuthSubject == otherAuthSubject else { return false }
            comparedStrongIdentity = true
        }

        if comparedStrongIdentity {
            return true
        }

        if self.normalizedProviderAccountID != nil || otherProviderAccountID != nil
            || self.normalizedAuthSubject != nil || otherAuthSubject != nil
        {
            return false
        }

        if let normalizedEmailHint, normalizedEmailHint == otherEmail {
            return true
        }

        return false
    }

    mutating func merge(from other: StoredAccount) {
        if self.nickname == nil || self.nickname?.isEmpty == true {
            self.nickname = other.nickname
        }

        let shouldPreferOtherIdentity = other.sourcePriority > self.sourcePriority
            || (other.sourcePriority == self.sourcePriority && other.recencyDate >= self.recencyDate)

        if shouldPreferOtherIdentity,
           let emailHint = other.emailHint?.trimmingCharacters(in: .whitespacesAndNewlines),
           !emailHint.isEmpty
        {
            self.emailHint = emailHint
        } else if self.emailHint == nil || self.emailHint?.isEmpty == true {
            self.emailHint = other.emailHint
        }

        if shouldPreferOtherIdentity,
           let authSubject = other.authSubject?.trimmingCharacters(in: .whitespacesAndNewlines),
           !authSubject.isEmpty
        {
            self.authSubject = authSubject
        } else if self.authSubject == nil || self.authSubject?.isEmpty == true {
            self.authSubject = other.authSubject
        }

        if shouldPreferOtherIdentity,
           let providerAccountID = other.providerAccountID?.trimmingCharacters(in: .whitespacesAndNewlines),
           !providerAccountID.isEmpty
        {
            self.providerAccountID = providerAccountID
        } else if self.providerAccountID == nil || self.providerAccountID?.isEmpty == true {
            self.providerAccountID = other.providerAccountID
        }

        if shouldPreferOtherIdentity {
            self.source = other.source
            self.codexHomePath = other.codexHomePath
        }
        self.updatedAt = max(self.updatedAt, other.updatedAt)
        self.lastAuthenticatedAt = max(self.lastAuthenticatedAt ?? .distantPast, other.lastAuthenticatedAt ?? .distantPast)
    }

    private var sourcePriority: Int {
        switch self.source {
        case .managedByApp:
            2
        case .ambient:
            1
        }
    }

    private var recencyDate: Date {
        self.lastAuthenticatedAt ?? self.updatedAt
    }

    static func normalizeEmail(_ value: String?) -> String? {
        Self.normalizeIdentifier(value)
    }

    static func normalizeIdentifier(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return value.lowercased()
    }
}

struct StoredAccountList: Codable, Sendable {
    let version: Int
    let accounts: [StoredAccount]
    let removedAccounts: [RemovedAccountIdentity]

    init(version: Int, accounts: [StoredAccount], removedAccounts: [RemovedAccountIdentity] = []) {
        self.version = version
        self.accounts = accounts
        self.removedAccounts = removedAccounts
    }

    private enum CodingKeys: String, CodingKey {
        case version
        case accounts
        case removedAccounts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.version = try container.decode(Int.self, forKey: .version)
        self.accounts = try container.decode([StoredAccount].self, forKey: .accounts)
        self.removedAccounts = try container.decodeIfPresent([RemovedAccountIdentity].self, forKey: .removedAccounts) ?? []
    }
}

struct RemovedAccountIdentity: Codable, Hashable, Sendable {
    let id: UUID
    let emailHint: String?
    let authSubject: String?
    let providerAccountID: String?
    let codexHomePath: String
    let source: StoredAccountSource
    let removedAt: Date

    init(account: StoredAccount, removedAt: Date = Date()) {
        self.id = UUID()
        self.emailHint = account.emailHint
        self.authSubject = account.authSubject
        self.providerAccountID = account.providerAccountID
        self.codexHomePath = account.codexHomePath
        self.source = account.source
        self.removedAt = removedAt
    }

    var normalizedProviderAccountID: String? {
        StoredAccount.normalizeIdentifier(self.providerAccountID)
    }

    var normalizedAuthSubject: String? {
        StoredAccount.normalizeIdentifier(self.authSubject)
    }

    var normalizedEmailHint: String? {
        StoredAccount.normalizeEmail(self.emailHint)
    }

    var standardizedHomePath: String {
        URL(fileURLWithPath: self.codexHomePath, isDirectory: true).standardizedFileURL.path
    }

    func matches(_ account: StoredAccount) -> Bool {
        if self.standardizedHomePath == account.standardizedHomePath {
            return true
        }

        let accountProviderAccountID = account.normalizedProviderAccountID
        let accountAuthSubject = account.normalizedAuthSubject
        var comparedStrongIdentity = false

        if let normalizedProviderAccountID, let accountProviderAccountID {
            guard normalizedProviderAccountID == accountProviderAccountID else { return false }
            comparedStrongIdentity = true
        }

        if let normalizedAuthSubject, let accountAuthSubject {
            guard normalizedAuthSubject == accountAuthSubject else { return false }
            comparedStrongIdentity = true
        }

        if comparedStrongIdentity {
            return true
        }

        if self.normalizedProviderAccountID != nil || accountProviderAccountID != nil
            || self.normalizedAuthSubject != nil || accountAuthSubject != nil
        {
            return false
        }

        if let normalizedEmailHint, normalizedEmailHint == account.normalizedEmailHint {
            return true
        }

        return false
    }
}

struct AccountRuntimeState: Sendable {
    var snapshot: AccountUsageSnapshot?
    var errorMessage: String?
    var isLoading: Bool = false
}

struct AccountUsageSnapshot: Codable, Sendable {
    let email: String?
    let providerAccountID: String?
    let plan: String?
    let allowed: Bool?
    let limitReached: Bool?
    let primaryWindow: UsageWindowSnapshot?
    let secondaryWindow: UsageWindowSnapshot?
    let credits: CreditsBalanceSnapshot?
    let updatedAt: Date

    var lowestRemainingPercent: Double {
        if self.isQuotaBlocked {
            return 0
        }

        let values = [self.secondaryWindow?.remainingPercent, self.primaryWindow?.remainingPercent]
            .compactMap { $0 }
        return values.min() ?? 101
    }

    var hasQuotaWindows: Bool {
        self.primaryWindow != nil || self.secondaryWindow != nil
    }

    var isQuotaBlocked: Bool {
        self.limitReached == true || self.allowed == false
    }

    var hasUsableQuotaNow: Bool {
        guard !self.isQuotaBlocked else {
            return false
        }

        let values = [self.secondaryWindow?.remainingPercent, self.primaryWindow?.remainingPercent]
            .compactMap { $0 }

        guard !values.isEmpty else {
            return false
        }

        return values.contains { $0 > 0.001 }
    }

    var hasUsableMenuBarQuotaNow: Bool {
        guard !self.isQuotaBlocked else {
            return false
        }

        if let primaryWindow {
            return primaryWindow.remainingPercent > 0.001
        }

        if let secondaryWindow {
            return secondaryWindow.remainingPercent > 0.001
        }

        return false
    }

    var sortPriority: Int {
        if self.hasUsableQuotaNow {
            return 0
        }
        if self.nextResetAt != nil {
            return 1
        }
        return 2
    }

    var nextResetAt: Date? {
        [self.primaryWindow?.resetAt, self.secondaryWindow?.resetAt]
            .compactMap { $0 }
            .min()
    }

    var planDisplayName: String {
        guard let plan, !plan.isEmpty else { return "Unknown" }
        return plan
            .replacingOccurrences(of: "_", with: " ")
            .split(separator: " ")
            .map { $0.prefix(1).uppercased() + $0.dropFirst().lowercased() }
            .joined(separator: " ")
    }
}

struct UsageWindowSnapshot: Codable, Sendable {
    let usedPercent: Double
    let resetAt: Date?
    let limitWindowSeconds: Int

    var remainingPercent: Double {
        max(0, 100 - self.usedPercent)
    }

    var displayName: String {
        switch self.limitWindowSeconds {
        case 18_000:
            return "5 Hours"
        case 604_800:
            return "7 Days"
        default:
            let hours = Double(self.limitWindowSeconds) / 3600
            if hours < 24 {
                return "\(Int(hours.rounded())) Hours"
            }
            let days = hours / 24
            return "\(Int(days.rounded())) Days"
        }
    }

    var shortLabel: String {
        switch self.limitWindowSeconds {
        case 18_000:
            return "5h"
        case 604_800:
            return "7d"
        default:
            let hours = Double(self.limitWindowSeconds) / 3600
            if hours < 24 {
                return "\(Int(hours.rounded()))h"
            }
            let days = hours / 24
            return "\(Int(days.rounded()))d"
        }
    }

    var resetAtDisplay: String? {
        guard let resetAt else { return nil }
        return resetAt.formatted(Self.resetAtFormat)
    }

    var compactResetAtDisplay: String? {
        guard let resetAt else { return nil }
        return resetAt.formatted(Self.compactResetAtFormat)
    }

    private static let resetAtFormat = Date.FormatStyle(date: .abbreviated, time: .shortened)
    private static let compactResetAtFormat = Date.FormatStyle()
        .month(.abbreviated)
        .day()
        .hour(.defaultDigits(amPM: .omitted))
        .minute(.twoDigits)
}

struct CreditsBalanceSnapshot: Codable, Sendable {
    let hasCredits: Bool
    let unlimited: Bool
    let balance: Double?

    var displayValue: String {
        if self.unlimited {
            return "Unlimited"
        }
        if let balance {
            return balance.formatted(.number.precision(.fractionLength(0...2)))
        }
        if self.hasCredits {
            return "Available"
        }
        return "None"
    }
}
