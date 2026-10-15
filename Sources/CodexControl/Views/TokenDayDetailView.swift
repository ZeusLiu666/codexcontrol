import SwiftUI

/// The anchor travels to RootView so scrolling never clips the day detail.
struct TokenDayDetailSelection {
    let point: DailyTokenUsagePoint
    let anchor: Anchor<CGRect>
    let isPinned: Bool
    let dismiss: () -> Void
    var viewport: Anchor<CGRect>? = nil
}

struct TokenDayDetailPreferenceKey: PreferenceKey {
    static var defaultValue: TokenDayDetailSelection? { nil }

    static func reduce(value: inout TokenDayDetailSelection?, nextValue: () -> TokenDayDetailSelection?) {
        if let next = nextValue() {
            value = next
        }
    }
}

struct TokenContributionHeatmap: View {
    let points: [DailyTokenUsagePoint]
    @State private var hoveredDay: Date?
    @State private var pinnedDay: Date?
    @FocusState private var focusedDay: Date?

    private var selectedDay: Date? {
        self.pinnedDay ?? self.hoveredDay ?? self.focusedDay
    }

    private var maximum: Int64 {
        max(1, self.points.map(\.usage.totalTokens).max() ?? 1)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text("Hover or select a day")
                    .font(.system(size: 9))
                Spacer(minLength: 8)
                HStack(spacing: 3) {
                    Text("Less")
                    ForEach(0 ... 4, id: \.self) { level in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(self.legendColor(level: level))
                            .frame(width: 7, height: 7)
                    }
                    Text("More")
                }
                .font(.system(size: 8))
                .accessibilityHidden(true)
            }
            .foregroundStyle(.secondary)

            HStack(spacing: 0) {
                ForEach(self.points) { point in
                    self.dayButton(point)
                }
            }
        }
        .onExitCommand(perform: self.dismiss)
        .onChange(of: self.points.map(\.id)) { _, ids in
            if let day = self.pinnedDay, !ids.contains(day) {
                self.pinnedDay = nil
            }
            if let day = self.hoveredDay, !ids.contains(day) {
                self.hoveredDay = nil
            }
            if let day = self.focusedDay, !ids.contains(day) {
                self.focusedDay = nil
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Daily token usage, last seven days")
    }

    private func dayButton(_ point: DailyTokenUsagePoint) -> some View {
        let isSelected = self.selectedDay == point.id
        let isToday = Calendar.autoupdatingCurrent.isDateInToday(point.date)

        return Button {
            if self.pinnedDay == point.id {
                self.dismiss()
            } else {
                self.pinnedDay = point.id
            }
        } label: {
            VStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(self.color(for: point))
                    .frame(width: 22, height: 22)
                    .overlay {
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .strokeBorder(Color.primary.opacity(0.08), lineWidth: 1)
                    }
                    .padding(3)
                    .overlay {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(isSelected ? Color.accentColor : .clear, lineWidth: 1.5)
                    }

                Text(isToday ? "Today" : point.date.formatted(.dateTime.weekday(.narrow)))
                    .font(.system(size: 9, weight: .medium))
                Text(point.date.formatted(.dateTime.day()))
                    .font(.system(size: 9, weight: isToday ? .semibold : .regular).monospacedDigit())
                    .foregroundStyle(isToday ? Color.accentColor : Color.secondary)
            }
            .foregroundStyle(.secondary)
            .padding(.vertical, 2)
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focusable()
        .focused(self.$focusedDay, equals: point.id)
        .onHover { inside in
            if inside {
                self.hoveredDay = point.id
            } else if self.hoveredDay == point.id {
                self.hoveredDay = nil
            }
        }
        .anchorPreference(key: TokenDayDetailPreferenceKey.self, value: .bounds) { anchor in
            isSelected ? TokenDayDetailSelection(
                point: point,
                anchor: anchor,
                isPinned: self.pinnedDay == point.id,
                dismiss: self.dismiss) : nil
        }
        .accessibilityLabel(point.date.formatted(.dateTime.weekday(.wide).month(.wide).day().year()))
        .accessibilityValue("\(TokenCountFormatter.full(point.usage.totalTokens)) total tokens. Input \(TokenCountFormatter.full(point.usage.inputTokens)), including \(TokenCountFormatter.full(point.usage.cachedInputTokens)) cached. Output \(TokenCountFormatter.full(point.usage.outputTokens)), including \(TokenCountFormatter.full(point.usage.reasoningOutputTokens)) reasoning.")
        .accessibilityHint(self.pinnedDay == point.id ? "Dismiss day details" : "Pin exact token details")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    private func dismiss() {
        self.pinnedDay = nil
        self.hoveredDay = nil
        self.focusedDay = nil
    }

    private func color(for point: DailyTokenUsagePoint) -> Color {
        guard point.usage.totalTokens > 0 else {
            return self.legendColor(level: 0)
        }
        let ratio = Double(point.usage.totalTokens) / Double(self.maximum)
        switch ratio {
        case ..<0.2: return self.legendColor(level: 1)
        case ..<0.4: return self.legendColor(level: 2)
        case ..<0.7: return self.legendColor(level: 3)
        default: return self.legendColor(level: 4)
        }
    }

    private func legendColor(level: Int) -> Color {
        switch level {
        case 1: Color.green.opacity(0.28)
        case 2: Color.green.opacity(0.48)
        case 3: Color.green.opacity(0.7)
        case 4: Color.green.opacity(0.95)
        default: Color.primary.opacity(0.07)
        }
    }
}

struct TokenDayDetailOverlay: View {
    let selection: TokenDayDetailSelection

    private let width: CGFloat = 248
    private let height: CGFloat = 222

    var body: some View {
        GeometryReader { geometry in
            let anchor = geometry[self.selection.anchor]
            let bounds = CGRect(origin: .zero, size: geometry.size)
            let viewport = self.selection.viewport.map { geometry[$0] } ?? bounds
            let preferredY = anchor.minY >= self.height + 14
                ? anchor.minY - self.height / 2 - 8
                : anchor.maxY + self.height / 2 + 8

            if anchor.intersects(viewport.intersection(bounds)) {
                TokenDayDetailCard(selection: self.selection)
                    .frame(width: self.width, height: self.height)
                    .position(
                        x: min(max(anchor.midX, self.width / 2 + 12), geometry.size.width - self.width / 2 - 12),
                        y: min(max(preferredY, self.height / 2 + 12), geometry.size.height - self.height / 2 - 12))
                    // A hover card must not steal the pointer from its day.
                    .allowsHitTesting(self.selection.isPinned)
            }
        }
    }
}

private struct TokenDayDetailCard: View {
    let selection: TokenDayDetailSelection

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .top, spacing: 6) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(self.selection.point.date.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day().year()))
                        .font(.system(size: 12, weight: .semibold))
                    Text(Calendar.autoupdatingCurrent.isDateInToday(self.selection.point.date) ? "Today · so far" : "Daily token usage")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if self.selection.isPinned {
                    Button(action: self.selection.dismiss) {
                        Image(systemName: "xmark")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.secondary)
                            .frame(width: 20, height: 20)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut(.cancelAction)
                    .accessibilityLabel("Close day details")
                }
            }

            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(TokenCountFormatter.full(self.selection.point.usage.totalTokens))
                    .font(.system(size: 21, weight: .semibold).monospacedDigit())
                    .minimumScaleFactor(0.65)
                    .lineLimit(1)
                Text("tokens")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }

            Divider()

            VStack(spacing: 5) {
                self.metric("Input", value: self.selection.point.usage.inputTokens)
                self.metric("Cached input", value: self.selection.point.usage.cachedInputTokens, isSubset: true)
                self.metric("Output", value: self.selection.point.usage.outputTokens)
                self.metric("Reasoning", value: self.selection.point.usage.reasoningOutputTokens, isSubset: true)
            }

            Text("Cached input and reasoning are included above.")
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(13)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(NSColor.windowBackgroundColor))
        }
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color.primary.opacity(0.14), lineWidth: 1)
        }
        .shadow(color: .black.opacity(0.18), radius: 14, y: 5)
        .onExitCommand(perform: self.selection.dismiss)
    }

    private func metric(_ title: String, value: Int64, isSubset: Bool = false) -> some View {
        HStack {
            Text(isSubset ? "↳ \(title)" : title)
                .foregroundStyle(.secondary)
            Spacer()
            Text(TokenCountFormatter.full(value))
                .fontWeight(isSubset ? .regular : .medium)
                .monospacedDigit()
        }
        .font(.system(size: 11))
    }
}
