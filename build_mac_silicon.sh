#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
VERSION="$(tr -d '\n' < "$PROJECT_DIR/VERSION")"
VERSION_UNDERSCORE="${VERSION//./_}"
APP_NAME="Local File Renamer V${VERSION_UNDERSCORE}"
ZIP_NAME="Local_File_Renamer_v${VERSION_UNDERSCORE}_macOS_Apple_Silicon.zip"

LOCAL_PYINSTALLER="$WORKSPACE_DIR/s3_copy_desktop_app/.venv/bin/pyinstaller"
if [[ -x "$LOCAL_PYINSTALLER" ]]; then
  PYINSTALLER_BIN="$LOCAL_PYINSTALLER"
elif command -v pyinstaller >/dev/null 2>&1; then
  PYINSTALLER_BIN="$(command -v pyinstaller)"
else
  echo "PyInstaller not found. Install it with: pip install pyinstaller"
  exit 1
fi

cd "$PROJECT_DIR"

"$PYINSTALLER_BIN" \
  --noconfirm \
  --clean \
  --windowed \
  --target-architecture arm64 \
  --name "$APP_NAME" \
  --icon "$PROJECT_DIR/assets/local_file_renamer.icns" \
  --hidden-import tkinter \
  local_file_renamer_app.py

mkdir -p "$PROJECT_DIR/downloads"
find "$PROJECT_DIR/dist/$APP_NAME.app" -name '._*' -type f -delete
COPYFILE_DISABLE=1 ditto -c -k --norsrc --noextattr --keepParent "$PROJECT_DIR/dist/$APP_NAME.app" "$PROJECT_DIR/downloads/$ZIP_NAME"

echo "Build complete: $PROJECT_DIR/dist/$APP_NAME.app"
echo "Package complete: $PROJECT_DIR/downloads/$ZIP_NAME"
echo "Architecture: $(uname -m)"
