"""Arrangement primitives (Slice 1).

FL's API can't place pattern clips on the playlist (confirmed by probe), so
"arrangement" here = create/name/fill section PATTERNS + mark the timeline with
named markers; the user drags the patterns onto the playlist.

Filling notes reuses the existing piano-roll bridge (fl_write_piano_roll_notes),
which writes into the CURRENTLY SELECTED pattern -- so the flow is
new_pattern (selects it) -> write notes.
"""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol
from ..connection import get_bridge


def register(mcp: FastMCP) -> None:
    _WR = {"readOnlyHint": False, "destructiveHint": False,
           "idempotentHint": False, "openWorldHint": True}
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}

    @mcp.tool(annotations={"title": "New named pattern (selects it)", **_WR})
    def fl_arrange_new_pattern(
        name: Annotated[str, Field(description="Pattern name, e.g. 'INTRO'.")],
    ) -> dict:
        """Create + select + name the next empty pattern. After this, the note
        bridge (fl_write_piano_roll_notes) writes INTO this pattern."""
        return get_bridge().call(protocol.CMD_ARRANGE_NEW_PATTERN, {"name": name})

    @mcp.tool(annotations={"title": "Select channel (note-bridge target)", **_WR})
    def fl_arrange_select_channel(
        channel: Annotated[int, Field(ge=0, description="Channel-rack channel index.")],
    ) -> dict:
        """Make a channel the active selection so the note bridge
        (fl_write_piano_roll_notes) writes INTO it. Use before writing each
        instrument's notes in a section (drums -> ch X, bass -> ch Y, ...)."""
        return get_bridge().call(protocol.CMD_CHANNEL_SELECT, {"channel": channel})

    @mcp.tool(annotations={"title": "Clone a pattern (copies notes)", **_WR})
    def fl_arrange_clone_pattern(
        src: Annotated[int, Field(ge=1, description="Source pattern index.")],
        new_name: Annotated[str, Field(description="Name for the clone.")],
    ) -> dict:
        """Clone a pattern (copies its notes) and rename the clone -- e.g. for
        verse -> verse2 variations."""
        return get_bridge().call(protocol.CMD_ARRANGE_CLONE_PATTERN,
                                 {"src": src, "new_name": new_name})

    @mcp.tool(annotations={"title": "Add a section marker at a bar", **_WR})
    def fl_arrange_add_marker(
        bar: Annotated[int, Field(ge=1, description="Bar number (1 = song start).")],
        name: Annotated[str, Field(description="Marker name, e.g. 'Verse'.")],
    ) -> dict:
        """Add a named timeline marker at a bar (intro/verse/chorus/drop)."""
        return get_bridge().call(protocol.CMD_ARRANGE_ADD_MARKER, {"bar": bar, "name": name})

    @mcp.tool(annotations={"title": "Select a pattern (multi-select aware)", **_WR})
    def fl_arrange_select_pattern(
        index: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
        value: Annotated[int, Field(
            description="-1 = toggle (default), 0 = deselect, 1 = select."
        )] = -1,
        preview: Annotated[bool, Field(
            description="If True and the pattern gets selected, FL enters pattern mode and starts playback."
        )] = False,
    ) -> dict:
        """Select (or toggle / deselect) a pattern by 1-based index. Pair
        with fl_arrange_new_pattern to build multi-pattern arrangements
        before dragging them onto the playlist."""
        return get_bridge().call(protocol.CMD_PATTERN_SELECT, {
            "index": index, "value": value, "preview": preview,
        })

    @mcp.tool(annotations={"title": "Check if a pattern is selected", **_RO})
    def fl_arrange_is_pattern_selected(
        index: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
    ) -> dict:
        """Return True if the pattern at index is currently selected."""
        return get_bridge().call(protocol.CMD_PATTERN_IS_SELECTED, {"index": index})

    @mcp.tool(annotations={"title": "Is the pattern the empty default?", **_RO})
    def fl_arrange_is_pattern_default(
        index: Annotated[int, Field(ge=1, description="Pattern index (1-based).")],
    ) -> dict:
        """Return True if the pattern at index is the FL default (no
        user-written notes). Useful for skipping over empty patterns when
        iterating."""
        return get_bridge().call(protocol.CMD_PATTERN_IS_DEFAULT, {"index": index})

    @mcp.tool(annotations={"title": "Burn step-sequencer loop on a channel", **_WR})
    def fl_arrange_burn_loop(
        channel: Annotated[int, Field(ge=0, description="Channel index.")],
        store_undo: Annotated[int, Field(
            description="0 = no undo checkpoint; 1 = store undo (default)."
        )] = 1,
        update_ui: Annotated[int, Field(
            description="0 = no UI update; 1 = update UI (default)."
        )] = 1,
    ) -> dict:
        """Disable the step-sequencer loop on a channel for the CURRENT
        pattern. Useful after a live performance capture that left looping
        enabled -- burn it so the channel plays linearly."""
        return get_bridge().call(protocol.CMD_PATTERN_BURN_LOOP, {
            "channel": channel,
            "store_undo": store_undo,
            "update_ui": update_ui,
        })
