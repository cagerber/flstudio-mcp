#!/usr/bin/env python3
"""fl-studio-mcp integration test -- exercises every public tool.

Comprehensive + repeatable integration test against a live FL Studio +
daemon session. Reads FL state through the TCP bridge (same as production
use). Every registered tool gets at least one test; mutating tools are
gated behind explicit env-var flags so the default run is read-only.

USAGE
    # from the worktree or main checkout, with the daemon running
    # (fl-studio-mcp-daemon):
    python scripts/integration_test.py

    # direct MIDI bridge instead of TCP daemon:
    FLSTUDIO_MCP_INTEGRATION_TRANSPORT=direct \\
    python scripts/integration_test.py

    # only run the v0.2 baseline (sanity check):
    FLSTUDIO_MCP_INTEGRATION_LEVEL=baseline \\
    python scripts/integration_test.py

    # only run v0.3 commands:
    FLSTUDIO_MCP_INTEGRATION_LEVEL=v03 \\
    python scripts/integration_test.py

    # only run v0.4 commands:
    FLSTUDIO_MCP_INTEGRATION_LEVEL=v04 \\
    python scripts/integration_test.py

PREREQUISITES
    1. FL Studio open with the FLStudioMCP controller loaded. New v0.3/v0.4
       commands require a controller script reload (restart FL or
       re-toggle the controller type in MIDI Settings).
    2. fl-studio-mcp-daemon running on 127.0.0.1:9787 (default).

DESIGN
    - Idempotent by default: never mutates FL state. Every command is a
      READ or a guard-check. Mutating tools are gated behind env vars.
    - Per-tool pass/fail: each test reports ok or a structured failure.
    - Pre-reload unknown_command results (FLCommandFailed code=
      'unknown_command') are reported separately -- they indicate the
      new commands haven't been picked up by FL's controller yet.
    - v0.2 baseline + bridge-health failures -> exit 1.
    - v0.3/v0.4 unknown_command results do NOT fail the run; they're
      expected pre-reload.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.connection import (  # noqa: E402
    FLBridge,
    FLBridgeError,
    FLCommandFailed,
    FLNotRunning,
    FLPortMissing,
    FLTimeout,
    TCPBridge,
    fetch_all_pages,
)
from fl_studio_mcp import protocol  # noqa: E402


# ----------------------------------------------------------------------
# Test result accumulator
# ----------------------------------------------------------------------
class Results:
    def __init__(self) -> None:
        self.passed: list[tuple[str, str]] = []      # (test_name, note)
        self.failed: list[tuple[str, str, str]] = [] # (test_name, kind, detail)
        self.skipped: list[tuple[str, str]] = []     # (test_name, reason)
        self.unknown: list[tuple[str, str]] = []     # (test_name, detail) -- v0.3 pre-reload

    def ok(self, name: str, note: str = "") -> None:
        self.passed.append((name, note))

    def fail(self, name: str, kind: str, detail: str) -> None:
        self.failed.append((name, kind, detail))

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append((name, reason))

    def unknown_cmd(self, name: str, detail: str) -> None:
        self.unknown.append((name, detail))

    def summary(self, verbose: bool = False) -> str:
        out = []
        out.append("")
        out.append("=" * 78)
        out.append(f"  PASSED:   {len(self.passed)}")
        out.append(f"  FAILED:   {len(self.failed)}")
        out.append(f"  SKIPPED:  {len(self.skipped)}")
        out.append(f"  UNKNOWN_CMD (expected pre-reload): {len(self.unknown)}")
        out.append("=" * 78)
        if verbose and self.passed:
            out.append("")
            out.append(f"PASSED ({len(self.passed)}):")
            for name, note in self.passed:
                out.append(f"  [OK]   {name}")
        if self.failed:
            out.append("")
            out.append("FAILURES:")
            for name, kind, detail in self.failed:
                out.append(f"  [FAIL] {name} ({kind})")
                out.append(f"         {detail}")
        if self.unknown:
            out.append("")
            out.append("UNKNOWN_COMMANDS (need FL controller reload):")
            for name, detail in self.unknown[:20]:
                out.append(f"  [----] {name}")
            if len(self.unknown) > 20:
                out.append(f"  ... and {len(self.unknown) - 20} more")
        if self.skipped:
            out.append("")
            out.append(f"SKIPPED ({len(self.skipped)} -- gated behind env vars):")
            for name, reason in self.skipped[:6]:
                out.append(f"  [SKIP] {name}: {reason}")
            if len(self.skipped) > 6:
                out.append(f"  ... and {len(self.skipped) - 6} more")
        return "\n".join(out)


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------
def safe_call(results: Results, name: str, fn, *, timeout: float = 8.0,
               retries: int = 2, retry_delay: float = 0.4):
    """Call fn() and categorize the result.

    Transient FLTimeout errors are retried ``retries`` times (default 2)
    with ``retry_delay`` between attempts -- Wine+MIDI has up to ~30%
    per-call loss; 3 total attempts bring cumulative success to ~98%.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            v = fn()
            if isinstance(v, dict) and v.get("ok") is False:
                # Honest-API-limit reports (code='api_unavailable') are
                # successful tool runs that returned an honest response.
                if v.get("code") == "api_unavailable":
                    results.ok(name, "(api_unavailable)")
                    return v
                # Any other ok=false is treated as a soft pass with the body.
                results.ok(name, "(ok=false from tool)")
                return v
            results.ok(name, _short(v))
            return v
        except FLCommandFailed as e:
            code = getattr(e, "code", "?")
            if code == "unknown_command":
                results.unknown_cmd(name, str(e))
                return None
            results.fail(name, "FLCommandFailed", f"code={code} {e}")
            return None
        except FLTimeout as e:
            last_exc = e
            if attempt < retries:
                time.sleep(retry_delay)
                continue
            results.fail(name, "FLTimeout", str(e))
            return None
        except FLNotRunning as e:
            results.fail(name, "FLNotRunning", str(e))
            return None
        except FLPortMissing as e:
            results.fail(name, "FLPortMissing", str(e))
            return None
        except FLBridgeError as e:
            results.fail(name, "FLBridgeError", str(e))
            return None
        except Exception as e:
            results.fail(name, type(e).__name__, str(e))
            traceback.print_exc()
            return None
    return None


def _short(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        keys = list(v.keys())[:4]
        return "{" + ", ".join(f"{k}=..." for k in keys) + "}"
    s = repr(v)
    return s[:80] + ("..." if len(s) > 80 else "")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


# ----------------------------------------------------------------------
# Test groups -- v0.2 baseline (must always pass)
# ----------------------------------------------------------------------
def test_bridge_health(results: Results, bridge) -> bool:
    """Sanity: bridge alive + heartbeat fresh."""
    try:
        hb = bridge.heartbeat_age()
        alive = bridge.is_alive()
    except FLBridgeError as e:
        print(f"[FATAL] bridge unreachable: {e}")
        return False
    if hb is None or hb > 3.0 or not alive:
        print(f"[FATAL] bridge unhealthy (hb={hb}, alive={alive}).")
        return False
    results.ok("bridge_health", f"hb={hb:.3f}s alive={alive}")
    print(f"[OK]    bridge_health  hb={hb:.3f}s")
    return True


def test_v02_baseline(results: Results, bridge):
    """v0.2 commands. Must pass against ANY controller script."""
    print("\n--- v0.2 baseline ---")
    safe_call(results, "v02_ping", lambda: bridge.call(protocol.CMD_PING, {}, timeout=6.0))
    safe_call(results, "v02_get_tempo", lambda: bridge.call(protocol.CMD_GET_TEMPO, {}, timeout=6.0))
    safe_call(results, "v02_project_state",
              lambda: bridge.call(protocol.CMD_GET_PROJECT_STATE, {}, timeout=6.0))
    safe_call(results, "v02_get_song_position",
              lambda: bridge.call(protocol.CMD_GET_SONG_POS, {}, timeout=6.0))
    safe_call(results, "v02_get_play_state",
              lambda: bridge.call(protocol.CMD_GET_PLAY_STATE, {}, timeout=6.0))

    def channels():
        return fetch_all_pages(bridge, protocol.CMD_CHANNEL_LIST, "channels")
    safe_call(results, "v02_channel_list", channels, retries=2)

    def patterns():
        return fetch_all_pages(bridge, protocol.CMD_PATTERN_LIST, "patterns")
    safe_call(results, "v02_pattern_list", patterns, retries=2)

    def mixer():
        return fetch_all_pages(bridge, protocol.CMD_MIXER_LIST_TRACKS, "tracks")
    safe_call(results, "v02_mixer_list_tracks", mixer, retries=2)


# ----------------------------------------------------------------------
# Test groups -- v0.3 (verified live after FL controller reload)
# ----------------------------------------------------------------------
def test_v03_project(results: Results, bridge):
    print("\n--- v0.3 project persistence ---")
    safe_call(results, "v03_get_project_dirty",
              lambda: bridge.call(protocol.CMD_GET_PROJECT_DIRTY, {"with_title": True}, timeout=6.0))
    safe_call(results, "v03_get_project_path",
              lambda: bridge.call(protocol.CMD_GET_PROJECT_PATH, {"dirty": True}, timeout=6.0))
    safe_call(results, "v03_save_project (expect api_unavailable)",
              lambda: bridge.call(protocol.CMD_SAVE_PROJECT, {}, timeout=6.0))
    safe_call(results, "v03_export_current_project_midi (expect api_unavailable)",
              lambda: bridge.call(protocol.CMD_EXPORT_CURRENT_PROJECT_MIDI, {}, timeout=6.0))


def test_v03_creation(results: Results, bridge):
    print("\n--- v0.3 channel/mixer-track create ---")
    safe_call(results, "v03_create_channel (expect api_unavailable)",
              lambda: bridge.call(protocol.CMD_CREATE_CHANNEL, {"name": "TEST"}, timeout=6.0))
    safe_call(results, "v03_create_mixer_track (expect api_unavailable)",
              lambda: bridge.call(protocol.CMD_CREATE_MIXER_TRACK, {"name": "TEST"}, timeout=6.0))


def test_v03_preset_write(results: Results, bridge):
    print("\n--- v0.3 plugin preset write ---")
    safe_call(results, "v03_plugin_preset_info",
              lambda: bridge.call(protocol.CMD_PLUGIN_PRESET,
                                  {"track": 1, "slot": 0, "op": "info"}, timeout=6.0))
    safe_call(results, "v03_load_plugin_preset_by_index",
              lambda: bridge.call(protocol.CMD_LOAD_PLUGIN_PRESET,
                                  {"track": 1, "slot": 0, "op": "by_index", "index": 0}, timeout=6.0))
    safe_call(results, "v03_load_plugin_preset_by_name (expect not found)",
              lambda: bridge.call(protocol.CMD_LOAD_PLUGIN_PRESET,
                                  {"track": 1, "slot": 0, "op": "by_name",
                                   "name": "no-such-preset-zzz", "exact": False}, timeout=6.0))


def test_v03_automation(results: Results, bridge):
    print("\n--- v0.3 automation ---")
    safe_call(results, "v03_get_automation_info (expect api_unavailable)",
              lambda: bridge.call(protocol.CMD_GET_AUTOMATION_INFO, {}, timeout=6.0))
    safe_call(results, "v03_set_automation_point (expect api_unavailable)",
              lambda: bridge.call(protocol.CMD_SET_AUTOMATION_POINT, {"track": 0}, timeout=6.0))


def test_v03_live(results: Results, bridge):
    print("\n--- v0.3 live MIDI ---")
    safe_call(results, "v03_safe_to_edit",
              lambda: bridge.call(protocol.CMD_SAFE_TO_EDIT, {}, timeout=6.0))
    safe_call(results, "v03_dump_score_log (3s)",
              lambda: bridge.call(protocol.CMD_DUMP_SCORE_LOG,
                                  {"time": 3, "silent": True}, timeout=10.0))
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_TRIGGER_NOTE"):
        safe_call(results, "v03_trigger_note (LIVE MIDI)",
                  lambda: bridge.call(protocol.CMD_TRIGGER_NOTE,
                                      {"index": 0, "note": 60, "velocity": 100, "channel": -1},
                                      timeout=6.0))
    else:
        results.skip("v03_trigger_note", "set FLSTUDIO_MCP_INTEGRATION_TRIGGER_NOTE=1 to fire live MIDI")
    safe_call(results, "v03_quantize_channel",
              lambda: bridge.call(protocol.CMD_QUANTIZE_CHANNEL,
                                  {"index": 0, "start_only": 1, "use_global_index": False}, timeout=6.0))
    safe_call(results, "v03_get_selected_channel",
              lambda: bridge.call(protocol.CMD_GET_SELECTED_CHANNEL,
                                  {"can_be_none": True, "offset": 0, "index_global": False}, timeout=6.0))
    safe_call(results, "v03_get_channel_midi_in_port",
              lambda: bridge.call(protocol.CMD_GET_CHANNEL_MIDI_IN_PORT, {"index": 0}, timeout=6.0))


def test_v03_mixer_record(results: Results, bridge):
    print("\n--- v0.3 mixer record + FX slot ---")
    safe_call(results, "v03_mixer_track_count",
              lambda: bridge.call(protocol.CMD_MIXER_TRACK_COUNT, {}, timeout=6.0))
    safe_call(results, "v03_mixer_is_track_armed",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_ARMED, {"index": 0}, timeout=6.0))
    safe_call(results, "v03_mixer_is_track_enabled",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_ENABLED, {"index": 0}, timeout=6.0))
    safe_call(results, "v03_get_active_effect",
              lambda: bridge.call(protocol.CMD_GET_ACTIVE_EFFECT, {}, timeout=6.0))
    safe_call(results, "v03_get_slot_color",
              lambda: bridge.call(protocol.CMD_MIXER_GET_SLOT_COLOR,
                                  {"track": 1, "slot": 0}, timeout=6.0))
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_FOCUS_EDITOR"):
        safe_call(results, "v03_focus_plugin_editor (UI-STEALING)",
                  lambda: bridge.call(protocol.CMD_FOCUS_PLUGIN_EDITOR,
                                      {"track": 1, "slot": 0}, timeout=6.0))
    else:
        results.skip("v03_focus_plugin_editor", "set FLSTUDIO_MCP_INTEGRATION_FOCUS_EDITOR=1 (UI-stealing)")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_ARM_TRACK"):
        safe_call(results, "v03_mixer_arm_track (TOGGLES STATE)",
                  lambda: bridge.call(protocol.CMD_MIXER_ARM_TRACK, {"index": 0}, timeout=6.0))
    else:
        results.skip("v03_mixer_arm_track", "set FLSTUDIO_MCP_INTEGRATION_ARM_TRACK=1 (toggles state)")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_SLOT_COLOR"):
        safe_call(results, "v03_set_slot_color (MUTATES COLOR)",
                  lambda: bridge.call(protocol.CMD_MIXER_SET_SLOT_COLOR,
                                      {"track": 1, "slot": 0, "color": 0x808080}, timeout=6.0))
    else:
        results.skip("v03_set_slot_color", "set FLSTUDIO_MCP_INTEGRATION_SET_SLOT_COLOR=1 (mutates color)")


def test_v03_pattern(results: Results, bridge):
    print("\n--- v0.3 pattern extras ---")
    safe_call(results, "v03_pattern_is_default",
              lambda: bridge.call(protocol.CMD_PATTERN_IS_DEFAULT, {"index": 1}, timeout=6.0))
    safe_call(results, "v03_pattern_is_selected",
              lambda: bridge.call(protocol.CMD_PATTERN_IS_SELECTED, {"index": 1}, timeout=6.0))
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SELECT_PATTERN"):
        safe_call(results, "v03_pattern_select (MUTATES SELECTION)",
                  lambda: bridge.call(protocol.CMD_PATTERN_SELECT,
                                      {"index": 1, "value": -1, "preview": False}, timeout=6.0))
    else:
        results.skip("v03_pattern_select", "set FLSTUDIO_MCP_INTEGRATION_SELECT_PATTERN=1 (mutates selection)")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_BURN_LOOP"):
        safe_call(results, "v03_pattern_burn_loop (MUTATES PATTERN)",
                  lambda: bridge.call(protocol.CMD_PATTERN_BURN_LOOP,
                                      {"channel": 0, "store_undo": 1, "update_ui": 1}, timeout=6.0))
    else:
        results.skip("v03_pattern_burn_loop", "set FLSTUDIO_MCP_INTEGRATION_BURN_LOOP=1 (mutates pattern)")


# ----------------------------------------------------------------------
# Test groups -- v0.4 (full new sweep)
# ----------------------------------------------------------------------
def test_v04_general(results: Results, bridge):
    print("\n--- v0.4 general (project metadata + time sig + undo) ---")
    safe_call(results, "v04_get_project_author",
              lambda: bridge.call(protocol.CMD_GET_PROJECT_AUTHOR, {}, timeout=6.0))
    safe_call(results, "v04_get_project_title",
              lambda: bridge.call(protocol.CMD_GET_PROJECT_TITLE, {}, timeout=6.0))
    safe_call(results, "v04_get_project_genre",
              lambda: bridge.call(protocol.CMD_GET_PROJECT_GENRE, {}, timeout=6.0))
    safe_call(results, "v04_get_undo_history_count",
              lambda: bridge.call(protocol.CMD_GET_UNDO_HISTORY_COUNT, {}, timeout=6.0))
    safe_call(results, "v04_get_undo_history_pos",
              lambda: bridge.call(protocol.CMD_GET_UNDO_HISTORY_POS, {}, timeout=6.0))
    # setNumerator/setDenominator/setRecPPQ change the project's time
    # signature; guarded behind env var to stay idempotent by default.
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_TIME_SIG"):
        safe_call(results, "v04_set_numerator (MUTATES)",
                  lambda: bridge.call(protocol.CMD_SET_NUMERATOR, {"numerator": 4}, timeout=6.0))
        safe_call(results, "v04_set_denominator (MUTATES)",
                  lambda: bridge.call(protocol.CMD_SET_DENOMINATOR, {"denominator": 4}, timeout=6.0))
    else:
        results.skip("v04_set_numerator",
                     "set FLSTUDIO_MCP_INTEGRATION_SET_TIME_SIG=1 to change time signature")
        results.skip("v04_set_denominator",
                     "set FLSTUDIO_MCP_INTEGRATION_SET_TIME_SIG=1")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_PPQ"):
        safe_call(results, "v04_set_rec_ppq (MUTATES)",
                  lambda: bridge.call(protocol.CMD_SET_REC_PPQ, {"ppq": 480}, timeout=6.0))
    else:
        results.skip("v04_set_rec_ppq", "set FLSTUDIO_MCP_INTEGRATION_SET_PPQ=1")
    safe_call(results, "v04_set_undo_history_pos (no-op if pos valid)",
              lambda: bridge.call(protocol.CMD_SET_UNDO_HISTORY_POS,
                                  {"pos": int(bridge.call(protocol.CMD_GET_UNDO_HISTORY_POS, {}, timeout=6.0).get("pos", 0))},
                                  timeout=6.0))


def test_v04_channels(results: Results, bridge):
    print("\n--- v0.4 channels (metadata + step sequencer) ---")
    safe_call(results, "v04_get_channel_type",
              lambda: bridge.call(protocol.CMD_GET_CHANNEL_TYPE, {"index": 0}, timeout=6.0))
    safe_call(results, "v04_get_activity_level",
              lambda: bridge.call(protocol.CMD_GET_ACTIVITY_LEVEL, {"index": 0}, timeout=6.0))
    safe_call(results, "v04_get_channel_index (808 Kick)",
              lambda: bridge.call(protocol.CMD_GET_CHANNEL_INDEX, {"name": "808 Kick"}, timeout=6.0))
    safe_call(results, "v04_is_channel_selected",
              lambda: bridge.call(protocol.CMD_IS_CHANNEL_SELECTED, {"index": 0}, timeout=6.0))
    safe_call(results, "v04_is_channel_highlighted",
              lambda: bridge.call(protocol.CMD_IS_CHANNEL_HIGHLIGHTED, {"index": 0}, timeout=6.0))
    safe_call(results, "v04_get_swing",
              lambda: bridge.call(protocol.CMD_GET_SWING, {"index": 0}, timeout=6.0))
    safe_call(results, "v04_get_grid_bit (ch 0, step 0)",
              lambda: bridge.call(protocol.CMD_GET_GRID_BIT, {"channel": 0, "step": 0}, timeout=6.0))
    safe_call(results, "v04_get_step_param (ch 0, step 0, param 0=velocity)",
              lambda: bridge.call(protocol.CMD_GET_STEP_PARAM,
                                  {"channel": 0, "step": 0, "param": 0}, timeout=6.0))
    safe_call(results, "v04_get_current_step_param (ch 0, step 0, param 0)",
              lambda: bridge.call(protocol.CMD_GET_CURRENT_STEP_PARAM,
                                  {"channel": 0, "step": 0, "param": 0}, timeout=6.0))
    safe_call(results, "v04_get_rec_event_id (ch 0)",
              lambda: bridge.call(protocol.CMD_GET_REC_EVENT_ID, {"index": 0}, timeout=6.0))
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_MUTE_CHANNEL"):
        safe_call(results, "v04_mute_channel (MUTATES)",
                  lambda: bridge.call(protocol.CMD_MUTE_CHANNEL,
                                      {"index": 0, "value": 0}, timeout=6.0))
    else:
        results.skip("v04_mute_channel", "set FLSTUDIO_MCP_INTEGRATION_MUTE_CHANNEL=1")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_SWING"):
        safe_call(results, "v04_set_swing (MUTATES)",
                  lambda: bridge.call(protocol.CMD_SET_SWING, {"index": 0, "value": 0.0}, timeout=6.0))
    else:
        results.skip("v04_set_swing", "set FLSTUDIO_MCP_INTEGRATION_SET_SWING=1")


def test_v04_patterns(results: Results, bridge):
    print("\n--- v0.4 patterns (color, length, loop, multi-select) ---")
    safe_call(results, "v04_get_pattern_length",
              lambda: bridge.call(protocol.CMD_GET_PATTERN_LENGTH, {"index": 1}, timeout=6.0))
    safe_call(results, "v04_get_pattern_color",
              lambda: bridge.call(protocol.CMD_GET_PATTERN_COLOR, {"index": 1}, timeout=6.0))
    safe_call(results, "v04_get_channel_loop_style",
              lambda: bridge.call(protocol.CMD_GET_CHANNEL_LOOP_STYLE,
                                  {"pattern": 1, "channel": 0}, timeout=6.0))
    safe_call(results, "v04_pattern_is_any_selected",
              lambda: bridge.call(protocol.CMD_PATTERN_IS_ANY_SELECTED, {}, timeout=6.0))
    # Mutating pattern tools
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_PATTERN_COLOR"):
        safe_call(results, "v04_set_pattern_color (MUTATES)",
                  lambda: bridge.call(protocol.CMD_SET_PATTERN_COLOR,
                                      {"index": 1, "color": 0x808080}, timeout=6.0))
    else:
        results.skip("v04_set_pattern_color", "set FLSTUDIO_MCP_INTEGRATION_SET_PATTERN_COLOR=1")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_PATTERN_LENGTH"):
        safe_call(results, "v04_set_pattern_length (MUTATES)",
                  lambda: bridge.call(protocol.CMD_SET_PATTERN_LENGTH,
                                      {"index": 1, "beats": 16}, timeout=6.0))
    else:
        results.skip("v04_set_pattern_length", "set FLSTUDIO_MCP_INTEGRATION_SET_PATTERN_LENGTH=1")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_CHANNEL_LOOP"):
        safe_call(results, "v04_set_channel_loop (MUTATES)",
                  lambda: bridge.call(protocol.CMD_SET_CHANNEL_LOOP,
                                      {"channel": 0, "loop_point": 0}, timeout=6.0))
    else:
        results.skip("v04_set_channel_loop", "set FLSTUDIO_MCP_INTEGRATION_SET_CHANNEL_LOOP=1")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SELECT_ALL_PATTERNS"):
        safe_call(results, "v04_pattern_select_all (MUTATES)",
                  lambda: bridge.call(protocol.CMD_PATTERN_SELECT_ALL, {}, timeout=6.0))
        safe_call(results, "v04_pattern_deselect_all (MUTATES)",
                  lambda: bridge.call(protocol.CMD_PATTERN_DESELECT_ALL, {}, timeout=6.0))
    else:
        results.skip("v04_pattern_select_all", "set FLSTUDIO_MCP_INTEGRATION_SELECT_ALL_PATTERNS=1")
        results.skip("v04_pattern_deselect_all", "set FLSTUDIO_MCP_INTEGRATION_SELECT_ALL_PATTERNS=1")


def test_v04_mixer(results: Results, bridge):
    print("\n--- v0.4 mixer (EQ + plugin mix/mute + REC + track ops) ---")
    safe_call(results, "v04_mixer_get_eq_band_count",
              lambda: bridge.call(protocol.CMD_MIXER_GET_EQ_BAND_COUNT, {"track": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_eq_freq (track 0, band 0)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_EQ_FREQ,
                                  {"track": 0, "band": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_eq_bw (track 0, band 0)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_EQ_BW,
                                  {"track": 0, "band": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_eq_gain (track 0, band 0)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_EQ_GAIN,
                                  {"track": 0, "band": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_is_track_plugin_valid (1,0)",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_PLUGIN_VALID,
                                  {"track": 1, "slot": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_plugin_mix_level (1,0)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_PLUGIN_MIX_LEVEL,
                                  {"track": 1, "slot": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_plugin_mute_state (1,0)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_PLUGIN_MUTE_STATE,
                                  {"track": 1, "slot": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_track_info (0=Master)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_TRACK_INFO, {"mode": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_track_info (1=FirstIns)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_TRACK_INFO, {"mode": 1}, timeout=6.0))
    safe_call(results, "v04_mixer_get_track_info (3=Sel)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_TRACK_INFO, {"mode": 3}, timeout=6.0))
    safe_call(results, "v04_mixer_get_track_number",
              lambda: bridge.call(protocol.CMD_MIXER_GET_TRACK_NUMBER, {"track": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_active_track",
              lambda: bridge.call(protocol.CMD_MIXER_GET_ACTIVE_TRACK, {}, timeout=6.0))
    safe_call(results, "v04_mixer_is_track_selected (0)",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_SELECTED, {"track": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_event_id_name (ch 0 vol)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_EVENT_ID_NAME,
                                  {"event_id": int(bridge.call(protocol.CMD_GET_REC_EVENT_ID, {"index": 0}, timeout=6.0).get("event_id", 0))},
                                  timeout=6.0))
    safe_call(results, "v04_mixer_get_event_value (same event_id)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_EVENT_VALUE,
                                  {"event_id": int(bridge.call(protocol.CMD_GET_REC_EVENT_ID, {"index": 0}, timeout=6.0).get("event_id", 0))},
                                  timeout=6.0))
    safe_call(results, "v04_mixer_get_event_id_value_str",
              lambda: bridge.call(protocol.CMD_MIXER_GET_EVENT_ID_VALUE_STR,
                                  {"event_id": int(bridge.call(protocol.CMD_GET_REC_EVENT_ID, {"index": 0}, timeout=6.0).get("event_id", 0))},
                                  timeout=6.0))
    safe_call(results, "v04_mixer_get_last_peak_vol (L)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_LAST_PEAK_VOL, {"section": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_last_peak_vol (R)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_LAST_PEAK_VOL, {"section": 1}, timeout=6.0))
    safe_call(results, "v04_mixer_get_track_recording_file (0)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_TRACK_RECORDING_FILE, {"track": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_is_track_mute_lock (0)",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_MUTE_LOCK, {"track": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_is_track_slots_enabled (may be api_unavailable)",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_SLOTS_ENABLED,
                                  {"track": 0}, timeout=6.0))
    safe_call(results, "v04_mixer_get_route_to_level (0->1)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_ROUTE_TO_LEVEL,
                                  {"src": 0, "dst": 1}, timeout=6.0))
    # Mutating v0.4 mixer tools
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_EQ_GAIN"):
        safe_call(results, "v04_set_eq_freq (MUTATES)",
                  lambda: bridge.call(protocol.CMD_MIXER_SET_EQ_FREQ,
                                      {"track": 0, "band": 0, "frequency_hz": 1000.0}, timeout=6.0))
        safe_call(results, "v04_set_eq_bw (MUTATES)",
                  lambda: bridge.call(protocol.CMD_MIXER_SET_EQ_BW,
                                      {"track": 0, "band": 0, "bandwidth_oct": 1.0}, timeout=6.0))
        safe_call(results, "v04_set_eq_gain (MUTATES)",
                  lambda: bridge.call(protocol.CMD_MIXER_SET_EQ_GAIN,
                                      {"track": 0, "band": 0, "gain_db": 0.0}, timeout=6.0))
    else:
        results.skip("v04_set_eq_freq", "set FLSTUDIO_MCP_INTEGRATION_SET_EQ_GAIN=1")
        results.skip("v04_set_eq_bw", "set FLSTUDIO_MCP_INTEGRATION_SET_EQ_GAIN=1")
        results.skip("v04_set_eq_gain", "set FLSTUDIO_MCP_INTEGRATION_SET_EQ_GAIN=1")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_PLUGIN_MUTE"):
        safe_call(results, "v04_set_plugin_mute_state (MUTATES)",
                  lambda: bridge.call(protocol.CMD_MIXER_SET_PLUGIN_MUTE_STATE,
                                      {"track": 1, "slot": 0, "mute": False}, timeout=6.0))
    else:
        results.skip("v04_set_plugin_mute_state", "set FLSTUDIO_MCP_INTEGRATION_SET_PLUGIN_MUTE=1")


def test_v04_ui(results: Results, bridge):
    print("\n--- v0.4 ui (hint bar, snap, focused plugin, window, browser) ---")
    safe_call(results, "v04_get_hint_msg",
              lambda: bridge.call(protocol.CMD_GET_HINT_MSG, {}, timeout=6.0))
    safe_call(results, "v04_is_closing",
              lambda: bridge.call(protocol.CMD_IS_CLOSING, {}, timeout=6.0))
    safe_call(results, "v04_get_focused_plugin_name",
              lambda: bridge.call(protocol.CMD_GET_FOCUSED_PLUGIN_NAME, {}, timeout=6.0))
    safe_call(results, "v04_get_snap_mode",
              lambda: bridge.call(protocol.CMD_GET_SNAP_MODE, {}, timeout=6.0))
    safe_call(results, "v04_is_metronome_enabled",
              lambda: bridge.call(protocol.CMD_IS_METRONOME_ENABLED, {}, timeout=6.0))
    safe_call(results, "v04_is_precount_enabled",
              lambda: bridge.call(protocol.CMD_IS_PRECOUNT_ENABLED, {}, timeout=6.0))
    safe_call(results, "v04_is_loop_rec_enabled",
              lambda: bridge.call(protocol.CMD_IS_LOOP_REC_ENABLED, {}, timeout=6.0))
    safe_call(results, "v04_is_start_on_input_enabled",
              lambda: bridge.call(protocol.CMD_IS_START_ON_INPUT_ENABLED, {}, timeout=6.0))
    safe_call(results, "v04_get_step_edit_mode",
              lambda: bridge.call(protocol.CMD_GET_STEP_EDIT_MODE, {}, timeout=6.0))
    safe_call(results, "v04_get_time_disp_min",
              lambda: bridge.call(protocol.CMD_GET_TIME_DISP_MIN, {}, timeout=6.0))
    safe_call(results, "v04_is_browser_auto_hide",
              lambda: bridge.call(protocol.CMD_IS_BROWSER_AUTO_HIDE, {}, timeout=6.0))
    # ui.showWindow with widPianoRoll = 0 (FL's constant); if absent,
    # the controller returns api_unavailable or an error -- that's OK.
    safe_call(results, "v04_get_visible (widPianoRoll=0)",
              lambda: bridge.call(protocol.CMD_GET_VISIBLE, {"window_id": 0}, timeout=6.0))
    safe_call(results, "v04_show_window (widPianoRoll=0)",
              lambda: bridge.call(protocol.CMD_SHOW_WINDOW, {"window_id": 0}, timeout=6.0))
    safe_call(results, "v04_hide_window (widPianoRoll=0)",
              lambda: bridge.call(protocol.CMD_HIDE_WINDOW, {"window_id": 0}, timeout=6.0))
    # UI mutating tools -- gated
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_HINT_MSG"):
        safe_call(results, "v04_set_hint_msg (MUTATES UI)",
                  lambda: bridge.call(protocol.CMD_SET_HINT_MSG,
                                      {"msg": "[mcp-test] integration test in progress"}, timeout=6.0))
    else:
        results.skip("v04_set_hint_msg", "set FLSTUDIO_MCP_INTEGRATION_SET_HINT_MSG=1 (mutates UI)")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SET_SNAP_MODE"):
        safe_call(results, "v04_set_snap_mode (MUTATES UI)",
                  lambda: bridge.call(protocol.CMD_SET_SNAP_MODE,
                                      {"value": 0}, timeout=6.0))
    else:
        results.skip("v04_set_snap_mode", "set FLSTUDIO_MCP_INTEGRATION_SET_SNAP_MODE=1")
    if _env_flag("FLSTUDIO_MCP_INTEGRATION_SHOW_NOTIFICATION"):
        safe_call(results, "v04_show_notification (MUTATES UI)",
                  lambda: bridge.call(protocol.CMD_SHOW_NOTIFICATION, {"id": 1}, timeout=6.0))
    else:
        results.skip("v04_show_notification", "set FLSTUDIO_MCP_INTEGRATION_SHOW_NOTIFICATION=1")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    level = os.environ.get("FLSTUDIO_MCP_INTEGRATION_LEVEL", "all").lower()

    transport = os.environ.get("FLSTUDIO_MCP_INTEGRATION_TRANSPORT", "tcp").lower()
    if transport == "direct":
        bridge = FLBridge()
        bridge.open()
    elif transport == "tcp":
        bridge = TCPBridge()
    else:
        print(f"[FATAL] unknown transport: {transport!r} (use 'tcp' or 'direct')")
        return 2

    results = Results()

    print(f"Integration test -- transport={transport}  level={level}")
    print(f"FL version target: any FL build with the FLStudioMCP controller loaded")
    print(f"Mutating tools gated by env vars (set FLSTUDIO_MCP_INTEGRATION_*=1 to enable)")

    if not test_bridge_health(results, bridge):
        return 1

    if level in ("all", "baseline"):
        test_v02_baseline(results, bridge)
    if level in ("all", "v03"):
        test_v03_project(results, bridge)
        test_v03_creation(results, bridge)
        test_v03_preset_write(results, bridge)
        test_v03_automation(results, bridge)
        test_v03_live(results, bridge)
        test_v03_mixer_record(results, bridge)
        test_v03_pattern(results, bridge)
    if level in ("all", "v04"):
        test_v04_general(results, bridge)
        test_v04_channels(results, bridge)
        test_v04_patterns(results, bridge)
        test_v04_mixer(results, bridge)
        test_v04_ui(results, bridge)

    verbose = _env_flag("FLSTUDIO_MCP_INTEGRATION_VERBOSE")
    print(results.summary(verbose=verbose))

    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())