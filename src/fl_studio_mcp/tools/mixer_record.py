"""Mixer record + FX-slot helpers (v0.3, stubs-found additions).

Found via FL-Studio-API-Stubs + live probe:
  - mixer.isTrackArmed / mixer.armTrack -- record-arm a mixer track.
  - mixer.isTrackEnabled -- 'functionally identical to not isTrackMuted'.
  - mixer.trackCount() -- FL's view of total tracks (master + current).
  - mixer.getActiveEffectIndex -- which plugin is currently focused.
  - mixer.focusEditor -- open a plugin's UI editor (UI-stealing).
  - mixer.getSlotColor / mixer.setSlotColor -- FX slot coloring.
"""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol
from ..connection import get_bridge


def register(mcp: FastMCP) -> None:
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
    _WR = {"readOnlyHint": False, "destructiveHint": False,
           "idempotentHint": False, "openWorldHint": True}

    @mcp.tool(annotations={"title": "Is mixer track armed for recording?", **_RO})
    def fl_mixer_is_track_armed(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
    ) -> dict:
        """Returns True if the mixer track is armed for recording."""
        return get_bridge().call(protocol.CMD_MIXER_IS_TRACK_ARMED, {"index": track})

    @mcp.tool(annotations={"title": "Toggle record-arm on mixer track", **_WR})
    def fl_mixer_arm_track(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
    ) -> dict:
        """Toggle record-arm on a mixer track. Read state first with
        fl_mixer_is_track_armed; this call flips it."""
        return get_bridge().call(protocol.CMD_MIXER_ARM_TRACK, {"index": track})

    @mcp.tool(annotations={"title": "Is mixer track enabled?", **_RO})
    def fl_mixer_is_track_enabled(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
    ) -> dict:
        """Returns True if the mixer track is enabled. Documented as
        'functionally identical to not isTrackMuted'."""
        return get_bridge().call(protocol.CMD_MIXER_IS_TRACK_ENABLED, {"index": track})

    @mcp.tool(annotations={"title": "Get FL's view of mixer track count", **_RO})
    def fl_mixer_track_count() -> dict:
        """Return FL's mixer track count (includes Master + Current). May
        differ from the count of named tracks; use this for raw index
        validation."""
        return get_bridge().call(protocol.CMD_MIXER_TRACK_COUNT, {})

    @mcp.tool(annotations={"title": "Get the currently-focused effect plugin", **_RO})
    def fl_get_active_effect() -> dict:
        """Return (track, slot) of the currently-focused effect plugin, or
        None if no plugin is focused. Useful for 'what did the user just
        click on?' automation."""
        return get_bridge().call(protocol.CMD_GET_ACTIVE_EFFECT, {})

    @mcp.tool(annotations={"title": "Focus a plugin's editor (UI-stealing)", **_WR})
    def fl_focus_plugin_editor(
        track: Annotated[int, Field(ge=0, description="Mixer track index of plugin.")],
        slot: Annotated[int, Field(ge=0, le=9, description="FX slot 0-9 of plugin.")],
    ) -> dict:
        """Focus the plugin's UI editor in FL. WARNING: this STICKS focus
        on the plugin and may steal keystrokes from the user. Intended
        for single programmatic invocations, not chained tool calls."""
        return get_bridge().call(protocol.CMD_FOCUS_PLUGIN_EDITOR, {
            "track": track, "slot": slot,
        })

    @mcp.tool(annotations={"title": "Get FX slot color", **_RO})
    def fl_get_slot_color(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
        slot: Annotated[int, Field(ge=0, le=9, description="FX slot 0-9.")],
    ) -> dict:
        """Return the color of an FX slot on a mixer track (0xBBGGRR)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_SLOT_COLOR, {
            "track": track, "slot": slot,
        })

    @mcp.tool(annotations={"title": "Set FX slot color", **_WR})
    def fl_set_slot_color(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
        slot: Annotated[int, Field(ge=0, le=9, description="FX slot 0-9.")],
        color: Annotated[int, Field(
            description="Color as 0xRRGGBB (alpha-prefixed int); FL stores 0x--BBGGRR."
        )],
    ) -> dict:
        """Color an FX slot on a mixer track. Pairs with the existing
        fl_set_mixer_color / fl_set_channel_color."""
        return get_bridge().call(protocol.CMD_MIXER_SET_SLOT_COLOR, {
            "track": track, "slot": slot, "color": color,
        })