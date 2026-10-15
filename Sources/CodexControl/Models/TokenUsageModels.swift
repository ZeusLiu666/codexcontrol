import Foundation

struct TokenUsageBreakdown: Codable, Hashable, Sendable {
    var inputTokens: Int64
    var cachedInputTokens: Int64
    var outputTokens: Int64
    var reasoningOutputTokens: Int64
    var totalTokens: Int64

    static let zero = TokenUsageBreakdown(
        inputTokens: 0,
        cachedInputTokens: 0,
        outputTokens: 0,
        reasoningOutputTokens: 0,
        totalTokens: 0)

    var uncachedInputTokens: Int64 {
        max(0, self.inputTokens - self.cachedInputTokens)
    }

    mutating func add(_ other: TokenUsageBreakdown) {
        self.inputTokens += other.inputTokens
        self.cachedInputTokens += other.cachedInputTokens
        self.outputTokens += other.outputTokens
        self.reasoningOutputTokens += other.reasoningOutputTokens
        self.totalTokens += other.totalTokens
    }

    static func + (left: TokenUsageBreakdown, right: TokenUsageBreakdown) -> TokenUsageBreakdown {
        var result = left
        result.add(right)
        return result
    }
}

struct DailyTokenUsagePoint: Codable, Hashable, Sendable, Identifiable {
    let date: Date
    let usage: TokenUsageBreakdown

    var id: Date { self.date }
}

struct AccountTokenUsageSnapshot: Codable, Hashable, Sendable {
    let today: TokenUsageBreakdown
    let lastSevenDays: TokenUsageBreakdown
    let allTime: TokenUsageBreakdown
    let daily: [DailyTokenUsagePoint]
    let trackingStartedAt: Date
    let updatedAt: Date

    var hasUsage: Bool {
        self.allTime.totalTokens > 0
    }
}

struct RemoteTokenUsageStatus: Identifiable, Hashable, Sendable {
    let host: String
    let isAvailable: Bool
    let detail: String
    let isOptional: Bool

    init(host: String, isAvailable: Bool, detail: String, isOptional: Bool = false) {
        self.host = host
        self.isAvailable = isAvailable
        self.detail = detail
        self.isOptional = isOptional
    }

    var id: String { self.host }
}

enum TokenCountFormatter {
    static func compact(_ value: Int64) -> String {
        let magnitude = abs(Double(value))
        let divisor: Double
        let suffix: String

        switch magnitude {
        case 1_000_000_000...:
            divisor = 1_000_000_000
            suffix = "B"
        case 1_000_000...:
            divisor = 1_000_000
            suffix = "M"
        case 1_000...:
            divisor = 1_000
            suffix = "K"
        default:
            return value.formatted(.number.grouping(.automatic))
        }

        let scaled = Double(value) / divisor
        let precision = scaled.magnitude >= 100 ? 0 : (scaled.magnitude >= 10 ? 1 : 2)
        return scaled.formatted(.number.precision(.fractionLength(0 ... precision))) + suffix
    }

    static func full(_ value: Int64) -> String {
        value.formatted(.number.grouping(.automatic))
    }
}
