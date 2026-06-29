#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(tr -d '\n' < "$PROJECT_DIR/VERSION")"
VERSION_UNDERSCORE="${VERSION//./_}"
APP_NAME="Local File Renamer V${VERSION_UNDERSCORE}"
ZIP_NAME="Local_File_Renamer_v${VERSION_UNDERSCORE}_macOS_Apple_Silicon.zip"
APP_PATH="$PROJECT_DIR/dist/$APP_NAME.app"
ZIP_PATH="$PROJECT_DIR/downloads/$ZIP_NAME"

if [[ -z "${CODESIGN_IDENTITY:-}" ]]; then
  echo "Set CODESIGN_IDENTITY to your Developer ID Application certificate name."
  exit 1
fi

if [[ -z "${NOTARY_PROFILE:-}" ]]; then
  echo "Set NOTARY_PROFILE to an xcrun notarytool keychain profile."
  echo "Create one with: xcrun notarytool store-credentials"
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "App not found: $APP_PATH"
  echo "Run ./build_mac_silicon.sh first."
  exit 1
fi

codesign --force --deep --options runtime --timestamp --sign "$CODESIGN_IDENTITY" "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

mkdir -p "$PROJECT_DIR/downloads"
find "$APP_PATH" -name '._*' -type f -delete
COPYFILE_DISABLE=1 ditto -c -k --norsrc --noextattr --keepParent "$APP_PATH" "$ZIP_PATH"

xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$APP_PATH"

COPYFILE_DISABLE=1 ditto -c -k --norsrc --noextattr --keepParent "$APP_PATH" "$ZIP_PATH"

echo "Notarized package complete: $ZIP_PATH"
