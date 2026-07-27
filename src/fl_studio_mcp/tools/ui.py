"""UI tools (v0.4) -- hint bar, snap mode, focused plugin, window, browser.

Verified live on FL 26.1.2 build 5557 (the ui module has 72 names; this
covers the most useful ones):
  - ui.getHintMsg / setHintMsg / showNotification
  - ui.getFocusedPluginName / isClosing
  - ui.getSnapMode / setSnapMode / snapOnOff
  - ui.isMetronomeEnabled / isPrecountEnabled / isLoopRecEnabled / isStartOnInputEnabled
  - ui.getStepEditMode / setStepEditMode
  - ui.getTimeDispMin / setTimeDispMin
  - ui.showWindow / hideWindow / getVisible / selectWindow
  - ui.navigateBrowser / navigateBrowserMenu / navigateBrowserTabs
  - ui.selectBrowserMenuItem / previewBrowserMenuItem / toggleBrowserNode
  - ui.isBrowserAutoHide / setBrowserAutoHide
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

    # ---- Hint bar ----------------------------------------------------

    @mcp.tool(annotations={"title": "Get the FL hint bar message", **_RO})
    def fl_get_hint_msg() -> dict:
        """Returns the text in FL's bottom hint bar (the one that shows
        tooltip-style help)."""
        return get_bridge().call(protocol.CMD_GET_HINT_MSG, {})

    @mcp.tool(annotations={"title": "Set the FL hint bar message", **_WR})
    def fl_set_hint_msg(
        msg: Annotated[str, Field(description="Message to display in the hint bar.")],
    ) -> dict:
        """Set the hint bar text. Use to surface your own status messages
        to the user. Supports hint-message icons (see FL docs)."""
        return get_bridge().call(protocol.CMD_SET_HINT_MSG, {"msg": msg})

    @mcp.tool(annotations={"title": "Show a built-in notification", **_WR})
    def fl_show_notification(
        id: Annotated[int, Field(description="Notification ID (0 = firmware-update, 1 = script-update).")],
    ) -> dict:
        """Show one of FL's built-in notifications."""
        return get_bridge().call(protocol.CMD_SHOW_NOTIFICATION, {"id": id})

    # ---- Focused-plugin / lifecycle ----------------------------------

    @mcp.tool(annotations={"title": "Get focused plugin name", **_RO})
    def fl_get_focused_plugin_name() -> dict:
        """Returns the name of the plugin the user is currently looking at."""
        return get_bridge().call(protocol.CMD_GET_FOCUSED_PLUGIN_NAME, {})

    @mcp.tool(annotations={"title": "Is FL closing?", **_RO})
    def fl_is_closing() -> dict:
        """Returns True when FL is in the process of closing. Useful to
        detect before sending commands that would fail during shutdown."""
        return get_bridge().call(protocol.CMD_IS_CLOSING, {})

    # ---- Snap mode ---------------------------------------------------

    @mcp.tool(annotations={"title": "Get snap mode", **_RO})
    def fl_get_snap_mode() -> dict:
        """Current snap mode index (see midi.snap_modes)."""
        return get_bridge().call(protocol.CMD_GET_SNAP_MODE, {})

    @mcp.tool(annotations={"title": "Set snap mode", **_WR})
    def fl_set_snap_mode(
        value: Annotated[int, Field(description="Snap mode index (see midi.snap_modes).")],
    ) -> dict:
        """Set the snap mode to a specific value."""
        return get_bridge().call(protocol.CMD_SET_SNAP_MODE, {"value": value})

    @mcp.tool(annotations={"title": "Toggle snap on/off", **_WR})
    def fl_snap_on_off() -> dict:
        """Toggle snapping on/off globally. Returns the new state."""
        return get_bridge().call(protocol.CMD_SNAP_ON_OFF, {})

    # ---- Transport / recording flags --------------------------------

    @mcp.tool(annotations={"title": "Is metronome enabled?", **_RO})
    def fl_is_metronome_enabled() -> dict:
        """Returns True if the metronome is enabled."""
        return get_bridge().call(protocol.CMD_IS_METRONOME_ENABLED, {})

    @mcp.tool(annotations={"title": "Is precount enabled?", **_RO})
    def fl_is_precount_enabled() -> dict:
        """Returns True if the precount (count-in) is enabled."""
        return get_bridge().call(protocol.CMD_IS_PRECOUNT_ENABLED, {})

    @mcp.tool(annotations={"title": "Is loop recording enabled?", **_RO})
    def fl_is_loop_rec_enabled() -> dict:
        """Returns True if loop recording is enabled."""
        return get_bridge().call(protocol.CMD_IS_LOOP_REC_ENABLED, {})

    @mcp.tool(annotations={"title": "Is start-on-input enabled?", **_RO})
    def fl_is_start_on_input_enabled() -> dict:
        """Returns True if 'start on MIDI input' is enabled."""
        return get_bridge().call(protocol.CMD_IS_START_ON_INPUT_ENABLED, {})

    @mcp.tool(annotations={"title": "Get step-edit mode", **_RO})
    def fl_get_step_edit_mode() -> dict:
        """Returns True if step-edit mode is active."""
        return get_bridge().call(protocol.CMD_GET_STEP_EDIT_MODE, {})

    @mcp.tool(annotations={"title": "Set step-edit mode", **_WR})
    def fl_set_step_edit_mode(
        value: Annotated[bool, Field(description="True to enable step-edit mode.")],
    ) -> dict:
        """Enable/disable step-edit mode in the piano roll."""
        return get_bridge().call(protocol.CMD_SET_STEP_EDIT_MODE, {"value": value})

    @mcp.tool(annotations={"title": "Get time display mode", **_RO})
    def fl_get_time_disp_min() -> dict:
        """Returns True if the song position panel displays time (vs bars/beats)."""
        return get_bridge().call(protocol.CMD_GET_TIME_DISP_MIN, {})

    @mcp.tool(annotations={"title": "Toggle time display mode", **_WR})
    def fl_set_time_disp_min() -> dict:
        """Toggle between time and bars/beats display in the song position panel."""
        return get_bridge().call(protocol.CMD_SET_TIME_DISP_MIN, {})

    # ---- Window control ----------------------------------------------

    @mcp.tool(annotations={"title": "Show a FL window by ID", **_WR})
    def fl_show_window(
        window_id: Annotated[int, Field(description="Window ID (see midi.window_indexes).")],
    ) -> dict:
        """Open / focus a FL UI window by its integer ID (e.g. piano roll,
        mixer, channel rack, browser)."""
        return get_bridge().call(protocol.CMD_SHOW_WINDOW, {"window_id": window_id})

    @mcp.tool(annotations={"title": "Hide a FL window by ID", **_WR})
    def fl_hide_window(
        window_id: Annotated[int, Field(description="Window ID (see midi.window_indexes).")],
    ) -> dict:
        """Hide a FL UI window by its integer ID."""
        return get_bridge().call(protocol.CMD_HIDE_WINDOW, {"window_id": window_id})

    @mcp.tool(annotations={"title": "Is a FL window visible?", **_RO})
    def fl_get_visible(
        window_id: Annotated[int, Field(description="Window ID (see midi.window_indexes).")],
    ) -> dict:
        """Returns True if the named window is currently visible."""
        return get_bridge().call(protocol.CMD_GET_VISIBLE, {"window_id": window_id})

    @mcp.tool(annotations={"title": "Select a FL window", **_WR})
    def fl_select_window(
        window_id: Annotated[int, Field(description="Window ID.")],
    ) -> dict:
        """Bring the named window to the foreground / focus it."""
        return get_bridge().call(protocol.CMD_SELECT_WINDOW, {"window_id": window_id})

    # ---- Browser navigation ------------------------------------------

    @mcp.tool(annotations={"title": "Navigate the file browser", **_WR})
    def fl_navigate_browser(
        direction: Annotated[int, Field(description="Direction (typically -1 up, +1 down).")],
    ) -> dict:
        """Navigate the FL file browser (file tree)."""
        return get_bridge().call(protocol.CMD_NAVIGATE_BROWSER, {"direction": direction})

    @mcp.tool(annotations={"title": "Navigate browser menu", **_WR})
    def fl_navigate_browser_menu(
        direction: Annotated[int, Field(description="Direction.")],
    ) -> dict:
        """Navigate within a browser menu (current selection)."""
        return get_bridge().call(protocol.CMD_NAVIGATE_BROWSER_MENU, {"direction": direction})

    @mcp.tool(annotations={"title": "Switch browser tab", **_WR})
    def fl_navigate_browser_tabs(
        direction: Annotated[int, Field(description="Direction.")],
    ) -> dict:
        """Switch between browser tabs."""
        return get_bridge().call(protocol.CMD_NAVIGATE_BROWSER_TABS, {"direction": direction})

    @mcp.tool(annotations={"title": "Select browser menu item", **_WR})
    def fl_select_browser_menu_item(
        index: Annotated[int, Field(description="Item index.")],
    ) -> dict:
        """Select an item from the browser menu (commit the current choice)."""
        return get_bridge().call(protocol.CMD_SELECT_BROWSER_MENU_ITEM, {"index": index})

    @mcp.tool(annotations={"title": "Preview browser menu item", **_WR})
    def fl_preview_browser_menu_item(
        index: Annotated[int, Field(description="Item index.")],
    ) -> dict:
        """Preview an item from the browser menu without committing."""
        return get_bridge().call(protocol.CMD_PREVIEW_BROWSER_MENU_ITEM, {"index": index})

    @mcp.tool(annotations={"title": "Toggle browser node", **_WR})
    def fl_toggle_browser_node(
        index: Annotated[int, Field(description="Node index.")],
    ) -> dict:
        """Expand/collapse a node in the browser tree."""
        return get_bridge().call(protocol.CMD_TOGGLE_BROWSER_NODE, {"index": index})

    @mcp.tool(annotations={"title": "Is browser auto-hide enabled?", **_RO})
    def fl_is_browser_auto_hide() -> dict:
        """Returns True if the browser auto-hides when not focused."""
        return get_bridge().call(protocol.CMD_IS_BROWSER_AUTO_HIDE, {})

    @mcp.tool(annotations={"title": "Set browser auto-hide", **_WR})
    def fl_set_browser_auto_hide(
        value: Annotated[bool, Field(description="True to enable auto-hide.")],
    ) -> dict:
        """Enable/disable browser auto-hide."""
        return get_bridge().call(protocol.CMD_SET_BROWSER_AUTO_HIDE, {"value": value})