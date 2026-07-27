"""Trigger FL's "Run last script again" hotkey from the daemon.

Windows uses the existing AttachThreadInput + synthetic-Alt focus path, then
sends Ctrl+Alt+Y. macOS activates FL Studio through AppleScript, then sends
Cmd+Opt+Y through pyautogui. Linux/Wine uses xdotool to find and focus FL
Studio's window, then sends Ctrl+Alt+Y. The Piano Roll must be FL's active
panel for the shortcut to fire because "Run last script again" is a
piano-roll command.
"""

from __future__ import annotations

import subprocess
import sys
import time


def _trigger_macos(settle=0.35):
    """Focus FL Studio on macOS and send Cmd+Opt+Y."""
    try:
        subprocess.check_call(
            ["osascript", "-e", 'tell application "FL Studio" to activate'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        focused = True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return {
            "platform": "macos",
            "fl_found": False,
            "focused": False,
            "sent_hotkey": False,
            "shortcut": "Cmd+Opt+Y",
            "error": f"{type(e).__name__}: {e}",
        }

    import pyautogui

    pyautogui.FAILSAFE = False
    time.sleep(settle)
    pyautogui.hotkey("command", "option", "y")
    return {
        "platform": "macos",
        "fl_found": True,
        "focused": focused,
        "sent_hotkey": True,
        "shortcut": "Cmd+Opt+Y",
    }


def _windows_api():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.IsIconic.argtypes = [wintypes.HWND]
    return user32, kernel32


def find_fl_hwnd():
    """Return the FL Studio main-window handle on Windows."""
    if sys.platform != "win32":
        return None
    _u, _k = _windows_api()
    _FL_WINDOW_CLASS = "TFruityLoopsMainForm"   # FL Studio main window (Delphi VCL)
    return _u.FindWindowW(_FL_WINDOW_CLASS, None)


def force_focus(hwnd):
    """Force a window to the foreground, defeating Windows foreground-lock."""
    if sys.platform != "win32":
        return False
    if not hwnd:
        return False
    _u, _k = _windows_api()
    _SW_RESTORE = 9
    _VK_MENU = 0x12          # Alt
    _KEYEVENTF_KEYUP = 0x02
    if _u.IsIconic(hwnd):
        _u.ShowWindow(hwnd, _SW_RESTORE)
    fg = _u.GetForegroundWindow()
    cur_tid = _k.GetCurrentThreadId()
    fg_tid = _u.GetWindowThreadProcessId(fg, None)
    tgt_tid = _u.GetWindowThreadProcessId(hwnd, None)
    _u.AttachThreadInput(cur_tid, fg_tid, True)
    _u.AttachThreadInput(cur_tid, tgt_tid, True)
    # A synthetic Alt tap lets SetForegroundWindow succeed under foreground-lock.
    _u.keybd_event(_VK_MENU, 0, 0, 0)
    _u.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
    _u.BringWindowToTop(hwnd)
    _u.SetForegroundWindow(hwnd)
    _u.AttachThreadInput(cur_tid, fg_tid, False)
    _u.AttachThreadInput(cur_tid, tgt_tid, False)
    return _u.GetForegroundWindow() == hwnd


def _trigger_windows(settle=0.35):
    """Focus FL Studio on Windows and send Ctrl+Alt+Y."""
    import pyautogui

    pyautogui.FAILSAFE = False
    hwnd = find_fl_hwnd()
    focused = force_focus(hwnd) if hwnd else False
    time.sleep(settle)
    pyautogui.hotkey("ctrl", "alt", "y")
    return {
        "platform": "windows",
        "fl_found": bool(hwnd),
        "focused": bool(focused),
        "sent_hotkey": True,
        "shortcut": "Ctrl+Alt+Y",
    }


def _trigger_linux(settle=0.35):
    """Focus FL Studio under Wine on Linux and send Ctrl+Alt+Y.

    Uses xdotool to find FL Studio's X11 window by title and focus it.
    Falls back gracefully if xdotool is not installed or FL isn't running.
    """
    import pyautogui

    pyautogui.FAILSAFE = False

    # Find FL Studio's window. Under Wine the window title contains
    # "FL Studio" (e.g. "FL Studio 2026").
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", "FL Studio"],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        return {
            "platform": "linux",
            "fl_found": False,
            "focused": False,
            "sent_hotkey": False,
            "shortcut": "Ctrl+Alt+Y",
            "error": (
                "xdotool is not installed. Run: sudo apt install xdotool. "
                "Without it, FL Studio cannot be auto-focused for note writing."
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            "platform": "linux",
            "fl_found": False,
            "focused": False,
            "sent_hotkey": False,
            "shortcut": "Ctrl+Alt+Y",
            "error": "xdotool search timed out.",
        }

    window_ids = result.stdout.strip().split()
    if not window_ids:
        return {
            "platform": "linux",
            "fl_found": False,
            "focused": False,
            "sent_hotkey": False,
            "shortcut": "Ctrl+Alt+Y",
            "error": (
                "FL Studio window not found. Make sure FL Studio is running "
                "under Wine and its window title contains 'FL Studio'."
            ),
        }

    # Use the first matching window
    win_id = window_ids[0]
    focused = False
    try:
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", win_id],
            capture_output=True, timeout=3,
        )
        focused = True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass

    time.sleep(settle)
    pyautogui.hotkey("ctrl", "alt", "y")
    return {
        "platform": "linux",
        "fl_found": True,
        "focused": focused,
        "sent_hotkey": True,
        "shortcut": "Ctrl+Alt+Y",
    }


def trigger_run_last_script(settle=0.35):
    """Focus FL Studio and send the platform "Run last script again" shortcut."""
    if sys.platform == "win32":
        return _trigger_windows(settle)
    if sys.platform == "darwin":
        return _trigger_macos(settle)
    # Linux and other Unix-like systems (Wine)
    return _trigger_linux(settle)
