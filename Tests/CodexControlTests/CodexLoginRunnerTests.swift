import Foundation
import XCTest
@testable import CodexControl

final class CodexLoginRunnerTests: XCTestCase {
    private func makeCommand(in directory: URL, body: String) throws -> String {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let command = directory.appendingPathComponent("synthetic-sign-in")
        try ("#!/bin/sh\n" + body + "\n").write(to: command, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: command.path)
        return command.path
    }

    func testTimeoutStopsLoginEvenWhenItIgnoresTermination() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let command = try makeCommand(in: directory, body: """
            trap '' TERM
            touch "$CODEX_HOME/ready"
            exec /bin/sleep 10
            """)
        let start = ContinuousClock.now
        let result = await CodexLoginRunner.run(homePath: directory.path, timeout: 2, binary: command)
        guard case .timedOut = result.outcome else { return XCTFail("Expected timeout") }
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent("ready").path))
        XCTAssertLessThan(start.duration(to: .now), .seconds(5))
    }

    func testDrainsOutputWithoutWaitingForDescendantToClosePipe() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let command = try makeCommand(in: directory, body: """
            printf '%090000d' 1
            printf '%090000d' 2 >&2
            /bin/sleep 8 &
            exit 7
            """)
        let start = ContinuousClock.now
        let result = await CodexLoginRunner.run(homePath: directory.path, timeout: 5, binary: command)
        guard case .failed(status: 7) = result.outcome else { return XCTFail("Expected CLI exit code") }
        XCTAssertEqual(result.output.count, 4000)
        XCTAssertLessThan(start.duration(to: .now), .seconds(5))
    }

    func testCancellationStopsRunningLogin() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let command = try makeCommand(in: directory, body: """
            touch "$CODEX_HOME/started"
            exec /bin/sleep 8
            """)
        let start = ContinuousClock.now
        let login = Task { await CodexLoginRunner.run(homePath: directory.path, binary: command) }
        let marker = directory.appendingPathComponent("started").path
        while !FileManager.default.fileExists(atPath: marker), start.duration(to: .now) < .seconds(3) {
            try await Task.sleep(for: .milliseconds(10))
        }
        login.cancel()
        guard case .cancelled = await login.value.outcome else { return XCTFail("Expected cancelled login") }
        XCTAssertTrue(FileManager.default.fileExists(atPath: marker))
        XCTAssertLessThan(start.duration(to: .now), .seconds(5))
    }
}
