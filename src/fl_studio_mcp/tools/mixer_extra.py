"""Mixer parametric EQ + REC event helpers + track ops (v0.4).

This is the big one -- the mixer's parametric EQ is the most useful tool
for any EQ-driven mix work, and it's fully scriptable via the API.

Verified live on FL 26.1.2 build 5557:
  - mixer.getEqBandCount / getEqFrequency / setEqFrequency
  - mixer.getEqBandwidth / setEqBandwidth
  - mixer.getEqGain / setEqGain
  - mixer.getTrackPluginId / isTrackPluginValid
  - mixer.getPluginMixLevel / setPluginMixLevel
  - mixer.getPluginMuteState / setPluginMuteState
  - mixer.getTrackInfo(mode) -- TN_Master / TN_FirstIns / TN_LastIns / TN_Sel
  - mixer.getTrackNumber / setTrackNumber
  - mixer.trackNumber / setActiveTrack
  - mixer.isTrackSelected / selectTrack / selectAll / deselectAll
  - mixer.getEventValue / getEventIDName / getEventIDValueString
  - mixer.automateEvent
  - mixer.enableTrack / enableTrackSlots
  - mixer.isTrackMuteLock
  - mixer.getLastPeakVol
  - mixer.getAutoSmoothEventValue / remoteFindEventValue
  - mixer.linkChannelToTrack / linkTrackToChannel
  - mixer.getRouteToLevel
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol
from ..connection import get_bridge


def register(mcp: FastMCP) -> None:
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
    _WR = {"readOnlyHint": False, "destructiveHint": False,
           "idempotentHint": True, "openWorldHint": True}

    # ------------------------------------------------------------------
    # Parametric EQ (the meat of mixer control)
    # ------------------------------------------------------------------

    @mcp.tool(annotations={"title": "Get mixer EQ band count", **_RO})
    def fl_mixer_get_eq_band_count(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
    ) -> dict:
        """Number of EQ bands available on this track's parametric EQ."""
        return get_bridge().call(protocol.CMD_MIXER_GET_EQ_BAND_COUNT,
                                  {"track": track})

    @mcp.tool(annotations={"title": "Get mixer EQ frequency", **_RO})
    def fl_mixer_get_eq_freq(
        track: Annotated[int, Field(ge=0)],
        band: Annotated[int, Field(ge=0, description="EQ band index (0-based).")],
    ) -> dict:
        """Get the center frequency (Hz) of an EQ band."""
        return get_bridge().call(protocol.CMD_MIXER_GET_EQ_FREQ,
                                  {"track": track, "band": band})

    @mcp.tool(annotations={"title": "Set mixer EQ frequency", **_WR})
    def fl_mixer_set_eq_freq(
        track: Annotated[int, Field(ge=0)],
        band: Annotated[int, Field(ge=0, description="EQ band index (0-based).")],
        frequency_hz: Annotated[float, Field(ge=20.0, le=20000.0,
            description="Center frequency in Hz (20..20000).")],
    ) -> dict:
        """Set the center frequency (Hz) of an EQ band."""
        return get_bridge().call(protocol.CMD_MIXER_SET_EQ_FREQ,
                                  {"track": track, "band": band,
                                   "frequency_hz": frequency_hz})

    @mcp.tool(annotations={"title": "Get mixer EQ bandwidth", **_RO})
    def fl_mixer_get_eq_bw(
        track: Annotated[int, Field(ge=0)],
        band: Annotated[int, Field(ge=0, description="EQ band index.")],
    ) -> dict:
        """Get the bandwidth (octaves) of an EQ band."""
        return get_bridge().call(protocol.CMD_MIXER_GET_EQ_BW,
                                  {"track": track, "band": band})

    @mcp.tool(annotations={"title": "Set mixer EQ bandwidth", **_WR})
    def fl_mixer_set_eq_bw(
        track: Annotated[int, Field(ge=0)],
        band: Annotated[int, Field(ge=0)],
        bandwidth_oct: Annotated[float, Field(ge=0.1, le=10.0,
            description="Bandwidth in octaves (0.1..10.0).")],
    ) -> dict:
        """Set the bandwidth (Q factor) of an EQ band."""
        return get_bridge().call(protocol.CMD_MIXER_SET_EQ_BW,
                                  {"track": track, "band": band,
                                   "bandwidth_oct": bandwidth_oct})

    @mcp.tool(annotations={"title": "Get mixer EQ gain", **_RO})
    def fl_mixer_get_eq_gain(
        track: Annotated[int, Field(ge=0)],
        band: Annotated[int, Field(ge=0)],
    ) -> dict:
        """Get the gain (dB) of an EQ band."""
        return get_bridge().call(protocol.CMD_MIXER_GET_EQ_GAIN,
                                  {"track": track, "band": band})

    @mcp.tool(annotations={"title": "Set mixer EQ gain", **_WR})
    def fl_mixer_set_eq_gain(
        track: Annotated[int, Field(ge=0)],
        band: Annotated[int, Field(ge=0)],
        gain_db: Annotated[float, Field(ge=-36.0, le=36.0,
            description="Gain in dB (-36..+36).")],
    ) -> dict:
        """Set the gain (dB) of an EQ band."""
        return get_bridge().call(protocol.CMD_MIXER_SET_EQ_GAIN,
                                  {"track": track, "band": band, "gain_db": gain_db})

    # ------------------------------------------------------------------
    # Plugin metadata (slot-level read)
    # ------------------------------------------------------------------

    @mcp.tool(annotations={"title": "Get plugin ID at mixer slot", **_RO})
    def fl_mixer_get_track_plugin_id(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=0, le=9, description="FX slot 0-9.")],
    ) -> dict:
        """Returns the plugin ID (FL's internal type ID) at the slot."""
        return get_bridge().call(protocol.CMD_MIXER_GET_TRACK_PLUGIN_ID,
                                  {"track": track, "slot": slot})

    @mcp.tool(annotations={"title": "Is mixer slot plugin valid?", **_RO})
    def fl_mixer_is_track_plugin_valid(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=0, le=9)],
    ) -> dict:
        """Returns True if a real plugin is loaded at the slot (vs empty)."""
        return get_bridge().call(protocol.CMD_MIXER_IS_TRACK_PLUGIN_VALID,
                                  {"track": track, "slot": slot})

    @mcp.tool(annotations={"title": "Get plugin mix level", **_RO})
    def fl_mixer_get_plugin_mix_level(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=0, le=9)],
    ) -> dict:
        """Returns the plugin's dry/wet mix level (0.0..1.0)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_PLUGIN_MIX_LEVEL,
                                  {"track": track, "slot": slot})

    @mcp.tool(annotations={"title": "Set plugin mix level", **_WR})
    def fl_mixer_set_plugin_mix_level(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=0, le=9)],
        level: Annotated[float, Field(ge=0.0, le=1.0, description="Mix level 0.0..1.0.")],
    ) -> dict:
        """Set the plugin's dry/wet mix level."""
        return get_bridge().call(protocol.CMD_MIXER_SET_PLUGIN_MIX_LEVEL,
                                  {"track": track, "slot": slot, "level": level})

    @mcp.tool(annotations={"title": "Get plugin mute state", **_RO})
    def fl_mixer_get_plugin_mute_state(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=0, le=9)],
    ) -> dict:
        """Returns True if the plugin is bypassed (mute state)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_PLUGIN_MUTE_STATE,
                                  {"track": track, "slot": slot})

    @mcp.tool(annotations={"title": "Set plugin mute state", **_WR})
    def fl_mixer_set_plugin_mute_state(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=0, le=9)],
        mute: Annotated[bool, Field(description="True to bypass (mute) the plugin.")],
    ) -> dict:
        """Bypass / unbypass a plugin."""
        return get_bridge().call(protocol.CMD_MIXER_SET_PLUGIN_MUTE_STATE,
                                  {"track": track, "slot": slot, "mute": mute})

    # ------------------------------------------------------------------
    # Track metadata + selection
    # ------------------------------------------------------------------

    @mcp.tool(annotations={"title": "Get mixer track info (Master/FirstIns/LastIns/Sel)", **_RO})
    def fl_mixer_get_track_info(
        mode: Annotated[int, Field(
            description="0 = TN_Master, 1 = TN_FirstIns, 2 = TN_LastIns, 3 = TN_Sel."
        )],
    ) -> dict:
        """Returns the mixer track index for one of the special tracks:
        Master (0), First Insert (1), Last Insert (2), or the currently
        selected track (3)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_TRACK_INFO, {"mode": mode})

    @mcp.tool(annotations={"title": "Get mixer track number", **_RO})
    def fl_mixer_get_track_number(
        track: Annotated[int, Field(ge=0)],
    ) -> dict:
        """Returns the track's 'track number' (its position slot)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_TRACK_NUMBER,
                                  {"track": track})

    @mcp.tool(annotations={"title": "Set mixer track number", **_WR})
    def fl_mixer_set_track_number(
        track: Annotated[int, Field(ge=0)],
        number: Annotated[int, Field(description="Target track-number position.")],
        flags: Annotated[int, Field(description="FL flags (see midi.mixer_setTrackNumber_flags).")] = 0,
    ) -> dict:
        """Move a track to a new position. Use flags to control whether
        linked tracks move together."""
        return get_bridge().call(protocol.CMD_MIXER_SET_TRACK_NUMBER,
                                  {"track": track, "number": number, "flags": flags})

    @mcp.tool(annotations={"title": "Get active mixer track", **_RO})
    def fl_mixer_get_active_track() -> dict:
        """Returns the mixer track that has the docked peak meter
        ('current track' / 'selected track')."""
        return get_bridge().call(protocol.CMD_MIXER_GET_ACTIVE_TRACK, {})

    @mcp.tool(annotations={"title": "Set active mixer track", **_WR})
    def fl_mixer_set_active_track(
        track: Annotated[int, Field(ge=0)],
    ) -> dict:
        """Move the docked peak meter to a track. Future meter readings
        come from this track."""
        return get_bridge().call(protocol.CMD_MIXER_SET_ACTIVE_TRACK, {"track": track})

    @mcp.tool(annotations={"title": "Is mixer track selected?", **_RO})
    def fl_mixer_is_track_selected(
        track: Annotated[int, Field(ge=0)],
    ) -> dict:
        """Returns True if the track is currently selected."""
        return get_bridge().call(protocol.CMD_MIXER_IS_TRACK_SELECTED, {"track": track})

    @mcp.tool(annotations={"title": "Select/deselect a mixer track", **_WR})
    def fl_mixer_select_track(
        track: Annotated[int, Field(ge=0)],
        value: Annotated[int, Field(
            description="-1 = toggle, 0 = deselect, 1 = select."
        )] = -1,
    ) -> dict:
        """Change a mixer track's selection state."""
        return get_bridge().call(protocol.CMD_MIXER_SELECT_TRACK,
                                  {"track": track, "value": value})

    @mcp.tool(annotations={"title": "Select all mixer tracks", **_WR})
    def fl_mixer_select_all() -> dict:
        """Multi-select every mixer track."""
        return get_bridge().call(protocol.CMD_MIXER_SELECT_ALL, {})

    @mcp.tool(annotations={"title": "Deselect all mixer tracks", **_WR})
    def fl_mixer_deselect_all() -> dict:
        """Deselect every mixer track."""
        return get_bridge().call(protocol.CMD_MIXER_DESELECT_ALL, {})

    # ------------------------------------------------------------------
    # REC event helpers (the lowest-level way to read/write FL state)
    # ------------------------------------------------------------------

    @mcp.tool(annotations={"title": "Get REC event value", **_RO})
    def fl_mixer_get_event_value(
        event_id: Annotated[int, Field(description="REC event ID.")],
    ) -> dict:
        """Returns the current value of a REC event."""
        return get_bridge().call(protocol.CMD_MIXER_GET_EVENT_VALUE, {"event_id": event_id})

    @mcp.tool(annotations={"title": "Get REC event name", **_RO})
    def fl_mixer_get_event_id_name(
        event_id: Annotated[int, Field(description="REC event ID.")],
    ) -> dict:
        """Returns the human-readable name of a REC event."""
        return get_bridge().call(protocol.CMD_MIXER_GET_EVENT_ID_NAME, {"event_id": event_id})

    @mcp.tool(annotations={"title": "Get REC event value as string", **_RO})
    def fl_mixer_get_event_id_value_str(
        event_id: Annotated[int, Field(description="REC event ID.")],
    ) -> dict:
        """Returns the current value formatted as FL would show it (e.g.
        '+3.2 dB', '78%')."""
        return get_bridge().call(protocol.CMD_MIXER_GET_EVENT_ID_VALUE_STR,
                                  {"event_id": event_id})

    @mcp.tool(annotations={"title": "Automate REC event (DANGEROUS)", **_WR})
    def fl_mixer_automate_event(
        event_id: Annotated[int, Field(description="REC event ID.")],
        value: Annotated[int, Field(description="New value.")],
        flags: Annotated[int, Field(description="FL flags.")] = 0,
        res: Annotated[float, Field(description="Resolution (0 = exact).")] = 0.0,
    ) -> dict:
        """Write to a REC event directly. CAUTION: wrong event IDs can crash
        FL or write to the wrong parameter. Prefer the typed tools
        (fl_set_mixer_volume, fl_set_channel_volume, etc) when available."""
        return get_bridge().call(protocol.CMD_MIXER_AUTOMATE_EVENT,
                                  {"event_id": event_id, "value": value,
                                   "flags": flags, "res": res})

    @mcp.tool(annotations={"title": "Get auto-smooth REC event value", **_RO})
    def fl_mixer_get_auto_smooth_event_val(
        event_id: Annotated[int, Field(description="REC event ID.")],
        flags: Annotated[int, Field(description="FL flags.")] = 0,
        res: Annotated[float, Field(description="Resolution.")] = 0.0,
    ) -> dict:
        """Returns the auto-smoothed REC event value (interpolated)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_AUTO_SMOOTH_EVENT_VAL,
                                  {"event_id": event_id, "flags": flags, "res": res})

    @mcp.tool(annotations={"title": "Remote-find REC event value", **_RO})
    def fl_mixer_remote_find_event_value(
        event_id: Annotated[int, Field(description="REC event ID.")],
        flags: Annotated[int, Field(description="FL flags.")] = 0,
        res: Annotated[float, Field(description="Resolution.")] = 0.0,
    ) -> dict:
        """Find the value of a remote-control REC event."""
        return get_bridge().call(protocol.CMD_MIXER_REMOTE_FIND_EVENT_VALUE,
                                  {"event_id": event_id, "flags": flags, "res": res})

    # ------------------------------------------------------------------
    # Misc mixer tools
    # ------------------------------------------------------------------

    @mcp.tool(annotations={"title": "Enable/disable a mixer track", **_WR})
    def fl_mixer_enable_track(
        track: Annotated[int, Field(ge=0)],
        value: Annotated[int, Field(ge=0, le=1, description="0 = disable, 1 = enable.")] = 1,
    ) -> dict:
        """Enable or disable a mixer track. Disabled tracks mute all plugins
        on them."""
        return get_bridge().call(protocol.CMD_MIXER_ENABLE_TRACK,
                                  {"track": track, "value": value})

    @mcp.tool(annotations={"title": "Get mixer track recording filename", **_RO})
    def fl_mixer_get_track_recording_file(
        track: Annotated[int, Field(ge=0)],
    ) -> dict:
        """Returns the file path that audio recorded on this track is
        being written to. Empty string if not recording."""
        return get_bridge().call(protocol.CMD_MIXER_GET_TRACK_RECORDING_FILE,
                                  {"track": track})

    @mcp.tool(annotations={"title": "Get send level (route to)", **_RO})
    def fl_mixer_get_route_to_level(
        src: Annotated[int, Field(ge=0, description="Source mixer track.")],
        dst: Annotated[int, Field(ge=0, description="Destination mixer track.")],
    ) -> dict:
        """Returns the send level from src -> dst (0.0..1.0)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_ROUTE_TO_LEVEL,
                                  {"src": src, "dst": dst})

    @mcp.tool(annotations={"title": "Enable/disable mixer FX slots", **_WR})
    def fl_mixer_enable_track_slots(
        track: Annotated[int, Field(ge=0)],
        value: Annotated[bool, Field(description="True = enable FX on this track.")] = True,
    ) -> dict:
        """Enable or disable ALL FX slots on a mixer track at once. When
        disabled, plugins don't process audio."""
        return get_bridge().call(protocol.CMD_MIXER_ENABLE_TRACK_SLOTS,
                                  {"track": track, "value": value})

    @mcp.tool(annotations={"title": "Is mixer track mute-locked?", **_RO})
    def fl_mixer_is_track_mute_lock(
        track: Annotated[int, Field(ge=0)],
    ) -> dict:
        """Returns True if the track's mute state is locked (cannot be
        changed by solo on other tracks)."""
        return get_bridge().call(protocol.CMD_MIXER_IS_TRACK_MUTE_LOCK, {"track": track})

    @mcp.tool(annotations={"title": "Get last peak volume", **_RO})
    def fl_mixer_get_last_peak_vol(
        section: Annotated[int, Field(ge=0, le=1,
            description="0 = left channel, 1 = right channel.")],
    ) -> dict:
        """Returns the last peak volume for the master output's left or
        right channel (0.0..1+, can exceed 1 for clipping)."""
        return get_bridge().call(protocol.CMD_MIXER_GET_LAST_PEAK_VOL, {"section": section})

    @mcp.tool(annotations={"title": "Link channel to mixer track", **_WR})
    def fl_mixer_link_channel_to_track(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
        select: Annotated[bool, Field(description="Select the mixer track after linking.")] = False,
    ) -> dict:
        """Pair a channel-rack channel to a mixer track."""
        return get_bridge().call(protocol.CMD_MIXER_LINK_CHANNEL_TO_TRACK,
                                  {"channel": channel, "track": track, "select": select})

    @mcp.tool(annotations={"title": "Link mixer track to channel", **_WR})
    def fl_mixer_link_track_to_channel(
        track: Annotated[int, Field(ge=0)],
        channel: Annotated[int, Field(ge=0)],
        select: Annotated[bool, Field(description="Select the mixer track after linking.")] = False,
    ) -> dict:
        """Pair a mixer track to a channel-rack channel (inverse direction)."""
        return get_bridge().call(protocol.CMD_MIXER_LINK_TRACK_TO_CHANNEL,
                                  {"track": track, "channel": channel, "select": select})