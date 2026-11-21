import SwiftUI

struct DashboardAccountCard<Content: View>: View {
    let isExpanded: Bool
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 10 : 7, content: content)
            .padding(.horizontal, 12)
            .padding(.vertical, isExpanded ? 11 : 9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color(nsColor: .controlBackgroundColor)))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(isExpanded ? Color.accentColor.opacity(0.40) : Color.primary.opacity(0.09)))
    }
}

struct DashboardAccountTitle: View {
    let name: String
    let subtitle: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(name)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.primary)
            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
        }
        .lineLimit(1)
        .truncationMode(.middle)
        .help([name, subtitle].compactMap { $0 }.joined(separator: "\n"))
    }
}

struct DashboardQuotaRow<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        HStack(alignment: .top, spacing: 7, content: content)
    }
}

struct DashboardQuotaTile: View {
    let title: String
    let value: String
    let remainingPercent: Double?
    let reset: String?
    var showsRawResetText = false

    private var tint: Color {
        guard let remainingPercent, remainingPercent.isFinite else { return .secondary }
        if remainingPercent <= 10 { return .red }
        if remainingPercent <= 20 { return .orange }
        return .green
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) {
                    titleLabel.fixedSize()
                    Spacer(minLength: 0)
                    valueLabel.fixedSize()
                }
                VStack(alignment: .leading, spacing: 3) {
                    titleLabel
                    valueLabel
                }
            }

            if let remainingPercent, remainingPercent.isFinite {
                GeometryReader { geometry in
                    Capsule()
                        .fill(tint.opacity(0.15))
                        .overlay(alignment: .leading) {
                            Capsule()
                                .fill(tint)
                                .frame(width: geometry.size.width * min(1, max(0, remainingPercent / 100)))
                        }
                }
                .frame(height: 4)
                .padding(.vertical, 2)
                .accessibilityHidden(true)
            }

            if let reset {
                Label(showsRawResetText ? reset : "重置 " + reset, systemImage: "clock")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.045), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    static func windowTitle(_ label: String) -> String {
        switch label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "weekly limit remaining", "weekly limit", "weekly", "7d": return "每周额度"
        case "5-hour limit remaining", "5-hour limit", "5 hour limit", "5h": return "5 小时额度"
        default: return label
        }
    }

    private var titleLabel: some View {
        Text(title)
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var valueLabel: some View {
        Text(value)
            .font(.system(size: 13, weight: .semibold, design: .rounded).monospacedDigit())
            .foregroundStyle(.primary)
    }
}

struct InlineStatePill: View {
    let text: String
    let systemName: String
    let tint: Color
    var lineLimit = 1

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: self.systemName)
                .font(.system(size: 10, weight: .semibold))
            Text(self.text)
                .lineLimit(self.lineLimit)
                .multilineTextAlignment(.leading)
        }
        .font(.system(size: 11, weight: .medium))
        .foregroundStyle(self.tint)
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(self.tint.opacity(0.08)))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(self.tint.opacity(0.14), lineWidth: 1))
    }
}

struct RowActionButton: View {
    let systemName: String
    let title: String
    var role: ButtonRole?
    let action: () -> Void

    var body: some View {
        Button(role: self.role, action: self.action) {
            Image(systemName: self.systemName)
                .font(.system(size: 12, weight: .semibold))
                .frame(width: 24, height: 24)
                .background(
                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                        .fill(Color(NSColor.windowBackgroundColor)))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(self.title)
        .help(self.title)
    }
}

struct HeaderActionPill: View {
    let title: String
    let systemName: String
    let action: () -> Void

    var body: some View {
        Button(action: self.action) {
            HStack(spacing: 5) {
                Image(systemName: self.systemName)
                    .font(.system(size: 9, weight: .semibold))
                Text(self.title)
                    .font(.system(size: 10, weight: .semibold, design: .rounded))
            }
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(
                Capsule(style: .continuous)
                    .fill(Color(NSColor.windowBackgroundColor)))
        }
        .buttonStyle(.plain)
    }
}
