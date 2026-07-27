"""Pattern color/length/loop/multi-select tools (v0.4).

Verified live on FL 26.1.2 build 5557:
  - patterns.getPatternLength / setPatternLength (length in beats)
  - patterns.getPatternColor / setPatternColor (0xBBGGRR)
  - patterns.getChannelLoopStyle / setChannelLoop (per-channel loop point)
  - patterns.selectAll / deselectAll
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

    @mcp.tool(annotations={"title": "Get pattern length", **_RO})
    def fl_arrange_get_pattern_length(
        index: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
    ) -> dict:
        """Returns the pattern length in beats."""
        return get_bridge().call(protocol.CMD_GET_PATTERN_LENGTH, {"index": index})

    @mcp.tool(annotations={"title": "Set pattern length", **_WR})
    def fl_arrange_set_pattern_length(
        index: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
        beats: Annotated[int, Field(ge=1, le=9999,
            description="New pattern length in beats (1..9999).")],
    ) -> dict:
        """Set the pattern length in beats. Note: ``setPatternLength`` is not
        exposed on every FL build; the controller returns an honest
        'api_unavailable' report if so."""
        return get_bridge().call(protocol.CMD_SET_PATTERN_LENGTH,
                                  {"index": index, "beats": beats})

    @mcp.tool(annotations={"title": "Get pattern color", **_RO})
    def fl_arrange_get_pattern_color(
        index: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
    ) -> dict:
        """Returns the pattern's color as 0xBBGGRR (alpha stripped)."""
        return get_bridge().call(protocol.CMD_GET_PATTERN_COLOR, {"index": index})

    @mcp.tool(annotations={"title": "Set pattern color", **_WR})
    def fl_arrange_set_pattern_color(
        index: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
        color: Annotated[int, Field(
            description="Color as 0xRRGGBB (alpha-prefixed int); FL stores 0x--BBGGRR."
        )],
    ) -> dict:
        """Color a pattern. Pairs with fl_set_mixer_color / fl_set_channel_color."""
        return get_bridge().call(protocol.CMD_SET_PATTERN_COLOR,
                                  {"index": index, "color": color})

    @mcp.tool(annotations={"title": "Get channel loop point in pattern", **_RO})
    def fl_arrange_get_channel_loop_style(
        pattern: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
    ) -> dict:
        """Returns the loop point (in steps) of the given channel within the
        given pattern. 0 = no loop."""
        return get_bridge().call(protocol.CMD_GET_CHANNEL_LOOP_STYLE,
                                  {"pattern": pattern, "channel": channel})

    @mcp.tool(annotations={"title": "Set channel loop point in pattern", **_WR})
    def fl_arrange_set_channel_loop(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        loop_point: Annotated[int, Field(ge=0,
            description="Loop point (step number); 0 disables looping.")] = 0,
    ) -> dict:
        """Set the channel's loop point in the CURRENT pattern. Use
        fl_arrange_select_pattern to switch patterns first."""
        return get_bridge().call(protocol.CMD_SET_CHANNEL_LOOP,
                                  {"channel": channel, "loop_point": loop_point})

    @mcp.tool(annotations={"title": "Select all patterns", **_WR})
    def fl_arrange_select_all() -> dict:
        """Select every pattern in the playlist (multi-select)."""
        return get_bridge().call(protocol.CMD_PATTERN_SELECT_ALL, {})

    @mcp.tool(annotations={"title": "Deselect all patterns", **_WR})
    def fl_arrange_deselect_all() -> dict:
        """Deselect every pattern in the playlist."""
        return get_bridge().call(protocol.CMD_PATTERN_DESELECT_ALL, {})

    @mcp.tool(annotations={"title": "Is any pattern selected?", **_RO})
    def fl_arrange_is_any_pattern_selected() -> dict:
        """Returns True if at least one pattern is currently selected."""
        return get_bridge().call(protocol.CMD_PATTERN_IS_ANY_SELECTED, {})