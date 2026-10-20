#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_NAME="OpenGo.app"
APP_DIR="$DIR/$APP_NAME"

echo "📦 Packaging $APP_NAME..."

# Remove old build if exists
rm -rf "$APP_DIR"

# Create directories
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Copy Icon
if [ -f "$DIR/AppIcon.icns" ]; then
    cp "$DIR/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
fi

# Copy App Files
cp "$DIR/app.py" "$APP_DIR/Contents/Resources/app.py"
cp "$DIR/index.html" "$APP_DIR/Contents/Resources/index.html"

# Write Info.plist
cat << 'EOF' > "$APP_DIR/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>OpenGo</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.azhaan.opengo</string>
    <key>CFBundleName</key>
    <string>OpenGo</string>
    <key>CFBundleDisplayName</key>
    <string>OpenGo</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsArbitraryLoads</key>
        <true/>
    </dict>
</dict>
</plist>
EOF

# Write Executable Launcher
cat << 'EOF' > "$APP_DIR/Contents/MacOS/OpenGo"
#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RESOURCES_DIR="$(dirname "$DIR")/Resources"
LOG_FILE="$HOME/Library/Logs/OpenGo.log"

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

cd "$RESOURCES_DIR"

echo "=== OpenGo launched at $(date) ===" >> "$LOG_FILE"

# Find python interpreter with pywebview & devicectl support
PYTHON_BIN=""
CANDIDATES=(
    "$DIR/../../.venv/bin/python3"
    "$HOME/Downloads/RE-AnyiGo/.venv/bin/python3"
    "$(which python3 2>/dev/null)"
)

for p in "${CANDIDATES[@]}"; do
    if [ -x "$p" ]; then
        PYTHON_BIN="$p"
        break
    fi
done

if [ -n "$PYTHON_BIN" ]; then
    exec "$PYTHON_BIN" "$RESOURCES_DIR/app.py" "$@" >> "$LOG_FILE" 2>&1
else
    exec python3 "$RESOURCES_DIR/app.py" "$@" >> "$LOG_FILE" 2>&1
fi
EOF

chmod +x "$APP_DIR/Contents/MacOS/OpenGo"

# Ad-hoc sign app bundle for macOS Gatekeeper
codesign --force --deep --sign - "$APP_DIR" 2>/dev/null || true

echo "✓ Created $APP_DIR"

# Install into /Applications if writable, otherwise ~/Applications
TARGET_APP="/Applications/$APP_NAME"
if [ -w "/Applications" ]; then
    rm -rf "$TARGET_APP"
    cp -R "$APP_DIR" "/Applications/"
    echo "✓ Installed to /Applications/$APP_NAME"
    INSTALLED_PATH="/Applications/$APP_NAME"
else
    mkdir -p "$HOME/Applications"
    rm -rf "$HOME/Applications/$APP_NAME"
    cp -R "$APP_DIR" "$HOME/Applications/"
    echo "✓ Installed to $HOME/Applications/$APP_NAME"
    INSTALLED_PATH="$HOME/Applications/$APP_NAME"
fi

# Register with macOS LaunchServices so Spotlight immediately indexes it
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -f "$LSREGISTER" ]; then
    "$LSREGISTER" -f "$INSTALLED_PATH" 2>/dev/null || true
fi
touch "$INSTALLED_PATH"

echo "🎉 Done! You can now search for 'OpenGo' in Spotlight (Cmd + Space) or launch it from Applications."
