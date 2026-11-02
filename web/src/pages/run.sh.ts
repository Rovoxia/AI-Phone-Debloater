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

mkdir -p "$INSTALL_DIR"
rm -rf "\${INSTALL_DIR:?}"/*
cp -R "\${SOURCE_SUBFOLDER}/"* "$INSTALL_DIR/"
if [ -f "\${EXTRACTED_ROOT}/VERSION" ]; then
    cp "\${EXTRACTED_ROOT}/VERSION" "$INSTALL_DIR/"
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
