import AppKit
import ApplicationServices
import Foundation

let geminiBundleID = "com.google.GeminiMacOS"

func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &result) == .success else { return nil }
    return result
}

func children(_ element: AXUIElement, _ name: String = kAXChildrenAttribute) -> [AXUIElement] {
    attribute(element, name) as? [AXUIElement] ?? []
}

func string(_ element: AXUIElement, _ name: String) -> String {
    attribute(element, name) as? String ?? ""
}

func strings(_ element: AXUIElement) -> [String] {
    var result: [String] = []
    for name in [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute] {
        let value = string(element, name)
        if !value.isEmpty && !result.contains(value) { result.append(value) }
    }
    return result
}

// Walk native controls only. Search boxes, web views and editable content are leaves.
func walk(_ root: AXUIElement, _ visit: (AXUIElement, String) -> Bool) {
    var stack: [(AXUIElement, Int)] = [(root, 0)]
    var remaining = 600
    while let (element, depth) = stack.popLast(), remaining > 0 {
        remaining -= 1
        let role = string(element, kAXRoleAttribute)
        guard visit(element, role), depth < 18,
              !["AXWebArea", kAXTextAreaRole, kAXTextFieldRole, kAXStaticTextRole].contains(role) else { continue }
        stack.append(contentsOf: children(element).reversed().map { ($0, depth + 1) })
    }
}

func localizedSettingNames(_ bundle: Bundle) -> (sections: Set<String>, usage: Set<String>, reload: Set<String>) {
    var sections: Set<String> = ["Settings", "设置", "設定"]
    var usage: Set<String> = ["Usage limits", "用量限额", "使用限額"]
    var reload: Set<String> = ["Reload", "重新加载", "重新載入"]
    // Gemini localizes its settings-window title to the selected sidebar section.
    let locales = Set(bundle.preferredLocalizations + ["en", "zh_CN", "zh_TW"])
    for locale in locales {
        guard let url = bundle.resourceURL?.appendingPathComponent("\(locale).lproj/App.strings"),
              let data = try? Data(contentsOf: url),
              let dictionary = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [String: String] else { continue }
        sections.formUnion(dictionary.filter { $0.key.hasPrefix("SETTINGS_STATE_") }.values)
        if let title = dictionary["SETTINGS_STATE_USAGE_LIMITS"] { usage.insert(title) }
        if let button = dictionary["USAGE_LIMITS_RELOAD"] { reload.insert(button) }
    }
    sections.formUnion(usage)
    return (sections, usage, reload)
}

func waitFor<T>(_ seconds: TimeInterval, _ action: () -> T?) -> T? {
    let until = ProcessInfo.processInfo.systemUptime + seconds
    repeat {
        if let result = action() { return result }
        Thread.sleep(forTimeInterval: 0.15)
    } while ProcessInfo.processInfo.systemUptime < until
    return nil
}

func press(_ element: AXUIElement) -> Bool {
    AXUIElementPerformAction(element, kAXPressAction as CFString) == .success
}

func openSettingsMenu(_ app: AXUIElement) -> Bool {
    guard let menuRef = attribute(app, kAXMenuBarAttribute), CFGetTypeID(menuRef) == AXUIElementGetTypeID() else { return false }
    let menuBar = (menuRef as! AXUIElement)
    let menu = children(menuBar).first { item in string(item, kAXTitleAttribute) == "Gemini" }
    guard let menu else { return false }
    func settingsItem() -> AXUIElement? {
        var match: AXUIElement?
        walk(menu) { item, role in
            guard match == nil else { return false }
            if role == kAXMenuItemRole {
                let title = string(item, kAXTitleAttribute).trimmingCharacters(in: CharacterSet(charactersIn: "…. "))
                if string(item, kAXMenuItemCmdCharAttribute) == "," || ["Settings", "设置", "設定", "Preferences"].contains(title) {
                    match = item
                }
            }
            return true
        }
        return match
    }
    if let item = settingsItem(), press(item) { return true }
    guard press(menu) else { return false }
    if let item = waitFor(0.75, settingsItem), press(item) { return true }
    _ = AXUIElementPerformAction(menu, kAXCancelAction as CFString)
    return false
}

func settingsWindow(_ app: AXUIElement, names: Set<String>) -> AXUIElement? {
    for window in children(app, kAXWindowsAttribute) {
        guard names.contains(string(window, kAXTitleAttribute)) else { continue }
        // A conversation can have the same title as a settings pane. Verify the
        // settings-specific search box before reading any labels inside the window.
        var isSettings = false
        walk(window) { element, _ in
            if string(element, kAXIdentifierAttribute) == "settings_search_field" { isSettings = true }
            return !isSettings
        }
        if isSettings { return window }
    }
    return nil
}

func selectUsage(_ window: AXUIElement, titles: Set<String>) -> Bool {
    var row: AXUIElement?
    var list: AXUIElement?
    walk(window) { element, role in
        guard row == nil else { return false }
        guard role == kAXListRole || role == kAXOutlineRole || role == kAXTableRole else { return true }
        for candidate in children(element, kAXRowsAttribute) + children(element) where string(candidate, kAXRoleAttribute) == kAXRowRole {
            var matches = false
            walk(candidate) { item, _ in
                if !Set(strings(item)).isDisjoint(with: titles) { matches = true }
                return !matches
            }
            if matches { row = candidate; list = element; break }
        }
        return false
    }
    guard let row else { return false }
    if press(row) { return true }
    if AXUIElementSetAttributeValue(row, kAXSelectedAttribute as CFString, kCFBooleanTrue) == .success { return true }
    guard let list else { return false }
    return AXUIElementSetAttributeValue(list, kAXSelectedRowsAttribute as CFString, [row] as CFArray) == .success
}

struct PanelView {
    var values: [String] = []
    var reload: AXUIElement?
}

func panelView(_ window: AXUIElement, reloadLabels: Set<String>) -> PanelView {
    var panel = PanelView()
    walk(window) { element, role in
        if [kAXTextFieldRole, kAXTextAreaRole, kAXOutlineRole, kAXRowRole, "AXWebArea"].contains(role) { return false }
        let labels = strings(element)
        if role == kAXButtonRole && !Set(labels + [string(element, kAXHelpAttribute)]).isDisjoint(with: reloadLabels) {
            panel.reload = element
        }
        if [kAXStaticTextRole, kAXGroupRole, kAXProgressIndicatorRole, "AXHeading"].contains(role) {
            panel.values.append(contentsOf: labels)
        }
        return true
    }
    return panel
}

struct Snapshot: Encodable {
    let ok = true
    let available = true
    let buckets: [QuotaBucket]
    let asOf: Double?
    let updatedText: String?

    init(_ values: [String]) throws {
        self.buckets = try QuotaPanel.read(values)
        let updated = QuotaPanel.reportedUpdate(values)
        self.asOf = updated?.date.timeIntervalSince1970
        self.updatedText = updated?.text
    }

    // The current Gemini App session owns these limits. Never infer its identity
    // from a separately signed-in CLI, browser or CodexControl account.
}

enum ReadMode: String {
    case peek, refresh
    case updateOpen = "update-open"
    case connectBackground = "connect-background"
}

func geminiApp(launch: Bool) throws -> (Bundle, NSRunningApplication, AXUIElement) {
    guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: geminiBundleID),
          let bundle = Bundle(url: url) else {
        throw ReaderFailure("appNotInstalled", "未找到 Google Gemini Mac 应用。")
    }
    guard AXIsProcessTrusted() else {
        throw ReaderFailure("accessibilityDenied", "请在「系统设置 → 隐私与安全性 → 辅助功能」中允许 CodexControl 读取 Gemini 的用量面板。")
    }

    func currentApp() -> NSRunningApplication? {
        NSRunningApplication.runningApplications(withBundleIdentifier: geminiBundleID).first { !$0.isTerminated }
    }
    var running = currentApp()
    if running == nil && launch {
        let opener = Process()
        opener.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        opener.arguments = ["-b", geminiBundleID]
        try opener.run()
        opener.waitUntilExit()
        running = waitFor(4, currentApp)
    }
    guard let running else { throw ReaderFailure("appNotRunning", "Gemini Mac 应用尚未运行。") }
    let app = AXUIElementCreateApplication(running.processIdentifier)
    AXUIElementSetMessagingTimeout(app, 1)
    return (bundle, running, app)
}

// Gemini 1.147 exposes its official account menu directly on the main window’s
// sidebar group. Limit discovery to that navigation path, outside all chat rows.
func openAccounts() throws {
    let (bundle, running, app) = try geminiApp(launch: true)
    let localized = bundle.localizedString(forKey: "SIDEBAR_USER_PROFILE_A11Y_LABEL", value: nil, table: "App")
    let labels: Set<String> = [localized, "Account and settings", "账号和设置", "帳戶和設定"]
    for window in children(app, kAXWindowsAttribute) {
        var groups = [window]
        for role in [kAXGroupRole, kAXSplitGroupRole, kAXGroupRole] {
            groups = groups.flatMap { children($0) }.filter { string($0, kAXRoleAttribute) == role }
        }
        for item in groups.flatMap({ children($0) }) where string(item, kAXRoleAttribute) == kAXMenuButtonRole {
            guard labels.contains(string(item, kAXDescriptionAttribute)) || labels.contains(string(item, kAXTitleAttribute)) else { continue }
            if attribute(window, kAXMinimizedAttribute) as? Bool == true {
                _ = AXUIElementSetAttributeValue(window, kAXMinimizedAttribute as CFString, kCFBooleanFalse)
            }
            running.activate(options: [])
            _ = AXUIElementPerformAction(window, kAXRaiseAction as CFString)
            if press(item) { return }
        }
    }
    running.activate(options: [])
    throw ReaderFailure("accountMenuUnavailable", "请在 Gemini 主窗口展开边栏，再点击「账号和设置」以添加或切换账号。")
}

func read(_ mode: ReadMode) throws -> Snapshot {
    let interactive = mode == .refresh || mode == .connectBackground
    let (bundle, running, app) = try geminiApp(launch: interactive)
    let titles = localizedSettingNames(bundle)
    func existingWindow() -> AXUIElement? { settingsWindow(app, names: titles.sections) }
    var window = existingWindow()
    if window == nil && interactive {
        running.activate(options: [])
        if openSettingsMenu(app) { window = waitFor(3, existingWindow) }
    }
    guard let window else {
        throw ReaderFailure("panelClosed", "请在 Gemini 菜单中打开「设置 → 用量限额」。")
    }
    var usageWindow: AXUIElement? = titles.usage.contains(string(window, kAXTitleAttribute)) ? window : nil
    if usageWindow == nil && interactive, selectUsage(window, titles: titles.usage) {
        usageWindow = waitFor(3) { existingWindow().flatMap { titles.usage.contains(string($0, kAXTitleAttribute)) ? $0 : nil } }
    }
    guard let usageWindow else { throw ReaderFailure("panelClosed", "请在 Gemini 设置中选择「用量限额」。") }

    // SwiftUI reuses its settings window when the user changes the selected
    // section. Check its title again before every read during an asynchronous reload.
    func currentPanel() throws -> PanelView {
        guard titles.usage.contains(string(usageWindow, kAXTitleAttribute)) else {
            throw ReaderFailure("panelClosed", "Gemini 用量限额面板已关闭。")
        }
        return panelView(usageWindow, reloadLabels: titles.reload)
    }

    func finish(_ snapshot: Snapshot) throws -> Snapshot {
        guard mode == .connectBackground else { return snapshot }
        guard titles.usage.contains(string(usageWindow, kAXTitleAttribute)) else {
            throw ReaderFailure("panelClosed", "Gemini 用量限额面板已关闭。")
        }
        if attribute(usageWindow, kAXMinimizedAttribute) as? Bool != true {
            let result = AXUIElementSetAttributeValue(usageWindow, kAXMinimizedAttribute as CFString, kCFBooleanTrue)
            guard result == .success, waitFor(1.5, { (attribute(usageWindow, kAXMinimizedAttribute) as? Bool) == true ? true : nil }) == true else {
                throw ReaderFailure("minimizeFailed", "Gemini 额度已读取，但未能将用量限额窗口最小化。")
            }
        }
        return snapshot
    }

    let initial = try currentPanel()
    if mode != .peek, let button = initial.reload, press(button) {
        let before = try? Snapshot(initial.values)
        let deadline = ProcessInfo.processInfo.systemUptime + 4
        var latest = initial
        repeat {
            Thread.sleep(forTimeInterval: 0.25)
            latest = try currentPanel()
            if let snapshot = try? Snapshot(latest.values),
               snapshot.updatedText != before?.updatedText || snapshot.buckets != before?.buckets {
                return try finish(snapshot)
            }
        } while ProcessInfo.processInfo.systemUptime < deadline
        // Gemini may return identical counters and relative time after a reload.
        // Retain its displayed update time instead of stamping this read as fresh.
        return try finish(Snapshot(latest.values))
    }
    if let snapshot = try? Snapshot(initial.values) { return try finish(snapshot) }
    if mode != .peek, let snapshot = waitFor(3, { try? Snapshot(currentPanel().values) }) { return try finish(snapshot) }
    return try finish(Snapshot(currentPanel().values))
}

do {
    let args = CommandLine.arguments.dropFirst()
    guard args.count == 1, let action = args.first else {
        throw ReaderFailure("invalidAction", "缺少 Gemini 操作。")
    }
    let data: Data
    if action == "accounts" {
        try openAccounts()
        data = try JSONSerialization.data(withJSONObject: ["ok": true])
    } else if let mode = ReadMode(rawValue: action) {
        data = try JSONEncoder().encode(read(mode))
    } else {
        throw ReaderFailure("invalidAction", "无法识别 Gemini 操作。")
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([10]))
} catch {
    let failure = error as? ReaderFailure ?? ReaderFailure("unavailable", "无法读取 Gemini 用量信息。")
    let message = ["ok": false, "code": failure.code, "message": failure.message] as [String: Any]
    if let data = try? JSONSerialization.data(withJSONObject: message) { FileHandle.standardOutput.write(data) }
    FileHandle.standardOutput.write(Data([10]))
}
