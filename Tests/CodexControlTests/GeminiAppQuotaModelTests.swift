import Foundation
import XCTest
@testable import CodexControl

@MainActor
final class GeminiAppQuotaModelTests: XCTestCase {
    private struct Fixture {
        let root: URL
        var resources: URL { root.appendingPathComponent("Contents/Resources") }
        var directory: URL { root.appendingPathComponent("GeminiApp") }
        var helper: URL { root.appendingPathComponent("Contents/Helpers/gemini-app-usage") }

        init() throws {
            root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            try FileManager.default.createDirectory(at: helper.deletingLastPathComponent(), withIntermediateDirectories: true)
        }

        func configure(peek: String, refresh: String, updateOpen: String? = nil,
                       accounts: String = #"{"ok":true}"#) throws {
            let script = """
            #!/bin/sh
            echo "$1" >> "$(dirname "$0")/calls"
            case "$1" in
              peek) echo '\(peek)' ;;
              update-open) echo '\(updateOpen ?? peek)' ;;
              accounts) echo '\(accounts)' ;;
              refresh|connect-background) echo '\(refresh)' ;;
              *) exit 2 ;;
            esac
            """
            try Data(script.utf8).write(to: helper, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: helper.path)
        }
    }

    private let closed = #"{"ok":false,"code":"panelClosed","message":"额度设置页已关闭。"}"#
    private let denied = #"{"ok":false,"code":"accessibilityDenied","message":"请授予辅助功能访问权限。"}"#
    private let success = #"{"ok":true,"available":true,"accountEmail":null,"buckets":[{"id":"fiveHour","label":"5 小时","remainingPercent":92,"resetText":"14:50 重置"},{"id":"weekly","label":"每周","remainingPercent":0}]}"#

    func testManualRefreshAndPassivePollingKeepAnOfflineSnapshotWithoutAccountInference() async throws {
        let fixture = try Fixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        try fixture.configure(peek: closed, refresh: success)
        let model = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources, automaticRefresh: false)
        await model.refreshInBackground()
        XCTAssertNil(model.snapshot)
        XCTAssertNil(model.error)

        await model.refresh()
        let snapshot = try XCTUnwrap(model.snapshot)
        XCTAssertEqual(snapshot.buckets.map(\.remainingPercent), [92, 0])
        XCTAssertEqual(snapshot.buckets[0].resetText, "14:50 重置")
        XCTAssertNil(snapshot.accountEmail)
        XCTAssertTrue(model.isCurrent)
        await model.refreshInBackground()
        XCTAssertFalse(model.isCurrent)
        XCTAssertNil(model.error)
        XCTAssertEqual(model.snapshot, snapshot)
        let reopen = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources, automaticRefresh: false)
        XCTAssertEqual(reopen.snapshot, snapshot)
        XCTAssertFalse(reopen.isCurrent)
        XCTAssertFalse(reopen.isRefreshing)
    }

    func testAppUserChangeReplacesAllWindowsAndMissingIdentityDoesNotInheritEmail() async throws {
        let fixture = try Fixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let withEmail = success.replacingOccurrences(of: "null", with: #""reader@example.test""#)
        let model = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources, automaticRefresh: false)
        try fixture.configure(peek: withEmail, refresh: withEmail)
        await model.refreshInBackground()
        XCTAssertEqual(model.snapshot?.accountEmail, "reader@example.test")
        XCTAssertEqual(model.accountSnapshots.map(\.accountEmail), ["reader@example.test"])
        let other = success.replacingOccurrences(of: "null", with: #""other@example.test""#)
        try fixture.configure(peek: other, refresh: other)
        await model.refreshInBackground()
        let single = #"{"ok":true,"buckets":[{"id":"weekly","label":"每周","remainingPercent":100}]}"#
        try fixture.configure(peek: single, refresh: single)
        await model.refreshInBackground()
        XCTAssertNil(model.snapshot?.accountEmail)
        XCTAssertEqual(model.snapshot?.buckets.map(\.id), ["weekly"])
        XCTAssertEqual(model.accountSnapshots.map(\.accountEmail), ["other@example.test", "reader@example.test"])
        let reopen = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources, automaticRefresh: false)
        XCTAssertEqual(reopen.accountSnapshots, model.accountSnapshots)
        XCTAssertNil(reopen.snapshot?.accountEmail)

        let prior = model.snapshot
        try fixture.configure(peek: denied, refresh: denied)
        await model.refresh()
        XCTAssertEqual(model.error, "请授予辅助功能访问权限。")
        XCTAssertEqual(model.errorCode, "accessibilityDenied")
        XCTAssertEqual(model.snapshot, prior)
        XCTAssertFalse(model.isCurrent)
    }

    func testClosedPanelAndBackgroundReloadThrottlePreserveSourceUpdateTime() async throws {
        let fixture = try Fixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        var time = Date(timeIntervalSince1970: 1_800_000_000)
        let appDate = time.addingTimeInterval(-600)
        func readings(asOf: Date) -> String {
            success.replacingOccurrences(of: #""available":true"#,
                with: #""available":true,"asOf":\#(asOf.timeIntervalSince1970),"updatedText":"10 minutes ago""#)
        }
        let model = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources,
                                        automaticRefresh: false, now: { time })
        try fixture.configure(peek: readings(asOf: appDate), refresh: denied)
        await model.refreshInBackground() // Initial peek observes an open, stale panel.
        let original = try XCTUnwrap(model.snapshot)
        XCTAssertEqual(original.sourceUpdatedAt, appDate)
        await model.refreshInBackground() // A stale open panel can now reload.
        time.addTimeInterval(60)
        try fixture.configure(peek: readings(asOf: appDate.addingTimeInterval(12)), refresh: denied)
        await model.refreshInBackground() // Rounding in the app's relative label.
        XCTAssertEqual(model.snapshot, original)
        time.addTimeInterval(241)
        try fixture.configure(peek: closed, refresh: denied, updateOpen: closed)
        await model.refreshInBackground()
        time.addTimeInterval(600)
        await model.refreshInBackground() // A closed panel only gets passive checks.
        XCTAssertEqual(model.snapshot, original)
        XCTAssertFalse(model.isCurrent)
        let url = fixture.helper.deletingLastPathComponent().appendingPathComponent("calls")
        let calls = try String(contentsOf: url, encoding: .utf8).split(separator: "\n")
        XCTAssertEqual(calls, ["peek", "update-open", "peek", "update-open", "peek"])
    }

    func testOpenPanelRefreshReportsProgressOnlyForUserActions() async throws {
        let fixture = try Fixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        try fixture.configure(peek: success, refresh: success)
        let model = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources, automaticRefresh: false)
        var observedBusy = false
        let observation = model.objectWillChange.sink { observedBusy = observedBusy || model.isRefreshing }
        defer { observation.cancel() }

        await model.refreshInBackground()
        XCTAssertFalse(observedBusy)
        await model.refreshOpenPanel()
        XCTAssertTrue(observedBusy)
        XCTAssertFalse(model.isRefreshing)
    }

    func testExplicitAccountMenuLeavesQuotaAndCacheUntouched() async throws {
        let fixture = try Fixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let model = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources, automaticRefresh: false)
        try fixture.configure(peek: closed, refresh: success)
        await model.manageAccounts()
        XCTAssertNil(model.snapshot)
        XCTAssertFalse(FileManager.default.fileExists(atPath: fixture.directory.path))
        await model.connectForBackgroundUpdates()
        let connected = try XCTUnwrap(model.snapshot)
        let file = fixture.directory.appendingPathComponent("quota.json")
        let data = try Data(contentsOf: file)
        try fixture.configure(peek: closed, refresh: success, accounts: denied)
        await model.manageAccounts()
        XCTAssertEqual(model.errorCode, "accessibilityDenied")
        XCTAssertTrue(model.isCurrent)
        try fixture.configure(peek: closed, refresh: success)
        await model.manageAccounts()
        XCTAssertNil(model.error)
        XCTAssertNil(model.errorCode)
        XCTAssertFalse(model.isRefreshing)
        XCTAssertEqual(model.snapshot, connected)
        XCTAssertEqual(try Data(contentsOf: file), data)
        let url = fixture.helper.deletingLastPathComponent().appendingPathComponent("calls")
        let calls = try String(contentsOf: url, encoding: .utf8).split(separator: "\n")
        XCTAssertEqual(calls, ["accounts", "connect-background", "accounts", "accounts"])
    }

    func testMalformedAndCLIShapedDataCannotReplaceAppQuota() async throws {
        let fixture = try Fixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        try FileManager.default.createDirectory(at: fixture.directory, withIntermediateDirectories: true)
        let cli = #"{"ok":true,"buckets":[{"name":"Gemini · weekly","value":"剩余 100%"}]}"#
        try Data(cli.utf8).write(to: fixture.directory.appendingPathComponent("quota.json"))
        let model = GeminiAppQuotaModel(directory: fixture.directory, resources: fixture.resources, automaticRefresh: false)
        XCTAssertNil(model.snapshot)
        try fixture.configure(peek: closed, refresh: success)
        await model.refresh()
        let prior = model.snapshot
        for bad in [cli, success.replacingOccurrences(of: "92", with: "101"),
                    success.replacingOccurrences(of: "fiveHour", with: "weekly")] {
            try fixture.configure(peek: bad, refresh: bad)
            await model.refresh()
            XCTAssertEqual(model.snapshot, prior)
            XCTAssertFalse(model.isCurrent)
            XCTAssertNotNil(model.error)
        }
    }
}
