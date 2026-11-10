import type { APIRoute } from 'astro';

export const prerender = true;

const scriptContent = `#!/usr/bin/env bash
# AI-Phone-Debloater WebApp Local ADB Bridge (Linux / macOS)

set -euo pipefail

ARCHIVE_URL="https://github.com/Rovoxia/AI-Phone-Debloater/archive/refs/heads/main.zip"
SUBFOLDER="cli"
INSTALL_DIR="\${HOME}/.ai-phone-debloater"
PORT=53123
if [ -n "\${BRIDGE_PORT}" ]; then PORT="\${BRIDGE_PORT}"; fi
APP_URL="https://debloater.rovoxia.com/app?bridge=1"

echo "========================================================"
echo "  AI-Phone-Debloater WebApp Local ADB Bridge (Linux/macOS)"
echo "========================================================"

# --- Helper: sync repo zip ---
sync_repo() {
    local tmpdir zipfile extracted_root source_subfolder new_versionfile installed_version

    tmpdir="\$(mktemp -d)"
    zipfile="\${tmpdir}/repo.zip"
    trap "rm -rf \"\${tmpdir}\"" EXIT

    echo "[INFO] Fetching latest repository files..."
    curl -sSL "\${ARCHIVE_URL}" -o "\${zipfile}"

    echo "[INFO] Extracting archive..."
    if command -v unzip &>/dev/null; then
        unzip -q "\${zipfile}" -d "\${tmpdir}"
    else
        python3 -c "import zipfile; zipfile.ZipFile('\${zipfile}').extractall('\${tmpdir}')"
    fi

    extracted_root="\$(find "\${tmpdir}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    source_subfolder="\${extracted_root}/\${SUBFOLDER}"

    if [ ! -d "\${source_subfolder}" ]; then
        echo "[ERROR] Subfolder '\${SUBFOLDER}' not found in repository archive." >&2
        exit 1
    fi

    installed_version=""
    installed_version_file="\${INSTALL_DIR}/VERSION"
    if [ -f "\${installed_version_file}" ]; then
        installed_version="\$(tr -d '\r\n' < "\${installed_version_file}")"
    fi

    new_versionfile="\${extracted_root}/VERSION"
    new_version=""
    if [ -f "\${new_versionfile}" ]; then
        new_version="\$(tr -d '\r\n' < "\${new_versionfile}")"
    else
        echo "[ERROR] VERSION file not found in repository archive." >&2
        exit 1
    fi

    version_changed=1
    if [ -n "\${installed_version}" ] && [ "\${installed_version}" = "\${new_version}" ]; then
        version_changed=0
    fi

    echo "[INFO] Syncing CLI to \${INSTALL_DIR} (Version: \${new_version})..."

    if [ "\${version_changed}" -eq 1 ]; then
        if [ -n "\${installed_version}" ]; then
            echo "[INFO] Version update detected (\${installed_version} -> \${new_version}). Refreshing binaries and ADB tools..."
        fi
        rm -rf "\${INSTALL_DIR}/tools" 2>/dev/null || true
    fi

    mkdir -p "\${INSTALL_DIR}"
    # Clean existing install directory except tools (tools only purged if version changed)
    find "\${INSTALL_DIR}" -mindepth 1 -maxdepth 1 ! -name 'tools' -exec rm -rf {} + 2>/dev/null || true

    # Copy updated CLI files
    cp -R "\${source_subfolder}/"* "\${INSTALL_DIR}/"

    # Copy VERSION file
    if [ -f "\${new_versionfile}" ]; then
        cp "\${new_versionfile}" "\${INSTALL_DIR}/"
    fi
}

# --- Helper: launch bridge server ---
launch_bridge() {
    local bridge_server debloat_engine

    bridge_server="\${INSTALL_DIR}/src/bridge_server.py"
    debloat_engine="\${INSTALL_DIR}/debloat_engine.py"

    if [ -f "\${bridge_server}" ]; then
        echo "[INFO] Starting bridge server on port \${PORT} ..."
        python3 "\${bridge_server}" "--port" "\${PORT}"
    else
        echo "[INFO] Starting debloat engine in bridge mode on port \${PORT} ..."
        python3 "\${debloat_engine}" "--bridge" "--port" "\${PORT}"
    fi
}

cleanup() {
    if [ -n "\${tmpdir}" ]; then
        rm -rf "\${tmpdir}"
    fi
}
trap cleanup EXIT

# --- Helpers / prerequisites ---
if ! command -v curl >/dev/null 2>&1; then
    echo "[ERROR] Required tool 'curl' is not installed." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Required tool 'python3' is not installed." >&2
    exit 1
fi

# Open default browser to the app with bridge=1 query param
open_browser() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "\${APP_URL}" >/dev/null 2>&1
    elif command -v open >/dev/null 2>&1; then
        open "\${APP_URL}" >/dev/null 2>&1
    elif command -v start >/dev/null 2>&1; then
        start "" "\${APP_URL}" >/dev/null 2>&1
    else
        echo "[WARN] No browser opener found. Opening manually: \${APP_URL}" >&2
    fi
}

# --- Main ---
sync_repo
mkdir -p "\${INSTALL_DIR}/src"

open_browser
launch_bridge

echo "[INFO] Bridge server active on http://127.0.0.1:\${PORT}"
echo "[INFO] Press Ctrl+C in this terminal to stop the bridge when done."

`;

export const GET: APIRoute = async () => {
  return new Response(scriptContent.trim(), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-cache, no-store, must-revalidate'
    }
  });
};
