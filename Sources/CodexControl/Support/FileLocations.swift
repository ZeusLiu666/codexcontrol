import Foundation

enum FileLocations {
    static var appSupportDirectory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser
        return base.appendingPathComponent("CodexControl", isDirectory: true)
    }

    static var legacyAppSupportDirectories: [URL] {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser
        return [
            base.appendingPathComponent(["Codex", "Gauge"].joined(), isDirectory: true),
            base.appendingPathComponent(["Codex", "Accounts"].joined(), isDirectory: true),
        ]
    }

    static var accountsFile: URL {
        self.appSupportDirectory.appendingPathComponent("accounts.json", isDirectory: false)
    }

    static var snapshotsFile: URL {
        self.appSupportDirectory.appendingPathComponent("snapshots.json", isDirectory: false)
    }

    static var tokenUsageFile: URL {
        self.appSupportDirectory.appendingPathComponent("token-usage.json", isDirectory: false)
    }

    static var remoteTokenUsageDirectory: URL {
        self.appSupportDirectory.appendingPathComponent("remote-token-usage", isDirectory: true)
    }

    static var remoteTokenUsageStateFile: URL {
        self.remoteTokenUsageDirectory.appendingPathComponent("state.json", isDirectory: false)
    }

    static var widgetSnapshotFile: URL {
        self.appSupportDirectory.appendingPathComponent("widget-snapshot.json", isDirectory: false)
    }

    static var widgetExtensionSnapshotFile: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Containers/com.ademisler.codexcontrol.widget/Data", isDirectory: true)
            .appendingPathComponent("Library/Application Support/CodexControl", isDirectory: true)
            .appendingPathComponent("widget-snapshot.json", isDirectory: false)
    }

    static var managedHomesDirectory: URL {
        self.appSupportDirectory.appendingPathComponent("managed-homes", isDirectory: true)
    }

    static var authBackupsDirectory: URL {
        self.appSupportDirectory.appendingPathComponent("auth-backups", isDirectory: true)
    }

    static var ambientCodexHome: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".codex", isDirectory: true)
    }

    static func ensureDirectories() throws {
        if !FileManager.default.fileExists(atPath: self.appSupportDirectory.path) {
            for legacyDirectory in self.legacyAppSupportDirectories where FileManager.default.fileExists(atPath: legacyDirectory.path) {
                try FileManager.default.moveItem(at: legacyDirectory, to: self.appSupportDirectory)
                break
            }
        }
        try FileManager.default.createDirectory(at: self.appSupportDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: self.managedHomesDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: self.authBackupsDirectory, withIntermediateDirectories: true)
    }
}
