#!/bin/zsh
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/Build/CodexControl.app"
OUT_DIR="$ROOT_DIR/ReleaseArtifacts"
VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_DIR/Contents/Info.plist")"
ARCH="$(uname -m)"
NAME="CodexControl-$VERSION-macos-$ARCH"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT
mkdir -p "$OUT_DIR" "$STAGING_DIR/dmg"
ditto --noextattr --norsrc "$APP_DIR" "$STAGING_DIR/dmg/CodexControl.app"
codesign --verify --deep --strict "$STAGING_DIR/dmg/CodexControl.app"
ln -s /Applications "$STAGING_DIR/dmg/Applications"
cp "$ROOT_DIR/Support/Install-Readme.txt" "$STAGING_DIR/dmg/Read Me.txt"
cp "$ROOT_DIR/LICENSE" "$STAGING_DIR/dmg/LICENSE.txt"
cp "$ROOT_DIR/NOTICE" "$STAGING_DIR/dmg/NOTICE.txt"
xattr -cr "$STAGING_DIR/dmg"
hdiutil create -volname "CodexControl $VERSION" -srcfolder "$STAGING_DIR/dmg" \
  -format UDZO -fs HFS+ -ov "$OUT_DIR/$NAME.dmg"

# Pin installation to /Applications rather than relocating to a backup copy.
mkdir -p "$STAGING_DIR/payload/Applications"
ditto --noextattr --norsrc "$APP_DIR" "$STAGING_DIR/payload/Applications/CodexControl.app"
xattr -cr "$STAGING_DIR/payload"
pkgbuild --analyze --root "$STAGING_DIR/payload" "$STAGING_DIR/components.plist"
/usr/libexec/PlistBuddy -c 'Set :0:BundleIsRelocatable false' "$STAGING_DIR/components.plist"
pkgbuild --root "$STAGING_DIR/payload" --component-plist "$STAGING_DIR/components.plist" \
  --identifier com.codexcontrol.installer --version "$VERSION" \
  --install-location / --ownership recommended "$OUT_DIR/$NAME.pkg"
(cd "$OUT_DIR" && shasum -a 256 "$NAME.dmg" "$NAME.pkg" > SHA256SUMS.txt)
printf '%s\n' "$OUT_DIR"
