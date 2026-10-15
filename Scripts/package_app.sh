#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FINAL_APP_DIR="$ROOT_DIR/Build/CodexControl.app"
BUILD_STAGING="$(mktemp -d)"
trap 'rm -rf "$BUILD_STAGING"' EXIT
APP_DIR="$BUILD_STAGING/CodexControl.app"
WIDGET_DIR="$APP_DIR/Contents/PlugIns/CodexControlWidget.appex"
SIGNING_IDENTITY="${CODE_SIGN_IDENTITY:--}"
typeset -a SWIFT_FLAGS BUILD_FLAGS SIGN_FLAGS
SWIFT_FLAGS=(-file-prefix-map "$ROOT_DIR=/CodexControl" -debug-prefix-map "$ROOT_DIR=/CodexControl")
if [[ -n "${TOOLCHAIN_VFS_OVERLAY:-}" ]]; then
  SWIFT_FLAGS+=(-vfsoverlay "$TOOLCHAIN_VFS_OVERLAY")
fi
if [[ -n "${TOOLCHAIN_MODULE_CACHE:-}" ]]; then
  SWIFT_FLAGS+=(-module-cache-path "$TOOLCHAIN_MODULE_CACHE")
fi
BUILD_FLAGS=(-c release --jobs 1 --scratch-path "$ROOT_DIR/.build-release")
for flag in "${SWIFT_FLAGS[@]}"; do
  BUILD_FLAGS+=(-Xswiftc "$flag")
done

cd "$ROOT_DIR"
swift build "${BUILD_FLAGS[@]}"
BIN_DIR="$(swift build "${BUILD_FLAGS[@]}" --show-bin-path)"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$WIDGET_DIR/Contents/MacOS"
cp "$BIN_DIR/CodexControl" "$APP_DIR/Contents/MacOS/CodexControl"
cp "$ROOT_DIR/Support/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$ROOT_DIR/Support/CodexControl.icns" "$APP_DIR/Contents/Resources/CodexControl.icns"
cp "$ROOT_DIR/LICENSE" "$APP_DIR/Contents/Resources/LICENSE.txt"
cp "$ROOT_DIR/NOTICE" "$APP_DIR/Contents/Resources/NOTICE.txt"
cp "$ROOT_DIR/Support/WidgetInfo.plist" "$WIDGET_DIR/Contents/Info.plist"

SDK_PATH="$(xcrun --sdk macosx --show-sdk-path)"
xcrun --sdk macosx swiftc -parse-as-library -application-extension -O \
  -sdk "$SDK_PATH" -target "$(uname -m)-apple-macos14.0" \
  -module-name CodexControlWidget "${SWIFT_FLAGS[@]}" \
  "$ROOT_DIR/Sources/CodexControlWidget/CodexControlWidget.swift" \
  -framework Foundation -framework SwiftUI -framework WidgetKit \
  -Xlinker -e -Xlinker _NSExtensionMain \
  -o "$WIDGET_DIR/Contents/MacOS/CodexControlWidget"

# Remove debug records and filesystem metadata before signing the distributable.
xcrun strip -S "$APP_DIR/Contents/MacOS/CodexControl" "$WIDGET_DIR/Contents/MacOS/CodexControlWidget"
xattr -cr "$APP_DIR"
SIGN_FLAGS=(--force --sign "$SIGNING_IDENTITY")
if [[ "$SIGNING_IDENTITY" != "-" ]]; then
  SIGN_FLAGS+=(--options runtime --timestamp)
fi
codesign "${SIGN_FLAGS[@]}" --entitlements "$ROOT_DIR/Support/Widget.entitlements" "$WIDGET_DIR"
codesign "${SIGN_FLAGS[@]}" "$APP_DIR"
codesign --verify --deep --strict "$APP_DIR"
mkdir -p "$ROOT_DIR/Build"
rm -rf "$FINAL_APP_DIR"
ditto --noextattr --norsrc "$APP_DIR" "$FINAL_APP_DIR"
codesign --verify --deep --strict "$FINAL_APP_DIR"
printf '%s\n' "$FINAL_APP_DIR"
