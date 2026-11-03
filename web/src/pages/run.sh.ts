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

# Bootstrap Python 3 if missing (required to run the debloat engine)
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    echo "[INFO] Python 3 not found. Installing Python via system package manager..."
    OS="$(uname -s)"
    case "$OS" in
        Linux)
            if command -v apt-get >/dev/null 2>&1; then
                sudo apt-get update -qq && sudo apt-get install -y -qq python3
            elif command -v apk >/dev/null 2>&1; then
                sudo apk add python3
            elif command -v pacman >/dev/null 2>&1; then
                sudo pacman -Sy --noconfirm python
            elif command -v dnf >/dev/null 2>&1; then
                sudo dnf install -y python3
            elif command -v yum >/dev/null 2>&1; then
                sudo yum install -y python3
            else
                echo "[ERROR] No supported package manager found. Install Python 3 manually from https://www.python.org/." >&2
                exit 1
            fi
            ;;
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                brew install python
            else
                echo "[ERROR] Homebrew not found. Install Python 3 from https://www.python.org/." >&2
                exit 1
            fi
            ;;
        *)
            echo "[ERROR] Unsupported OS: $OS. Install Python 3 manually from https://www.python.org/." >&2
            exit 1
            ;;
    esac
fi

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

# If version changed, purge old tools so fresh ADB binaries are downloaded
if [ "$INSTALLED_VERSION" != "$NEW_VERSION" ]; then
    if [ -n "$INSTALLED_VERSION" ]; then
        echo "[INFO] Version update detected (\${INSTALLED_VERSION} -> \${NEW_VERSION}). Refreshing binaries and ADB tools..."
    fi
    rm -rf "$INSTALL_DIR/tools" 2>/dev/null || true
fi

mkdir -p "$INSTALL_DIR"
# Clean existing install directory except tools (tools only purged if version changed)
find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name 'tools' -exec rm -rf {} + 2>/dev/null || true

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
