# Changelog

## Unreleased -- v0.3 / MCP enhancements (mcp-enhancements branch)

Driven by a cross-reference of the
[MaddyGuthridge/FL-Studio-API-Stubs](https://github.com/MaddyGuthridge/FL-Studio-API-Stubs)
docs against a live `api_probe()` of FL 26.1.2 build 5557. Result: 18 new
commands + 6 honest-API-limit reports + bridge resilience + Linux support.

### New tools

**Project persistence** (4 tools):
  - `fl_get_project_dirty` -- REAL. `general.getChangedFlag()`.
  - `fl_get_project_path` -- returns title via `ui.getProgTitle()` (path not exposed).
  - `fl_save_project` -- honest "FL's scripting API does not expose save()" report.
  - `fl_export_current_project_midi` -- honest "API does not expose note enumeration" report.

**Channel / mixer-track create** (2 tools):
  - `fl_create_channel` / `fl_create_mixer_track` -- honest "add via FL UI" reports.

**Plugin preset write path** (2 tools):
  - `fl_load_plugin_preset(track, slot, name, exact)` -- step through presets until name matches.
  - `fl_load_plugin_preset_by_index(track, slot, index)` -- step to a specific index.

**Automation** (2 tools):
  - `fl_get_automation_info` / `fl_set_automation_point` -- honest "no automation-clip API" reports.

**Live MIDI** (6 tools, stubs-found):
  - `fl_dump_score_log(time, silent)` -- `general.dumpScoreLog`, the live-capture-into-pattern path.
  - `fl_safe_to_edit` -- `general.safeToEdit` guard.
  - `fl_trigger_note(index, note, velocity, channel)` -- `channels.midiNoteOn` (velocity 0 = note-off).
  - `fl_quantize_channel(index, start_only, use_global_index)` -- `channels.quickQuantize`.
  - `fl_get_selected_channel(can_be_none, offset, index_global)` -- `channels.selectedChannel`.
  - `fl_get_channel_midi_in_port(index)` -- `channels.getChannelMidiInPort`.

**Mixer record + FX slot** (8 tools, stubs-found):
  - `fl_mixer_is_track_armed(track)` / `fl_mixer_arm_track(track)` -- record-arm.
  - `fl_mixer_is_track_enabled(track)` -- `mixer.isTrackEnabled`.
  - `fl_mixer_track_count()` -- FL's view of track count.
  - `fl_get_active_effect()` -- focused plugin (track, slot) or None.
  - `fl_focus_plugin_editor(track, slot)` -- opens plugin UI (UI-stealing, warned).
  - `fl_get_slot_color(track, slot)` / `fl_set_slot_color(track, slot, color)` -- FX slot color.

**Pattern extras** (4 tools, stubs-found):
  - `fl_arrange_select_pattern(index, value, preview)` -- multi-select aware.
  - `fl_arrange_is_pattern_selected(index)`.
  - `fl_arrange_is_pattern_default(index)` -- True for untouched patterns.
  - `fl_arrange_burn_loop(channel, store_undo, update_ui)` -- disable step loop.

### Bridge resilience

`FLBridge.call()` now:
  - Auto-retries once on `FLTimeout` with +50% budget (env: `FLSTUDIO_MCP_RETRY_ON_TIMEOUT=1`).
  - Auto-closes + reopens MIDI ports after N consecutive failures (env: `FLSTUDIO_MCP_REOPEN_ON_DEAD=1`, `FLSTUDIO_MCP_REOPEN_AFTER=3`).

Catches the "FL was restarted / controller script was reloaded" case where
the MIDI device list changed under the bridge. TCP transport path is
unaffected (daemon handles its own reconnect).

### Honest-API-limit reports

For `fl_save_project`, `fl_export_current_project_midi`, `fl_create_channel`,
`fl_create_mixer_track`, `fl_get_automation_info`, `fl_set_automation_point`:
the tool returns `ok=False, code='api_unavailable'` with a clear "FL's
scripting API does not expose X on this build" message + the recommended
manual workaround. Verified against FL 26.1.2 build 5557 that
`general.save`, `channels.new`, `mixer.new`, and channel-rack automation
are absent from the controller-script API.

### Linux / Wine support (already on `main`, formalized here)

- `scripts/install_linux.sh` -- Linux/Wine installer (copies controller
  script, installs the Python server, seeds the note-bridge pyscript,
  loads `snd-virmidi`, checks for `xdotool`).
- `scripts/run_daemon_linux.sh` -- pins `FLSTUDIO_MCP_PORT_TO_FL` /
  `FLSTUDIO_MCP_PORT_FROM_FL` to `Midi Through Port-0` to dodge Wine's
  per-device ALSA-client renumbering.
- `protocol.py: ChunkReassembler` + `connection.py` chunked-CC fallback --
  some Wine MIDI drivers drop outbound SysEx from inside Wine; the
  controller now emits every response + heartbeat twice (SysEx + a
  Control-Change stream on channel 15 / ctrl 102-104) and the server
  decodes whichever arrives.
- `pyscript_trigger.py` -- Linux/xdotool path for the piano-roll note
  trigger.

The controller script now sends every outbound frame both as SysEx *and* as
a stream of Control Change messages (one byte per message, on a reserved
channel/controller triple: `CHUNK_CHANNEL=15`, controllers `102/103/104` for
start/data/end). The server's MIDI callback reassembles whichever one
actually arrives (`protocol.ChunkReassembler`). No config changes needed;
this is transparent on Windows/macOS, and unblocks Wine hosts without
requiring a patched Wine build.

## v0.2.0 -- MIDI SysEx transport

**Breaking change**: the transport between the MCP server and the FL
controller script switched from a file-based JSON queue to MIDI SysEx.
Protocol version bumped 1 -> 2. v0.1 clients and v0.2 controllers (or vice
versa) refuse to talk.

### Why

FL Studio's controller-script Python sandbox blocks every form of file
write. Confirmed on FL 24+ with MIDI scripting version 40 / embedded Python
3.12.1:

- `open("...", "w").write("...")` ->
  `SystemError: <class '_io.FileIO'> returned NULL without setting an exception`
- `os.open(..., O_WRONLY|O_CREAT|O_TRUNC)` ->
  `TypeError: bad argument type for built-in operation`
- `os.makedirs(...)` ->
  `mkdir returned NULL without setting an exception`

A normal OS process writing to the same directory succeeds, so it is the
controller-script sandbox specifically, not OS permissions. Piano Roll
`.pyscript`s run in a different sandbox and do allow file I/O, but those
only execute on explicit user trigger -- they're not suitable for the
heartbeat / always-on loop the server depends on.

So all transport moved to MIDI SysEx, which is allowed in controller
scripts via `device.midiOutSysex` (out) and `OnMidiMsg` (in).

### What changed

- `src/fl_studio_mcp/protocol.py`: new SysEx wire format, manufacturer ID
  `0x7D`, magic `"MCP"`, base64-JSON payload. Default port names
  `FLStudioMCP RX` (server -> FL) and `FLStudioMCP TX` (FL -> server).
- `src/fl_studio_mcp/connection.py`: rewritten on `mido` + `python-rtmidi`.
  Background callback dispatches incoming SysEx, blocks the caller on a
  `threading.Event` keyed by request id. Heartbeat detected via incoming
  `DIR_HEARTBEAT` messages from FL.
- `fl_controller/FLStudioMCP/device_FLStudioMCP.py`: rewritten with
  `OnMidiMsg` dispatch and `device.midiOutSysex` response, plus a 500 ms
  heartbeat in `OnIdle`. No more file I/O.
- `pyproject.toml`: added `mido>=1.3.2` and `python-rtmidi>=1.5.8`.
- `server.py`: new `--list-ports` flag for debugging port mismatches.
- `fl_ping`: reports `port_to_fl` and `port_from_fl` instead of a bridge
  root.

### What did NOT change

- The 10 Phase 0 tool names and signatures
  (`fl_ping`, `fl_get_tempo`, `fl_set_tempo`, `fl_play`, `fl_stop`,
  `fl_toggle_play`, `fl_record`, `fl_get_play_state`,
  `fl_get_song_position`, `fl_set_song_position`).
- The command-name catalogue (`CMD_PING`, `CMD_GET_TEMPO`, etc).
- The tool-side error model (`FLNotRunning`, `FLTimeout`,
  `FLCommandFailed`). A new `FLPortMissing` was added for the MIDI-port
  setup failure mode.

### Setup deltas vs v0.1

You now need two virtual MIDI ports created up front:

- Windows: install loopMIDI, create `FLStudioMCP RX` and `FLStudioMCP TX`.
- macOS: add two ports of those names under IAC Driver in Audio MIDI Setup.

Then in FL: Options -> MIDI Settings, enable both ports, set their Port
numbers to the same value (the controller script uses the matching number
to route its responses to the correct output).

## v0.1.0 -- File-queue bridge (withdrawn)

Initial release. Withdrawn because the file-queue design did not work on
FL builds that sandbox controller-script file I/O (which appears to be
every recent FL build, not an edge case).
