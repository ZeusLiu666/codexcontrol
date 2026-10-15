import Foundation

private struct TokenUsageLedger: Codable {
    var version = 1
    var trackingStartedAt: Date
    var activeAccountID: UUID?
    var dailyByAccount: [String: [String: TokenUsageBreakdown]] = [:]
    var checkpoints: [String: UInt64] = [:]
    var updatedAt: Date
}

actor TokenUsageTracker {
    private let ledgerURL: URL
    private let sessionRoots: [URL]
    private var ledger: TokenUsageLedger?
    private let timestampFormatter: ISO8601DateFormatter

    init(
        ledgerURL: URL = FileLocations.tokenUsageFile,
        sessionRoots: [URL] = [
            FileLocations.ambientCodexHome.appendingPathComponent("sessions", isDirectory: true),
            FileLocations.ambientCodexHome.appendingPathComponent("archived_sessions", isDirectory: true),
            FileLocations.remoteTokenUsageDirectory,
        ])
    {
        self.ledgerURL = ledgerURL
        self.sessionRoots = sessionRoots
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        self.timestampFormatter = formatter
    }

    func start(activeAccountID: UUID?, now: Date = Date()) throws -> [UUID: AccountTokenUsageSnapshot] {
        if self.ledger == nil {
            if let loaded = try self.loadLedger() {
                self.ledger = loaded
            } else {
                var newLedger = TokenUsageLedger(
                    trackingStartedAt: now,
                    activeAccountID: activeAccountID,
                    updatedAt: now)
                if let activeAccountID {
                    newLedger.dailyByAccount[activeAccountID.uuidString] = [:]
                }
                for fileURL in self.sessionFiles() {
                    newLedger.checkpoints[self.checkpointKey(for: fileURL)] = self.completeFileSize(at: fileURL)
                }
                self.ledger = newLedger
                try self.saveLedger()
                return self.snapshots(now: now)
            }
        }

        return try self.scan(activeAccountID: activeAccountID, now: now)
    }

    func scan(activeAccountID: UUID?, now: Date = Date()) throws -> [UUID: AccountTokenUsageSnapshot] {
        guard var ledger = self.ledger else {
            return try self.start(activeAccountID: activeAccountID, now: now)
        }

        let attributionAccountID = ledger.activeAccountID ?? activeAccountID
        if let attributionAccountID {
            if ledger.dailyByAccount[attributionAccountID.uuidString] == nil {
                ledger.dailyByAccount[attributionAccountID.uuidString] = [:]
            }
            for fileURL in self.sessionFiles() {
                self.processNewEvents(
                    in: fileURL,
                    accountID: attributionAccountID,
                    ledger: &ledger)
            }
        }

        if let activeAccountID, ledger.dailyByAccount[activeAccountID.uuidString] == nil {
            ledger.dailyByAccount[activeAccountID.uuidString] = [:]
        }

        ledger.activeAccountID = activeAccountID
        ledger.updatedAt = now
        self.ledger = ledger
        try self.saveLedger()
        return self.snapshots(now: now)
    }

    func removeAccount(_ accountID: UUID, now: Date = Date()) throws -> [UUID: AccountTokenUsageSnapshot] {
        guard var ledger = self.ledger else {
            return [:]
        }
        ledger.dailyByAccount.removeValue(forKey: accountID.uuidString)
        if ledger.activeAccountID == accountID {
            ledger.activeAccountID = nil
        }
        ledger.updatedAt = now
        self.ledger = ledger
        try self.saveLedger()
        return self.snapshots(now: now)
    }

    private func processNewEvents(in fileURL: URL, accountID: UUID, ledger: inout TokenUsageLedger) {
        let key = self.checkpointKey(for: fileURL)
        let attributes = try? FileManager.default.attributesOfItem(atPath: fileURL.path)
        let fileSize = (attributes?[.size] as? NSNumber)?.uint64Value ?? 0
        var offset = ledger.checkpoints[key] ?? 0
        if offset > fileSize {
            offset = 0
        }
        guard fileSize > offset,
              let handle = try? FileHandle(forReadingFrom: fileURL)
        else {
            ledger.checkpoints[key] = offset
            return
        }

        defer { try? handle.close() }
        do {
            try handle.seek(toOffset: offset)
            guard let data = try handle.readToEnd(),
                  let finalNewline = data.lastIndex(of: 0x0A)
            else {
                return
            }

            let completeData = data.prefix(through: finalNewline)
            for rawLine in completeData.split(separator: 0x0A, omittingEmptySubsequences: true) {
                guard let event = self.parseTokenEvent(Data(rawLine)) else {
                    continue
                }
                let targetAccountID = event.accountID ?? accountID
                let dayKey = self.dayKey(for: event.timestamp)
                var accountDays = ledger.dailyByAccount[targetAccountID.uuidString] ?? [:]
                var usage = accountDays[dayKey] ?? .zero
                usage.add(event.usage)
                accountDays[dayKey] = usage
                ledger.dailyByAccount[targetAccountID.uuidString] = accountDays
            }
            ledger.checkpoints[key] = offset + UInt64(completeData.count)
        } catch {
            return
        }
    }

    private func parseTokenEvent(_ data: Data) -> (timestamp: Date, usage: TokenUsageBreakdown, accountID: UUID?)? {
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              root["type"] as? String == "event_msg",
              let payload = root["payload"] as? [String: Any],
              payload["type"] as? String == "token_count",
              let info = payload["info"] as? [String: Any],
              let lastUsage = info["last_token_usage"] as? [String: Any],
              let timestampString = root["timestamp"] as? String,
              let timestamp = self.timestampFormatter.date(from: timestampString)
        else {
            return nil
        }

        func count(_ key: String) -> Int64 {
            (lastUsage[key] as? NSNumber)?.int64Value ?? 0
        }

        return (
            timestamp,
            TokenUsageBreakdown(
                inputTokens: count("input_tokens"),
                cachedInputTokens: count("cached_input_tokens"),
                outputTokens: count("output_tokens"),
                reasoningOutputTokens: count("reasoning_output_tokens"),
                totalTokens: count("total_tokens")),
            UUID(uuidString: root["codexcontrol_account_id"] as? String ?? ""))
    }

    private func snapshots(now: Date) -> [UUID: AccountTokenUsageSnapshot] {
        guard let ledger = self.ledger else { return [:] }
        let calendar = Calendar.autoupdatingCurrent
        let today = calendar.startOfDay(for: now)
        let sevenDayDates = Array((0 ..< 7).compactMap { offset in
            calendar.date(byAdding: .day, value: -offset, to: today)
        }.reversed())

        return Dictionary(uniqueKeysWithValues: ledger.dailyByAccount.compactMap { accountKey, accountDays in
            guard let accountID = UUID(uuidString: accountKey) else { return nil }

            let daily = sevenDayDates.map { date in
                DailyTokenUsagePoint(
                    date: date,
                    usage: accountDays[self.dayKey(for: date)] ?? .zero)
            }
            let lastSevenDays = sevenDayDates.reduce(.zero) { partial, date in
                partial + (accountDays[self.dayKey(for: date)] ?? .zero)
            }
            let allTime = accountDays.values.reduce(.zero, +)
            let todayUsage = accountDays[self.dayKey(for: today)] ?? .zero
            return (
                accountID,
                AccountTokenUsageSnapshot(
                    today: todayUsage,
                    lastSevenDays: lastSevenDays,
                    allTime: allTime,
                    daily: daily,
                    trackingStartedAt: ledger.trackingStartedAt,
                    updatedAt: ledger.updatedAt))
        })
    }

    private func dayKey(for date: Date) -> String {
        let components = Calendar.autoupdatingCurrent.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", components.year ?? 0, components.month ?? 0, components.day ?? 0)
    }

    private func sessionFiles() -> [URL] {
        var files: [URL] = []
        let keys: [URLResourceKey] = [.isRegularFileKey]
        for root in self.sessionRoots {
            guard let enumerator = FileManager.default.enumerator(
                at: root,
                includingPropertiesForKeys: keys,
                options: [.skipsHiddenFiles, .skipsPackageDescendants])
            else {
                continue
            }
            for case let fileURL as URL in enumerator where fileURL.pathExtension == "jsonl" {
                guard fileURL.lastPathComponent.hasPrefix("rollout-") else { continue }
                files.append(fileURL)
            }
        }
        return files.sorted { $0.path < $1.path }
    }

    private func checkpointKey(for fileURL: URL) -> String {
        fileURL.lastPathComponent
    }

    private func completeFileSize(at fileURL: URL) -> UInt64 {
        guard let handle = try? FileHandle(forReadingFrom: fileURL) else { return 0 }
        defer { try? handle.close() }
        guard let size = try? handle.seekToEnd(), size > 0 else { return 0 }

        let tailLength = min(UInt64(8192), size)
        do {
            try handle.seek(toOffset: size - tailLength)
            guard let tail = try handle.readToEnd(),
                  let finalNewline = tail.lastIndex(of: 0x0A)
            else {
                return 0
            }
            return size - tailLength + UInt64(tail.distance(from: tail.startIndex, to: finalNewline)) + 1
        } catch {
            return 0
        }
    }

    private func loadLedger() throws -> TokenUsageLedger? {
        guard FileManager.default.fileExists(atPath: self.ledgerURL.path) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(TokenUsageLedger.self, from: Data(contentsOf: self.ledgerURL))
    }

    private func saveLedger() throws {
        guard let ledger = self.ledger else { return }
        try FileManager.default.createDirectory(
            at: self.ledgerURL.deletingLastPathComponent(),
            withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        try encoder.encode(ledger).write(to: self.ledgerURL, options: .atomic)
    }
}
