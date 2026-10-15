import Foundation

/// Pulls only token-count records from Codex sessions on configured SSH hosts.
///
/// The remote command never reads conversation content into the result. It parses
/// the session files on the server and returns compact JSON records plus byte
/// checkpoints, so subsequent refreshes only inspect appended data.
actor RemoteTokenUsageMirror {
    private typealias Source = RemoteSourceConfiguration.Source

    private struct HostState: Codable {
        var checkpoints: [String: UInt64] = [:]
        var pendingEvents: [PendingEvent] = []
        var bootstrapped = false

        private enum CodingKeys: String, CodingKey {
            case checkpoints
            case pendingEvents
            case bootstrapped
        }

        init(
            checkpoints: [String: UInt64] = [:],
            pendingEvents: [PendingEvent] = [],
            bootstrapped: Bool = false)
        {
            self.checkpoints = checkpoints
            self.pendingEvents = pendingEvents
            self.bootstrapped = bootstrapped
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            self.checkpoints = try container.decodeIfPresent([String: UInt64].self, forKey: .checkpoints) ?? [:]
            self.pendingEvents = try container.decodeIfPresent([PendingEvent].self, forKey: .pendingEvents) ?? []
            self.bootstrapped = try container.decodeIfPresent(Bool.self, forKey: .bootstrapped) ?? false
        }
    }

    private struct PendingEvent: Codable {
        let providerAccountID: String?
        let timestamp: String
        let usage: TokenUsageBreakdown
    }

    private struct MirrorState: Codable {
        var version = 1
        var hosts: [String: HostState] = [:]
        var updatedAt = Date()
    }

    private struct RemoteEvent {
        let providerAccountID: String?
        let timestamp: String
        let usage: TokenUsageBreakdown
    }

    private struct SSHConnectionDetails {
        let user: String
        let hostname: String
        let port: String
    }

    private struct CollectorResult {
        let providerAccountID: String?
        let events: [RemoteEvent]
        let checkpoints: [String: UInt64]
        let bootstrapped: Bool
        let connection: SSHConnectionDetails
    }

    private let stateURL: URL
    private let cacheDirectory: URL
    private let configuredSources: [Source]?
    private let configurationURL: URL
    private var state: MirrorState?

    init(
        stateURL: URL = FileLocations.remoteTokenUsageStateFile,
        cacheDirectory: URL = FileLocations.remoteTokenUsageDirectory,
        hosts: [String]? = nil,
        configurationURL: URL = RemoteSourceConfiguration.fileURL)
    {
        self.stateURL = stateURL
        self.cacheDirectory = cacheDirectory
        self.configurationURL = configurationURL
        self.configuredSources = hosts.map { hosts in
            RemoteSourceConfiguration.validated(hosts.map { Source(host: $0, isOptional: false) })
        }
    }

    func sync(accounts: [StoredAccount], fallbackAccountID: UUID?) -> [RemoteTokenUsageStatus] {
        let sources = self.configuredSources ?? RemoteSourceConfiguration.load(from: self.configurationURL)
        guard !sources.isEmpty else { return [] }

        do {
            try FileManager.default.createDirectory(at: self.cacheDirectory, withIntermediateDirectories: true)
        } catch {
            return sources.map {
                RemoteTokenUsageStatus(
                    host: $0.host,
                    isAvailable: false,
                    detail: "Local cache unavailable",
                    isOptional: $0.isOptional)
            }
        }

        do {
            if self.state == nil {
                self.state = try self.loadState() ?? MirrorState()
            }
        } catch {
            return sources.map {
                RemoteTokenUsageStatus(
                    host: $0.host,
                    isAvailable: false,
                    detail: "Local checkpoint unreadable",
                    isOptional: $0.isOptional)
            }
        }

        let accountMap = accounts.reduce(into: [String: UUID]()) { result, account in
            guard let providerAccountID = account.normalizedProviderAccountID else { return }
            result[providerAccountID] = account.id
        }

        var statuses: [RemoteTokenUsageStatus] = []
        for source in sources {
            do {
                let hostState = self.state?.hosts[source.host] ?? HostState()
                let result = try self.collect(source: source, hostState: hostState)
                let pending = hostState.pendingEvents + result.events.map { event in
                    PendingEvent(
                        providerAccountID: event.providerAccountID,
                        timestamp: event.timestamp,
                        usage: event.usage)
                }
                var readyEvents: [(RemoteEvent, UUID)] = []
                var remainingEvents: [PendingEvent] = []
                for event in pending {
                    let mappedAccountID = event.providerAccountID
                        .flatMap { accountMap[StoredAccount.normalizeIdentifier($0) ?? $0] }
                        ?? (event.providerAccountID == nil ? fallbackAccountID : nil)
                    if let mappedAccountID {
                        readyEvents.append((
                            RemoteEvent(
                                providerAccountID: event.providerAccountID,
                                timestamp: event.timestamp,
                                usage: event.usage),
                            mappedAccountID))
                    } else {
                        remainingEvents.append(event)
                    }
                }
                try self.append(
                    readyEvents,
                    to: self.cacheDirectory.appendingPathComponent(
                        "rollout-remote-\(source.cacheName).jsonl",
                        isDirectory: false))

                self.state?.hosts[source.host] = HostState(
                    checkpoints: result.checkpoints,
                    pendingEvents: remainingEvents,
                    bootstrapped: result.bootstrapped)
                self.state?.updatedAt = Date()
                try self.saveState()

                let detail: String
                if result.providerAccountID == nil {
                    detail = fallbackAccountID == nil
                        ? "Connected; account identity unavailable"
                        : "Connected; attributed to active account"
                } else if !remainingEvents.isEmpty {
                    detail = "Connected; account is not in CodexControl"
                } else {
                    detail = readyEvents.isEmpty ? "Connected; no new events" : "Connected"
                }
                statuses.append(RemoteTokenUsageStatus(
                    host: source.host,
                    isAvailable: true,
                    detail: detail,
                    isOptional: source.isOptional))
            } catch {
                statuses.append(RemoteTokenUsageStatus(
                    host: source.host,
                    isAvailable: false,
                    detail: self.conciseError(error),
                    isOptional: source.isOptional))
            }
        }
        return statuses
    }

    private func collect(source: Source, hostState: HostState) throws -> CollectorResult {
        // Resolve the alias on every refresh. This deliberately follows the
        // user's current ~/.ssh/config instead of caching a hostname or port,
        // including aliases whose ports can change.
        let connection = try self.resolveSSHConfiguration(for: source)
        let encoder = JSONEncoder()
        let stateData = try encoder.encode(hostState)
        let stateBase64 = stateData.base64EncodedString()
        let script = Self.remoteScript(stateBase64: stateBase64)

        let input = Pipe()
        let output = Pipe()
        let errorOutput = Pipe()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ssh")
        process.arguments = [
            "-T",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=\(source.isOptional ? 3 : 8)",
            "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=1",
            "-o", "ClearAllForwardings=yes",
            source.host,
            "python3",
            "-",
        ]
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errorOutput

        try process.run()
        try input.fileHandleForWriting.write(contentsOf: Data(script.utf8))
        try input.fileHandleForWriting.close()

        let outputData = output.fileHandleForReading.readDataToEndOfFile()
        let errorData = errorOutput.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            let stderr = String(data: errorData, encoding: .utf8) ?? ""
            throw RemoteTokenUsageMirrorError.commandFailed(stderr)
        }

        return try self.parseCollectorOutput(outputData, connection: connection)
    }

    private func resolveSSHConfiguration(for source: Source) throws -> SSHConnectionDetails {
        let output = Pipe()
        let errorOutput = Pipe()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ssh")
        process.arguments = [
            "-G",
            "-o", "ClearAllForwardings=yes",
            source.host,
        ]
        process.standardOutput = output
        process.standardError = errorOutput

        try process.run()
        let outputData = output.fileHandleForReading.readDataToEndOfFile()
        let errorData = errorOutput.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        guard process.terminationStatus == 0,
              let text = String(data: outputData, encoding: .utf8)
        else {
            let stderr = String(data: errorData, encoding: .utf8) ?? ""
            throw RemoteTokenUsageMirrorError.configurationFailed(stderr)
        }

        var values: [String: String] = [:]
        for line in text.split(whereSeparator: \.isNewline) {
            let fields = line.split(maxSplits: 1, whereSeparator: \.isWhitespace)
            guard fields.count == 2 else { continue }
            values[String(fields[0])] = String(fields[1])
        }

        guard let user = values["user"], !user.isEmpty,
              let hostname = values["hostname"], !hostname.isEmpty,
              let port = values["port"], !port.isEmpty
        else {
            throw RemoteTokenUsageMirrorError.configurationFailed("SSH config did not resolve \(source.host)")
        }
        return SSHConnectionDetails(user: user, hostname: hostname, port: port)
    }

    private func parseCollectorOutput(
        _ data: Data,
        connection: SSHConnectionDetails) throws -> CollectorResult
    {
        guard let text = String(data: data, encoding: .utf8) else {
            throw RemoteTokenUsageMirrorError.invalidOutput
        }

        var providerAccountID: String?
        var events: [RemoteEvent] = []
        var checkpoints: [String: UInt64] = [:]
        var bootstrapped = false

        for line in text.split(whereSeparator: \.isNewline) {
            guard let lineData = line.data(using: .utf8),
                  let object = try JSONSerialization.jsonObject(with: lineData) as? [String: Any],
                  let kind = object["kind"] as? String
            else {
                continue
            }

            switch kind {
            case "meta":
                providerAccountID = object["account_id"] as? String
            case "event":
                guard let timestamp = object["timestamp"] as? String,
                      let usage = self.usage(from: object["usage"] as? [String: Any])
                else { continue }
                events.append(RemoteEvent(
                    providerAccountID: nil,
                    timestamp: timestamp,
                    usage: usage))
            case "checkpoint":
                guard let file = object["file"] as? String,
                      let offset = (object["offset"] as? NSNumber)?.uint64Value
                else { continue }
                checkpoints[file] = offset
            case "state":
                bootstrapped = object["bootstrapped"] as? Bool ?? false
            default:
                continue
            }
        }

        guard bootstrapped else {
            throw RemoteTokenUsageMirrorError.invalidOutput
        }
        return CollectorResult(
            providerAccountID: providerAccountID,
            events: events.map { event in
                RemoteEvent(
                    providerAccountID: providerAccountID,
                    timestamp: event.timestamp,
                    usage: event.usage)
            },
            checkpoints: checkpoints,
            bootstrapped: bootstrapped,
            connection: connection)
    }

    private func usage(from object: [String: Any]?) -> TokenUsageBreakdown? {
        guard let object else { return nil }
        func value(_ key: String) -> Int64 {
            (object[key] as? NSNumber)?.int64Value ?? 0
        }
        return TokenUsageBreakdown(
            inputTokens: value("input_tokens"),
            cachedInputTokens: value("cached_input_tokens"),
            outputTokens: value("output_tokens"),
            reasoningOutputTokens: value("reasoning_output_tokens"),
            totalTokens: value("total_tokens"))
    }

    private func append(_ events: [(RemoteEvent, UUID)], to url: URL) throws {
        guard !events.isEmpty else { return }
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.seekToEnd()

        for (event, accountID) in events {
            let payload: [String: Any] = [
                "timestamp": event.timestamp,
                "type": "event_msg",
                "codexcontrol_account_id": accountID.uuidString,
                "payload": [
                    "type": "token_count",
                    "info": [
                        "last_token_usage": [
                            "input_tokens": event.usage.inputTokens,
                            "cached_input_tokens": event.usage.cachedInputTokens,
                            "output_tokens": event.usage.outputTokens,
                            "reasoning_output_tokens": event.usage.reasoningOutputTokens,
                            "total_tokens": event.usage.totalTokens,
                        ],
                    ],
                ],
            ]
            let data = try JSONSerialization.data(withJSONObject: payload, options: [])
            try handle.write(contentsOf: data)
            try handle.write(contentsOf: Data([0x0A]))
        }
    }

    private func loadState() throws -> MirrorState? {
        guard FileManager.default.fileExists(atPath: self.stateURL.path) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(MirrorState.self, from: Data(contentsOf: self.stateURL))
    }

    private func saveState() throws {
        guard let state = self.state else { return }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        try encoder.encode(state).write(to: self.stateURL, options: .atomic)
    }

    private func conciseError(_ error: Error) -> String {
        let text: String
        if case let RemoteTokenUsageMirrorError.commandFailed(stderr) = error {
            text = stderr
        } else if case let RemoteTokenUsageMirrorError.configurationFailed(stderr) = error {
            text = stderr
        } else {
            text = error.localizedDescription
        }
        let lowercased = text.lowercased()
        if lowercased.contains("permission denied") || lowercased.contains("password") {
            return "SSH key required"
        }
        if lowercased.contains("timed out") || lowercased.contains("timeout") {
            return "SSH timeout"
        }
        if lowercased.contains("no route") || lowercased.contains("network is unreachable") {
            return "Network unavailable"
        }
        return "SSH unavailable"
    }

    private static func remoteScript(stateBase64: String) -> String {
        // The first successful run reads only files touched in the last seven days.
        // This avoids a multi-gigabyte historical scan while preserving all future
        // usage incrementally.
        """
        import base64
        import json
        import pathlib
        import time
        import datetime

        state = json.loads(base64.b64decode(\"\(stateBase64)\").decode(\"utf-8\"))
        checkpoints = dict(state.get(\"checkpoints\", {}))
        bootstrapped = bool(state.get(\"bootstrapped\", False))
        cutoff = time.time() - (7 * 24 * 60 * 60) if not bootstrapped else None

        def emit(value):
            print(json.dumps(value, separators=(\",\", \":\"), ensure_ascii=True))

        account_id = None
        try:
            auth = json.loads((pathlib.Path.home() / \".codex\" / \"auth.json\").read_text())
            account_id = (auth.get(\"tokens\") or {}).get(\"account_id\")
        except Exception:
            pass
        emit({\"kind\": \"meta\", \"account_id\": account_id})

        roots = [pathlib.Path.home() / \".codex\" / \"sessions\", pathlib.Path.home() / \".codex\" / \"archived_sessions\"]
        seen = set()
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob(\"**/rollout-*.jsonl\")):
                name = path.name
                if name in seen:
                    continue
                seen.add(name)
                try:
                    size = path.stat().st_size
                    if not bootstrapped and name not in checkpoints and path.stat().st_mtime < cutoff:
                        checkpoints[name] = size
                        emit({\"kind\": \"checkpoint\", \"file\": name, \"offset\": size})
                        continue
                    offset = int(checkpoints.get(name, 0))
                    if offset > size:
                        offset = 0
                    with path.open(\"rb\") as handle:
                        handle.seek(offset)
                        data = handle.read()
                    final_newline = data.rfind(b\"\\n\")
                    if final_newline < 0:
                        checkpoints[name] = offset
                        emit({\"kind\": \"checkpoint\", \"file\": name, \"offset\": offset})
                        continue
                    complete = data[:final_newline + 1]
                    for raw in complete.splitlines():
                        try:
                            event = json.loads(raw)
                            if event.get(\"type\") != \"event_msg\":
                                continue
                            payload = event.get(\"payload\") or {}
                            if payload.get(\"type\") != \"token_count\":
                                continue
                            timestamp = event.get(\"timestamp\")
                            info = payload.get(\"info\") or {}
                            usage = info.get(\"last_token_usage\") or {}
                            if not timestamp or not isinstance(usage, dict):
                                continue
                            if cutoff is not None:
                                try:
                                    parsed = datetime.datetime.fromisoformat(timestamp.replace(\"Z\", \"+00:00\")).timestamp()
                                    if parsed < cutoff:
                                        continue
                                except Exception:
                                    continue
                            values = {key: int(usage.get(key, 0) or 0) for key in (\"input_tokens\", \"cached_input_tokens\", \"output_tokens\", \"reasoning_output_tokens\", \"total_tokens\")}
                            emit({\"kind\": \"event\", \"timestamp\": timestamp, \"usage\": values})
                        except Exception:
                            continue
                    new_offset = offset + len(complete)
                    checkpoints[name] = new_offset
                    emit({\"kind\": \"checkpoint\", \"file\": name, \"offset\": new_offset})
                except (OSError, ValueError):
                    continue
        emit({\"kind\": \"state\", \"bootstrapped\": True})
        """
    }
}

private enum RemoteTokenUsageMirrorError: Error {
    case commandFailed(String)
    case configurationFailed(String)
    case invalidOutput
}
