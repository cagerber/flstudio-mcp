"""Project persistence tools (v0.3).

These tools reflect a hard fact about the FL Studio scripting API verified
on FL 26.1.2 build 5557 (see fl_controller/FLStudioMCP/device_FLStudioMCP.py
for the api_probe results): the controller script CANNOT enumerate notes
inside patterns/channels, CANNOT create new channels or mixer tracks,
and CANNOT write to the filesystem (controller-script sandbox).

What it CAN do:
  - Read the project title        (ui.getProgTitle)
  - Read the dirty/unsaved flag   (general.getChangedFlag)
  - Iterate plugin presets        (plugins.getName + plugins.nextPreset)
  - Manipulate channel/mixer/pattern state for what already exists

So the tools below are honest capability reports:
  - fl_get_project_dirty   -> REAL. Useful for auto-save workflows.
  - fl_get_project_path    -> title only. Path not exposed by FL.
  - fl_save_project        -> explicit "press Ctrl+S" with current state.
  - fl_export_current_project_midi -> explicit "use fl_export_midi + spec".

The agent will no longer burn time retrying impossible commands; it'll get
a clear "not exposed by FL's scripting API on this build" + the workaround.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol
from ..connection import get_bridge


def register(mcp: FastMCP) -> None:
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}

    @mcp.tool(annotations={"title": "Get project dirty (unsaved) flag", **_RO})
    def fl_get_project_dirty(
        with_title: Annotated[
            bool, Field(description="Include the project title in the response.")
        ] = True,
    ) -> dict:
        """Report whether the FL project has unsaved changes.

        Uses general.getChangedFlag() in the controller script. Useful for
        auto-save workflows: "warn before closing if dirty", "checkpoint
        every N changes", etc."""
        return get_bridge().call(
            protocol.CMD_GET_PROJECT_DIRTY, {"with_title": with_title}
        )

    @mcp.tool(annotations={"title": "Get project title (path unavailable)", **_RO})
    def fl_get_project_path(
        with_dirty: Annotated[
            bool, Field(description="Include the dirty flag in the response.")
        ] = True,
    ) -> dict:
        """Return the project TITLE (what FL shows in its title bar).

        FL's scripting API does NOT expose the absolute file path. The title
        typically equals the file stem (e.g. 'my_song' for my_song.flp).

        Response includes a 'note' explaining this limitation + 'dirty' if
        with_dirty=True (default)."""
        return get_bridge().call(
            protocol.CMD_GET_PROJECT_PATH, {"dirty": with_dirty}
        )

    @mcp.tool(annotations={"title": "Save project (FL API limitation report)", **_RO})
    def fl_save_project(
        path: Annotated[
            Optional[str],
            Field(description="Optional intended path; documented in the response only."),
        ] = None,
    ) -> dict:
        """Report whether the project is dirty + return a recommendation to
        press Ctrl+S (Cmd+S on macOS). FL's scripting API on this build does
        NOT expose a save()/saveAs() function -- verified via api_probe --
        and the controller-script sandbox blocks file I/O.

        If you need a true programmatic save, options are:
          1. Press Ctrl+S in FL (this tool will tell you when it's needed).
          2. Use an external FL plugin or a UI automation harness.
          3. Use general.saveUndo() -- but that's an undo checkpoint, not a
             file save, and won't help with persistence.
        """
        params: dict = {}
        if path is not None:
            params["path"] = path
        return get_bridge().call(protocol.CMD_SAVE_PROJECT, params)

    @mcp.tool(annotations={
        "title": "Export current project to .mid (API limitation report)", **_RO
    })
    def fl_export_current_project_midi(
        output_path: Annotated[
            Optional[str],
            Field(description="Optional intended .mid path; documented only."),
        ] = None,
    ) -> dict:
        """Report a clear API limitation: FL's scripting API does NOT expose
        note enumeration (no pattern.getNote* / channel.getNote* functions
        on FL 26.1.2 build 5557). The controller script cannot enumerate
        every note in every pattern/channel, so it cannot write a .mid of
        the current project.

        Workarounds:
          1. fl_export_midi -- build a .mid from a track spec you describe.
          2. FL's File > Export > MIDI (manual).
        """
        params: dict = {}
        if output_path is not None:
            params["path"] = output_path
        return get_bridge().call(protocol.CMD_EXPORT_CURRENT_PROJECT_MIDI, params)

    @mcp.tool(annotations={
        "title": "Create channel (FL API limitation report)", **_RO
    })
    def fl_create_channel(
        name: Annotated[
            Optional[str], Field(description="Optional intended name; documented only.")
        ] = None,
        position: Annotated[
            Optional[int], Field(description="Optional intended 0-based index; documented only.")
        ] = None,
    ) -> dict:
        """Report that FL's scripting API does NOT expose channel creation
        (channels.new / channels.add do not exist on FL 26.1.2 build 5557).

        Workaround: in FL, Channel Rack > '+' > choose Sampler / your plugin.
        After adding the channel, you can rename it via fl_set_channel_name
        and route notes to it via fl_arrange_select_channel + the note-bridge
        tools (fl_write_raga_chords, fl_write_raga_melody, etc).
        """
        params: dict = {}
        if name is not None:
            params["name"] = name
        if position is not None:
            params["position"] = position
        return get_bridge().call(protocol.CMD_CREATE_CHANNEL, params)

    @mcp.tool(annotations={
        "title": "Create mixer track (FL API limitation report)", **_RO
    })
    def fl_create_mixer_track(
        name: Annotated[
            Optional[str], Field(description="Optional intended name; documented only.")
        ] = None,
        position: Annotated[
            Optional[int], Field(description="Optional intended index; documented only.")
        ] = None,
    ) -> dict:
        """Report that FL's scripting API does NOT expose mixer-track creation
        (mixer.new / mixer.add do not exist on FL 26.1.2 build 5557).

        Workaround: in FL, Mixer > '+' > Insert track (or right-click an
        existing track > Insert). After adding, rename via fl_set_mixer_name.
        """
        params: dict = {}
        if name is not None:
            params["name"] = name
        if position is not None:
            params["position"] = position
        return get_bridge().call(protocol.CMD_CREATE_MIXER_TRACK, params)