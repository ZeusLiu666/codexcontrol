import Combine
import Darwin
import Foundation

struct GeminiAppQuotaBucket: Identifiable, Codable, Equatable, Sendable {
    let id: String
    let label: String
    let remainingPercent: Int
    let resetText: String?
}

struct GeminiAppQuotaSnapshot: Codable, Equatable, Sendable {
    let buckets: [GeminiAppQuotaBucket]
    let accountEmail: String?
    let updatedAt: Date
    var sourceUpdatedAt: Date? = nil

    fileprivate static func validBuckets(_ buckets: [GeminiAppQuotaBucket]) -> Bool {
        !buckets.isEmpty && Set(buckets.map(\.id)).count == buckets.count && buckets.allSatisfy {
            ["fiveHour", "weekly"].contains($0.id) &&
                !$0.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
                (0...100).contains($0.remainingPercent)
        }
    }
}

@MainActor
final class GeminiAppQuotaModel: ObservableObject {
    @Published private(set) var snapshot: GeminiAppQuotaSnapshot?
    @Published private(set) var accountSnapshots: [GeminiAppQuotaSnapshot] = []
    @Published private(set) var error: String?
    @Published private(set) var errorCode: String?
    @Published private var pendingUserActions = 0
    var isRefreshing: Bool { pendingUserActions > 0 }
    /// True after reading the live panel. Restoring a cache or finding the panel closed clears this flag.
    @Published private(set) var isCurrent = false

    private struct HelperReply: Decodable, Sendable {
        let ok: Bool
        let available: Bool?
        let buckets: [GeminiAppQuotaBucket]?
        let accountEmail: String?
        let asOf: Double?
        let updatedText: String?
        let code: String?
        let message: String?
    }

    private struct Cache: Codable {
        let source: String
        let snapshot: GeminiAppQuotaSnapshot
        let accounts: [GeminiAppQuotaSnapshot]?
    }

    private enum Mode: String {
        case peek
        case updateOpen = "update-open"
        case refresh
        case connectBackground = "connect-background"
        case accounts

        var isExplicitAction: Bool {
            switch self {
            case .refresh, .connectBackground, .accounts: true
            case .peek, .updateOpen: false
            }
        }
    }

    private let directory: URL
    private let helper: URL?
    private let now: () -> Date
    private var lastReloadAttempt: Date?
    private var active: (mode: Mode, task: Task<Void, Never>)?
    private var polling: Task<Void, Never>?
    private var cacheNeedsRetry = false
    private var cacheURL: URL { directory.appendingPathComponent("quota.json") }

    init(directory: URL = FileLocations.appSupportDirectory.appendingPathComponent("GeminiApp", isDirectory: true),
         resources: URL? = Bundle.main.resourceURL, automaticRefresh: Bool = true,
         now: @escaping () -> Date = { Date() }) {
        self.now = now
        self.directory = directory
        self.helper = resources?.deletingLastPathComponent().appendingPathComponent("Helpers/gemini-app-usage")
        do {
            let cached = try JSONDecoder().decode(Cache.self, from: Data(contentsOf: cacheURL))
            guard cached.source == "gemini-app", GeminiAppQuotaSnapshot.validBuckets(cached.snapshot.buckets) else {
                throw CocoaError(.fileReadCorruptFile)
            }
            snapshot = cached.snapshot
            accountSnapshots = Self.namedSnapshots((cached.accounts ?? []) + [cached.snapshot])
        } catch let err as CocoaError where err.code == .fileReadNoSuchFile {
            // The first successful read creates a cache.
        } catch {
            self.error = "无法读取上次保存的 Gemini App 额度。"
        }
        if automaticRefresh {
            polling = Task { [weak self] in
                while !Task.isCancelled {
                    guard self != nil else { return }
                    await self?.refreshInBackground()
                    do { try await Task.sleep(for: .seconds(60)) } catch { return }
                }
            }
        }
    }

    deinit { polling?.cancel() }

    /// User initiated. The helper may bring Gemini App's settings to the front.
    func refresh() async { await performUserAction(.refresh) }

    /// Gemini handles the account chooser and any sign-in itself.
    func manageAccounts() async { await performUserAction(.accounts) }

    /// Explicitly open the official quota panel and minimize it for background updates.
    func connectForBackgroundUpdates() async { await performUserAction(.connectBackground) }

    /// Explicit dashboard-wide refresh. Reload a panel only if it is already visible.
    func refreshOpenPanel() async { await performUserAction(.updateOpen) }

    /// Neither background mode opens settings or requests permissions.
    func refreshInBackground() async {
        let lastUpdate = snapshot?.sourceUpdatedAt ?? snapshot?.updatedAt ?? .distantPast
        let lastCheck = max(lastUpdate, lastReloadAttempt ?? .distantPast)
        let reload = isCurrent && now().timeIntervalSince(lastCheck) >= 300
        await read(reload ? .updateOpen : .peek)
    }

    private func performUserAction(_ mode: Mode) async {
        pendingUserActions += 1
        defer { pendingUserActions -= 1 }
        await read(mode)
    }

    private func read(_ mode: Mode) async {
        if let active {
            await active.task.value
            let needsAction = (mode.isExplicitAction && active.mode != mode) ||
                (mode == .updateOpen && (active.mode == .peek || active.mode == .accounts))
            if needsAction && !Task.isCancelled { await read(mode) }
            return
        }
        if mode != .peek && mode != .accounts { lastReloadAttempt = now() }
        let task = Task { [weak self] in
            guard let self else { return }
            defer { self.active = nil }
            do {
                guard let helper else { throw CocoaError(.fileNoSuchFile) }
                let reply = try await Self.run(helper: helper, argument: mode.rawValue)
                if mode == .accounts {
                    self.errorCode = reply.ok ? nil : reply.code
                    self.error = reply.ok ? nil : (reply.message ?? "无法打开 Gemini App 的账号菜单。")
                    return
                }
                guard reply.ok, reply.available != false else {
                    self.isCurrent = false
                    let idle = ["appNotRunning", "panelClosed", "appNotInstalled"].contains(reply.code ?? "")
                    if mode.isExplicitAction || (!idle && reply.available != false) {
                        self.errorCode = reply.code
                        self.error = reply.message ?? "暂时无法读取 Gemini App 的额度。"
                    }
                    return
                }
                guard let buckets = reply.buckets, GeminiAppQuotaSnapshot.validBuckets(buckets) else {
                    throw CocoaError(.coderReadCorrupt)
                }
                let fresh = self.observedSnapshot(buckets: buckets, reply: reply, now: self.now())
                let changed = self.snapshot != fresh
                self.isCurrent = true
                self.error = nil
                self.errorCode = nil
                guard changed || self.cacheNeedsRetry else { return }
                self.snapshot = fresh
                self.accountSnapshots = Self.namedSnapshots(self.accountSnapshots + [fresh])
                do {
                    try self.persist(fresh)
                    self.cacheNeedsRetry = false
                } catch {
                    self.cacheNeedsRetry = true
                    self.error = "已读取 Gemini App 额度，但无法在本机保存。"
                }
            } catch {
                if mode != .accounts { self.isCurrent = false }
                self.errorCode = "unavailable"
                self.error = mode == .accounts ? "无法打开 Gemini App 的账号菜单。" : "Gemini App 额度读取工具不可用或返回了无效数据。"
            }
        }
        active = (mode, task)
        await task.value
    }

    private func observedSnapshot(buckets: [GeminiAppQuotaBucket], reply: HelperReply, now: Date) -> GeminiAppQuotaSnapshot {
        let email = Self.email(reply.accountEmail)
        let sourceDate = reply.asOf.flatMap { seconds -> Date? in
            guard seconds > 0, seconds <= now.timeIntervalSince1970 + 5 else { return nil }
            return Date(timeIntervalSince1970: min(seconds, now.timeIntervalSince1970))
        }
        if let old = snapshot, old.buckets == buckets, old.accountEmail?.lowercased() == email?.lowercased() {
            guard let sourceDate else { return old }
            // Relative labels have limited precision. Reading “2 minutes ago” again
            // should not manufacture a new update on each background poll.
            let label = reply.updatedText?.lowercased() ?? ""
            let precision: TimeInterval
            if label.contains("day") || label.contains("天") { precision = 86_400 }
            else if label.contains("hour") || label.contains("小时") || label.contains("小時") { precision = 3_600 }
            else { precision = 60 }
            if let previous = old.sourceUpdatedAt, sourceDate.timeIntervalSince(previous) < precision { return old }
        }
        return GeminiAppQuotaSnapshot(buckets: buckets, accountEmail: email, updatedAt: now, sourceUpdatedAt: sourceDate)
    }

    private static func email(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              value.range(of: #"^[^@\s]+@[^@\s]+\.[^@\s]+$"#, options: .regularExpression) != nil else { return nil }
        return value
    }

    private static func namedSnapshots(_ records: [GeminiAppQuotaSnapshot]) -> [GeminiAppQuotaSnapshot] {
        var latest: [String: GeminiAppQuotaSnapshot] = [:]
        for record in records {
            guard let key = email(record.accountEmail)?.lowercased(),
                  GeminiAppQuotaSnapshot.validBuckets(record.buckets),
                  record.updatedAt >= (latest[key]?.updatedAt ?? .distantPast) else { continue }
            latest[key] = record
        }
        return latest.keys.sorted().compactMap { latest[$0] }
    }

    private func persist(_ fresh: GeminiAppQuotaSnapshot) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        // Multiple copies of the menu-bar app may observe different signed-in accounts.
        let lock = open(directory.path, O_RDONLY | O_DIRECTORY)
        guard lock >= 0 else { throw POSIXError(.EACCES) }
        defer { close(lock) }
        guard flock(lock, LOCK_EX) == 0 else { throw POSIXError(.EIO) }
        var latest = fresh
        if let data = try? Data(contentsOf: cacheURL), let cached = try? JSONDecoder().decode(Cache.self, from: data),
           cached.source == "gemini-app", GeminiAppQuotaSnapshot.validBuckets(cached.snapshot.buckets) {
            accountSnapshots = Self.namedSnapshots(accountSnapshots + (cached.accounts ?? []) + [cached.snapshot])
            if cached.snapshot.updatedAt > latest.updatedAt { latest = cached.snapshot }
        }
        let cache = Cache(source: "gemini-app", snapshot: latest, accounts: accountSnapshots)
        try JSONEncoder().encode(cache).write(to: cacheURL, options: .atomic)
    }

    nonisolated private static func run(helper: URL, argument: String) async throws -> HelperReply {
        try await Task.detached(priority: .utility) {
            let process = Process()
            let output = Pipe()
            process.executableURL = helper
            process.arguments = [argument]
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = output
            process.standardError = FileHandle.nullDevice
            try process.run()
            let timeout = Task {
                do { try await Task.sleep(for: .seconds(45)) } catch { return }
                guard process.isRunning else { return }
                process.terminate()
                do { try await Task.sleep(for: .seconds(2)) } catch { return }
                if process.isRunning { _ = Darwin.kill(process.processIdentifier, SIGKILL) }
            }
            defer { timeout.cancel() }
            let data = try output.fileHandleForReading.readToEnd() ?? Data()
            process.waitUntilExit()
            let reply = try JSONDecoder().decode(HelperReply.self, from: data)
            guard !reply.ok || process.terminationStatus == 0 else { throw CocoaError(.executableRuntimeMismatch) }
            return reply
        }.value
    }
}
