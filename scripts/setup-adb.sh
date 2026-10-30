#!/usr/bin/env bash
# setup-adb.sh
# Detects/installs ADB on macOS and Linux and verifies an authorized device connection.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"
PLATFORM_TOOLS_DIR="$TOOLS_DIR/platform-tools"
ADB="$PLATFORM_TOOLS_DIR/adb"

OS="$(uname -s)"

have_adb=0
if command -v adb >/dev/null 2>&1; then
    echo "ADB found in PATH: $(command -v adb)"
    have_adb=1
fi

install_via_package_manager() {
    case "$OS" in
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                echo "Installing android-platform-tools via Homebrew..."
                brew install android-platform-tools
                return $?
            else
                echo "Homebrew not found. Install from https://brew.sh" >&2
                return 1
            fi
            ;;
        Linux)
            if [ -f /etc/os-release ]; then
                # shellcheck disable=SC1091
                . /etc/os-release
            fi
            case "${ID:-}" in
                ubuntu|debian)
                    echo "Installing adb via apt..."
                    sudo apt-get update && sudo apt-get install -y android-tools-adb
                    return $?
                    ;;
                fedora)
                    echo "Installing adb via dnf..."
                    sudo dnf install -y android-tools
                    return $?
                    ;;
                arch|manjaro)
                    echo "Installing adb via pacman..."
                    sudo pacman -S --noconfirm android-tools
                    return $?
                    ;;
                *)
                    echo "Unknown Linux distro: ${ID:-unknown}" >&2
                    return 1
                    ;;
            esac
            ;;
        *)
            echo "Unsupported OS: $OS" >&2
            return 1
            ;;
    esac
}

download_platform_tools() {
    mkdir -p "$TOOLS_DIR"
    case "$OS" in
        Darwin)
            URL="https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
            ARCHIVE="$TOOLS_DIR/platform-tools-latest-darwin.zip"
            ;;
        Linux)
            URL="https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
            ARCHIVE="$TOOLS_DIR/platform-tools-latest-linux.zip"
            ;;
        *)
            echo "Unsupported OS for download: $OS" >&2
            return 1
            ;;
    esac

    echo "Downloading $URL ..."
    if command -v curl >/dev/null 2>&1; then
        curl -L --fail -o "$ARCHIVE" "$URL"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$ARCHIVE" "$URL"
    else
        echo "Neither curl nor wget is available." >&2
        return 1
    fi || return 1

    echo "Extracting to $PLATFORM_TOOLS_DIR ..."
    mkdir -p "$PLATFORM_TOOLS_DIR"
    if command -v unzip >/dev/null 2>&1; then
        unzip -o "$ARCHIVE" -d "$PLATFORM_TOOLS_DIR" >/dev/null
    else
        echo "unzip is not available." >&2
        return 1
    fi

    # The zip extracts into a nested platform-tools folder; flatten it.
    INNER="$PLATFORM_TOOLS_DIR/platform-tools"
    if [ -d "$INNER" ]; then
        mv "$INNER"/* "$PLATFORM_TOOLS_DIR/"
        rmdir "$INNER" 2>/dev/null || true
    fi

    rm -f "$ARCHIVE"
    chmod +x "$PLATFORM_TOOLS_DIR/adb" 2>/dev/null || true
    return 0
}

if [ "$have_adb" -eq 0 ]; then
    echo "ADB not found in PATH."
    echo "Trying to install via system package manager..."
    if install_via_package_manager; then
        echo "ADB installed via package manager."
    else
        echo "Package manager install failed or unavailable."
        read -p "Download official Google platform-tools and install to ./tools/platform-tools? [Y/n] " ans || true
        ans="${ans:-Y}"
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            if ! download_platform_tools; then
                echo "Failed to download/install platform-tools." >&2
                exit 1
            fi
        else
            echo "Aborted. Install ADB manually and re-run this script." >&2
            exit 1
        fi
    fi
fi

# Locate adb.
if command -v adb >/dev/null 2>&1; then
    ADB_BIN="$(command -v adb)"
elif [ -x "$ADB" ]; then
    ADB_BIN="$ADB"
    export PATH="$PLATFORM_TOOLS_DIR:$PATH"
else
    echo "ADB executable not found." >&2
    exit 1
fi

echo "ADB: $ADB_BIN"

# Test connection.
echo "Starting adb server..."
"$ADB_BIN" start-server >/dev/null 2>&1
sleep 2

echo "Running adb devices..."
"$ADB_BIN" devices

if "$ADB_BIN" devices | grep -q '\tunauthorized'; then
    echo
    echo "A device is listed as 'unauthorized'."
    echo "On your phone screen, accept the RSA authorization prompt to allow USB debugging."
elif "$ADB_BIN" devices | grep -q '\toffline'; then
    echo
    echo "A device is listed as 'offline'."
    echo "Check the USB cable and try again."
elif "$ADB_BIN" devices | grep -q '\tdevice'; then
    echo "A device is authorized and ready."
else
    echo
    echo "No authorized device found."
    echo "To connect:"
    echo "  1. Enable Developer Options on your phone (tap Build Number 7 times in Settings)."
    echo "  2. Enable USB debugging in Developer Options."
    echo "  3. Connect the phone via USB."
    echo "  4. Accept the 'Allow USB debugging?' RSA prompt on the phone screen."
    echo "  5. Re-run this script."
fi
