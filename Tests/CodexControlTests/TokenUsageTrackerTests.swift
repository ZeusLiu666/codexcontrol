import Foundation
import XCTest
@testable import CodexControl

final class TokenUsageTrackerTests: XCTestCase {
    func testStartsWithBaselineAndOnlyCountsAppendedEvents() async throws {
        let fixture = try self.makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let accountID = UUID()
        let oldEvent = self.tokenEvent(timestamp: "2026-08-25T01:00:00.000Z", total: 100)
        try Data((oldEvent + "\n").utf8).write(to: fixture.log)

        let tracker = TokenUsageTracker(
            ledgerURL: fixture.ledger,
            sessionRoots: [fixture.sessions, fixture.archived])
        var snapshots = try await tracker.start(
            activeAccountID: accountID,
            now: self.date("2026-08-26T02:00:00.000Z"))
        XCTAssertEqual(snapshots[accountID]?.allTime.totalTokens, 0)

        try self.append(
            self.tokenEvent(timestamp: "2026-08-26T03:00:00.000Z", total: 220) + "\n",
            to: fixture.log)
        snapshots = try await tracker.scan(
            activeAccountID: accountID,
            now: self.date("2026-08-26T03:01:00.000Z"))

        XCTAssertEqual(snapshots[accountID]?.today.totalTokens, 220)
        XCTAssertEqual(snapshots[accountID]?.today.inputTokens, 180)
        XCTAssertEqual(snapshots[accountID]?.today.cachedInputTokens, 80)
        XCTAssertEqual(snapshots[accountID]?.today.outputTokens, 40)
        XCTAssertEqual(snapshots[accountID]?.today.reasoningOutputTokens, 10)
        XCTAssertEqual(snapshots[accountID]?.daily.count, 7)
        XCTAssertEqual(
            snapshots[accountID]?.daily.first?.date,
            Calendar.autoupdatingCurrent.startOfDay(for: self.date("2026-08-20T02:00:00.000Z")))
        XCTAssertEqual(
            snapshots[accountID]?.daily.last?.date,
            Calendar.autoupdatingCurrent.startOfDay(for: self.date("2026-08-26T02:00:00.000Z")))
    }

    func testAccountTransitionSettlesPendingUsageToPreviousAccount() async throws {
        let fixture = try self.makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        try Data().write(to: fixture.log)
        let firstAccountID = UUID()
        let secondAccountID = UUID()
        let tracker = TokenUsageTracker(
            ledgerURL: fixture.ledger,
            sessionRoots: [fixture.sessions, fixture.archived])

        _ = try await tracker.start(
            activeAccountID: firstAccountID,
            now: self.date("2026-08-26T01:00:00.000Z"))
        try self.append(
            self.tokenEvent(timestamp: "2026-08-26T01:05:00.000Z", total: 120) + "\n",
            to: fixture.log)

        var snapshots = try await tracker.scan(
            activeAccountID: secondAccountID,
            now: self.date("2026-08-26T01:06:00.000Z"))
        XCTAssertEqual(snapshots[firstAccountID]?.allTime.totalTokens, 120)
        XCTAssertEqual(snapshots[secondAccountID]?.allTime.totalTokens, 0)

        try self.append(
            self.tokenEvent(timestamp: "2026-08-26T01:10:00.000Z", total: 75) + "\n",
            to: fixture.log)
        snapshots = try await tracker.scan(
            activeAccountID: secondAccountID,
            now: self.date("2026-08-26T01:11:00.000Z"))
        XCTAssertEqual(snapshots[firstAccountID]?.allTime.totalTokens, 120)
        XCTAssertEqual(snapshots[secondAccountID]?.allTime.totalTokens, 75)
    }

    func testSevenDayWindowRollsForwardWithCurrentDate() async throws {
        let fixture = try self.makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        try Data().write(to: fixture.log)
        let accountID = UUID()
        let tracker = TokenUsageTracker(
            ledgerURL: fixture.ledger,
            sessionRoots: [fixture.sessions, fixture.archived])

        _ = try await tracker.start(
            activeAccountID: accountID,
            now: self.date("2026-08-26T02:00:00.000Z"))
        let snapshots = try await tracker.scan(
            activeAccountID: accountID,
            now: self.date("2026-09-02T02:00:00.000Z"))

        XCTAssertEqual(snapshots[accountID]?.daily.count, 7)
        XCTAssertEqual(
            snapshots[accountID]?.daily.first?.date,
            Calendar.autoupdatingCurrent.startOfDay(for: self.date("2026-08-27T02:00:00.000Z")))
        XCTAssertEqual(
            snapshots[accountID]?.daily.last?.date,
            Calendar.autoupdatingCurrent.startOfDay(for: self.date("2026-09-02T02:00:00.000Z")))
    }

    func testIncompleteLineWaitsForNewlineAndMovedLogIsNotCountedTwice() async throws {
        let fixture = try self.makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        try Data().write(to: fixture.log)
        let accountID = UUID()
        let tracker = TokenUsageTracker(
            ledgerURL: fixture.ledger,
            sessionRoots: [fixture.sessions, fixture.archived])
        _ = try await tracker.start(
            activeAccountID: accountID,
            now: self.date("2026-08-26T01:00:00.000Z"))

        try self.append(
            self.tokenEvent(timestamp: "2026-08-26T01:05:00.000Z", total: 90),
            to: fixture.log)
        var snapshots = try await tracker.scan(
            activeAccountID: accountID,
            now: self.date("2026-08-26T01:06:00.000Z"))
        XCTAssertEqual(snapshots[accountID]?.allTime.totalTokens, 0)

        try self.append("\n", to: fixture.log)
        snapshots = try await tracker.scan(
            activeAccountID: accountID,
            now: self.date("2026-08-26T01:07:00.000Z"))
        XCTAssertEqual(snapshots[accountID]?.allTime.totalTokens, 90)

        let archivedLog = fixture.archived.appendingPathComponent(fixture.log.lastPathComponent)
        try FileManager.default.moveItem(at: fixture.log, to: archivedLog)
        snapshots = try await tracker.scan(
            activeAccountID: accountID,
            now: self.date("2026-08-26T01:08:00.000Z"))
        XCTAssertEqual(snapshots[accountID]?.allTime.totalTokens, 90)
    }

    private func makeFixture() throws -> (root: URL, sessions: URL, archived: URL, ledger: URL, log: URL) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("CodexControlTokenTests-\(UUID().uuidString)", isDirectory: true)
        let sessions = root.appendingPathComponent("sessions", isDirectory: true)
        let archived = root.appendingPathComponent("archived_sessions", isDirectory: true)
        try FileManager.default.createDirectory(at: sessions, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: archived, withIntermediateDirectories: true)
        return (
            root,
            sessions,
            archived,
            root.appendingPathComponent("token-usage.json"),
            sessions.appendingPathComponent("rollout-test.jsonl"))
    }

    private func append(_ text: String, to url: URL) throws {
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: Data(text.utf8))
    }

    private func tokenEvent(timestamp: String, total: Int64) -> String {
        let input = max(0, total - 40)
        return """
        {"timestamp":"\(timestamp)","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":\(input),"cached_input_tokens":80,"output_tokens":40,"reasoning_output_tokens":10,"total_tokens":\(total)}}}}
        """
    }

    private func date(_ value: String) -> Date {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: value)!
    }
}
