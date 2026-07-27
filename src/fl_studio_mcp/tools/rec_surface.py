"""Typed REC surface tools (v0.5) -- the named-constant layer over FL's
controller API. The controller script imports the real `midi.py` from
FL's runtime Python; the server mirrors those constants in
`fl_studio_mcp.midi_const` so we can validate + name them before sending
to the controller.

NEW TOOLS (32 across 7 categories):
  - Per-channel REC_Chan_* properties: get/set_channel_property for 16
    named properties (volume, pan, filter_cutoff, filter_resonance,
    pitch, mute, fx_track, swing_mix, gate_time, crossfade, etc.)
  - Mixer-track REC_Mixer_* properties: get/set_mixer_property for
    volume / pan / stereo_sep.
  - Full 8-band EQ: set_eq_band (one-shot type/freq/bw/gain), get_eq_band
    (read all 4 props).
  - Master controls: get/set_master_volume, get/set_master_shuffle,
    get/set_master_pitch.
  - Transport: start_stop (0/1), get/set_song_position_bars,
    get_song_length_bars.
  - Scale (channel-rack harmonic scale): set_scale (read is honest-not-
    implemented for this FL build; FL doesn't expose a getter).
  - Named enum wrappers: get_channel_type_named (returns string),
    get/set_step_param_named (uses pVelocity/pPan/etc.),
    get_step_param_list (all 9 params at once).
  - Server-side helpers: note_name (MIDI int -> "C5"),
    vol_to_db (FL's volume curve -> dB).
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol
from ..connection import get_bridge


# Mirrored from FL's midi.py -- the canonical list of channel property
# names. The server validates the user-supplied name against this list
# before sending the wire command, so typos fail fast with a clear
# error message instead of a server-side exception.
CHANNEL_PROPERTY_NAMES = (
    "volume", "pan", "filter_cutoff", "filter_resonance", "pitch",
    "filter_type", "portamento_time", "mute", "fx_track", "gate_time",
    "crossfade", "time_offset", "swing_mix", "sample_offset",
    "stretch_time",
)
MIXER_PROPERTY_NAMES = ("volume", "pan", "stereo_sep", "stereo_separation")
STEP_PARAM_NAMES = (
    "pitch", "velocity", "release", "fine_pitch", "pan",
    "mod_x", "mod_y", "shift", "repeat",
)
SCALE_NAMES = (
    "major", "harmonic_minor", "melodic_minor", "whole_tone", "diminished",
    "major_pentatonic", "minor_pentatonic", "japanese", "major_bebop",
    "dominant_bebop", "blues", "arabic", "enigmatic", "neapolitan",
    "neapolitan_minor", "hungarian_minor", "dorian", "phrygian", "lydian",
    "mixolydian", "aeolian", "locrian", "chromatic",
)


def _check(allowed: tuple, name: str, what: str):
    if name not in allowed:
        raise ValueError(f"unknown {what}: {name!r}. valid: {list(allowed)}")


def register(mcp: FastMCP) -> None:
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
    _WR = {"readOnlyHint": False, "destructiveHint": False,
           "idempotentHint": True, "openWorldHint": True}

    # ----- Per-channel REC_Chan_* ---------------------------------

    @mcp.tool(annotations={"title": "Get channel property (typed)", **_RO})
    def fl_get_channel_property(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        property: Annotated[str, Field(
            description=f"Property name. One of: {list(CHANNEL_PROPERTY_NAMES)}"
        )],
    ) -> dict:
        """Read a per-channel property (volume, pan, pitch, filter cutoff,
        mute, fx_track, etc.) by name. The controller resolves the name
        to the matching REC_Chan_* offset."""
        _check(CHANNEL_PROPERTY_NAMES, property, "channel_property")
        return get_bridge().call(protocol.CMD_GET_CHANNEL_PROPERTY,
                                  {"channel": channel, "property": property})

    @mcp.tool(annotations={"title": "Set channel property (typed)", **_WR})
    def fl_set_channel_property(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        property: Annotated[str, Field(
            description=f"Property name. One of: {list(CHANNEL_PROPERTY_NAMES)}"
        )],
        value: Annotated[int, Field(description="New value (int, in FL's scale for that property).")],
    ) -> dict:
        """Write a per-channel property by name. Goes through the proper
        REC controller flags so the change is undo-able + recorded."""
        _check(CHANNEL_PROPERTY_NAMES, property, "channel_property")
        return get_bridge().call(protocol.CMD_SET_CHANNEL_PROPERTY, {
            "channel": channel, "property": property, "value": value,
        })

    # ----- Mixer-track REC_Mixer_* --------------------------------

    @mcp.tool(annotations={"title": "Get mixer track property (typed)", **_RO})
    def fl_get_mixer_property(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
        property: Annotated[str, Field(
            description=f"Property name. One of: {list(MIXER_PROPERTY_NAMES)}"
        )],
    ) -> dict:
        """Read a mixer-track property (volume, pan, stereo_sep) by name."""
        _check(MIXER_PROPERTY_NAMES, property, "mixer_property")
        return get_bridge().call(protocol.CMD_GET_MIXER_PROPERTY,
                                  {"track": track, "property": property})

    @mcp.tool(annotations={"title": "Set mixer track property (typed)", **_WR})
    def fl_set_mixer_property(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
        property: Annotated[str, Field(
            description=f"Property name. One of: {list(MIXER_PROPERTY_NAMES)}"
        )],
        value: Annotated[int, Field(description="New value (int, in FL's scale).")],
    ) -> dict:
        """Write a mixer-track property by name."""
        _check(MIXER_PROPERTY_NAMES, property, "mixer_property")
        return get_bridge().call(protocol.CMD_SET_MIXER_PROPERTY, {
            "track": track, "property": property, "value": value,
        })

    # ----- Full 8-band EQ -----------------------------------------

    @mcp.tool(annotations={"title": "Set EQ band (one-shot)", **_WR})
    def fl_set_eq_band(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
        band: Annotated[int, Field(ge=0, le=7, description="EQ band 0..7.")],
        type: Annotated[Optional[int], Field(description="EQ type int (0..5): 0=lp, 1=hp, 2=lp_shelf, 3=hp_shelf, 4=peaking, 5=notch.")] = None,
        gain: Annotated[Optional[float], Field(description="Gain in dB (-36..+36).")] = None,
        frequency_hz: Annotated[Optional[float], Field(description="Center freq in Hz (20..20000).")] = None,
        bandwidth_oct: Annotated[Optional[float], Field(description="Bandwidth in octaves (0.1..10.0).")] = None,
    ) -> dict:
        """Set any subset of {type, gain, frequency_hz, bandwidth_oct} on
        a single EQ band. Unspecified props are left unchanged. Returns
        what was actually written."""
        params: dict = {"track": track, "band": band}
        if type is not None:
            params["type"] = type
        if gain is not None:
            params["gain"] = gain
        if frequency_hz is not None:
            params["frequency_hz"] = frequency_hz
        if bandwidth_oct is not None:
            params["bandwidth_oct"] = bandwidth_oct
        if not any(k in params for k in ("type", "gain", "frequency_hz", "bandwidth_oct")):
            return {"ok": False, "error": "must supply at least one of type/gain/frequency_hz/bandwidth_oct"}
        return get_bridge().call(protocol.CMD_SET_EQ_BAND, params)

    @mcp.tool(annotations={"title": "Get EQ band (all 4 props)", **_RO})
    def fl_get_eq_band(
        track: Annotated[int, Field(ge=0, description="Mixer track index.")],
        band: Annotated[int, Field(ge=0, le=7, description="EQ band 0..7.")],
    ) -> dict:
        """Read all 4 EQ-band properties (gain_db, frequency_hz,
        bandwidth_oct, type) in one call."""
        return get_bridge().call(protocol.CMD_GET_EQ_BAND,
                                  {"track": track, "band": band})

    # ----- Master controls (REC_Global_*) -------------------------

    @mcp.tool(annotations={"title": "Get master volume", **_RO})
    def fl_get_master_volume() -> dict:
        """Master fader position (0.0..1.0)."""
        return get_bridge().call(protocol.CMD_GET_MASTER_VOLUME, {})

    @mcp.tool(annotations={"title": "Set master volume", **_WR})
    def fl_set_master_volume(
        volume: Annotated[float, Field(ge=0.0, le=1.0, description="Master volume 0.0..1.0.")],
    ) -> dict:
        """Set the master fader."""
        return get_bridge().call(protocol.CMD_SET_MASTER_VOLUME, {"volume": volume})

    @mcp.tool(annotations={"title": "Get master shuffle", **_RO})
    def fl_get_master_shuffle() -> dict:
        """Master shuffle amount."""
        return get_bridge().call(protocol.CMD_GET_MASTER_SHUFFLE, {})

    @mcp.tool(annotations={"title": "Set master shuffle", **_WR})
    def fl_set_master_shuffle(
        shuffle: Annotated[float, Field(ge=0.0, le=1.0, description="Shuffle 0.0..1.0.")],
    ) -> dict:
        """Set the master shuffle."""
        return get_bridge().call(protocol.CMD_SET_MASTER_SHUFFLE, {"shuffle": shuffle})

    @mcp.tool(annotations={"title": "Get master pitch", **_RO})
    def fl_get_master_pitch() -> dict:
        """Master pitch in semi-tones (0 = center)."""
        return get_bridge().call(protocol.CMD_GET_MASTER_PITCH, {})

    @mcp.tool(annotations={"title": "Set master pitch", **_WR})
    def fl_set_master_pitch(
        pitch_semitones: Annotated[float, Field(
            description="Master pitch offset in semi-tones (e.g. 0.5, -12.0)."
        )],
    ) -> dict:
        """Set the master pitch (semi-tones)."""
        return get_bridge().call(protocol.CMD_SET_MASTER_PITCH, {"pitch_semitones": pitch_semitones})

    # ----- Transport + start/stop ---------------------------------

    @mcp.tool(annotations={"title": "Start or stop transport", **_WR})
    def fl_start_stop(
        value: Annotated[int, Field(ge=0, le=1, description="0 = stop, 1 = start.")],
    ) -> dict:
        """Programmatic transport start/stop. Equivalent to pressing the
        play/stop button."""
        return get_bridge().call(protocol.CMD_START_STOP, {"value": value})

    @mcp.tool(annotations={"title": "Get song position (bars)", **_RO})
    def fl_get_song_position_bars() -> dict:
        """Current playhead position in bars (0-based)."""
        return get_bridge().call(protocol.CMD_GET_SONG_POSITION_BARS, {})

    @mcp.tool(annotations={"title": "Set song position (bars)", **_WR})
    def fl_set_song_position_bars(
        bars: Annotated[int, Field(ge=0, description="Bar position (0-based).")],
    ) -> dict:
        """Move the playhead to a specific bar. Does NOT auto-play."""
        return get_bridge().call(protocol.CMD_SET_SONG_POSITION_BARS, {"bars": bars})

    @mcp.tool(annotations={"title": "Get song length (bars)", **_RO})
    def fl_get_song_length_bars() -> dict:
        """Total song length in bars."""
        return get_bridge().call(protocol.CMD_GET_SONG_LENGTH_BARS, {})

    # ----- Scale (channel-rack harmonic) ---------------------------

    @mcp.tool(annotations={"title": "Set channel-rack scale (typed)", **_WR})
    def fl_set_scale(
        scale: Annotated[str, Field(
            description=f"Scale name. One of: {list(SCALE_NAMES)}"
        )],
    ) -> dict:
        """Set the channel-rack's harmonic scale by name (e.g. 'major',
        'minor_pentatonic', 'dorian'). Note: FL's scripting API exposes
        scale as a UI-only setting on this build; the controller will
        return an honest 'api_unavailable' report -- use FL's UI for the
        actual scale change in that case. The name->int mapping IS
        available, so the result includes the scale int."""
        _check(SCALE_NAMES, scale, "scale")
        return get_bridge().call(protocol.CMD_SET_SCALE, {"scale": scale})

    # ----- Named enum wrappers ------------------------------------

    @mcp.tool(annotations={"title": "Get channel type (named string)", **_RO})
    def fl_get_channel_type_named(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Like fl_get_channel_type but returns BOTH the raw int AND a
        named string (one of: sampler, ts404, generator, layer,
        audio_clip, auto_clip)."""
        return get_bridge().call(protocol.CMD_GET_CHANNEL_TYPE_NAMED, {"index": index})

    @mcp.tool(annotations={"title": "Get step param (named)", **_RO})
    def fl_get_step_param_named(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
        param: Annotated[str, Field(
            description=f"Parameter name. One of: {list(STEP_PARAM_NAMES)}"
        )],
    ) -> dict:
        """Read a per-step parameter by name ('velocity', 'pan', etc.).
        Returns the float value (typically 0..1 for most params)."""
        _check(STEP_PARAM_NAMES, param, "step_param")
        return get_bridge().call(protocol.CMD_GET_STEP_PARAM_NAMED, {
            "channel": channel, "step": step, "param": param,
        })

    @mcp.tool(annotations={"title": "Set step param (named)", **_WR})
    def fl_set_step_param_named(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
        param: Annotated[str, Field(
            description=f"Parameter name. One of: {list(STEP_PARAM_NAMES)}"
        )],
        value: Annotated[float, Field(description="Parameter value (0..1 for most params).")],
    ) -> dict:
        """Set a per-step parameter by name."""
        _check(STEP_PARAM_NAMES, param, "step_param")
        return get_bridge().call(protocol.CMD_SET_STEP_PARAM_NAMED, {
            "channel": channel, "step": step, "param": param, "value": value,
        })

    @mcp.tool(annotations={"title": "Get all 9 step params for (channel, step)", **_RO})
    def fl_get_step_param_list(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
    ) -> dict:
        """Return ALL 9 step parameters (pitch, velocity, release,
        fine_pitch, pan, mod_x, mod_y, shift, repeat) in one call.
        Each value is a float (0..1) or null if unavailable."""
        return get_bridge().call(protocol.CMD_GET_STEP_PARAM_LIST,
                                  {"channel": channel, "step": step})

    # ----- Server-side helpers (no FL roundtrip) ----------------

    @mcp.tool(annotations={"title": "MIDI note -> name (server-side)", **_RO})
    def fl_note_name(
        note: Annotated[int, Field(ge=0, le=127, description="MIDI note number.")],
    ) -> dict:
        """Convert a MIDI note number to its name. E.g. 60 -> 'C5',
        69 -> 'A4'. Server-side (no FL roundtrip)."""
        return get_bridge().call(protocol.CMD_NOTE_NAME, {"note": note})

    @mcp.tool(annotations={"title": "FL volume (0..1) -> dB (server-side)", **_RO})
    def fl_vol_to_db(
        volume: Annotated[float, Field(ge=0.0, le=1.0, description="Volume 0.0..1.0 (FL's normalized curve).")],
    ) -> dict:
        """Convert FL's normalized volume curve (0..1) to dB.
        Server-side (no FL roundtrip). 0.0 -> 0 dB, 0.5 -> -12.7 dB,
        0.8 -> -4.7 dB, 1.0 -> 0 dB."""
        return get_bridge().call(protocol.CMD_VOL_TO_DB, {"volume": volume})