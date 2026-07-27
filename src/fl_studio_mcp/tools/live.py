"""Live MIDI + score-log tools (v0.3).

Found via FL-Studio-API-Stubs + live probe:
  - general.dumpScoreLog(time, silent) -- write last N seconds of played
    MIDI to the selected pattern. This is FL's live-capture-into-pattern
    mechanism.
  - general.safeToEdit() -- edit-safety guard.
  - channels.midiNoteOn(idx, note, velocity, channel=-1) -- live MIDI
    note trigger. velocity=0 = note-off.
  - channels.quickQuantize(index, startOnly, useGlobalIndex)
  - channels.selectedChannel(canBeNone, offset, indexGlobal)
  - channels.getChannelMidiInPort(index)
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
           "idempotentHint": False, "openWorldHint": True}

    @mcp.tool(annotations={"title": "Dump score log into selected pattern", **_WR})
    def fl_dump_score_log(
        time: Annotated[int, Field(ge=1, le=60,
            description="Seconds of recently played MIDI to write to the selected pattern.")] = 5,
        silent: Annotated[bool, Field(description="Suppress the empty-score message in the FL log.")] = True,
    ) -> dict:
        """Write the last N seconds of played MIDI into the SELECTED pattern.

        This is FL's built-in live-capture-into-pattern mechanism. To use:
          1. Select the target pattern in FL.
          2. Play something (or let an FL channel play it).
          3. Call fl_dump_score_log -- the last ``time`` seconds of MIDI
             land in the piano roll of the selected pattern.

        Returns a note describing what happened; verify by opening the
        pattern in the piano roll. The pattern must exist (use
        fl_arrange_new_pattern to make one)."""
        return get_bridge().call(protocol.CMD_DUMP_SCORE_LOG,
                                  {"time": time, "silent": silent})

    @mcp.tool(annotations={"title": "Check if FL is safe to edit", **_RO})
    def fl_safe_to_edit() -> dict:
        """Returns True when FL is in a state where edit operations
        (dumpScoreLog, automation writes, etc) won't crash. Use as a guard
        before destructive calls."""
        return get_bridge().call(protocol.CMD_SAFE_TO_EDIT, {})

    @mcp.tool(annotations={"title": "Trigger a MIDI note (live)", **_WR})
    def fl_trigger_note(
        index: Annotated[int, Field(ge=0,
            description="Global channel index (channel-rack, not group-respecting).")],
        note: Annotated[int, Field(ge=0, le=127, description="MIDI note 0-127.")],
        velocity: Annotated[int, Field(ge=0, le=127, description="Velocity 1-127; 0 = note-off.")] = 100,
        channel: Annotated[int, Field(
            description="MIDI channel to use; -1 = user's selected channel. Only takes effect if the target channel has MIDI-channel-through enabled."
        )] = -1,
    ) -> dict:
        """Live-fire a MIDI note on a channel. Fires immediately (in real
        time), bypassing the piano-roll editor. Useful for triggering
        sound effects, arpeggiator-style playback, or testing a channel's
        instrument. velocity=0 is a note-off.

        Note: the channel must NOT be receiving MIDI from this script's
        own controller port (otherwise you'll get an infinite feedback
        loop). The script auto-blocks the FLStudioMCP MIDI-in port on
        channels that receive from it.
        """
        return get_bridge().call(protocol.CMD_TRIGGER_NOTE, {
            "index": index, "note": note, "velocity": velocity, "channel": channel,
        })

    @mcp.tool(annotations={"title": "Quick-quantize a channel", **_WR})
    def fl_quantize_channel(
        index: Annotated[int, Field(ge=0,
            description="Channel index (respects groups unless use_global_index=True).")],
        start_only: Annotated[int, Field(ge=0, le=1,
            description="1 = quantize starts only (preserves lengths); 0 = quantize starts + lengths.")] = 1,
        use_global_index: Annotated[bool, Field(
            description="If True, index is the global channel index instead of the group-respecting one."
        )] = False,
    ) -> dict:
        """Quick-quantize the notes on a channel: snaps to the current snap
        mode. start_only=1 preserves note lengths (just nudges the start);
        start_only=0 also snaps lengths. The current snap mode is whatever
        FL has set in the toolbar."""
        return get_bridge().call(protocol.CMD_QUANTIZE_CHANNEL, {
            "index": index, "start_only": start_only,
            "use_global_index": use_global_index,
        })

    @mcp.tool(annotations={"title": "Get selected channel(s)", **_RO})
    def fl_get_selected_channel(
        can_be_none: Annotated[bool, Field(
            description="If True, returns -1 when no channel is selected; else returns 0 (first channel)."
        )] = False,
        offset: Annotated[int, Field(
            description="0 = first selected; 1 = second selected; etc."
        )] = 0,
        index_global: Annotated[bool, Field(
            description="If True, use global channel index instead of group-respecting."
        )] = False,
    ) -> dict:
        """Return the index of a selected channel. Pair with channel-rack
        operations that need a target channel."""
        return get_bridge().call(protocol.CMD_GET_SELECTED_CHANNEL, {
            "can_be_none": can_be_none, "offset": offset,
            "index_global": index_global,
        })

    @mcp.tool(annotations={"title": "Get channel MIDI-in port assignment", **_RO})
    def fl_get_channel_midi_in_port(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Return the MIDI input port assigned to a channel (i.e. which
        physical/virtual MIDI input the channel receives from)."""
        return get_bridge().call(protocol.CMD_GET_CHANNEL_MIDI_IN_PORT,
                                  {"index": index})