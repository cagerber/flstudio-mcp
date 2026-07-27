"""General FL state + project metadata tools (v0.4).

Discovered via paginated api_probe() of FL 26.1.2 build 5557:
  - general.getProjectAuthor / getProjectTitle / getProjectGenre
  - general.setNumerator / setDenominator / setRecPPQ (time signature + PPQ)
  - general.getUndoHistoryCount / getUndoHistoryPos / setUndoHistoryPos
  - general.undo (count) / general.undoUp (redo path)

Each command is verified live and tested in scripts/integration_test.py.
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

    @mcp.tool(annotations={"title": "Get project author", **_RO})
    def fl_get_project_author() -> dict:
        """Project author string (FL project metadata)."""
        return get_bridge().call(protocol.CMD_GET_PROJECT_AUTHOR, {})

    @mcp.tool(annotations={"title": "Get project title", **_RO})
    def fl_get_project_title() -> dict:
        """Project title (FL project metadata; may differ from ui.getProgTitle
        which is the FL window title)."""
        return get_bridge().call(protocol.CMD_GET_PROJECT_TITLE, {})

    @mcp.tool(annotations={"title": "Get project genre", **_RO})
    def fl_get_project_genre() -> dict:
        """Project genre string."""
        return get_bridge().call(protocol.CMD_GET_PROJECT_GENRE, {})

    @mcp.tool(annotations={"title": "Set time signature numerator", **_WR})
    def fl_set_numerator(
        numerator: Annotated[int, Field(ge=1, le=32,
            description="Time-signature numerator (1..32).")],
    ) -> dict:
        """Set the time signature numerator (top number of N/4)."""
        return get_bridge().call(protocol.CMD_SET_NUMERATOR, {"numerator": numerator})

    @mcp.tool(annotations={"title": "Set time signature denominator", **_WR})
    def fl_set_denominator(
        denominator: Annotated[int, Field(
            description="Time-signature denominator. Must be a power of 2: 1, 2, 4, 8, or 16."
        )],
    ) -> dict:
        """Set the time signature denominator (bottom number of N/D)."""
        return get_bridge().call(protocol.CMD_SET_DENOMINATOR, {"denominator": denominator})

    @mcp.tool(annotations={"title": "Set PPQ (ticks per quarter)", **_WR})
    def fl_set_rec_ppq(
        ppq: Annotated[int, Field(ge=24, le=1920,
            description="Ticks per quarter note (PPQ). 24..1920. Common values: 96, 192, 384, 480, 960, 1920.")],
    ) -> dict:
        """Set the project's ticks-per-quarter note (PPQ)."""
        return get_bridge().call(protocol.CMD_SET_REC_PPQ, {"ppq": ppq})

    @mcp.tool(annotations={"title": "Get undo history depth", **_RO})
    def fl_get_undo_history_count() -> dict:
        """Number of undo history entries available."""
        return get_bridge().call(protocol.CMD_GET_UNDO_HISTORY_COUNT, {})

    @mcp.tool(annotations={"title": "Get undo history cursor", **_RO})
    def fl_get_undo_history_pos() -> dict:
        """Current undo-history cursor position (0 = newest, count = oldest)."""
        return get_bridge().call(protocol.CMD_GET_UNDO_HISTORY_POS, {})

    @mcp.tool(annotations={"title": "Set undo history cursor", **_WR})
    def fl_set_undo_history_pos(
        pos: Annotated[int, Field(ge=0,
            description="Target undo-history position (0..count). 0 = newest, count = oldest.")],
    ) -> dict:
        """Move the undo history cursor (FL's undo/redo slider)."""
        return get_bridge().call(protocol.CMD_SET_UNDO_HISTORY_POS, {"pos": pos})

    @mcp.tool(annotations={"title": "Undo (reverses last edit)", **_WR})
    def fl_undo(
        count: Annotated[int, Field(ge=1, description="Number of undo steps.")] = 1,
    ) -> dict:
        """Undo ``count`` edits. Equivalent to pressing Ctrl+Z ``count`` times."""
        return get_bridge().call(protocol.CMD_UNDO, {"count": count})

    @mcp.tool(annotations={"title": "Redo (re-applies undone edit)", **_WR})
    def fl_redo(
        count: Annotated[int, Field(ge=1, description="Number of redo steps.")] = 1,
    ) -> dict:
        """Redo ``count`` edits. Equivalent to pressing Ctrl+Y / Ctrl+Shift+Z
        ``count`` times. Implemented via general.undoUp() (the forward direction)."""
        return get_bridge().call(protocol.CMD_REDO, {"count": count})