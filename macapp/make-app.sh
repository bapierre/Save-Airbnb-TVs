#!/bin/bash
# Assemble TVCast.app from the built products. ffmpeg is located on the system at runtime
# for now; bundling a static ffmpeg into Resources/ is a remaining step for distribution.
set -euo pipefail
cd "$(dirname "$0")"
CONF="${1:-release}"
swift build -c "$CONF" --product TVCastApp
swift build -c "$CONF" --product sckcap
BIN=".build/$CONF"
APP="TVCast.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN/TVCastApp" "$APP/Contents/MacOS/TVCast"
cp "$BIN/sckcap" "$APP/Contents/Resources/sckcap"
# Bundle ffmpeg if a copy is provided (STATIC recommended); else the app uses system ffmpeg.
if [ -n "${FFMPEG:-}" ] && [ -x "${FFMPEG:-}" ]; then
  cp "$FFMPEG" "$APP/Contents/Resources/ffmpeg"
fi
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>TVCast</string>
  <key>CFBundleDisplayName</key><string>TVCast</string>
  <key>CFBundleIdentifier</key><string>com.saveairbnbtvs.tvcast</string>
  <key>CFBundleExecutable</key><string>TVCast</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSScreenCaptureUsageDescription</key>
  <string>TVCast captures your screen and system audio to stream them to your TV.</string>
</dict>
</plist>
PLIST
echo "built $APP"
