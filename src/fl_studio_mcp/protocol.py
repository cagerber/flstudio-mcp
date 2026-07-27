"""Shared protocol constants for the FL Studio MCP bridge.

v0.2: All-MIDI transport. The earlier file-queue design assumed the FL
controller script could write JSON files, but FL's controller-script Python
sandbox blocks every form of file write on at least some builds
(confirmed: FL 24+ MIDI scripting v40, Python 3.12.1). We pivoted to a
MIDI SysEx wire format that works on every FL version that supports MIDI
scripting (20.7+).

Wire format (bytes between SysEx F0 and F7):

    7D 4D 43 50 <dir> <id8> <base64_json>

    7D            non-commercial / private manufacturer ID
    4D 43 50      magic, ASCII "MCP" -- lets us ignore unrelated SysEx
    <dir>         0x01 = request, 0x02 = response, 0x03 = heartbeat
    <id8>         8 ASCII chars [a-z0-9], correlates request and response
    <base64_json> base64 of the UTF-8 JSON payload, fits in 7-bit MIDI bytes

The framing F0 ... F7 is added by the MIDI library (mido) on send and
stripped on receive -- protocol-side helpers work on the payload bytes only.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import secrets
import string
from typing import Tuple


# Bump when the wire format changes incompatibly. Server and FL refuse to
# talk to a mismatched peer.
PROTOCOL_VERSION = 2

# How long the server waits for a heartbeat before declaring FL not running.
HEARTBEAT_STALE_SECONDS = 3.0

# Server-side timeout for any single command round trip.
DEFAULT_TIMEOUT_SECONDS = 5.0

# How often the FL controller emits a heartbeat SysEx.
HEARTBEAT_INTERVAL_SECONDS = 0.5


# ---------------------------------------------------------------------------
# Default MIDI port names
# ---------------------------------------------------------------------------
# These names must match what the user creates in loopMIDI (Windows) or in
# the IAC Driver (macOS Audio MIDI Setup). The names are case-insensitive
# and matched as substrings, so e.g. "FLStudioMCP RX 0" from Windows also
# matches "FLStudioMCP RX".

# Port that carries commands FROM the MCP server TO FL Studio.
# Server opens this as OUTPUT. FL opens this as INPUT.
DEFAULT_PORT_TO_FL = "FLStudioMCP RX"

# Port that carries responses + heartbeats FROM FL Studio TO the MCP server.
# Server opens this as INPUT. FL opens this as OUTPUT.
DEFAULT_PORT_FROM_FL = "FLStudioMCP TX"


def port_to_fl_name() -> str:
    return os.environ.get("FLSTUDIO_MCP_PORT_TO_FL", DEFAULT_PORT_TO_FL)


def port_from_fl_name() -> str:
    return os.environ.get("FLSTUDIO_MCP_PORT_FROM_FL", DEFAULT_PORT_FROM_FL)


# ---------------------------------------------------------------------------
# Command catalogue
# ---------------------------------------------------------------------------
# Unchanged from v0.1 so the existing tool layer keeps working. New commands
# get appended here AND in fl_controller/FLStudioMCP/device_FLStudioMCP.py.

# Transport
CMD_PING = "ping"
CMD_GET_TEMPO = "get_tempo"
CMD_SET_TEMPO = "set_tempo"
CMD_PLAY = "play"
CMD_STOP = "stop"
CMD_TOGGLE_PLAY = "toggle_play"
CMD_RECORD = "record"
CMD_GET_PLAY_STATE = "get_play_state"
CMD_GET_SONG_POS = "get_song_position"
CMD_SET_SONG_POS = "set_song_position"

# Project (Phase 1) -- aggregate read
CMD_GET_PROJECT_STATE = "get_project_state"

# Mixer (Phase 2)
CMD_MIXER_LIST_TRACKS = "mixer_list_tracks"
CMD_MIXER_GET_TRACK = "mixer_get_track"
CMD_MIXER_SET_VOLUME = "mixer_set_volume"
CMD_MIXER_SET_PAN = "mixer_set_pan"
CMD_MIXER_SET_MUTE = "mixer_set_mute"
CMD_MIXER_SET_SOLO = "mixer_set_solo"
CMD_MIXER_SET_NAME = "mixer_set_name"

# Channels (Phase 1)
CMD_CHANNEL_LIST = "channel_list"
CMD_CHANNEL_GET = "channel_get"
CMD_CHANNEL_SET_VOLUME = "channel_set_volume"
CMD_CHANNEL_SET_PAN = "channel_set_pan"
CMD_CHANNEL_SET_MUTE = "channel_set_mute"
CMD_CHANNEL_SET_SOLO = "channel_set_solo"
CMD_CHANNEL_SELECT = "channel_select"

# Patterns (Phase 3)
CMD_PATTERN_LIST = "pattern_list"
CMD_PATTERN_SELECT = "pattern_select"
CMD_PATTERN_RENAME = "pattern_rename"             # NOT YET IMPLEMENTED (no handler) -- reserved
CMD_PATTERN_GET_LENGTH = "pattern_get_length"     # NOT YET IMPLEMENTED (no handler) -- reserved

# Plugin params (Phase 1B)
CMD_PLUGIN_LIST = "plugin_list"            # list plugins on a mixer track's slots
CMD_PLUGIN_GET_PARAMS = "plugin_get_params"  # paginated param dump for one plugin
CMD_PLUGIN_LIST_PARAMS = "plugin_list_params"   # NOT YET IMPLEMENTED (no handler) -- reserved
CMD_PLUGIN_GET_PARAM = "plugin_get_param"
CMD_PLUGIN_SET_PARAM = "plugin_set_param"

# Routing / grouping / cleanup (read surface -- Slice 1)
CMD_MIXER_GET_ROUTING = "mixer_get_routing"            # one track's send destinations
CMD_MIXER_GET_ROUTING_ALL = "mixer_get_routing_all"    # paginated routing matrix
CMD_CHANNEL_ROUTING_SUMMARY = "channel_routing_summary"  # channel -> mixer links

# Routing writes (Slice 2)
CMD_MIXER_SET_ROUTE = "mixer_set_route"                # setRouteTo + afterRoutingChanged

# Level awareness (read) -- meter peaks, meaningful only during playback
CMD_MIXER_GET_PEAKS = "mixer_get_peaks"                # getTrackPeaks L/R/max

# Track / channel color (RGB int 0xRRGGBB). Set accepts r/g/b 0-255 (fresh) or
# an explicit "color" int (rollback re-sends the exact int FL gave us).
CMD_MIXER_SET_COLOR = "mixer_set_color"
CMD_MIXER_GET_COLOR = "mixer_get_color"
CMD_CHANNEL_SET_COLOR = "channel_set_color"
CMD_CHANNEL_GET_COLOR = "channel_get_color"

# Plugin presets (navigate/read) -- op: info | next | prev
CMD_PLUGIN_PRESET = "plugin_preset"                    # getPresetCount/next/prev/getName

# API introspection / arrangement probe -- op: dir | ppq | marker_add | undo
CMD_API_PROBE = "api_probe"

# Arrangement primitives (Slice 1) -- pattern create/clone + section markers
CMD_ARRANGE_NEW_PATTERN = "arrange_new_pattern"        # find empty + jumpTo + name
CMD_ARRANGE_CLONE_PATTERN = "arrange_clone_pattern"    # clonePattern + rename
CMD_ARRANGE_ADD_MARKER = "arrange_add_marker"          # addAutoTimeMarker at a bar

# Note-bridge hardening -- ensure the Piano roll is open before a note-write
CMD_ENSURE_PIANO_ROLL = "ensure_piano_roll"            # ui.showWindow(widPianoRoll)

# Project persistence (added in v0.3 / MCP enhancements pass)
CMD_SAVE_PROJECT = "save_project"                      # general.save + (optionally) saveAs
CMD_GET_PROJECT_PATH = "get_project_path"              # ui.getProjectPath / Title
CMD_GET_PROJECT_DIRTY = "get_project_dirty"            # has the project been modified since last save?
CMD_EXPORT_CURRENT_PROJECT_MIDI = "export_current_project_midi"  # dumps every channel's notes -> type-1 .mid

# Channel / mixer track creation (added in v0.3)
CMD_CREATE_CHANNEL = "create_channel"                  # channels.new + setName + return index
CMD_CREATE_MIXER_TRACK = "create_mixer_track"          # mixer.new + setName + return index

# Plugin preset write path (added in v0.3) -- FL can iterate presets, so we
# can scan to the requested name. Naming convention: full preset name match
# preferred, falls back to substring if no exact.
CMD_LOAD_PLUGIN_PRESET = "load_plugin_preset"          # op=by_name | by_index

# Automation (added in v0.3) -- thin read + single-point write
CMD_GET_AUTOMATION_INFO = "get_automation_info"        # surface which slots/channels have automation
CMD_SET_AUTOMATION_POINT = "set_automation_point"      # write one point at (pos_ticks, value_norm)

# v0.3 / MCP enhancements -- discovered from FL-Studio-API-Stubs + live probe
# These are the FUNCTIONS we DIDN'T HAVE in v0.2 that the stubs surfaced
# (verified live against FL 26.1.2 build 5557):

# The big find: general.dumpScoreLog is the live-capture -> pattern path
# (writes the last ``time`` seconds of played MIDI to the selected pattern).
CMD_DUMP_SCORE_LOG = "dump_score_log"                  # general.dumpScoreLog(time, silent)
CMD_SAFE_TO_EDIT = "safe_to_edit"                      # general.safeToEdit() -- edit guard
CMD_TRIGGER_NOTE = "trigger_note"                      # channels.midiNoteOn(idx, note, vel, ch=-1)
CMD_QUANTIZE_CHANNEL = "quantize_channel"              # channels.quickQuantize(idx, startOnly, useGlobalIndex)
CMD_GET_SELECTED_CHANNEL = "get_selected_channel"      # channels.selectedChannel(canBeNone, offset, indexGlobal)
CMD_GET_CHANNEL_MIDI_IN_PORT = "get_channel_midi_in_port"  # channels.getChannelMidiInPort(idx)
CMD_GET_ACTIVE_EFFECT = "get_active_effect"            # mixer.getActiveEffectIndex() -> (track, slot) | None
CMD_FOCUS_PLUGIN_EDITOR = "focus_plugin_editor"        # mixer.focusEditor(track, slot)
CMD_MIXER_IS_TRACK_ARMED = "mixer_is_track_armed"      # mixer.isTrackArmed(idx)
CMD_MIXER_ARM_TRACK = "mixer_arm_track"                # mixer.armTrack(idx)
CMD_MIXER_IS_TRACK_ENABLED = "mixer_is_track_enabled"  # mixer.isTrackEnabled(idx)
CMD_MIXER_TRACK_COUNT = "mixer_track_count"            # mixer.trackCount() -- distinct from mixer list count
CMD_MIXER_GET_SLOT_COLOR = "mixer_get_slot_color"      # mixer.getSlotColor(track, slot)
CMD_MIXER_SET_SLOT_COLOR = "mixer_set_slot_color"      # mixer.setSlotColor(track, slot, color)
CMD_PATTERN_BURN_LOOP = "pattern_burn_loop"            # patterns.burnLoop(channel, storeUndo, updateUi)
CMD_PATTERN_IS_DEFAULT = "pattern_is_default"          # patterns.isPatternDefault(idx)
CMD_PATTERN_SELECT = "pattern_select"                  # patterns.selectPattern(idx, value=-1, preview=False)
CMD_PATTERN_IS_SELECTED = "pattern_is_selected"        # patterns.isPatternSelected(idx)

# v0.4 -- discovered via repeated paginated api_probe() of FL 26.1.2 build 5557.
# All verified LIVE present on the running daemon (NOT just in stubs docs --
# some stubs functions aren't actually in the FL 26.1.2 runtime).

# general.* -- project metadata, time signature, undo
CMD_GET_PROJECT_AUTHOR = "get_project_author"            # general.getProjectAuthor
CMD_GET_PROJECT_TITLE  = "get_project_title"             # general.getProjectTitle
CMD_GET_PROJECT_GENRE  = "get_project_genre"             # general.getProjectGenre
CMD_SET_NUMERATOR      = "set_numerator"                 # general.setNumerator (time-sig)
CMD_SET_DENOMINATOR    = "set_denominator"               # general.setDenominator (time-sig)
CMD_SET_REC_PPQ        = "set_rec_ppq"                   # general.setRecPPQ
CMD_GET_UNDO_HISTORY_COUNT = "get_undo_history_count"    # general.getUndoHistoryCount
CMD_GET_UNDO_HISTORY_POS  = "get_undo_history_pos"       # general.getUndoHistoryPos
CMD_SET_UNDO_HISTORY_POS  = "set_undo_history_pos"       # general.setUndoHistoryPos
CMD_UNDO               = "undo"                          # general.undo(count=1)
CMD_REDO               = "redo"                          # general.undoUpDown / undoUp

# channels.* -- channel metadata + step sequencer
CMD_GET_CHANNEL_TYPE        = "get_channel_type"          # channels.getChannelType(index)
CMD_GET_ACTIVITY_LEVEL      = "get_activity_level"        # channels.getActivityLevel(index)
CMD_GET_CHANNEL_INDEX       = "get_channel_index"         # channels.getChannelIndex(name) -- name lookup
CMD_IS_CHANNEL_SELECTED     = "is_channel_selected"       # channels.isChannelSelected
CMD_IS_CHANNEL_HIGHLIGHTED  = "is_channel_highlighted"    # channels.isHighLighted
CMD_MUTE_CHANNEL            = "mute_channel"              # channels.muteChannel(index, value=-1)
CMD_GET_SWING               = "get_swing"                 # channels.getSwing(index)
CMD_SET_SWING               = "set_swing"                 # channels.setSwing(index, value)
CMD_GET_GRID_BIT            = "get_grid_bit"              # channels.getGridBit(channel, step)
CMD_SET_GRID_BIT            = "set_grid_bit"              # channels.setGridBit(channel, step, value)
CMD_GET_STEP_PARAM          = "get_step_param"            # channels.getStepParam(channel, step, param)
CMD_GET_CURRENT_STEP_PARAM  = "get_current_step_param"    # channels.getCurrentStepParam(channel, step, param)
CMD_SET_STEP_PARAM_BY_INDEX = "set_step_param_by_index"   # channels.setStepParameterByIndex(channel, step, param, value)
CMD_GET_REC_EVENT_ID        = "get_rec_event_id"          # channels.getRecEventId(index)
CMD_INC_EVENT_VALUE         = "inc_event_value"           # channels.incEventValue(eventId, step, res=1/24)

# patterns.* -- color, length, channel loop, multi-select
CMD_GET_PATTERN_LENGTH    = "get_pattern_length"          # patterns.getPatternLength(index) -- BEATS
CMD_SET_PATTERN_LENGTH    = "set_pattern_length"          # patterns.setPatternLength(index, beats) (not in 26.1.2 runtime; honest-report if absent)
CMD_GET_PATTERN_COLOR     = "get_pattern_color"           # patterns.getPatternColor(index)
CMD_SET_PATTERN_COLOR     = "set_pattern_color"           # patterns.setPatternColor(index, color)
CMD_GET_CHANNEL_LOOP_STYLE = "get_channel_loop_style"     # patterns.getChannelLoopStyle(pattern, channel)
CMD_SET_CHANNEL_LOOP      = "set_channel_loop"            # patterns.setChannelLoop(channel, loopPoint)
CMD_PATTERN_SELECT_ALL    = "pattern_select_all"          # patterns.selectAll()
CMD_PATTERN_DESELECT_ALL  = "pattern_deselect_all"        # patterns.deselectAll()
CMD_PATTERN_IS_ANY_SELECTED = "pattern_is_any_selected"   # patterns.isPatternSelected(0) -- existence check

# mixer.* -- full parametric EQ, plugin mix/mute, automation helpers, track ops
CMD_MIXER_GET_EQ_BAND_COUNT = "mixer_get_eq_band_count"   # mixer.getEqBandCount(track)
CMD_MIXER_GET_EQ_FREQ       = "mixer_get_eq_freq"         # mixer.getEqFrequency(track, band)
CMD_MIXER_SET_EQ_FREQ       = "mixer_set_eq_freq"         # mixer.setEqFrequency(track, band, freq)
CMD_MIXER_GET_EQ_BW         = "mixer_get_eq_bw"           # mixer.getEqBandwidth(track, band)
CMD_MIXER_SET_EQ_BW         = "mixer_set_eq_bw"           # mixer.setEqBandwidth(track, band, bw)
CMD_MIXER_GET_EQ_GAIN       = "mixer_get_eq_gain"         # mixer.getEqGain(track, band)
CMD_MIXER_SET_EQ_GAIN       = "mixer_set_eq_gain"         # mixer.setEqGain(track, band, gain)
CMD_MIXER_GET_TRACK_PLUGIN_ID   = "mixer_get_track_plugin_id"   # mixer.getTrackPluginId(track, slot)
CMD_MIXER_IS_TRACK_PLUGIN_VALID = "mixer_is_track_plugin_valid" # mixer.isTrackPluginValid(track, slot)
CMD_MIXER_GET_PLUGIN_MIX_LEVEL  = "mixer_get_plugin_mix_level"  # mixer.getPluginMixLevel(track, slot)
CMD_MIXER_SET_PLUGIN_MIX_LEVEL  = "mixer_set_plugin_mix_level"  # mixer.setPluginMixLevel(track, slot, level)
CMD_MIXER_GET_PLUGIN_MUTE_STATE = "mixer_get_plugin_mute_state" # mixer.getPluginMuteState(track, slot)
CMD_MIXER_SET_PLUGIN_MUTE_STATE = "mixer_set_plugin_mute_state" # mixer.setPluginMuteState(track, slot, mute)
CMD_MIXER_GET_TRACK_INFO        = "mixer_get_track_info"        # mixer.getTrackInfo(mode)
CMD_MIXER_GET_TRACK_NUMBER      = "mixer_get_track_number"      # mixer.getTrackNumber(track)
CMD_MIXER_SET_TRACK_NUMBER      = "mixer_set_track_number"      # mixer.setTrackNumber(track, number, flags)
CMD_MIXER_GET_ACTIVE_TRACK      = "mixer_get_active_track"      # mixer.getActiveEffectIndex / setActiveTrack
CMD_MIXER_SET_ACTIVE_TRACK      = "mixer_set_active_track"      # mixer.setActiveTrack(index)
CMD_MIXER_IS_TRACK_SELECTED     = "mixer_is_track_selected"     # mixer.isTrackSelected(track)
CMD_MIXER_SELECT_TRACK          = "mixer_select_track"          # mixer.selectTrack(track, value=-1)
CMD_MIXER_SELECT_ALL            = "mixer_select_all"            # mixer.selectAll()
CMD_MIXER_DESELECT_ALL          = "mixer_deselect_all"          # mixer.deselectAll()
CMD_MIXER_GET_EVENT_VALUE       = "mixer_get_event_value"       # mixer.getEventValue(eventId)
CMD_MIXER_GET_EVENT_ID_NAME     = "mixer_get_event_id_name"     # mixer.getEventIDName(eventId)
CMD_MIXER_GET_EVENT_ID_VALUE_STR = "mixer_get_event_id_value_str" # mixer.getEventIDValueString(eventId)
CMD_MIXER_AUTOMATE_EVENT        = "mixer_automate_event"        # mixer.automateEvent(eventId, value, flags, res=0)
CMD_MIXER_ENABLE_TRACK          = "mixer_enable_track"          # mixer.enableTrack(track, value=1)
CMD_MIXER_GET_TRACK_RECORDING_FILE = "mixer_get_track_recording_file" # mixer.getTrackRecordingFileName(track)
CMD_MIXER_GET_ROUTE_TO_LEVEL    = "mixer_get_route_to_level"    # mixer.getRouteToLevel(src, dst)
CMD_MIXER_IS_TRACK_SLOTS_ENABLED = "mixer_is_track_slots_enabled" # mixer.isTrackSlotsEnabled(track)
CMD_MIXER_ENABLE_TRACK_SLOTS    = "mixer_enable_track_slots"    # mixer.enableTrackSlots(track, value=1)
CMD_MIXER_IS_TRACK_REV_POLARITY = "mixer_is_track_rev_polarity" # mixer.isTrackRevPolarity(track)
CMD_MIXER_REV_TRACK_POLARITY    = "mixer_rev_track_polarity"    # mixer.revTrackPolarity(track, value)
CMD_MIXER_IS_TRACK_SWAP_CHANNELS = "mixer_is_track_swap_channels" # mixer.isTrackSwapChannels(track)
CMD_MIXER_SWAP_TRACK_CHANNELS   = "mixer_swap_track_channels"   # mixer.swapTrackChannels(track, value)
CMD_MIXER_IS_TRACK_MUTE_LOCK    = "mixer_is_track_mute_lock"    # mixer.isTrackMuteLock(track)
CMD_MIXER_GET_TRACK_STEREO_SEP  = "mixer_get_track_stereo_sep"  # mixer.getTrackStereoSep(track) -- not in 26.1.2 runtime, see handler
CMD_MIXER_SET_TRACK_STEREO_SEP  = "mixer_set_track_stereo_sep"  # mixer.setTrackStereoSep(track, sep) -- not in 26.1.2 runtime
CMD_MIXER_LINK_CHANNEL_TO_TRACK = "mixer_link_channel_to_track" # mixer.linkChannelToTrack(channel, track, select=False)
CMD_MIXER_LINK_TRACK_TO_CHANNEL = "mixer_link_track_to_channel" # mixer.linkTrackToChannel(track, channel, select=False)
CMD_MIXER_GET_LAST_PEAK_VOL     = "mixer_get_last_peak_vol"     # mixer.getLastPeakVol(section)
CMD_MIXER_GET_AUTO_SMOOTH_EVENT_VAL = "mixer_get_auto_smooth_event_val" # mixer.getAutoSmoothEventValue(...)
CMD_MIXER_REMOTE_FIND_EVENT_VALUE = "mixer_remote_find_event_value" # mixer.remoteFindEventValue(eventId, flags, res=0)

# ui.* -- hint bar, snap, focused plugin, window show/hide, browser nav
CMD_GET_HINT_MSG           = "get_hint_msg"                # ui.getHintMsg()
CMD_SET_HINT_MSG           = "set_hint_msg"                # ui.setHintMsg(msg)
CMD_SHOW_NOTIFICATION      = "show_notification"           # ui.showNotification(id)
CMD_GET_FOCUSED_PLUGIN_NAME = "get_focused_plugin_name"   # ui.getFocusedPluginName()
CMD_IS_CLOSING             = "is_closing"                  # ui.isClosing()
CMD_GET_SNAP_MODE          = "get_snap_mode"               # ui.getSnapMode()
CMD_SET_SNAP_MODE          = "set_snap_mode"               # ui.setSnapMode(value)
CMD_SNAP_ON_OFF            = "snap_on_off"                 # ui.snapOnOff() -- toggle
CMD_IS_METRONOME_ENABLED   = "is_metronome_enabled"        # ui.isMetronomeEnabled()
CMD_IS_PRECOUNT_ENABLED    = "is_precount_enabled"         # ui.isPrecountEnabled()
CMD_IS_LOOP_REC_ENABLED    = "is_loop_rec_enabled"         # ui.isLoopRecEnabled()
CMD_IS_START_ON_INPUT_ENABLED = "is_start_on_input_enabled" # ui.isStartOnInputEnabled()
CMD_GET_STEP_EDIT_MODE     = "get_step_edit_mode"          # ui.getStepEditMode()
CMD_SET_STEP_EDIT_MODE     = "set_step_edit_mode"          # ui.setStepEditMode(value)
CMD_GET_TIME_DISP_MIN      = "get_time_disp_min"           # ui.getTimeDispMin() -- True=time, False=bars
CMD_SET_TIME_DISP_MIN      = "set_time_disp_min"           # ui.setTimeDispMin() -- toggle
CMD_SHOW_WINDOW            = "show_window"                 # ui.showWindow(window_id)
CMD_HIDE_WINDOW            = "hide_window"                 # ui.hideWindow(window_id)
CMD_GET_VISIBLE            = "get_visible"                 # ui.getVisible(window_id)
CMD_SELECT_WINDOW          = "select_window"               # ui.selectWindow(window_id)
CMD_NAVIGATE_BROWSER       = "navigate_browser"            # ui.navigateBrowser(dir)
CMD_NAVIGATE_BROWSER_MENU  = "navigate_browser_menu"       # ui.navigateBrowserMenu(dir)
CMD_NAVIGATE_BROWSER_TABS  = "navigate_browser_tabs"       # ui.navigateBrowserTabs(dir)
CMD_SELECT_BROWSER_MENU_ITEM = "select_browser_menu_item" # ui.selectBrowserMenuItem(index)
CMD_PREVIEW_BROWSER_MENU_ITEM = "preview_browser_menu_item" # ui.previewBrowserMenuItem(index)
CMD_TOGGLE_BROWSER_NODE    = "toggle_browser_node"         # ui.toggleBrowserNode(index)
CMD_IS_BROWSER_AUTO_HIDE   = "is_browser_auto_hide"        # ui.isBrowserAutoHide()
CMD_SET_BROWSER_AUTO_HIDE  = "set_browser_auto_hide"       # ui.setBrowserAutoHide(value)

# v0.5 -- typed REC surface using FL's midi.py constants. The server
# passes a string name for the property/target/scale/snap/window; the
# controller script imports the real `midi` module from FL's runtime
# Python and resolves the string to the matching REC_* integer.
#
# These give the MCP a clean typed API (no raw event_id arithmetic
# leaking out to the user) while keeping the wire format compact.

# Per-channel REC_Chan_* (16+ properties)
CMD_GET_CHANNEL_PROPERTY    = "get_channel_property"        # name -> midi.REC_Chan_*
CMD_SET_CHANNEL_PROPERTY    = "set_channel_property"        # name -> midi.REC_Chan_*
# Mixer track REC_Mixer_* (volume, pan, stereo sep, plus full 8-band EQ)
CMD_GET_MIXER_PROPERTY      = "get_mixer_property"          # name -> midi.REC_Mixer_*
CMD_SET_MIXER_PROPERTY      = "set_mixer_property"          # name -> midi.REC_Mixer_*
CMD_SET_EQ_BAND             = "set_eq_band"                 # one-shot: type+freq+bw+gain for a band
CMD_GET_EQ_BAND             = "get_eq_band"                 # read all 4 props for a band
# Global REC_Global_* (master volume, shuffle, pitch, tempo)
CMD_GET_MASTER_VOLUME       = "get_master_volume"           # REC_MainVol
CMD_SET_MASTER_VOLUME       = "set_master_volume"           # REC_MainVol
CMD_GET_MASTER_SHUFFLE      = "get_master_shuffle"          # REC_MainShuffle
CMD_SET_MASTER_SHUFFLE      = "set_master_shuffle"          # REC_MainShuffle
CMD_GET_MASTER_PITCH        = "get_master_pitch"            # REC_MainPitch
CMD_SET_MASTER_PITCH        = "set_master_pitch"            # REC_MainPitch
# Special RECs (transport + start/stop)
CMD_START_STOP              = "start_stop"                  # REC_StartStop: 0=Stop, 1=Start
CMD_GET_SONG_POSITION_BARS  = "get_song_position_bars"      # REC_SongPosition
CMD_SET_SONG_POSITION_BARS  = "set_song_position_bars"      # REC_SongPosition
CMD_GET_SONG_LENGTH_BARS    = "get_song_length_bars"        # REC_SongLength
# Scales (channel-rack harmonic scale)
CMD_GET_SCALE               = "get_scale"                   # current scale int
CMD_SET_SCALE               = "set_scale"                   # name -> HARMONICSCALE_*
# Channel-type + step-param + window + snap-mode named enum wrappers
# (v0.4 returned raw ints from these; v0.5 takes/returns names where useful)
CMD_GET_CHANNEL_TYPE_NAMED  = "get_channel_type_named"      # returns "sampler"/"generator"/...
CMD_GET_STEP_PARAM_NAMED    = "get_step_param_named"        # param="velocity", returns value
CMD_SET_STEP_PARAM_NAMED    = "set_step_param_named"        # param="velocity", value
CMD_GET_STEP_PARAM_LIST     = "get_step_param_list"         # for a whole channel+step, return all 9
# Note-name utilities (server-side; uses utils.py mirror)
CMD_NOTE_NAME               = "note_name"                   # MIDI int -> "C5"
CMD_VOL_TO_DB               = "vol_to_db"                   # 0..1 FL curve -> dB


# ---------------------------------------------------------------------------
# SysEx wire format
# ---------------------------------------------------------------------------

SYSEX_MANUFACTURER = 0x7D            # MIDI-spec reserved for private use
SYSEX_MAGIC = (0x4D, 0x43, 0x50)     # ASCII "MCP"

DIR_REQUEST = 0x01
DIR_RESPONSE = 0x02
DIR_HEARTBEAT = 0x03

REQUEST_ID_LEN = 8
REQUEST_ID_ALPHABET = string.ascii_lowercase + string.digits

# Total header length: 1 (manuf) + 3 (magic) + 1 (dir) + REQUEST_ID_LEN.
_HEADER_LEN = 1 + 3 + 1 + REQUEST_ID_LEN


def new_request_id() -> str:
    return "".join(secrets.choice(REQUEST_ID_ALPHABET) for _ in range(REQUEST_ID_LEN))


def encode_message(direction: int, request_id: str, payload: dict) -> bytes:
    """Build the SysEx payload bytes (everything between F0 and F7).

    The serializer (mido.Message('sysex', data=...)) will add the framing.
    """
    if direction not in (DIR_REQUEST, DIR_RESPONSE, DIR_HEARTBEAT):
        raise ValueError("Bad direction: %r" % direction)
    rid = request_id.encode("ascii")
    if len(rid) != REQUEST_ID_LEN or any(b > 0x7F for b in rid):
        raise ValueError("Bad request id: %r" % request_id)

    body_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    body_b64 = base64.b64encode(body_json.encode("ascii"))

    out = bytearray()
    out.append(SYSEX_MANUFACTURER)
    out.extend(SYSEX_MAGIC)
    out.append(direction & 0x7F)
    out.extend(rid)
    out.extend(body_b64)
    return bytes(out)


def decode_message(data) -> Tuple[int, str, dict] | None:
    """Decode a SysEx payload. Returns None if not one of ours.

    ``data`` is the bytes between F0 and F7 (mido strips the framing).
    Accepts bytes, bytearray, or any iterable of ints in [0, 127].
    """
    buf = bytes(data)
    if len(buf) < _HEADER_LEN:
        return None
    if buf[0] != SYSEX_MANUFACTURER:
        return None
    if tuple(buf[1:4]) != SYSEX_MAGIC:
        return None
    direction = buf[4]
    rid = buf[5 : 5 + REQUEST_ID_LEN].decode("ascii", errors="replace")
    body = buf[_HEADER_LEN:]
    try:
        body_json = base64.b64decode(body, validate=True).decode("utf-8")
        payload = json.loads(body_json)
    except Exception:
        return None
    return direction, rid, payload


# ---------------------------------------------------------------------------
# Request / response envelope shapes
# ---------------------------------------------------------------------------

def make_request(command: str, params: dict | None = None) -> dict:
    return {
        "v": PROTOCOL_VERSION,
        "cmd": command,
        "params": params or {},
    }


def make_response_ok(data) -> dict:
    return {"v": PROTOCOL_VERSION, "ok": True, "data": data}


def make_response_err(error: str, *, code: str = "error") -> dict:
    return {"v": PROTOCOL_VERSION, "ok": False, "error": error, "code": code}


# ---------------------------------------------------------------------------
# Chunked short-message fallback transport
# ---------------------------------------------------------------------------
# Some Wine MIDI drivers (winealsa.drv) silently drop SysEx sent from inside
# Wine (device.midiOutSysex / midiOutLongMsg) even though short messages
# (midiOutMsg / midiOutShortMsg) work fine. FL sends every outbound frame
# (heartbeat + response) both as SysEx AND as this chunked short-message
# stream; whichever one actually makes it through ALSA gets decoded here.
# One Control Change per byte, on a channel/controller triple nothing else
# on this dedicated port uses.
CHUNK_CHANNEL = 15
CHUNK_CTRL_START = 102
CHUNK_CTRL_DATA = 103
CHUNK_CTRL_END = 104


class ChunkReassembler:
    """Reassembles a byte buffer from a stream of chunked CC messages.

    FL's script never interleaves two frames (it sends one fully inside a
    single, non-reentrant callback), so a single in-flight buffer is enough.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._active = False

    def feed_cc(self, channel: int, control: int, value: int) -> bytes | None:
        """Feed one Control Change message. Returns the completed buffer on
        end-of-frame, otherwise None."""
        if channel != CHUNK_CHANNEL:
            return None
        if control == CHUNK_CTRL_START:
            self._buf = bytearray()
            self._active = True
        elif control == CHUNK_CTRL_DATA:
            if self._active:
                self._buf.append(value & 0x7F)
        elif control == CHUNK_CTRL_END:
            if self._active:
                self._active = False
                return bytes(self._buf)
        return None


def system_label() -> str:
    """Short OS label, useful in heartbeats and logs."""
    return "%s %s" % (platform.system(), platform.release())
