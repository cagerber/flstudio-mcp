"""Automation helpers (v0.3).

FL's scripting API does NOT expose automation clips on this build (verified
via api_probe -- channels has 54 public names; NONE contain 'auto'). The
step sequencer / grid bit functions (channels.getStepParam, channels.getGridBit)
are NOT automation -- they are SEQUENCER DATA for the channel step grid.

So both tools in this module are honest not-implemented reports that point
the user at FL's UI workflow. The reports echo the user's requested params
back so the agent can see what was attempted and recommend the equivalent
manual step.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol
from ..connection import get_bridge


def register(mcp: FastMCP) -> None:
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}

    @mcp.tool(annotations={"title": "Get automation info (FL API limitation report)", **_RO})
    def fl_get_automation_info(
        track: Annotated[
            Optional[int], Field(description="Optional intended track; documented only.")
        ] = None,
        slot: Annotated[
            Optional[int], Field(description="Optional intended slot; documented only.")
        ] = None,
    ) -> dict:
        """Report that FL's scripting API does not expose automation clips.

        The channel step sequencer (channels.getStepParam / getGridBit /
        setGridBit / setStepParameterByIndex) IS scriptable but those are
        step sequencer DATA, not automation clips.

        Returns the current channel/pattern counts so the caller can decide
        whether to fall back to step-sequencer manipulation for per-step
        parameter control.
        """
        params: dict = {}
        if track is not None:
            params["track"] = track
        if slot is not None:
            params["slot"] = slot
        return get_bridge().call(protocol.CMD_GET_AUTOMATION_INFO, params)

    @mcp.tool(annotations={"title": "Set automation point (FL API limitation report)", **_RO})
    def fl_set_automation_point(
        track: Annotated[
            Optional[int], Field(description="Optional intended track; documented only.")
        ] = None,
        slot: Annotated[
            Optional[int], Field(description="Optional intended slot; documented only.")
        ] = None,
        position_ticks: Annotated[
            Optional[int], Field(description="Optional intended position; documented only.")
        ] = None,
        value: Annotated[
            Optional[float], Field(description="Optional intended value (normalized); documented only.")
        ] = None,
        target: Annotated[
            Optional[str], Field(description="Optional intended target knob/param; documented only.")
        ] = None,
    ) -> dict:
        """Report that FL's scripting API does not expose automation clips.

        For automated control of channel-rack state per-step, use the
        channel step sequencer (channels.setGridBit / channels.setStepParameterByIndex).
        For smooth parameter curves over time, automation must be created in
        the FL UI on the playlist.
        """
        params: dict = {}
        if track is not None:
            params["track"] = track
        if slot is not None:
            params["slot"] = slot
        if position_ticks is not None:
            params["position_ticks"] = position_ticks
        if value is not None:
            params["value"] = value
        if target is not None:
            params["target"] = target
        return get_bridge().call(protocol.CMD_SET_AUTOMATION_POINT, params)