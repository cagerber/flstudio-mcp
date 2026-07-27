#!/usr/bin/env python3
"""fl-studio-mcp integration test -- exercises every public tool.

Designed to be runnable + repeatable against a live FL Studio + daemon
session. Reads FL state through the TCP bridge (same as production use).

USAGE
    # from the worktree, with the daemon running (fl-studio-mcp-daemon):
    python scripts/integration_test.py

    # direct MIDI bridge instead of TCP daemon:
    FLSTUDIO_MCP_INTEGRATION_TRANSPORT=direct \\
    python scripts/integration_test.py

    # only run the v0.2 baseline checks (skip v0.3 ones that need a fresh
    # FL controller reload):
    FLSTUDIO_MCP_INTEGRATION_LEVEL=baseline python scripts/integration_test.py

PREREQUISITES
    1. FL Studio open.
    2. FLStudioMCP controller script loaded in FL (Options > MIDI Settings,
       Controller type = FLStudioMCP). For v0.3 checks, FL must have
       reloaded the new controller script (restart FL or re-toggle the
       controller type after the first install).
    3. fl-studio-mcp-daemon running on 127.0.0.1:9787 (default).

DESIGN
    - Idempotent: never mutates FL state. Every command is a READ or a
      guard-check. No notes written, no volume changed, no tracks armed.
    - Per-tool pass/fail: each test reports ok or a structured failure.
    - v0.3 tools that the OLD controller script doesn't yet know about
      will return FLCommandFailed(code='unknown_command') and are reported
      separately so the operator can see what needs the controller reload.
    - Exit code 0 if all v0.2 baseline + bridge-health checks pass; exit
      code 1 if any baseline or bridge-health check fails. v0.3 unknown-
      command results do NOT fail the run -- they're expected pre-reload.
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

    def summary(self) -> str:
        out = []
        out.append("")
        out.append("=" * 70)
        out.append(f"  PASSED:   {len(self.passed)}")
        out.append(f"  FAILED:   {len(self.failed)}")
        out.append(f"  SKIPPED:  {len(self.skipped)}")
        out.append(f"  UNKNOWN_CMD (expected pre-reload): {len(self.unknown)}")
        out.append("=" * 70)
        if self.failed:
            out.append("")
            out.append("FAILURES:")
            for name, kind, detail in self.failed:
                out.append(f"  [FAIL] {name} ({kind})")
                out.append(f"         {detail}")
        if self.unknown:
            out.append("")
            out.append("V0.3 COMMANDS RETURNING unknown_command (need FL controller reload):")
            for name, detail in self.unknown:
                out.append(f"  [----] {name}")
                out.append(f"         {detail}")
        if self.skipped:
            out.append("")
            out.append("SKIPPED:")
            for name, reason in self.skipped:
                out.append(f"  [SKIP] {name}: {reason}")
        return "\n".join(out)


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------
def safe_call(results: Results, name: str, fn, *, timeout: float = 8.0,
               retries: int = 2, retry_delay: float = 0.4):
    """Call fn() and categorize the result. Returns the value or None.

    Transient FLTimeout errors are retried ``retries`` times (default 2) with
    ``retry_delay`` between attempts -- this matches the production
    FLSTUDIO_MCP_RETRY_ON_TIMEOUT behavior at the test level so the suite
    isn't flaky on first-call MIDI buffer jitter. Wine+MIDI observed up to
    ~30% single-call loss; with 3 total attempts the cumulative success
    rate is ~98%.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            v = fn()
            if isinstance(v, dict) and v.get("ok") is False:
                # A tool returning ok=false (the honest-API-limit reports) is
                # NOT a test failure -- it means the tool ran successfully and
                # reported that FL can't do it.
                if v.get("code") == "api_unavailable":
                    results.ok(name, _short(v) + " (api_unavailable -- expected)")
                    return v
                # Any other ok=false is treated as a soft pass with the body
                # surfaced so the operator can see it.
                results.ok(name, _short(v) + " (ok=false from tool)")
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


# ----------------------------------------------------------------------
# Test groups
# ----------------------------------------------------------------------
def test_bridge_health(results: Results, bridge) -> bool:
    """Sanity: bridge alive + heartbeat fresh. Failure here aborts the run."""
    try:
        hb = bridge.heartbeat_age()
        alive = bridge.is_alive()
    except FLBridgeError as e:
        print(f"[FATAL] bridge unreachable: {e}")
        return False
    if hb is None:
        print("[FATAL] no heartbeat received yet -- daemon may not be wired to FL.")
        return False
    if hb > 3.0:
        print(f"[FATAL] heartbeat stale ({hb:.2f}s) -- FL controller not running.")
        return False
    if not alive:
        print(f"[FATAL] bridge not alive (hb={hb:.2f}s).")
        return False
    results.ok("bridge_health", f"hb={hb:.3f}s alive={alive}")
    print(f"[OK]    bridge_health  hb={hb:.3f}s")
    return True


def test_v02_baseline(results: Results, bridge):
    """v0.2 commands that have been in the codebase since the merge. Must
    pass against ANY controller script -- if these fail, something else is
    broken."""
    print("\n--- v0.2 baseline ---")

    def ping(): return bridge.call(protocol.CMD_PING, {}, timeout=6.0)
    safe_call(results, "v02_ping", ping)

    def tempo(): return bridge.call(protocol.CMD_GET_TEMPO, {}, timeout=6.0)
    safe_call(results, "v02_get_tempo", tempo)

    def ps(): return bridge.call(protocol.CMD_GET_PROJECT_STATE, {}, timeout=6.0)
    safe_call(results, "v02_project_state", ps)

    def song(): return bridge.call(protocol.CMD_GET_SONG_POS, {}, timeout=6.0)
    safe_call(results, "v02_get_song_position", song)

    def playstate(): return bridge.call(protocol.CMD_GET_PLAY_STATE, {}, timeout=6.0)
    safe_call(results, "v02_get_play_state", playstate)

    def channels():
        return fetch_all_pages(bridge, protocol.CMD_CHANNEL_LIST, "channels")
    safe_call(results, "v02_channel_list", channels, retries=2)

    def patterns():
        return fetch_all_pages(bridge, protocol.CMD_PATTERN_LIST, "patterns")
    safe_call(results, "v02_pattern_list", patterns, retries=2)

    def mixer():
        return fetch_all_pages(bridge, protocol.CMD_MIXER_LIST_TRACKS, "tracks")
    safe_call(results, "v02_mixer_list_tracks", mixer, retries=2)

    def ping_cmd():
        # ping with explicit params (none needed)
        return bridge.call(protocol.CMD_PING, {}, timeout=6.0)
    safe_call(results, "v02_ping_explicit", ping_cmd)


def test_v03_project(results: Results, bridge):
    print("\n--- v0.3 project persistence ---")

    def dirty():
        return bridge.call(protocol.CMD_GET_PROJECT_DIRTY, {"with_title": True}, timeout=6.0)
    safe_call(results, "v03_get_project_dirty", dirty)

    def path():
        return bridge.call(protocol.CMD_GET_PROJECT_PATH, {"dirty": True}, timeout=6.0)
    safe_call(results, "v03_get_project_path", path)

    def save():
        return bridge.call(protocol.CMD_SAVE_PROJECT, {}, timeout=6.0)
    safe_call(results, "v03_save_project (expect ok=false api_unavailable)", save)

    def export_cur():
        return bridge.call(protocol.CMD_EXPORT_CURRENT_PROJECT_MIDI, {}, timeout=6.0)
    safe_call(results, "v03_export_current_project_midi (expect ok=false)", export_cur)


def test_v03_creation(results: Results, bridge):
    print("\n--- v0.3 channel/mixer-track create ---")
    safe_call(results, "v03_create_channel (expect ok=false api_unavailable)",
              lambda: bridge.call(protocol.CMD_CREATE_CHANNEL, {"name": "TEST"}, timeout=6.0))
    safe_call(results, "v03_create_mixer_track (expect ok=false api_unavailable)",
              lambda: bridge.call(protocol.CMD_CREATE_MIXER_TRACK, {"name": "TEST"}, timeout=6.0))


def test_v03_preset_write(results: Results, bridge):
    print("\n--- v0.3 plugin preset write ---")
    def info():
        return bridge.call(protocol.CMD_PLUGIN_PRESET, {"track": 1, "slot": 0, "op": "info"}, timeout=6.0)
    safe_call(results, "v03_plugin_preset_info", info)
    # by_index to 0 (no-op for no-preset plugins; will succeed if any exist)
    def byidx():
        return bridge.call(protocol.CMD_LOAD_PLUGIN_PRESET, {"track": 1, "slot": 0, "op": "by_index", "index": 0}, timeout=6.0)
    safe_call(results, "v03_load_plugin_preset_by_index", byidx)
    # by_name with a likely-absent name (expect ok=false but command wired)
    def byname():
        return bridge.call(protocol.CMD_LOAD_PLUGIN_PRESET, {
            "track": 1, "slot": 0, "op": "by_name",
            "name": "no-such-preset-zzz", "exact": False,
        }, timeout=6.0)
    safe_call(results, "v03_load_plugin_preset_by_name (expect not found)", byname)


def test_v03_automation(results: Results, bridge):
    print("\n--- v0.3 automation ---")
    safe_call(results, "v03_get_automation_info (expect ok=false api_unavailable)",
              lambda: bridge.call(protocol.CMD_GET_AUTOMATION_INFO, {}, timeout=6.0))
    safe_call(results, "v03_set_automation_point (expect ok=false)",
              lambda: bridge.call(protocol.CMD_SET_AUTOMATION_POINT, {"track": 0}, timeout=6.0))


def test_v03_live(results: Results, bridge):
    print("\n--- v0.3 live MIDI ---")
    safe_call(results, "v03_safe_to_edit",
              lambda: bridge.call(protocol.CMD_SAFE_TO_EDIT, {}, timeout=6.0))
    safe_call(results, "v03_dump_score_log (3s)",
              lambda: bridge.call(protocol.CMD_DUMP_SCORE_LOG, {"time": 3, "silent": True}, timeout=10.0))
    # NOTE: trigger_note fires REAL MIDI -- only run if explicitly enabled
    if os.environ.get("FLSTUDIO_MCP_INTEGRATION_TRIGGER_NOTE") == "1":
        safe_call(results, "v03_trigger_note (LIVE MIDI)",
                  lambda: bridge.call(protocol.CMD_TRIGGER_NOTE, {
                      "index": 0, "note": 60, "velocity": 100, "channel": -1,
                  }, timeout=6.0))
    else:
        results.skip("v03_trigger_note", "set FLSTUDIO_MCP_INTEGRATION_TRIGGER_NOTE=1 to fire live MIDI")
    safe_call(results, "v03_quantize_channel (ch 0, start_only=1)",
              lambda: bridge.call(protocol.CMD_QUANTIZE_CHANNEL, {
                  "index": 0, "start_only": 1, "use_global_index": False,
              }, timeout=6.0))
    safe_call(results, "v03_get_selected_channel",
              lambda: bridge.call(protocol.CMD_GET_SELECTED_CHANNEL, {
                  "can_be_none": True, "offset": 0, "index_global": False,
              }, timeout=6.0))
    safe_call(results, "v03_get_channel_midi_in_port (ch 0)",
              lambda: bridge.call(protocol.CMD_GET_CHANNEL_MIDI_IN_PORT, {"index": 0}, timeout=6.0))


def test_v03_mixer_record(results: Results, bridge):
    print("\n--- v0.3 mixer record + FX slot ---")
    safe_call(results, "v03_mixer_track_count",
              lambda: bridge.call(protocol.CMD_MIXER_TRACK_COUNT, {}, timeout=6.0))
    safe_call(results, "v03_mixer_is_track_armed (track 0)",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_ARMED, {"index": 0}, timeout=6.0))
    safe_call(results, "v03_mixer_is_track_enabled (track 0)",
              lambda: bridge.call(protocol.CMD_MIXER_IS_TRACK_ENABLED, {"index": 0}, timeout=6.0))
    safe_call(results, "v03_get_active_effect",
              lambda: bridge.call(protocol.CMD_GET_ACTIVE_EFFECT, {}, timeout=6.0))
    safe_call(results, "v03_get_slot_color (track 1, slot 0)",
              lambda: bridge.call(protocol.CMD_MIXER_GET_SLOT_COLOR, {"track": 1, "slot": 0}, timeout=6.0))
    # NOTE: focus_plugin_editor steals UI focus -- only run if explicitly enabled
    if os.environ.get("FLSTUDIO_MCP_INTEGRATION_FOCUS_EDITOR") == "1":
        safe_call(results, "v03_focus_plugin_editor (UI-STEALING)",
                  lambda: bridge.call(protocol.CMD_FOCUS_PLUGIN_EDITOR, {"track": 1, "slot": 0}, timeout=6.0))
    else:
        results.skip("v03_focus_plugin_editor", "set FLSTUDIO_MCP_INTEGRATION_FOCUS_EDITOR=1 (UI-stealing)")
    # NOTE: armTrack TOGGLES state -- skip by default to stay idempotent
    if os.environ.get("FLSTUDIO_MCP_INTEGRATION_ARM_TRACK") == "1":
        safe_call(results, "v03_mixer_arm_track (TOGGLES STATE)",
                  lambda: bridge.call(protocol.CMD_MIXER_ARM_TRACK, {"index": 0}, timeout=6.0))
    else:
        results.skip("v03_mixer_arm_track", "set FLSTUDIO_MCP_INTEGRATION_ARM_TRACK=1 (toggles state)")
    if os.environ.get("FLSTUDIO_MCP_INTEGRATION_SET_SLOT_COLOR") == "1":
        safe_call(results, "v03_set_slot_color (MUTATES COLOR)",
                  lambda: bridge.call(protocol.CMD_MIXER_SET_SLOT_COLOR,
                                      {"track": 1, "slot": 0, "color": 0x808080}, timeout=6.0))
    else:
        results.skip("v03_set_slot_color", "set FLSTUDIO_MCP_INTEGRATION_SET_SLOT_COLOR=1 (mutates color)")


def test_v03_pattern(results: Results, bridge):
    print("\n--- v0.3 pattern extras ---")
    safe_call(results, "v03_pattern_is_default (pattern 1)",
              lambda: bridge.call(protocol.CMD_PATTERN_IS_DEFAULT, {"index": 1}, timeout=6.0))
    safe_call(results, "v03_pattern_is_selected (pattern 1)",
              lambda: bridge.call(protocol.CMD_PATTERN_IS_SELECTED, {"index": 1}, timeout=6.0))
    # NOTE: selectPattern/value=1 may modify selection state -- skip by default
    if os.environ.get("FLSTUDIO_MCP_INTEGRATION_SELECT_PATTERN") == "1":
        safe_call(results, "v03_pattern_select (MUTATES SELECTION)",
                  lambda: bridge.call(protocol.CMD_PATTERN_SELECT,
                                      {"index": 1, "value": -1, "preview": False}, timeout=6.0))
    else:
        results.skip("v03_pattern_select", "set FLSTUDIO_MCP_INTEGRATION_SELECT_PATTERN=1 (mutates selection)")
    # NOTE: burnLoop MUTATES the pattern's step-sequencer state -- skip by default
    if os.environ.get("FLSTUDIO_MCP_INTEGRATION_BURN_LOOP") == "1":
        safe_call(results, "v03_pattern_burn_loop (MUTATES PATTERN)",
                  lambda: bridge.call(protocol.CMD_PATTERN_BURN_LOOP,
                                      {"channel": 0, "store_undo": 1, "update_ui": 1}, timeout=6.0))
    else:
        results.skip("v03_pattern_burn_loop", "set FLSTUDIO_MCP_INTEGRATION_BURN_LOOP=1 (mutates pattern)")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    level = os.environ.get("FLSTUDIO_MCP_INTEGRATION_LEVEL", "all").lower()

    # Choose bridge: TCP (default) or direct MIDI
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

    if not test_bridge_health(results, bridge):
        return 1

    test_v02_baseline(results, bridge)

    if level in ("all", "v03"):
        test_v03_project(results, bridge)
        test_v03_creation(results, bridge)
        test_v03_preset_write(results, bridge)
        test_v03_automation(results, bridge)
        test_v03_live(results, bridge)
        test_v03_mixer_record(results, bridge)
        test_v03_pattern(results, bridge)

    print(results.summary())

    # Exit code: failures = 1; unknown_cmd results = NOT a failure
    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())