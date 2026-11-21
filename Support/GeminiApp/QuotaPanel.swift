import Foundation

struct QuotaBucket: Codable, Equatable {
    let id: String
    let label: String
    let remainingPercent: Int
    let resetText: String?
}

struct ReaderFailure: Error {
    let code: String
    let message: String

    init(_ code: String, _ message: String) {
        self.code = code
        self.message = message
    }
}

enum QuotaPanel {
    private struct Section {
        let id: String
        let label: String
        var used: Int?
        var reset: String?
    }

    private static let fiveHours = #"(?:\b(?:five|5)[\s‐‑–—-]*hour(?:ly|s)?\b|\bcurrent (?:session|usage)\b|当前用量|目前用量|5\s*(?:个|個)?\s*(?:小时|小時)|当前会话|目前的工作階段)"#
    private static let weekly = #"(?:\b(?:weekly|this week|current week|7[\s‐‑–—-]*days?)\b|每(?:星期|周|週)|本(?:星期|周|週)|一(?:周|週)|7\s*天)"#
    private static let percentUsed = #"(?:已(?:经)?使用|已用|已消耗)\s*([0-9]+)\s*[%％]|(?<![0-9.])([0-9]+)\s*[%％]\s*(?:used\b|已用)"#
    private static let reset = #"(?:\bresets?\b|重(?:置|設)(?:时间|時間)?)[^\n]*"#

    private static func match(_ pattern: String, in value: String) -> String? {
        guard let range = value.range(of: pattern, options: [.regularExpression, .caseInsensitive]) else { return nil }
        return String(value[range])
    }

    // Gemini’s Chinese formatter joins its date and 24-hour time without a separator.
    // Split only an exact DDHH pair; a shorter run of digits is ambiguous.
    private static func displayReset(_ text: String) -> String {
        let pattern = #"^(重(?:置|設)(?:时间|時間)?[：:]\s*)([0-9]{1,2})月\s*([0-9]{2})([0-9]{2}):([0-9]{2})$"#
        let original = text as NSString
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let result = regex.firstMatch(in: text, range: NSRange(location: 0, length: original.length)) else { return text }
        let field = { (index: Int) in original.substring(with: result.range(at: index)) }
        guard let month = Int(field(2)), (1...12).contains(month),
              let day = Int(field(3)), (1...[31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]).contains(day),
              let hour = Int(field(4)), (0...23).contains(hour),
              let minute = Int(field(5)), (0...59).contains(minute) else { return text }
        return "\(field(1))\(month)月\(day)日 \(field(4)):\(field(5))"
    }

    static func reportedUpdate(_ values: [String], now: Date = Date()) -> (text: String, date: Date)? {
        for value in values {
            let label = value.trimmingCharacters(in: .whitespacesAndNewlines)
            if label == "更新时间：刚刚" || label.caseInsensitiveCompare("Updated just now") == .orderedSame ||
                label == "更新時間：剛剛" {
                return (label, now)
            }
            let relative = #"^(?:更新时间[：:]\s*[0-9]+\s*分钟前|更新時間[：:]\s*[0-9]+\s*分鐘前|updated\s+[0-9]+\s+min(?:ute)?s?\s+ago)$"#
            if match(relative, in: label) != nil, let number = match("[0-9]+", in: label),
               let minutes = Double(number), minutes.isFinite {
                return (label, now.addingTimeInterval(-minutes * 60))
            }
        }
        return nil
    }

    static func read(_ values: [String]) throws -> [QuotaBucket] {
        var sections: [Section] = []
        var current: Int?
        for value in values.flatMap({ $0.components(separatedBy: .newlines) }) {
            let line = value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty else { continue }
            if line.localizedCaseInsensitiveContains("Unable to load usage information") ||
                line.contains("无法加载使用情况信息") || line.contains("無法載入用量資訊") {
                throw ReaderFailure("unavailable", "Gemini 未能加载用量信息。")
            }
            // A reset such as “Resets in 5 hours” is a time, not a section heading.
            let resetText = match(reset, in: line)
            let heading = resetText.flatMap { line.range(of: $0) }.map { String(line[..<$0.lowerBound]) } ?? line
            let five = match(fiveHours, in: heading)
            let week = match(weekly, in: heading)
            if five != nil && week != nil {
                // Explanatory paragraphs can mention both billing windows.
                current = nil
                continue
            }
            if let periodLabel = five ?? week {
                let id = five != nil ? "fiveHour" : "weekly"
                if let index = sections.firstIndex(where: { $0.id == id }) {
                    current = index
                } else {
                    let label = heading.count <= 35 && match(percentUsed, in: heading) == nil ? heading : periodLabel
                    sections.append(Section(id: id, label: label))
                    current = sections.count - 1
                }
            }
            guard let current else { continue }
            if let usage = match(percentUsed, in: line),
               let digits = match("[0-9]+", in: usage), let percent = Int(digits) {
                guard (0...100).contains(percent),
                      sections[current].used.map({ $0 == percent }) ?? true else {
                    throw ReaderFailure("unsupportedFormat", "无法确定 Gemini 显示的用量百分比。")
                }
                sections[current].used = percent
            }
            if let resetText, sections[current].reset == nil {
                sections[current].reset = displayReset(resetText.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }

        let buckets = sections.compactMap { section -> QuotaBucket? in
            guard let used = section.used else { return nil }
            return QuotaBucket(id: section.id, label: section.label, remainingPercent: 100 - used, resetText: section.reset)
        }
        guard !buckets.isEmpty else {
            throw ReaderFailure("unsupportedFormat", "未在 Gemini 用量限额面板识别到带周期的已用百分比。")
        }
        return buckets
    }
}
