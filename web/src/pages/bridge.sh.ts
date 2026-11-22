import type { APIRoute } from 'astro';

export const prerender = true;

const scriptContent = `#!/usr/bin/env bash
# AI-Phone-Debloater WebApp Local ADB Bridge (Linux / macOS)

set -euo pipefail

ARCHIVE_URL="https://github.com/Rovoxia/AI-Phone-Debloater/archive/refs/heads/main.zip"
SUBFOLDER="cli"
INSTALL_DIR="\${HOME}/.ai-phone-debloater"
PORT="\${BRIDGE_PORT:-53123}"
APP_URL="https://debloater.rovoxia.com/app?bridge=1"

echo "========================================================"
echo "  AI-Phone-Debloater WebApp Local ADB Bridge (Linux/macOS)"
echo "========================================================"

# --- Helper: sync repo zip ---
sync_repo() {
    local tmpdir zipfile extracted_root source_subfolder new_versionfile installed_version

    tmpdir="\$(mktemp -d)"
    zipfile="\${tmpdir}/repo.zip"
    # tmpdir is local to this function, so it is expanded now, not when the trap runs.
    # shellcheck disable=SC2064
    trap "rm -rf \\"\${tmpdir}\\"" EXIT

    echo "[INFO] Fetching latest repository files..."
    curl -fsSL "\${ARCHIVE_URL}" -o "\${zipfile}"

    echo "[INFO] Extracting archive..."
    if command -v unzip &>/dev/null; then
        unzip -q "\${zipfile}" -d "\${tmpdir}"
    elif command -v python3 &>/dev/null; then
        python3 -c "import zipfile; zipfile.ZipFile('\${zipfile}').extractall('\${tmpdir}')"
    else
        echo "[ERROR] Cannot extract the download: neither 'unzip' nor 'python3' is installed. Install unzip and run this command again." >&2
        exit 1
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
        installed_version="\$(tr -d '\\r\\n' < "\${installed_version_file}")"
    fi

    new_versionfile="\${extracted_root}/VERSION"
    new_version=""
    if [ -f "\${new_versionfile}" ]; then
        new_version="\$(tr -d '\\r\\n' < "\${new_versionfile}")"
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

# --- Helpers / prerequisites ---
if ! command -v curl >/dev/null 2>&1; then
    echo "[ERROR] Required tool 'curl' is not installed." >&2
    exit 1
fi

# No python3 check here: the launcher (bin/debloat.sh) finds or installs Python itself.

# Per-session token: the bridge refuses device calls without it. It reaches the web app
# in the URL fragment, which a browser never sends to any server.
TOKEN="\$(od -An -N16 -tx1 /dev/urandom | tr -d ' \\n')"
if [ "\${#TOKEN}" -ne 32 ]; then
    echo "[ERROR] Could not generate a session token from /dev/urandom." >&2
    exit 1
fi
APP_URL="\${APP_URL}#token=\${TOKEN}"

# Open default browser to the app with bridge=1 query param
open_browser() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "\${APP_URL}" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
        open "\${APP_URL}" >/dev/null 2>&1 || true
    elif command -v start >/dev/null 2>&1; then
        start "" "\${APP_URL}" >/dev/null 2>&1 || true
    else
        echo "[WARN] No browser opener found. Open this URL yourself: \${APP_URL}" >&2
    fi
}

# --- Main ---
sync_repo
open_browser

echo "[INFO] Starting bridge server on http://127.0.0.1:\${PORT}"
echo "[INFO] Press Ctrl+C in this terminal to stop the bridge when done."
# The token is set for the bridge process only, not exported to the browser opened above.
AIPD_BRIDGE_TOKEN="\${TOKEN}" bash "\${INSTALL_DIR}/bin/debloat.sh" --bridge --port "\${PORT}"
`;

export const GET: APIRoute = async () => {
  return new Response(scriptContent.trim(), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-cache, no-store, must-revalidate'
    }
  });
};
