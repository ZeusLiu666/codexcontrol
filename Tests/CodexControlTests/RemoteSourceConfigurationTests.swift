import XCTest
@testable import CodexControl

@MainActor
final class RemoteSourceConfigurationTests: XCTestCase {
    func testMissingConfigurationDisablesRemoteSources() {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        XCTAssertEqual(RemoteSourceConfiguration.load(from: url), [])
    }

    func testInvalidConfigurationDisablesAllSources() throws {
        for json in ["not json", "{}", "null", #"[{"host":"server"}]"#,
                     #"[{"host":"server","isOptional":"false"}]"#]
        {
            XCTAssertEqual(try self.load(json), [])
        }
        for host in ["", "-oProxyCommand=command", "../server", "/server", "user@server", "server:22",
                     "server name", "server\n", "server;command", "$(command)", "*.example.com", "服务器",
                     "server..example", "server.", String(repeating: "a", count: 254)]
        {
            let data = try JSONSerialization.data(withJSONObject: [
                ["host": "valid-server", "isOptional": false],
                ["host": host, "isOptional": false],
            ])
            XCTAssertEqual(try self.load(String(decoding: data, as: UTF8.self)), [], host)
        }
    }

    func testDeduplicationPreservesOrderAndFirstOptionalPolicy() throws {
        let sources = try self.load(#"[{"host":"codex-server","isOptional":false},{"host":"backup_1.example.com","isOptional":true},{"host":"codex-server","isOptional":true}]"#)
        XCTAssertEqual(sources, [
            .init(host: "codex-server", isOptional: false),
            .init(host: "backup_1.example.com", isOptional: true),
        ])
    }

    func testDisabledSyncDoesNotCreateCacheOrState() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let mirror = RemoteTokenUsageMirror(
            stateURL: root.appendingPathComponent("cache/state.json"),
            cacheDirectory: root.appendingPathComponent("cache"),
            configurationURL: root.appendingPathComponent("remote-hosts.json"))
        let statuses = await mirror.sync(accounts: [], fallbackAccountID: nil)
        XCTAssertTrue(statuses.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.path))

        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        for json in ["[]", "invalid", #"[{"host":"-option","isOptional":false}]"#] {
            try Data(json.utf8).write(to: root.appendingPathComponent("remote-hosts.json"))
            let refreshedStatuses = await mirror.sync(accounts: [], fallbackAccountID: nil)
            XCTAssertTrue(refreshedStatuses.isEmpty)
            XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("cache").path))
        }
    }

    private func load(_ json: String) throws -> [RemoteSourceConfiguration.Source] {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: url) }
        try Data(json.utf8).write(to: url)
        return RemoteSourceConfiguration.load(from: url)
    }
}
