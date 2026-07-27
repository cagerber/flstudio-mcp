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
