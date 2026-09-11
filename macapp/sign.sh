#!/bin/bash
# Sign, notarize, and staple TVCast.app for distribution outside the App Store.
#
# Prereqs (one-time):
#   1. A "Developer ID Application" certificate in your login keychain.
#      Check with:  security find-identity -v -p codesigning
#   2. A stored notarization profile:
#      xcrun notarytool store-credentials tvcast-notary \
#        --apple-id you@example.com --team-id TEAMID --password APP_SPECIFIC_PASSWORD
#
# Usage:
#   ./make-app.sh release
#   IDENTITY="Developer ID Application: Your Name (TEAMID)" NOTARY_PROFILE=tvcast-notary ./sign.sh
set -euo pipefail
cd "$(dirname "$0")"
APP="TVCast.app"
: "${IDENTITY:?set IDENTITY to your 'Developer ID Application: ...' identity}"

echo "→ signing $APP with hardened runtime"
codesign --force --deep --options runtime --timestamp \
  --sign "$IDENTITY" "$APP"
codesign --verify --strict --verbose=2 "$APP"
echo "→ signature OK"

if [ -n "${NOTARY_PROFILE:-}" ]; then
  ZIP="TVCast.zip"
  rm -f "$ZIP"
  ditto -c -k --keepParent "$APP" "$ZIP"
  echo "→ submitting to Apple notary service (this can take a few minutes)…"
  xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
  echo "→ stapling the notarization ticket"
  xcrun stapler staple "$APP"
  xcrun stapler validate "$APP"
  rm -f "$ZIP"
  echo "→ notarized and stapled. $APP will open cleanly on any Mac."
else
  echo "→ signed only (no NOTARY_PROFILE set). Good for this Mac; set NOTARY_PROFILE to"
  echo "  notarize for other Macs."
fi
