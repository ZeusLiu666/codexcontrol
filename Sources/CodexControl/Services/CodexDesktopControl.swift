import AppKit
import Foundation

enum CodexDesktopControlError: LocalizedError {
    case applicationNotFound
    case terminationTimedOut
    case launchFailed(Int32)

    var errorDescription: String? {
        switch self {
        case .applicationNotFound:
            return "Codex Desktop.app could not be found."
        case .terminationTimedOut:
            return "Codex Desktop did not fully exit before relaunch."
        case let .launchFailed(status):
            return "Codex Desktop failed to relaunch (exit \(status))."
        }
    }
}

struct CodexDesktopControl {
    private static let bundleIdentifier = "com.openai.codex"
    private static let pollIntervalNanoseconds: UInt64 = 250_000_000
    private static let relaunchDelayNanoseconds: UInt64 = 700_000_000
    private static let gracefulPollCount = 8
    private static let forcedPollCount = 24

    func restartCodexDesktop() async throws {
        guard let applicationURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: Self.bundleIdentifier) else {
            throw CodexDesktopControlError.applicationNotFound
        }

        let runningApplications = NSRunningApplication.runningApplications(withBundleIdentifier: Self.bundleIdentifier)
        if !runningApplications.isEmpty {
            for application in runningApplications {
                _ = application.terminate()
            }

            try await self.waitForExit()
            try await Task.sleep(nanoseconds: Self.relaunchDelayNanoseconds)
        }

        try self.launchCodexDesktop(at: applicationURL)
    }

    private func waitForExit() async throws {
        for attempt in 0 ..< Self.forcedPollCount {
            let runningApplications = NSRunningApplication.runningApplications(withBundleIdentifier: Self.bundleIdentifier)
            if runningApplications.isEmpty {
                return
            }

            if attempt == Self.gracefulPollCount {
                for application in runningApplications {
                    _ = application.forceTerminate()
                }
            }

            try await Task.sleep(nanoseconds: Self.pollIntervalNanoseconds)
        }

        throw CodexDesktopControlError.terminationTimedOut
    }

    private func launchCodexDesktop(at applicationURL: URL) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        process.arguments = ["-a", applicationURL.path]
        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            throw CodexDesktopControlError.launchFailed(process.terminationStatus)
        }
    }
}
