"""Channel metadata + step sequencer tools (v0.4).

Verified live on FL 26.1.2 build 5557:
  - channels.getChannelType / getActivityLevel / getChannelIndex(name)
  - channels.isChannelSelected / isHighLighted
  - channels.muteChannel(idx, value=-1)
  - channels.getSwing / setSwing
  - channels.getGridBit / setGridBit
  - channels.getStepParam / getCurrentStepParam / setStepParameterByIndex
  - channels.getRecEventId / incEventValue
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
           "idempotentHint": True, "openWorldHint": True}

    @mcp.tool(annotations={"title": "Get channel type", **_RO})
    def fl_get_channel_type(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Returns the channel type as an int. See midi.channel_types for
        the enum (sampler, generator plugin, automation, layer)."""
        return get_bridge().call(protocol.CMD_GET_CHANNEL_TYPE, {"index": index})

    @mcp.tool(annotations={"title": "Get channel activity level", **_RO})
    def fl_get_activity_level(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Real-time activity meter value (0..1). Returns 0 when transport
        is stopped or the channel is silent."""
        return get_bridge().call(protocol.CMD_GET_ACTIVITY_LEVEL, {"index": index})

    @mcp.tool(annotations={"title": "Get channel index by name", **_RO})
    def fl_get_channel_index(
        name: Annotated[str, Field(description="Channel name to look up.")],
    ) -> dict:
        """Returns the channel-rack index for the named channel, or -1 if
        not found."""
        return get_bridge().call(protocol.CMD_GET_CHANNEL_INDEX, {"name": name})

    @mcp.tool(annotations={"title": "Is channel selected?", **_RO})
    def fl_is_channel_selected(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Returns True if the channel is currently selected in the channel rack."""
        return get_bridge().call(protocol.CMD_IS_CHANNEL_SELECTED, {"index": index})

    @mcp.tool(annotations={"title": "Is channel highlighted?", **_RO})
    def fl_is_channel_highlighted(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Returns True if the channel is highlighted (vs just selected)."""
        return get_bridge().call(protocol.CMD_IS_CHANNEL_HIGHLIGHTED, {"index": index})

    @mcp.tool(annotations={"title": "Mute / unmute / toggle channel", **_WR})
    def fl_mute_channel(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
        value: Annotated[int, Field(
            description="-1 = toggle, 0 = unmute, 1 = mute."
        )] = -1,
    ) -> dict:
        """Set the channel's mute state. Pass value=1 to mute, 0 to unmute,
        or -1 to toggle the current state."""
        return get_bridge().call(protocol.CMD_MUTE_CHANNEL,
                                  {"index": index, "value": value})

    @mcp.tool(annotations={"title": "Get channel swing", **_RO})
    def fl_get_swing(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Swing amount for the channel's MIDI input, 0.0..1.0."""
        return get_bridge().call(protocol.CMD_GET_SWING, {"index": index})

    @mcp.tool(annotations={"title": "Set channel swing", **_WR})
    def fl_set_swing(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
        value: Annotated[float, Field(ge=0.0, le=1.0, description="Swing 0.0..1.0.")],
    ) -> dict:
        """Set the channel's swing amount."""
        return get_bridge().call(protocol.CMD_SET_SWING, {"index": index, "value": value})

    @mcp.tool(annotations={"title": "Get grid bit (step sequencer)", **_RO})
    def fl_get_grid_bit(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
    ) -> dict:
        """Read whether the step at (channel, step) is set in the channel's
        step-sequencer grid."""
        return get_bridge().call(protocol.CMD_GET_GRID_BIT,
                                  {"channel": channel, "step": step})

    @mcp.tool(annotations={"title": "Set grid bit (step sequencer)", **_WR})
    def fl_set_grid_bit(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
        value: Annotated[bool, Field(description="True = set the bit, False = clear it.")] = True,
    ) -> dict:
        """Set or clear a step at (channel, step) in the channel's step grid."""
        return get_bridge().call(protocol.CMD_SET_GRID_BIT,
                                  {"channel": channel, "step": step, "value": value})

    @mcp.tool(annotations={"title": "Get step parameter", **_RO})
    def fl_get_step_param(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
        param: Annotated[int, Field(ge=0, description="Parameter index (see midi.step_params).")],
    ) -> dict:
        """Read a parameter of a step (e.g. velocity, panning, release) on
        the channel step grid."""
        return get_bridge().call(protocol.CMD_GET_STEP_PARAM,
                                  {"channel": channel, "step": step, "param": param})

    @mcp.tool(annotations={"title": "Get current step parameter", **_RO})
    def fl_get_current_step_param(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
        param: Annotated[int, Field(ge=0, description="Parameter index.")],
    ) -> dict:
        """Like get_step_param but resolves the parameter through any
        channel-level overrides."""
        return get_bridge().call(protocol.CMD_GET_CURRENT_STEP_PARAM,
                                  {"channel": channel, "step": step, "param": param})

    @mcp.tool(annotations={"title": "Set step parameter by index", **_WR})
    def fl_set_step_param_by_index(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        step: Annotated[int, Field(ge=0, description="Step number (0-based).")],
        param: Annotated[int, Field(ge=0, description="Parameter index.")],
        value: Annotated[float, Field(description="Parameter value (normalized 0..1 or per-parameter units).")],
    ) -> dict:
        """Set a per-step parameter (e.g. velocity at step 4 on channel 2)."""
        return get_bridge().call(protocol.CMD_SET_STEP_PARAM_BY_INDEX,
                                  {"channel": channel, "step": step,
                                   "param": param, "value": value})

    @mcp.tool(annotations={"title": "Get REC event ID for channel", **_RO})
    def fl_get_rec_event_id(
        index: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Returns the REC event ID base for a channel (used to compute
        per-property event IDs for incEventValue/processRECEvent)."""
        return get_bridge().call(protocol.CMD_GET_REC_EVENT_ID, {"index": index})

    @mcp.tool(annotations={"title": "Increment REC event value", **_WR})
    def fl_inc_event_value(
        event_id: Annotated[int, Field(description="REC event ID (use get_rec_event_id as a base).")],
        step: Annotated[int, Field(description="Delta step (e.g. 1 for +1, -1 for -1).")] = 1,
        res: Annotated[float, Field(
            description="Resolution multiplier. Default 1/24 for encoder-friendly responsiveness."
        )] = 1.0 / 24.0,
    ) -> dict:
        """Increment the value of a REC event by ``step`` (encoder-style delta).
        Returns the new value. Use the result with processRECEvent."""
        return get_bridge().call(protocol.CMD_INC_EVENT_VALUE,
                                  {"event_id": event_id, "step": step, "res": res})