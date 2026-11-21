import Foundation

// Compile together with Support/GeminiApp/QuotaPanel.swift.
@main
struct QuotaPanelTests {
    static func main() throws {
        let chinese = [
            "更新时间：2 分钟前", "当前用量", "已使用 19%", "重置时间：16:24",
            "每周限额", "已使用 0%", "重置时间：11月 2416:24", "使用 AI 点数", "剩余点数：0",
        ]
        let expected = [
            QuotaBucket(id: "fiveHour", label: "当前用量", remainingPercent: 81, resetText: "重置时间：16:24"),
            QuotaBucket(id: "weekly", label: "每周限额", remainingPercent: 100, resetText: "重置时间：11月24日 16:24"),
        ]
        let values = try QuotaPanel.read(chinese)
        precondition(values == expected)
        for reset in ["重置时间：11月 216:24", "重置时间：2月 3016:24", "重置时间：11月 2426:24"] {
            let value = try QuotaPanel.read(["每周限额", "已使用 0%", reset])
            precondition(value.first?.resetText == reset)
        }
        let now = Date(timeIntervalSince1970: 10000)
        precondition(QuotaPanel.reportedUpdate(chinese, now: now)?.date == now.addingTimeInterval(-120))

        let traditional = try QuotaPanel.read(["每週限額", "已使用 16%", "重設時間：11月 2416:24"])
        precondition(traditional.first?.resetText == "重設時間：11月24日 16:24")

        let english = ["Current usage", "100% used", "Resets in 5 hours", "Weekly limit", "3% used", "Updated just now"]
        let result = try QuotaPanel.read(english)
        precondition(result.map(\.remainingPercent) == [0, 97])
        precondition(result.first?.resetText == "Resets in 5 hours")
        precondition(QuotaPanel.reportedUpdate(english, now: now)?.date == now)
        precondition(QuotaPanel.reportedUpdate(["Updated 4 min ago"], now: now)?.date == now.addingTimeInterval(-240))
        for labels in [
            ["剩余点数：50"],
            ["当前用量", "已使用 101%"],
            ["Weekly limit", "5% used", "8% used"],
            ["Weekly limit", "Estimated refill in 12% of a day"],
            ["無法載入用量資訊。", "每週限額", "已使用 0%"],
            ["无法加载使用情况信息。", "每周限额", "已使用 0%"],
        ] {
            precondition((try? QuotaPanel.read(labels)) == nil)
        }
        print("Gemini App quota parser checks passed")
    }
}
