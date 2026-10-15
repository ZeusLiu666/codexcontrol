import Foundation

/// Local opt-in configuration, read again on each refresh.
enum RemoteSourceConfiguration {
    struct Source: Decodable, Equatable, Sendable {
        let host: String
        let isOptional: Bool

        var cacheName: String { self.host }
    }

    static var fileURL: URL {
        FileLocations.appSupportDirectory.appendingPathComponent("remote-hosts.json", isDirectory: false)
    }

    static func load(from url: URL = RemoteSourceConfiguration.fileURL) -> [Source] {
        guard let data = try? Data(contentsOf: url),
              let sources = try? JSONDecoder().decode([Source].self, from: data)
        else { return [] }
        return self.validated(sources)
    }

    /// Fail closed for invalid entries. Duplicate aliases keep their first policy.
    static func validated(_ sources: [Source]) -> [Source] {
        guard sources.allSatisfy({ self.isValidHost($0.host) }) else { return [] }
        var seen = Set<String>()
        return sources.filter { seen.insert($0.host).inserted }
    }

    private static func isValidHost(_ host: String) -> Bool {
        let bytes = Array(host.utf8)
        func isAlphanumeric(_ byte: UInt8) -> Bool {
            (65 ... 90).contains(byte) || (97 ... 122).contains(byte) || (48 ... 57).contains(byte)
        }
        guard let first = bytes.first, isAlphanumeric(first), bytes.count <= 253,
              bytes.last != 46, !host.contains("..")
        else { return false }
        // SSH users and ports belong in ~/.ssh/config. Reject options, paths,
        // whitespace, shell syntax, wildcards, and non-ASCII lookalikes here.
        return bytes.allSatisfy { isAlphanumeric($0) || $0 == 46 || $0 == 45 || $0 == 95 }
    }
}
