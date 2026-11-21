import Darwin
import Foundation

enum CodexAccountManagerError: LocalizedError {
    case binaryMissing
    case loginFailed(String)
    case loginTimedOut
    case loginCancelled
    case launchFailed(String)
    case missingIdentity
    case missingAuth
    case unsafeDeletePath

    var errorDescription: String? {
        switch self {
        case .binaryMissing:
            return "找不到 Codex 命令。"
        case let .loginFailed(output):
            return "Codex 登录未完成。\n\(output)"
        case .loginTimedOut:
            return "Codex 登录超时，请重新尝试。"
        case .loginCancelled:
            return "已取消添加账号。"
        case let .launchFailed(message):
            return "无法启动 Codex 登录：\(message)"
        case .missingIdentity:
            return "已完成登录，读取账号身份时出错。"
        case .missingAuth:
            return "所选账号缺少 auth.json。"
        case .unsafeDeletePath:
            return "该目录不由 CodexControl 管理。"
        }
    }
}

struct CodexLoginResult {
    enum Outcome {
        case success
        case timedOut
        case cancelled
        case failed(status: Int32)
        case missingBinary
        case launchFailed(String)
    }

    let outcome: Outcome
    let output: String
}

struct CodexSwitchResult {
    let materializedAccount: StoredAccount?
    let backupPath: String?
}

/// Drain output while the CLI is running. A browser or another descendant can
/// inherit a pipe writer, so finishing must not depend on receiving EOF.
private final class LoginOutput: @unchecked Sendable {
    let pipe = Pipe()
    private let queue = DispatchQueue(label: "CodexControl.login-output")
    private var collected = Data()
    private var reader: DispatchSourceRead?

    deinit { reader?.cancel() }

    func start() throws {
        let fd = pipe.fileHandleForReading.fileDescriptor
        let flags = fcntl(fd, F_GETFL)
        guard flags >= 0, fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0 else {
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
        let source = DispatchSource.makeReadSource(fileDescriptor: fd, queue: queue)
        source.setEventHandler { [weak self] in self?.drain() }
        reader = source
        source.resume()
    }

    func finish() -> String {
        queue.sync {
            reader?.cancel()
            drain()
            let output = String(decoding: collected, as: UTF8.self)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return output.isEmpty ? "登录进程未返回诊断信息。" : String(output.prefix(4000))
        }
    }

    private func drain() {
        let fd = pipe.fileHandleForReading.fileDescriptor
        var buffer = [UInt8](repeating: 0, count: 8192)
        // Yield between batches even when a writer produces output continuously.
        for _ in 0..<32 {
            let count = Darwin.read(fd, &buffer, buffer.count)
            if count == 0 {
                reader?.cancel()
                return
            }
            if count < 0 {
                if errno == EINTR { continue }
                return
            }
            // Keep enough UTF-8 bytes for the diagnostic prefix while draining
            // all additional output to prevent the writer blocking on a full pipe.
            collected.append(contentsOf: buffer.prefix(min(count, 16_000 - collected.count)))
        }
    }
}

enum CodexLoginRunner {
    static func run(homePath: String, timeout: TimeInterval = 180,
                    binary: String? = CodexBinaryLocator.resolve()) async -> CodexLoginResult {
        let process = Process()

        return await withTaskCancellationHandler {
            guard !Task.isCancelled else { return CodexLoginResult(outcome: .cancelled, output: "") }
            guard let binary else { return CodexLoginResult(outcome: .missingBinary, output: "") }

            var env = ProcessInfo.processInfo.environment
            env["CODEX_HOME"] = homePath
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = [binary, "login"]
            process.environment = env

            let capture = LoginOutput()
            process.standardOutput = capture.pipe
            process.standardError = capture.pipe
            do {
                try capture.start()
                try process.run()
            } catch {
                return CodexLoginResult(outcome: .launchFailed(error.localizedDescription), output: "")
            }

            if Task.isCancelled { stop(process) }
            let deadline = Task {
                do { try await Task.sleep(for: .seconds(max(0, timeout))) } catch { return false }
                guard process.isRunning else { return false }
                stop(process)
                return true
            }
            await withCheckedContinuation { (finished: CheckedContinuation<Void, Never>) in
                DispatchQueue.global(qos: .utility).async {
                    process.waitUntilExit()
                    finished.resume()
                }
            }
            deadline.cancel()
            let timedOut = await deadline.value
            let output = capture.finish()
            if Task.isCancelled { return CodexLoginResult(outcome: .cancelled, output: output) }
            if timedOut { return CodexLoginResult(outcome: .timedOut, output: output) }
            let outcome: CodexLoginResult.Outcome = process.terminationStatus == 0
                ? .success : .failed(status: process.terminationStatus)
            return CodexLoginResult(outcome: outcome, output: output)
        } onCancel: {
            stop(process)
        }
    }

    private static func stop(_ process: Process) {
        guard process.isRunning else { return }
        let pid = process.processIdentifier
        guard pid > 0 else { return }
        _ = Darwin.kill(pid, SIGTERM)
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 0.75) {
            if process.isRunning { _ = Darwin.kill(pid, SIGKILL) }
        }
    }
}

struct CodexAccountManager {
    func addManagedAccount() async throws -> StoredAccount {
        try FileLocations.ensureDirectories()
        let homeURL = FileLocations.managedHomesDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: homeURL, withIntermediateDirectories: true)

        do {
            let account = try await self.authenticateAccount(homeURL: homeURL, source: .managedByApp)
            return account
        } catch {
            try? FileManager.default.removeItem(at: homeURL)
            throw error
        }
    }

    func reauthenticate(_ account: StoredAccount) async throws -> StoredAccount {
        let homeURL = URL(fileURLWithPath: account.codexHomePath, isDirectory: true)
        return try await self.authenticateAccount(homeURL: homeURL, source: account.source, existing: account)
    }

    func loadActiveIdentity() -> AuthBackedIdentity? {
        let authURL = FileLocations.ambientCodexHome.appendingPathComponent("auth.json", isDirectory: false)
        guard FileManager.default.fileExists(atPath: authURL.path) else {
            return nil
        }

        return try? CodexAPI.loadIdentity(codexHomePath: FileLocations.ambientCodexHome.path)
    }

    // The tombstone's ID binds the atomic accounts.json write to its staged
    // directories. On startup, an interrupted transaction can be finished or undone.
    func removeAccount(_ account: StoredAccount, tombstone: RemovedAccountIdentity,
                       persist: () throws -> Void) throws -> Error? {
        guard account.source.ownsFiles else {
            try persist()
            return nil
        }

        return try withManagedHomesLock { root in
            let fm = FileManager.default
            let targets = try managedHomePathsMatching(account).compactMap { path -> URL? in
                let target = URL(fileURLWithPath: path).standardizedFileURL
                guard target.deletingLastPathComponent().path == root.path,
                      !target.lastPathComponent.hasPrefix(".") else {
                    throw CodexAccountManagerError.unsafeDeletePath
                }
                var info = stat()
                guard lstat(target.path, &info) == 0 else {
                    if errno == ENOENT { return nil }
                    throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
                }
                guard (info.st_mode & S_IFMT) == S_IFDIR else {
                    throw CodexAccountManagerError.unsafeDeletePath
                }
                return target
            }
            let stage = root.appendingPathComponent(".removing-" + tombstone.id.uuidString)
            try fm.createDirectory(at: stage, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            do {
                for target in targets {
                    try fm.moveItem(at: target, to: stage.appendingPathComponent(target.lastPathComponent))
                }
                try persist()
            } catch {
                try restoreStagedHomes(from: stage, to: root)
                throw error
            }
            do {
                try fm.removeItem(at: stage)
                return nil
            } catch {
                // Removal is already committed. Discovery retries this cleanup.
                return error
            }
        }
    }

    private func withManagedHomesLock<T>(_ action: (URL) throws -> T) throws -> T {
        try FileLocations.ensureDirectories()
        let root = FileLocations.managedHomesDirectory.standardizedFileURL
        let lock = open(root.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
        guard lock >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        defer { close(lock) }
        guard flock(lock, LOCK_EX) == 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        return try action(root)
    }

    private func restoreStagedHomes(from stage: URL, to root: URL) throws {
        let fm = FileManager.default
        for home in try fm.contentsOfDirectory(at: stage, includingPropertiesForKeys: nil) {
            try fm.moveItem(at: home, to: root.appendingPathComponent(home.lastPathComponent))
        }
        try fm.removeItem(at: stage)
    }

    func discoverManagedAccounts(existing: [StoredAccount]) throws -> [StoredAccount] {
        try withManagedHomesLock { root in
            let fm = FileManager.default
            let entries = try fm.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
            let prefix = ".removing-"
            let stages = entries.filter { $0.lastPathComponent.hasPrefix(prefix) }
            if !stages.isEmpty {
                let committed = Set(try AccountStore().loadRemovedAccounts().map(\.id))
                for stage in stages {
                    let suffix = stage.lastPathComponent.dropFirst(prefix.count)
                    let values = try stage.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
                    guard let id = UUID(uuidString: String(suffix)), values.isDirectory == true,
                          values.isSymbolicLink == false else { continue }
                    if committed.contains(id) {
                        // A leftover staged directory must not block the other accounts.
                        try? fm.removeItem(at: stage)
                    } else {
                        try restoreStagedHomes(from: stage, to: root)
                    }
                }
            }
            let homes = try fm.contentsOfDirectory(at: root, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
            return homes.compactMap { discoveredManagedAccount(at: $0, existing: existing) }
        }
    }

    func discoverAmbientAccount(existing: [StoredAccount]) throws -> StoredAccount? {
        let homeURL = FileLocations.ambientCodexHome
        let authURL = homeURL.appendingPathComponent("auth.json", isDirectory: false)
        guard FileManager.default.fileExists(atPath: authURL.path) else {
            return nil
        }

        guard let identity = try? CodexAPI.loadIdentity(codexHomePath: homeURL.path),
              identity.email != nil || identity.providerAccountID != nil
        else {
            return nil
        }

        let discoveredAt = self.directoryTimestamp(for: homeURL)
        let candidate = StoredAccount(
            id: UUID(),
            nickname: nil,
            emailHint: identity.email,
            authSubject: identity.authSubject,
            providerAccountID: identity.providerAccountID,
            codexHomePath: homeURL.path,
            source: .ambient,
            createdAt: discoveredAt,
            updatedAt: discoveredAt,
            lastAuthenticatedAt: discoveredAt)

        let matchedExisting = existing.first(where: { $0.matches(candidate) })

        return StoredAccount(
            id: matchedExisting?.id ?? UUID(),
            nickname: matchedExisting?.nickname,
            emailHint: identity.email ?? matchedExisting?.emailHint,
            authSubject: identity.authSubject ?? matchedExisting?.authSubject,
            providerAccountID: identity.providerAccountID ?? matchedExisting?.providerAccountID,
            codexHomePath: homeURL.path,
            source: .ambient,
            createdAt: matchedExisting?.createdAt ?? discoveredAt,
            updatedAt: max(matchedExisting?.updatedAt ?? .distantPast, discoveredAt),
            lastAuthenticatedAt: max(matchedExisting?.lastAuthenticatedAt ?? .distantPast, discoveredAt))
    }

    func switchActiveAccount(_ target: StoredAccount, existing: [StoredAccount]) throws -> CodexSwitchResult {
        try FileLocations.ensureDirectories()

        let targetHomeURL = URL(fileURLWithPath: target.codexHomePath, isDirectory: true)
        let targetAuthURL = targetHomeURL.appendingPathComponent("auth.json", isDirectory: false)
        guard FileManager.default.fileExists(atPath: targetAuthURL.path) else {
            throw CodexAccountManagerError.missingAuth
        }

        let ambientHomeURL = FileLocations.ambientCodexHome.standardizedFileURL
        let standardizedTargetHomeURL = targetHomeURL.standardizedFileURL
        if standardizedTargetHomeURL == ambientHomeURL {
            return CodexSwitchResult(materializedAccount: nil, backupPath: nil)
        }

        let ambientAccount = try self.discoverAmbientAccount(existing: existing)
        let materializedAccount: StoredAccount?
        if let ambientAccount, ambientAccount.source == .ambient, !ambientAccount.matches(target) {
            materializedAccount = try self.materializeAsManaged(ambientAccount)
        } else {
            materializedAccount = nil
        }

        try FileManager.default.createDirectory(at: FileLocations.ambientCodexHome, withIntermediateDirectories: true)
        let ambientAuthURL = FileLocations.ambientCodexHome.appendingPathComponent("auth.json", isDirectory: false)
        let backupPath = try self.backupAmbientAuth()
        let stagedAuthURL = FileLocations.ambientCodexHome.appendingPathComponent(".auth.staged.json", isDirectory: false)
        if FileManager.default.fileExists(atPath: stagedAuthURL.path) {
            try FileManager.default.removeItem(at: stagedAuthURL)
        }
        try FileManager.default.copyItem(at: targetAuthURL, to: stagedAuthURL)

        if FileManager.default.fileExists(atPath: ambientAuthURL.path) {
            _ = try FileManager.default.replaceItemAt(ambientAuthURL, withItemAt: stagedAuthURL)
        } else {
            try FileManager.default.moveItem(at: stagedAuthURL, to: ambientAuthURL)
        }

        return CodexSwitchResult(
            materializedAccount: materializedAccount,
            backupPath: backupPath)
    }

    private func authenticateAccount(
        homeURL: URL,
        source: StoredAccountSource,
        existing: StoredAccount? = nil) async throws -> StoredAccount
    {
        let result = await CodexLoginRunner.run(homePath: homeURL.path)

        switch result.outcome {
        case .success:
            break
        case .cancelled:
            throw CodexAccountManagerError.loginCancelled
        case .missingBinary:
            throw CodexAccountManagerError.binaryMissing
        case .timedOut:
            throw CodexAccountManagerError.loginTimedOut
        case let .launchFailed(message):
            throw CodexAccountManagerError.launchFailed(message)
        case .failed:
            throw CodexAccountManagerError.loginFailed(result.output)
        }

        let identity = try CodexAPI.loadIdentity(codexHomePath: homeURL.path)
        guard identity.email != nil || identity.providerAccountID != nil else {
            throw CodexAccountManagerError.missingIdentity
        }

        let now = Date()
        return StoredAccount(
            id: existing?.id ?? UUID(),
            nickname: existing?.nickname,
            emailHint: identity.email ?? existing?.emailHint,
            authSubject: identity.authSubject ?? existing?.authSubject,
            providerAccountID: identity.providerAccountID ?? existing?.providerAccountID,
            codexHomePath: homeURL.path,
            source: source,
            createdAt: existing?.createdAt ?? now,
            updatedAt: now,
            lastAuthenticatedAt: now)
    }

    private func discoveredManagedAccount(at homeURL: URL, existing: [StoredAccount]) -> StoredAccount? {
        guard let values = try? homeURL.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey]),
              values.isDirectory == true, values.isSymbolicLink == false else {
            return nil
        }

        let authURL = homeURL.appendingPathComponent("auth.json", isDirectory: false)
        guard FileManager.default.fileExists(atPath: authURL.path) else {
            return nil
        }

        guard let identity = try? CodexAPI.loadIdentity(codexHomePath: homeURL.path),
              identity.email != nil || identity.providerAccountID != nil
        else {
            return nil
        }

        let discoveredAt = self.directoryTimestamp(for: homeURL)
        let candidate = StoredAccount(
            id: UUID(),
            nickname: nil,
            emailHint: identity.email,
            authSubject: identity.authSubject,
            providerAccountID: identity.providerAccountID,
            codexHomePath: homeURL.path,
            source: .managedByApp,
            createdAt: discoveredAt,
            updatedAt: discoveredAt,
            lastAuthenticatedAt: discoveredAt)

        let matchedExisting = existing.first(where: { $0.matches(candidate) })

        return StoredAccount(
            id: matchedExisting?.id ?? UUID(),
            nickname: matchedExisting?.nickname,
            emailHint: identity.email ?? matchedExisting?.emailHint,
            authSubject: identity.authSubject ?? matchedExisting?.authSubject,
            providerAccountID: identity.providerAccountID ?? matchedExisting?.providerAccountID,
            codexHomePath: homeURL.path,
            source: .managedByApp,
            createdAt: matchedExisting?.createdAt ?? discoveredAt,
            updatedAt: max(matchedExisting?.updatedAt ?? .distantPast, discoveredAt),
            lastAuthenticatedAt: max(matchedExisting?.lastAuthenticatedAt ?? .distantPast, discoveredAt))
    }

    private func materializeAsManaged(_ account: StoredAccount) throws -> StoredAccount {
        try FileLocations.ensureDirectories()

        let sourceHomeURL = URL(fileURLWithPath: account.codexHomePath, isDirectory: true)
        let sourceAuthURL = sourceHomeURL.appendingPathComponent("auth.json", isDirectory: false)
        guard FileManager.default.fileExists(atPath: sourceAuthURL.path) else {
            throw CodexAccountManagerError.missingAuth
        }

        let destinationHomeURL = FileLocations.managedHomesDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: destinationHomeURL, withIntermediateDirectories: true)
        try FileManager.default.copyItem(
            at: sourceAuthURL,
            to: destinationHomeURL.appendingPathComponent("auth.json", isDirectory: false))

        let now = Date()
        return StoredAccount(
            id: account.id,
            nickname: account.nickname,
            emailHint: account.emailHint,
            authSubject: account.authSubject,
            providerAccountID: account.providerAccountID,
            codexHomePath: destinationHomeURL.path,
            source: .managedByApp,
            createdAt: account.createdAt,
            updatedAt: now,
            lastAuthenticatedAt: account.lastAuthenticatedAt ?? now)
    }

    private func backupAmbientAuth() throws -> String? {
        try FileLocations.ensureDirectories()

        let ambientAuthURL = FileLocations.ambientCodexHome.appendingPathComponent("auth.json", isDirectory: false)
        guard FileManager.default.fileExists(atPath: ambientAuthURL.path) else {
            return nil
        }

        let backupURL = FileLocations.authBackupsDirectory
            .appendingPathComponent(
                "ambient-auth-\(self.timestampSlug())-\(UUID().uuidString.lowercased()).json",
                isDirectory: false)
        try FileManager.default.copyItem(at: ambientAuthURL, to: backupURL)
        return backupURL.path
    }

    private func directoryTimestamp(for homeURL: URL) -> Date {
        let authURL = homeURL.appendingPathComponent("auth.json", isDirectory: false)
        if let authValues = try? authURL.resourceValues(forKeys: [.contentModificationDateKey]),
           let contentModificationDate = authValues.contentModificationDate
        {
            return contentModificationDate
        }

        let values = try? homeURL.resourceValues(forKeys: [.creationDateKey, .contentModificationDateKey])
        return values?.contentModificationDate
            ?? values?.creationDate
            ?? Date()
    }

    private func managedHomePathsMatching(_ account: StoredAccount) throws -> Set<String> {
        var targets: Set<String> = [
            URL(fileURLWithPath: account.codexHomePath, isDirectory: true).standardizedFileURL.path,
        ]

        let homeURLs = try FileManager.default.contentsOfDirectory(
            at: FileLocations.managedHomesDirectory,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles])

        for homeURL in homeURLs {
            guard let discovered = self.discoveredManagedAccount(at: homeURL, existing: [account]),
                  discovered.matches(account)
            else {
                continue
            }
            targets.insert(homeURL.standardizedFileURL.path)
        }

        return targets
    }

    private func timestampSlug() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: Date())
    }
}
