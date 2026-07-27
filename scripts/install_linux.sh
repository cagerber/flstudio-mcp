#!/usr/bin/env bash
# ============================================================================
#  flstudio-mcp -- Linux/Wine installer
#    [1] controller script  -> FL Settings\Hardware\FLStudioMCP\
#    [2] MCP server          -> pip install -e .
#    [3] note-bridge script  -> seeds MCP_Apply.pyscript in Piano roll scripts\
#    [4] snd-virmidi check
#    [5] xdotool check
#
#  Assumes the standard FL user-data location under Wine:
#    $WINEPREFIX/drive_c/users/$USER/Documents/Image-Line/FL Studio/Settings
#
#  Set WINEPREFIX if FL uses a non-default prefix (default: ~/.fl_studio_wine).
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
WINEPREFIX="${WINEPREFIX:-$HOME/.fl_studio_wine}"
WINE_USER="${USER:-anton}"
FL_SETTINGS="$WINEPREFIX/drive_c/users/$WINE_USER/Documents/Image-Line/FL Studio/Settings"
HW_TARGET="$FL_SETTINGS/Hardware/FLStudioMCP"

echo ""
echo "=== flstudio-mcp Linux/Wine installer ==="
echo "    WINEPREFIX: $WINEPREFIX"
echo "    FL settings: $FL_SETTINGS"
echo ""

# ---- [1] Controller script ------------------------------------------------
echo "[1/5] Installing FL Studio controller script..."

if [ ! -d "$FL_SETTINGS/Hardware" ]; then
    echo "  FL Studio Settings/Hardware folder not found at:"
    echo "    $FL_SETTINGS/Hardware"
    echo "  Creating it now. If this is wrong, run FL Studio once to generate"
    echo "  the correct path, then re-run this script."
    mkdir -p "$HW_TARGET"
fi

mkdir -p "$HW_TARGET"
cp "$REPO_ROOT/fl_controller/FLStudioMCP/device_FLStudioMCP.py" "$HW_TARGET/"
echo "  Installed to $HW_TARGET"

# ---- [2] MCP server -------------------------------------------------------
echo ""
echo "[2/5] Installing the MCP server (editable)..."
cd "$REPO_ROOT"
pip install -e . 2>&1 | tail -3
echo "  Done."

# ---- [3] Note-bridge pyscript ---------------------------------------------
echo ""
echo "[3/5] Seeding the note-bridge pyscript (MCP_Apply)..."
python3 -c "
import os, fl_studio_mcp.pyscript_gen as g
os.makedirs(g.PIANO_ROLL_SCRIPTS_DIR, exist_ok=True)
print('   seeded ' + g.write_apply_script([], mode='append'))
" 2>/dev/null || echo "  Note: could not pre-seed MCP_Apply (non-fatal). The daemon writes it on first note-write."

# ---- [4] Virtual MIDI ports -----------------------------------------------
echo ""
echo "[4/5] Checking virtual MIDI ports..."

# Check if snd-virmidi module is loaded
if lsmod 2>/dev/null | grep -q snd_virmidi; then
    echo "  snd-virmidi already loaded."
elif [ -r /proc/modules ]; then
    echo "  snd-virmidi not loaded. Attempting to load..."
    if sudo modprobe snd-virmidi 2>/dev/null; then
        echo "  snd-virmidi loaded successfully."
    else
        echo "  WARNING: Could not load snd-virmidi. Run:"
        echo "    sudo modprobe snd-virmidi"
        echo "  Then create virtual MIDI ports or set FLSTUDIO_MCP_PORT_TO_FL /"
        echo "  FLSTUDIO_MCP_PORT_FROM_FL env vars to point at existing ALSA MIDI ports."
    fi
fi

# List available MIDI ports for reference
python3 -c "
import mido
print('  Available MIDI outputs:', mido.get_output_names())
print('  Available MIDI inputs: ', mido.get_input_names())
" 2>/dev/null || echo "  (could not list MIDI ports — mido not installed yet)"

# ---- [4b] Daemon launch wrapper --------------------------------------------
echo ""
echo "Writing daemon launch wrapper (pins the MIDI port names)..."
WRAPPER="$SCRIPT_DIR/run_daemon_linux.sh"
cat > "$WRAPPER" <<'WRAPPER_EOF'
#!/usr/bin/env bash
# Launches fl-studio-mcp-daemon with the MIDI port names confirmed to work
# under Wine. Wine assigns a *new* numbered ALSA client (e.g. "WINE ALSA
# Output #6", "#7", "#3", ...) to every enabled MIDI device, so the generic
# substring patterns "WINE ALSA Output"/"WINE ALSA Input" are ambiguous and
# can bind to the wrong one. "Midi Through Port-0" is a stable ALSA client
# name -- use it as the FLStudioMCP controller port in FL's MIDI Settings
# (Input + Output, same Port number, Controller type = FLStudioMCP) and pin
# the daemon to it here.
export FLSTUDIO_MCP_PORT_TO_FL="${FLSTUDIO_MCP_PORT_TO_FL:-Midi Through Port-0}"
export FLSTUDIO_MCP_PORT_FROM_FL="${FLSTUDIO_MCP_PORT_FROM_FL:-Midi Through Port-0}"
exec fl-studio-mcp-daemon "$@"
WRAPPER_EOF
chmod +x "$WRAPPER"
echo "  Wrote $WRAPPER"

# ---- [5] xdotool ----------------------------------------------------------
echo ""
echo "[5/5] Checking xdotool (needed for piano-roll note trigger)..."
if command -v xdotool &>/dev/null; then
    echo "  xdotool found."
else
    echo "  xdotool NOT found. Install it for auto-focus of FL Studio:"
    echo "    sudo apt install xdotool"
    echo "  Without it, you'll need to manually click FL's Piano Roll and press"
    echo "  Ctrl+Alt+Y to apply notes."
fi

# ---- Done -----------------------------------------------------------------
echo ""
echo "============================================================================"
echo " Done. Next steps (see README for detail):"
echo "============================================================================"
echo "  1. FL Studio > Options > MIDI Settings (F10):"
echo "     Input  > Midi Through Port-0: Enable, Controller type = FLStudioMCP, Port = 1"
echo "     Output > Midi Through Port-0: Enable, Port = 1 (SAME number)"
echo "     View > Script output should show [FLStudioMCP] Ready"
echo "     (A dedicated VirMIDI port works too, but Wine renumbers its ALSA"
echo "      client per-device, which made the generic 'WINE ALSA Output/Input'"
echo "      patterns pick the wrong port. 'Midi Through Port-0' is stable.)"
echo ""
echo "  2. Start the bridge daemon (pins the port names above) and keep it running:"
echo "     $WRAPPER"
echo ""
echo "  3. Register with your MCP client:"
echo "     {\"fl-studio\": {\"command\": \"fl-studio-mcp\", \"env\": {\"FLSTUDIO_MCP_TRANSPORT\": \"tcp\"}}}"
echo ""
echo "  4. Each session: open the Piano roll, from Scripting menu run \"MCP_Apply\""
echo "     once (this arms note-writing). Then call fl_ping to verify."
echo ""
echo "  Optional audio features:"
echo "    pip install -e \".[audio]\"           (tempo/key + melody)"
echo "    pip install -e \".[audio,audio-accurate]\"  (+ CREPE pitch tracking)"
echo ""
