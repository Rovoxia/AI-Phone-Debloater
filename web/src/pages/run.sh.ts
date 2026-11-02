import type { APIRoute } from 'astro';

export const prerender = true;

const scriptContent = `#!/usr/bin/env bash
# AI-Phone-Debloater Zero-Git Runner for Linux & macOS

set -euo pipefail

ARCHIVE_URL="https://github.com/Rovoxia/AI-Phone-Debloater/archive/refs/heads/main.zip"
SUBFOLDER="cli"
INSTALL_DIR="$HOME/.ai-phone-debloater"

echo "========================================================"
echo "  AI-Phone-Debloater Zero-Git Runner (Linux/macOS)"
echo "========================================================"

for cmd in curl; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "[ERROR] Required tool '$cmd' is not installed." >&2
        exit 1
    fi
done

TEMP_DIR="\$(mktemp -d)"
ZIP_FILE="\${TEMP_DIR}/repo.zip"

cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

echo "[INFO] Fetching latest repository files..."
curl -sSL "$ARCHIVE_URL" -o "$ZIP_FILE"

echo "[INFO] Extracting archive..."
if command -v unzip &> /dev/null; then
    unzip -q "$ZIP_FILE" -d "$TEMP_DIR"
else
    python3 -c "import zipfile; zipfile.ZipFile('$ZIP_FILE').extractall('$TEMP_DIR')"
fi

EXTRACTED_ROOT=\$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)
SOURCE_SUBFOLDER="\${EXTRACTED_ROOT}/\${SUBFOLDER}"

if [ ! -d "$SOURCE_SUBFOLDER" ]; then
    echo "[ERROR] Subfolder '$SUBFOLDER' not found in repository archive." >&2
    exit 1
fi

INSTALLED_VERSION_FILE="$INSTALL_DIR/VERSION"
INSTALLED_VERSION=""
if [ -f "$INSTALLED_VERSION_FILE" ]; then
    INSTALLED_VERSION=\$(tr -d '\r\n' < "$INSTALLED_VERSION_FILE")
fi

NEW_VERSION_FILE="\${EXTRACTED_ROOT}/VERSION"
NEW_VERSION="1.0.0"
if [ -f "$NEW_VERSION_FILE" ]; then
    NEW_VERSION=\$(tr -d '\r\n' < "$NEW_VERSION_FILE")
fi

echo "[INFO] Syncing CLI to \${INSTALL_DIR} (Version: \${NEW_VERSION})..."

# Ensure permanent external backups directory exists safely in User's home
SAFE_BACKUPS_DIR="\$HOME/AiPhoneDebloater/backups"
mkdir -p "\$SAFE_BACKUPS_DIR"

# Migrate any legacy backups from install dir or accidental cli folder into safe external home folder
for ld in "\$INSTALL_DIR/backups" "\$HOME/cli/backups"; do
    if [ -d "\$ld" ]; then
        cp -R "\$ld"/* "\$SAFE_BACKUPS_DIR/" 2>/dev/null || true
        rm -rf "\$ld" 2>/dev/null || true
    fi
done

# If version changed, purge old tools so fresh ADB binaries are downloaded
if [ "$INSTALLED_VERSION" != "$NEW_VERSION" ]; then
    if [ -n "$INSTALLED_VERSION" ]; then
        echo "[INFO] Version update detected (\${INSTALLED_VERSION} -> \${NEW_VERSION}). Refreshing binaries and ADB tools..."
    fi
    rm -rf "$INSTALL_DIR/tools" 2>/dev/null || true
fi

mkdir -p "$INSTALL_DIR"
# Clean existing install directory completely (backups live safely outside in ~/AiPhoneDebloater/backups)
rm -rf "\${INSTALL_DIR:?}"/*

# Copy updated CLI files
cp -R "\${SOURCE_SUBFOLDER}/"* "$INSTALL_DIR/"

# Copy VERSION file
if [ -f "$NEW_VERSION_FILE" ]; then
    cp "$NEW_VERSION_FILE" "$INSTALL_DIR/"
fi

LAUNCHER="$INSTALL_DIR/bin/debloat.sh"
if [ ! -f "$LAUNCHER" ]; then
    LAUNCHER="$INSTALL_DIR/debloat.sh"
fi

if [ -f "$LAUNCHER" ]; then
    echo "[INFO] Launching debloater interactive engine..."
    exec bash "$LAUNCHER"
else
    echo "[ERROR] Launcher script not found at bin/debloat.sh or root." >&2
    exit 1
fi
`;

export const GET: APIRoute = async () => {
  return new Response(scriptContent.trim(), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-cache, no-store, must-revalidate'
    }
  });
};
