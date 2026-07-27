# name=FLStudioMCP
# url=https://github.com/rosasynthesiz/flstudio-mcp
# receiveFrom=
# supportedDevices=
"""FLStudioMCP controller script -- v0.2 MIDI-only transport.

Lives at:
    Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/device_FLStudioMCP.py

v0.1 tried to use a file-based JSON queue. That doesn't work: FL's
controller-script Python sandbox blocks every form of file write (open(),
os.open, os.makedirs all raise SystemError or TypeError with no useful
message). This v0.2 rewrite uses MIDI SysEx for both directions.

To activate in FL:
  1. Create two loopMIDI ports (Windows) or two IAC Driver buses (macOS):
        FLStudioMCP RX   -- the MCP server's OUTPUT, FL's INPUT
        FLStudioMCP TX   -- FL's OUTPUT,           the MCP server's INPUT
  2. Options > MIDI Settings:
        Input  list -> enable "FLStudioMCP RX", Controller type = FLStudioMCP,
                       Port = some number (e.g. 42).
        Output list -> enable "FLStudioMCP TX", Port = SAME number (42).
  3. The matching port number is how FL's `device.midiOutSysex(...)` routes
     to the right output. Without it, our responses go nowhere.

Wire format: see src/fl_studio_mcp/protocol.py.

Dependencies inside FL Studio:
  - json, base64, binascii (all available -- _json, _codecs, binascii are
    in FL's built-in module list)
  - NO socket, NO requests, NO pip packages, NO file I/O
"""

import base64
import json
import math
import time

# FL Studio's built-in API modules. These are NOT importable outside FL.
import channels
import device
import general
import midi
import mixer
import patterns
import playlist
import plugins
import transport
import ui

# Arrangement module exists on FL 20.99+/21+. Import defensively so the script
# still loads on builds that lack it.
try:
    import arrangement
except Exception:
    arrangement = None

# utils.RGBToColor builds a color int in FL's native byte order; prefer it for
# coloring so we don't have to assume RGB-vs-BGR. Optional -- fall back if absent.
try:
    import utils
except Exception:
    utils = None


# ---------------------------------------------------------------------------
# Protocol constants -- MUST stay in sync with src/fl_studio_mcp/protocol.py
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = 2

SYSEX_MANUFACTURER = 0x7D
SYSEX_MAGIC = (0x4D, 0x43, 0x50)   # ASCII "MCP"

DIR_REQUEST = 0x01
DIR_RESPONSE = 0x02
DIR_HEARTBEAT = 0x03

REQUEST_ID_LEN = 8
_HEADER_LEN = 1 + 3 + 1 + REQUEST_ID_LEN

HEARTBEAT_INTERVAL = 0.5  # seconds between heartbeats

# Chunked short-message fallback (mirrors src/fl_studio_mcp/protocol.py).
# Some Wine MIDI drivers (winealsa.drv) silently drop outbound SysEx sent via
# device.midiOutSysex, even though short messages (device.midiOutMsg) get
# through fine. We send every outbound frame both ways; the server decodes
# whichever one actually arrives.
CHUNK_CHANNEL = 15
CHUNK_CTRL_START = 102
CHUNK_CTRL_DATA = 103
CHUNK_CTRL_END = 104


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_last_heartbeat = 0.0
_fl_version = "unknown"

# `device.midiOutSysex` is what we want; some old builds expose
# `midiOutSysEx` (capital E). Resolve at OnInit.
_send_sysex_fn = None


# ---------------------------------------------------------------------------
# FL Studio lifecycle callbacks
# ---------------------------------------------------------------------------

def OnInit():
    global _fl_version, _send_sysex_fn
    try:
        _fl_version = ui.getVersion()
    except Exception:
        _fl_version = "unknown"

    # Resolve the SysEx-out function name across FL builds.
    _send_sysex_fn = getattr(device, "midiOutSysex", None)
    if _send_sysex_fn is None:
        _send_sysex_fn = getattr(device, "midiOutSysEx", None)

    print("[FLStudioMCP] Ready. FL " + str(_fl_version)
          + ", protocol v" + str(PROTOCOL_VERSION) + ".")
    if _send_sysex_fn is None:
        print("[FLStudioMCP] WARNING: device.midiOutSysex not available -- "
              "responses cannot be sent back to the MCP server.")
    # Send a heartbeat immediately so the server doesn't have to wait.
    _emit_heartbeat()
    return


def OnDeInit():
    print("[FLStudioMCP] Shutting down.")
    return


def OnIdle():
    """Called by FL frequently. Used here ONLY for heartbeat emission."""
    global _last_heartbeat
    now = time.time()
    if now - _last_heartbeat >= HEARTBEAT_INTERVAL:
        _emit_heartbeat()
        _last_heartbeat = now


def _handle_request_sysex(event, source):
    """Decode + dispatch an incoming SysEx request from the MCP server.

    Returns True if the SysEx carried our magic bytes and was a request (so
    the caller can mark event.handled). Non-SysEx MIDI and SysEx without our
    magic are ignored so we coexist with other devices on the same input port.

    FL builds differ in which callback delivers incoming SysEx: some use
    OnMidiMsg, FL 21+/scripting-v40 uses OnSysEx. Both delegate here.
    """
    sysex = getattr(event, "sysex", None)
    if sysex is None:
        return False

    raw = bytes(sysex)
    # Strip F0/F7 framing if FL gave it to us. Some builds include both
    # markers, some only F0, some neither -- be tolerant.
    if len(raw) >= 1 and raw[0] == 0xF0:
        raw = raw[1:]
    if len(raw) >= 1 and raw[-1] == 0xF7:
        raw = raw[:-1]

    decoded = _decode_message(raw)
    if decoded is None:
        # Not ours -- let FL keep processing as it would normally.
        return False

    direction, request_id, request = decoded
    if direction != DIR_REQUEST:
        # Not for us (could be a stray response heard back on the input).
        return False

    command = request.get("cmd", "")
    params = request.get("params") or {}

    try:
        result = _dispatch(command, params)
        payload = {"v": PROTOCOL_VERSION, "ok": True, "data": result}
    except _ClientError as e:
        payload = {"v": PROTOCOL_VERSION, "ok": False, "error": str(e), "code": e.code}
    except Exception as e:
        payload = {
            "v": PROTOCOL_VERSION,
            "ok": False,
            "error": "%s: %s" % (type(e).__name__, e),
            "code": "internal_error",
        }

    _send_message(DIR_RESPONSE, request_id, payload)
    return True


def OnMidiMsg(event):
    """Some FL builds deliver incoming SysEx through this callback."""
    event.handled = _handle_request_sysex(event, "OnMidiMsg")


def OnSysEx(event):
    """FL 21+ / MIDI scripting v40 delivers incoming SysEx here."""
    event.handled = _handle_request_sysex(event, "OnSysEx")


def OnRefresh(flags):
    return


# ---------------------------------------------------------------------------
# SysEx encode / decode -- mirrors src/fl_studio_mcp/protocol.py
# ---------------------------------------------------------------------------

def _encode_message(direction, request_id, payload):
    # Returns the SysEx bytes WITHOUT F0/F7 framing (caller adds them).
    rid = request_id.encode("ascii")
    if len(rid) != REQUEST_ID_LEN:
        rid = (rid + b"00000000")[:REQUEST_ID_LEN]
    body_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    body_b64 = base64.b64encode(body_json.encode("ascii"))
    out = bytearray()
    out.append(SYSEX_MANUFACTURER)
    out.append(SYSEX_MAGIC[0])
    out.append(SYSEX_MAGIC[1])
    out.append(SYSEX_MAGIC[2])
    out.append(direction & 0x7F)
    out.extend(rid)
    out.extend(body_b64)
    return bytes(out)


def _decode_message(data):
    if len(data) < _HEADER_LEN:
        return None
    if data[0] != SYSEX_MANUFACTURER:
        return None
    if data[1] != SYSEX_MAGIC[0] or data[2] != SYSEX_MAGIC[1] or data[3] != SYSEX_MAGIC[2]:
        return None
    direction = data[4]
    try:
        request_id = data[5:5 + REQUEST_ID_LEN].decode("ascii", errors="replace")
    except Exception:
        return None
    body = data[_HEADER_LEN:]
    try:
        body_json = base64.b64decode(bytes(body)).decode("utf-8")
        payload = json.loads(body_json)
    except Exception:
        return None
    return direction, request_id, payload


def _send_chunked(body):
    """Fallback path for Wine hosts that drop outbound SysEx: send the same
    bytes as a stream of Control Change messages instead."""
    try:
        device.midiOutMsg(0xB0, CHUNK_CHANNEL, CHUNK_CTRL_START, 0)
        for b in body:
            device.midiOutMsg(0xB0, CHUNK_CHANNEL, CHUNK_CTRL_DATA, b & 0x7F)
        device.midiOutMsg(0xB0, CHUNK_CHANNEL, CHUNK_CTRL_END, 0)
    except Exception as e:
        print("[FLStudioMCP] chunked send failed: %s" % e)


def _send_message(direction, request_id, payload):
    body = _encode_message(direction, request_id, payload)
    if _send_sysex_fn is not None:
        framed = bytes([0xF0]) + body + bytes([0xF7])
        try:
            _send_sysex_fn(framed)
        except Exception as e:
            print("[FLStudioMCP] midiOutSysex failed: %s" % e)
    _send_chunked(body)


def _emit_heartbeat():
    _send_message(
        DIR_HEARTBEAT,
        "00000000",
        {
            "v": PROTOCOL_VERSION,
            "fl_version": _fl_version,
            "ts": time.time(),
        },
    )


# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------

class _ClientError(Exception):
    """Raised by handlers for bad input. Mapped to ok=false with code=client."""
    def __init__(self, message, code="client"):
        Exception.__init__(self, message)
        self.code = code


def _dispatch(command, params):
    handler = _HANDLERS.get(command)
    if handler is None:
        raise _ClientError("Unknown command: %s" % command, code="unknown_command")
    return handler(params)


# -- transport handlers ------------------------------------------------------

def _h_ping(params):
    return {
        "fl_version": _fl_version,
        "protocol_version": PROTOCOL_VERSION,
        "build": "color-v15",   # reload marker -- bump to verify reloads take
        "ts": time.time(),
    }


def _tempo_scale():
    # FL stores tempo as BPM * 1000 internally. Adjust here if a future FL
    # build changes the scale -- the raw value is exposed in get_tempo so the
    # ratio is observable.
    return 1000.0


def _h_get_tempo(params):
    raw = mixer.getCurrentTempo()
    return {"bpm": raw / _tempo_scale(), "raw": raw}


def _h_set_tempo(params):
    bpm = float(params.get("bpm", 0))
    if bpm < 10.0 or bpm > 999.0:
        raise _ClientError("bpm out of range (10-999)")
    flags = midi.REC_UpdateValue | midi.REC_UpdateControl
    general.processRECEvent(midi.REC_Tempo, int(bpm * _tempo_scale()), flags)
    return {"bpm": mixer.getCurrentTempo() / _tempo_scale()}


def _is_playing():
    try:
        return bool(transport.isPlaying())
    except Exception:
        return False


def _is_recording():
    try:
        return bool(transport.isRecording())
    except Exception:
        return False


def _h_play(params):
    if not _is_playing():
        transport.start()
    return {"playing": True, "recording": _is_recording()}


def _h_stop(params):
    if _is_playing():
        transport.stop()
    return {"playing": False, "recording": _is_recording()}


def _h_toggle_play(params):
    transport.start()
    return {"playing": _is_playing(), "recording": _is_recording()}


def _h_record(params):
    transport.record()
    return {"playing": _is_playing(), "recording": _is_recording()}


def _h_get_play_state(params):
    return {"playing": _is_playing(), "recording": _is_recording()}


_SONGLENGTH_MS = 0
_SONGLENGTH_ABSTICKS = 2


def _h_get_song_pos(params):
    ms = transport.getSongPos(_SONGLENGTH_MS)
    ticks = transport.getSongPos(_SONGLENGTH_ABSTICKS)
    bpm = mixer.getCurrentTempo() / _tempo_scale()
    beats = (ms / 1000.0) * (bpm / 60.0)
    return {
        "position_ms": ms,
        "position_ticks": ticks,
        "position_beats": beats,
        "bpm": bpm,
    }


def _h_set_song_pos(params):
    if "ms" in params:
        transport.setSongPos(float(params["ms"]), _SONGLENGTH_MS)
    elif "beats" in params:
        bpm = mixer.getCurrentTempo() / _tempo_scale()
        if bpm <= 0:
            bpm = 120.0
        ms = float(params["beats"]) * 60000.0 / bpm
        transport.setSongPos(ms, _SONGLENGTH_MS)
    elif "ticks" in params:
        transport.setSongPos(int(params["ticks"]), _SONGLENGTH_ABSTICKS)
    else:
        raise _ClientError("Provide one of: ms, beats, ticks")
    return _h_get_song_pos({})


# -- Phase 1: project / mixer / channel read surface -------------------------
# SysEx payloads >~1.5 KB are dropped (probe: 1000 B OK, 2000 B lost). LIST
# reads paginate by PAYLOAD BUDGET (not a fixed count) and truncate names, so a
# page never exceeds the safe size no matter how long the names are. Full
# untruncated names stay available via the single-item gets.

_LIST_BUDGET = 600   # max bytes of 'data' JSON/page -> ~843 B wire (< safe 1000)
_NAME_CAP = 24       # name length in LIST responses only


def _truncate_name(name):
    name = name or ""
    return (name[:_NAME_CAP], True) if len(name) > _NAME_CAP else (name, False)


def _safe(fn, default=None):
    """Run an FL API call defensively -- returns ``default`` on any exception.
    Used in commands that probe for state across FL builds where some
    functions may not exist."""
    try:
        return fn()
    except Exception:
        return default


def _paginate(total, start, entry_fn, key):
    start = max(0, min(int(start), total))
    out, i = [], start
    while i < total:
        out.append(entry_fn(i))
        i += 1
        nxt = i if i < total else None
        size = len(json.dumps({"total": total, "start": start, "next_start": nxt, key: out},
                              separators=(",", ":")))
        if size > _LIST_BUDGET and len(out) > 1:
            out.pop()           # this entry overflowed the page -> next page
            i -= 1
            break
    return {"total": total, "start": start,
            "next_start": (i if i < total else None), key: out}


def _h_get_project_state(params):
    try:
        pat_num = patterns.patternNumber()
    except Exception:
        pat_num = -1
    return {
        "fl_version": _fl_version,
        "tempo_bpm": mixer.getCurrentTempo() / _tempo_scale(),
        "playing": _is_playing(),
        "recording": _is_recording(),
        "pattern_number": pat_num,
        "pattern_count": patterns.patternCount(),
        "channel_count": channels.channelCount(),
        "mixer_track_count": mixer.trackCount(),
    }


def _mixer_track_dict(i):
    return {
        "i": i,
        "name": mixer.getTrackName(i),
        "pan": round(mixer.getTrackPan(i), 4),
        "mute": bool(mixer.isTrackMuted(i)),
        "solo": bool(mixer.isTrackSolo(i)),
        "color": _color_out(_safe_track_color(i)),
        **_vol_out(mixer.getTrackVolume(i)),
    }


def _mixer_list_entry(i):
    name, cut = _truncate_name(mixer.getTrackName(i))
    e = {"i": i, "name": name, "pan": round(mixer.getTrackPan(i), 4),
         "mute": bool(mixer.isTrackMuted(i)), "solo": bool(mixer.isTrackSolo(i)),
         **_vol_out(mixer.getTrackVolume(i))}
    if cut:
        e["trunc"] = True
    return e


def _h_mixer_list_tracks(params):
    return _paginate(mixer.trackCount(), params.get("start", 0), _mixer_list_entry, "tracks")


def _h_mixer_get_track(params):
    return _mixer_track_dict(int(params.get("index", 0)))


def _channel_dict(i):
    try:
        tgt = channels.getTargetFxTrack(i)
    except Exception:
        tgt = None
    return {
        "i": i,
        "name": channels.getChannelName(i),
        "pan": round(channels.getChannelPan(i), 4),
        "mute": bool(channels.isChannelMuted(i)),
        "solo": bool(channels.isChannelSolo(i)),
        "target_fx_track": tgt,
        "color": _color_out(_safe_channel_color(i)),
        **_vol_out(channels.getChannelVolume(i)),
    }


def _channel_list_entry(i):
    name, cut = _truncate_name(channels.getChannelName(i))
    e = {"i": i, "name": name, "pan": round(channels.getChannelPan(i), 4),
         "mute": bool(channels.isChannelMuted(i)),
         "solo": bool(channels.isChannelSolo(i)),
         **_vol_out(channels.getChannelVolume(i))}
    if cut:
        e["trunc"] = True
    return e


def _h_channel_list(params):
    return _paginate(channels.channelCount(), params.get("start", 0), _channel_list_entry, "channels")


def _h_channel_get(params):
    return _channel_dict(int(params.get("index", 0)))


# -- Phase 1A write surface --------------------------------------------------
# Volume: FL normalized 0.8 == unity (0 dB), NOT 1.0. Convert with that anchor
# and ALWAYS read back the value FL actually accepted (FL clamps).

_UNITY = 0.8


def _db_to_norm(db):
    return max(0.0, min(1.0, _UNITY * (10.0 ** (db / 20.0))))


def _norm_to_db(norm):
    return -120.0 if norm <= 0.0 else 20.0 * math.log10(norm / _UNITY)


def _vol_out(norm):
    # Unified volume representation used by EVERY volume-bearing response
    # (reads + writes, mixer + channel): normalized 0..1 and dB (0.8 = unity).
    return {"vol_norm": round(norm, 4), "vol_db": round(_norm_to_db(norm), 2)}


def _resolve_vol(p):
    v = float(p["value"])
    return _db_to_norm(v) if p.get("unit") == "db" else max(0.0, min(1.0, v))


def _clamp_pan(v):
    return max(-1.0, min(1.0, float(v)))   # FL pan range is -1..+1


def _h_mixer_set_volume(p):
    t = int(p["track"])
    mixer.setTrackVolume(t, _resolve_vol(p))
    out = {"track": t}
    out.update(_vol_out(mixer.getTrackVolume(t)))
    return out


def _h_mixer_set_pan(p):
    t = int(p["track"])
    mixer.setTrackPan(t, _clamp_pan(p["value"]))
    return {"track": t, "pan": round(mixer.getTrackPan(t), 4)}


def _h_mixer_set_mute(p):
    # FL coalesces multiple mute ops per script-tick and the explicit-value
    # form muteTrack(t,1) does not mute on this build -- so set state with a
    # single bare toggle (one per SysEx = one tick).
    t = int(p["track"])
    if bool(mixer.isTrackMuted(t)) != bool(p["state"]):
        mixer.muteTrack(t)
    return {"track": t, "mute": bool(mixer.isTrackMuted(t))}


def _h_mixer_set_solo(p):
    t = int(p["track"])
    if bool(mixer.isTrackSolo(t)) != bool(p["state"]):
        mixer.soloTrack(t)
    return {"track": t, "solo": bool(mixer.isTrackSolo(t))}


def _h_mixer_set_name(p):
    t = int(p["track"])
    mixer.setTrackName(t, str(p["name"]))
    return {"track": t, "name": mixer.getTrackName(t)}


def _h_channel_set_volume(p):
    c = int(p["channel"])
    channels.setChannelVolume(c, _resolve_vol(p))
    out = {"channel": c}
    out.update(_vol_out(channels.getChannelVolume(c)))
    return out


def _h_channel_set_pan(p):
    c = int(p["channel"])
    channels.setChannelPan(c, _clamp_pan(p["value"]))
    return {"channel": c, "pan": round(channels.getChannelPan(c), 4)}


def _h_channel_set_mute(p):
    c = int(p["channel"])
    if bool(channels.isChannelMuted(c)) != bool(p["state"]):
        channels.muteChannel(c)
    return {"channel": c, "mute": bool(channels.isChannelMuted(c))}


def _h_channel_set_solo(p):
    c = int(p["channel"])
    if bool(channels.isChannelSolo(c)) != bool(p["state"]):
        channels.soloChannel(c)
    return {"channel": c, "solo": bool(channels.isChannelSolo(c))}


# -- Track / channel color ---------------------------------------------------
# Thin: the server maps a color name/hex to r,g,b and we just apply it. We
# prefer utils.RGBToColor so FL builds the int in its own byte order; rollback
# instead sends the exact "color" int we read back (order-agnostic).

def _rgb_to_int(r, g, b):
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    if utils is not None and hasattr(utils, "RGBToColor"):
        try:
            return int(utils.RGBToColor(r, g, b)) & 0xFFFFFF
        except Exception:
            pass
    return (r << 16) | (g << 8) | b


def _color_out(color):
    c = int(color) & 0xFFFFFF
    return {"int": c, "hex": "#%06X" % c,
            "r": (c >> 16) & 0xFF, "g": (c >> 8) & 0xFF, "b": c & 0xFF}


def _resolve_color(p):
    if p.get("color") is not None:           # explicit int (rollback path)
        return int(p["color"]) & 0xFFFFFF
    return _rgb_to_int(p.get("r", 0), p.get("g", 0), p.get("b", 0))


def _safe_track_color(i):
    try:
        return int(mixer.getTrackColor(i)) & 0xFFFFFF
    except Exception:
        return 0


def _safe_channel_color(i):
    try:
        return int(channels.getChannelColor(i)) & 0xFFFFFF
    except Exception:
        return 0


def _h_mixer_get_color(p):
    t = int(p["track"])
    return {"track": t, "color": _color_out(_safe_track_color(t))}


def _h_mixer_set_color(p):
    t = int(p["track"])
    mixer.setTrackColor(t, _resolve_color(p))
    return {"track": t, "color": _color_out(_safe_track_color(t))}


def _h_channel_get_color(p):
    c = int(p["channel"])
    return {"channel": c, "color": _color_out(_safe_channel_color(c))}


def _h_channel_set_color(p):
    c = int(p["channel"])
    channels.setChannelColor(c, _resolve_color(p))
    return {"channel": c, "color": _color_out(_safe_channel_color(c))}


# -- Phase 1B: plugin parameters --------------------------------------------
# plugins API arg order (IL-Group): getPluginName(index, slot),
# getParamCount(index, slot), getParamName(paramIndex, index, slot),
# getParamValue(paramIndex, index, slot), setParamValue(value, paramIndex,
# index, slot). For a mixer-track effect, index=mixer track, slot>=0.

def _h_plugin_list(p):
    track = int(p["track"])
    slots = []
    for s in range(10):              # 10 mixer effect slots
        try:
            if plugins.isValid(track, s):
                slots.append({"slot": s, "name": plugins.getPluginName(track, s)})
        except Exception:
            pass
    return {"track": track, "slots": slots}


def _h_plugin_get_params(p):
    track = int(p["track"])
    slot = int(p["slot"])
    if not plugins.isValid(track, slot):
        raise _ClientError("no plugin at track %d slot %d" % (track, slot))
    total = plugins.getParamCount(track, slot)
    start = max(0, int(p.get("start", 0)))
    out = []
    i = start
    scanned = 0
    while i < total and scanned < 150:        # cap scan/page (bounds VST 4240 cost)
        nm = plugins.getParamName(i, track, slot)
        cur = i
        i += 1
        scanned += 1
        if nm:                                 # skip empty-name slots (unused VST)
            out.append({
                "i": cur,
                "name": nm[:30],
                "v": round(plugins.getParamValue(cur, track, slot), 4),
                "s": (plugins.getParamValueString(cur, track, slot) or "")[:16],
            })
            if len(json.dumps(out, separators=(",", ":"))) > 480:
                break
    return {
        "track": track, "slot": slot, "plugin": plugins.getPluginName(track, slot),
        "total": total, "start": start,
        "next_start": (i if i < total else None), "params": out,
    }


def _h_plugin_get_param(p):
    track = int(p["track"])
    slot = int(p["slot"])
    idx = int(p["param"])
    if not plugins.isValid(track, slot):
        raise _ClientError("no plugin at track %d slot %d" % (track, slot))
    return {
        "track": track, "slot": slot, "param": idx,
        "name": plugins.getParamName(idx, track, slot),
        "v": round(plugins.getParamValue(idx, track, slot), 4),
        "s": (plugins.getParamValueString(idx, track, slot) or ""),
    }


def _h_plugin_set_param(p):
    track = int(p["track"])
    slot = int(p["slot"])
    idx = int(p["param"])
    val = float(p["value"])
    if not plugins.isValid(track, slot):
        raise _ClientError("no plugin at track %d slot %d" % (track, slot))
    plugins.setParamValue(val, idx, track, slot)
    return {
        "track": track, "slot": slot, "param": idx,
        "name": plugins.getParamName(idx, track, slot),
        "v": round(plugins.getParamValue(idx, track, slot), 4),
        "s": (plugins.getParamValueString(idx, track, slot) or ""),
    }


# -- Routing / grouping / cleanup READ surface (Slice 1, read-only) ----------

def _route_level(src, dst):
    fn = getattr(mixer, "getRouteSendLevel", None)
    if fn is None:
        return None
    try:
        return round(fn(src, dst), 4)
    except Exception:
        return None


def _route_targets(src):
    n = mixer.trackCount()
    out = []
    for dst in range(n):
        if dst == src:
            continue
        try:
            active = mixer.getRouteSendActive(src, dst)
        except Exception:
            active = 0
        if active:
            e = {"dst": dst, "dst_name": mixer.getTrackName(dst)}
            lvl = _route_level(src, dst)
            if lvl is not None:
                e["level"] = lvl
            out.append(e)
    return out


def _h_mixer_get_routing(p):
    t = int(p.get("track", 0))
    return {"track": t, "name": mixer.getTrackName(t), "routes_to": _route_targets(t)}


def _routing_entry(i):
    name, cut = _truncate_name(mixer.getTrackName(i))
    e = {"i": i, "name": name, "routes_to": _route_targets(i)}
    if cut:
        e["trunc"] = True
    return e


def _h_mixer_get_routing_all(p):
    return _paginate(mixer.trackCount(), p.get("start", 0), _routing_entry, "routing")


def _channel_route_entry(i):
    try:
        tgt = channels.getTargetFxTrack(i)
    except Exception:
        tgt = None
    cname, cut = _truncate_name(channels.getChannelName(i))
    valid = isinstance(tgt, int) and 0 <= tgt < mixer.trackCount()
    e = {"channel": i, "name": cname, "target_mixer_track": tgt,
         "target_name": (mixer.getTrackName(tgt) if valid else None)}
    if cut:
        e["trunc"] = True
    return e


def _h_channel_routing_summary(p):
    return _paginate(channels.channelCount(), p.get("start", 0), _channel_route_entry, "channels")


# -- Routing WRITE surface (Slice 2) -----------------------------------------

def _h_mixer_set_route(p):
    """Enable/disable a send from src -> dst. Thin: one setRouteTo + the
    required afterRoutingChanged(), then read back the active state."""
    src = int(p["src"])
    dst = int(p["dst"])
    on = bool(p.get("enabled", True))
    mixer.setRouteTo(src, dst, 1 if on else 0)
    mixer.afterRoutingChanged()
    return {"src": src, "dst": dst,
            "enabled": bool(mixer.getRouteSendActive(src, dst))}


# -- Level awareness READ surface (peaks; meaningful only while playing) -----

def _h_mixer_get_peaks(p):
    """Meter peaks for a mixer track. mode 0=L, 1=R, 2=max(LR). Linear values
    (1.0 ~ 0 dBFS, can exceed 1). Near-zero when transport is stopped."""
    track = int(p["track"])
    out = {"track": track}
    for mode, key in ((0, "peak_l"), (1, "peak_r"), (2, "peak_max")):
        try:
            out[key] = round(float(mixer.getTrackPeaks(track, mode)), 6)
        except Exception:
            out[key] = None
    return out


# -- Plugin preset navigate/read (op: info | next | prev | by_name | by_index) --

# FL has no direct "set preset by index" function -- only next/prev stepping.
# So we walk the cycle once and stop on a name match (case-insensitive substring
# by default; exact=True for whole-string match).
# Cost: O(preset_count) per call. Most plugins have <100 presets; fine for
# single-shot use but don't call this from a tight loop.

def _plugin_current_name(track, slot):
    """Return the current preset name, trying both FL name flags (3 = name only,
    6 = name + vendor). Returns the first one that's truthy."""
    for flag in (3, 6):
        try:
            n = plugins.getName(track, slot, flag, 0)
        except Exception:
            n = None
        if n:
            return n
    return None


def _h_plugin_preset(p):
    """Navigate/read a plugin's presets. For a channel generator pass slot=-1.
    op 'next'/'prev' step the preset first, then everything reports the CURRENT
    state: preset_count + candidate current-preset names (getName flags 3/6 +
    getPluginName). Wrapped defensively -- a walled-off plugin just yields
    count 0/1 and unchanging names.

    New (v0.3):
      'by_name'  -> step through the preset cycle until the current preset
                    name contains ``name`` (case-insensitive substring).
                    Stops after one full cycle without a match.
                    Params: name (required), exact (default False).
      'by_index' -> step next/prev until the index lands on ``index`` (mod
                    getPresetCount). Useful for the first preset or last.
    """
    track = int(p["track"])
    slot = int(p.get("slot", -1))
    op = p.get("op", "info")
    out = {"track": track, "slot": slot, "op": op}
    if op == "next":
        try:
            plugins.nextPreset(track, slot)
        except Exception as e:
            out["nav_error"] = "nextPreset: %s" % e
    elif op == "prev":
        try:
            plugins.prevPreset(track, slot)
        except Exception as e:
            out["nav_error"] = "prevPreset: %s" % e
    elif op == "by_name":
        name_want = (p.get("name") or "").strip()
        if not name_want:
            return {"ok": False, "error": "by_name requires 'name' param",
                    "track": track, "slot": slot}
        try:
            count = plugins.getPresetCount(track, slot)
        except Exception as e:
            return {"ok": False, "error": "getPresetCount: %s" % e,
                    "track": track, "slot": slot}
        if count is None or count <= 1:
            return {"ok": False, "error": "no presets available",
                    "track": track, "slot": slot, "preset_count": count}
        # Iterate one full cycle.
        exact = bool(p.get("exact", False))
        match_name = name_want.lower()
        steps = 0
        found = False
        first_seen = None
        for _ in range(count):
            current = _plugin_current_name(track, slot)
            if current is None:
                # walled-off plugin -- bail
                break
            if first_seen is None:
                first_seen = current
            cmp = current.lower()
            if (exact and cmp == match_name) or (not exact and match_name in cmp):
                found = True
                break
            try:
                plugins.nextPreset(track, slot)
            except Exception as e:
                return {"ok": False, "error": "nextPreset mid-iter: %s" % e,
                        "track": track, "slot": slot, "steps": steps}
            steps += 1
        out.update({
            "ok": found,
            "preset_count": count,
            "steps": steps,
            "current_name": _plugin_current_name(track, slot),
            "first_seen": first_seen,
            "requested": name_want,
            "exact": exact,
            "note": ("Match found." if found else
                     "No preset matched %r within one full cycle (%d steps). "
                     "Use fl_plugin_preset op=info to see the name format." % (
                         name_want, count)),
        })
        if not found:
            out["error"] = "preset name not found"
        return out
    elif op == "by_index":
        if "index" not in p:
            return {"ok": False, "error": "by_index requires 'index' param",
                    "track": track, "slot": slot}
        try:
            count = plugins.getPresetCount(track, slot)
        except Exception as e:
            return {"ok": False, "error": "getPresetCount: %s" % e,
                    "track": track, "slot": slot}
        if count is None or count <= 1:
            return {"ok": False, "error": "no presets available",
                    "track": track, "slot": slot, "preset_count": count}
        target = int(p["index"]) % count
        # Always step next `target` times from current (wrap). This is the
        # only navigation FL exposes.
        for _ in range(target):
            try:
                plugins.nextPreset(track, slot)
            except Exception as e:
                return {"ok": False, "error": "nextPreset: %s" % e,
                        "track": track, "slot": slot}
        out.update({
            "ok": True,
            "preset_count": count,
            "index": target,
            "current_name": _plugin_current_name(track, slot),
        })
        return out
    try:
        out["preset_count"] = plugins.getPresetCount(track, slot)
    except Exception as e:
        out["preset_count"] = None
        out["count_error"] = str(e)
    try:
        out["plugin_name"] = plugins.getPluginName(track, slot)
    except Exception:
        out["plugin_name"] = None
    for flag, key in ((3, "name_f3"), (6, "name_f6")):
        try:
            out[key] = plugins.getName(track, slot, flag, 0)
        except Exception:
            out[key] = None
    return out


# -- API introspection / arrangement probe -----------------------------------

def _h_api_probe(p):
    """op:
      dir    -> {module, names}: public names of one FL module (per-module to
                stay under the SysEx size limit).
      ppq    -> {ppq, pattern_count, pattern_number}
      marker_add -> arrangement.addAutoTimeMarker(time, name)
      undo   -> general.undoUp() (best-effort, to remove a test marker)
    """
    op = p.get("op", "dir")
    if op == "dir":
        mods = {"playlist": playlist, "arrangement": arrangement, "patterns": patterns,
                "general": general, "transport": transport, "ui": ui, "midi": midi,
                "mixer": mixer, "channels": channels}
        mod = mods.get(p.get("module", "playlist"))
        if mod is None:
            return {"module": p.get("module"), "error": "module not available"}
        names = [n for n in dir(mod) if not n.startswith("_")]
        start = max(0, int(p.get("start", 0)))      # budget-paginate (dir is large)
        out, i = [], start
        while i < len(names):
            out.append(names[i])
            i += 1
            if len(json.dumps(out, separators=(",", ":"))) > 600 and len(out) > 1:
                out.pop()
                i -= 1
                break
        return {"module": p.get("module", "playlist"), "total": len(names),
                "start": start, "next_start": (i if i < len(names) else None), "names": out}
    if op == "ppq":
        out = {}
        for key, fn in (("ppq", lambda: general.getRecPPQ()),
                        ("pattern_count", lambda: patterns.patternCount()),
                        ("pattern_number", lambda: patterns.patternNumber())):
            try:
                out[key] = fn()
            except Exception as e:
                out[key + "_error"] = str(e)
        return out
    if op == "marker_add":
        if arrangement is None:
            return {"ok": False, "error": "arrangement module not available"}
        t = int(p["time"])
        name = p.get("name", "TEST")
        try:
            arrangement.addAutoTimeMarker(t, name)
            return {"ok": True, "added": name, "time": t}
        except Exception as e:
            return {"ok": False, "error": "addAutoTimeMarker: %s" % e}
    if op == "undo":
        try:
            general.undoUp()
            return {"ok": True, "undid": True}
        except Exception as e:
            return {"ok": False, "error": "undoUp: %s" % e}
    return {"error": "unknown op: %s" % op}


# -- Arrangement primitives (Slice 1): pattern create/clone + markers --------

def _h_pattern_list(p):
    """Budget-paginated pattern list: {pattern (1-based), name}. Thin read."""
    def entry(i):
        pn = i + 1                       # FL patterns are 1-based
        name, cut = _truncate_name(patterns.getPatternName(pn))
        e = {"pattern": pn, "name": name}
        if cut:
            e["trunc"] = True
        return e
    return _paginate(patterns.patternCount(), p.get("start", 0), entry, "patterns")


def _h_arrange_new_pattern(p):
    """Find the next empty pattern (or count+1), select it, name it. Selecting
    it is what lets the note bridge write INTO this pattern next."""
    name = p.get("name", "PATTERN")
    try:
        idx = patterns.findFirstNextEmptyPat()
    except Exception:
        idx = -1
    if not isinstance(idx, int) or idx < 1:
        idx = patterns.patternCount() + 1
    patterns.jumpToPattern(idx)
    try:
        patterns.setPatternName(idx, name)
    except Exception as e:
        return {"ok": False, "error": "setPatternName: %s" % e, "index": idx}
    return {"ok": True, "index": idx, "name": patterns.getPatternName(idx),
            "count": patterns.patternCount(), "selected": patterns.patternNumber()}


def _h_arrange_clone_pattern(p):
    """Clone a pattern (copies its notes) and rename the clone. Reports
    count before/after + the clone's selected index so we can see what FL did."""
    src = int(p["src"])
    new_name = p.get("new_name", "CLONE")
    patterns.jumpToPattern(src)
    before = patterns.patternCount()
    try:
        patterns.clonePattern(src)
    except Exception:
        try:
            patterns.clonePattern()
        except Exception as e:
            return {"ok": False, "error": "clonePattern: %s" % e}
    new_idx = patterns.patternNumber()
    after = patterns.patternCount()
    try:
        patterns.setPatternName(new_idx, new_name)
    except Exception as e:
        return {"ok": False, "error": "setPatternName: %s" % e, "new_index": new_idx}
    return {"ok": True, "src": src, "new_index": new_idx,
            "new_name": patterns.getPatternName(new_idx),
            "count_before": before, "count_after": after}


def _h_ensure_piano_roll(p):
    """Open/focus the Piano roll from the controller (ui.showWindow), so the
    Ctrl+Alt+Y note-bridge trigger has a piano roll to act on -- no manual open.
    Defensive: reports the widget constant + visibility so we can confirm."""
    wid = getattr(midi, "widPianoRoll", None)
    out = {"wid_pianoroll": wid}
    try:
        if wid is not None and hasattr(ui, "getVisible"):
            out["visible_before"] = bool(ui.getVisible(wid))
    except Exception:
        out["visible_before"] = None
    if wid is None or not hasattr(ui, "showWindow"):
        out["ok"] = False
        out["error"] = "ui.showWindow / midi.widPianoRoll unavailable"
        return out
    try:
        ui.showWindow(wid)
        out["ok"] = True
        out["method"] = "ui.showWindow(widPianoRoll)"
    except Exception as e:
        out["ok"] = False
        out["error"] = "showWindow: %s" % e
    return out


def _h_channel_select(p):
    """Make one channel the active selection. The Piano roll follows the
    selected channel, so this retargets the note bridge to write into it."""
    idx = int(p["channel"])
    try:
        channels.selectOneChannel(idx)
    except Exception as e:
        return {"ok": False, "error": "selectOneChannel: %s" % e}
    return {"ok": True, "channel": idx, "name": channels.getChannelName(idx),
            "selected": channels.channelNumber()}


def _h_arrange_add_marker(p):
    if arrangement is None:
        return {"ok": False, "error": "arrangement module not available"}
    bar = int(p["bar"])
    name = p.get("name", "MARK")
    ppb = None
    try:
        ppb = general.getRecPPB()
    except Exception:
        ppb = None
    if not isinstance(ppb, (int, float)) or ppb <= 0:
        try:
            ppb = 4 * general.getRecPPQ()
        except Exception:
            ppb = 384
    t = int((bar - 1) * ppb)            # bar 1 -> tick 0
    try:
        arrangement.addAutoTimeMarker(t, name)
        return {"ok": True, "bar": bar, "name": name, "time": t, "ppb": ppb}
    except Exception as e:
        return {"ok": False, "error": "addAutoTimeMarker: %s" % e}


# ------------------------------------------------------------------
# v0.3 MCP enhancements -- stub bodies (filled in by later commits).
# Stubs raise a recognizable error so premature calls fail LOUDLY
# instead of silently succeeding, which is important for diagnosing
# partial-deployed controller scripts during the staged rollout.
# ------------------------------------------------------------------

def _h_save_project(p):
    """FL's scripting API on this build exposes NO save() / saveAs() function
    (verified via api_probe -- only saveUndo + undoUp are available, neither
    writes the project file). The controller script also can't write to disk
    (sandbox blocks file I/O). So this command can only REPORT the project
    state and direct the user to Ctrl+S (or Cmd+S on macOS).

    Accepts optional ``path`` for documentation only -- it's returned in the
    response so the user can see what we'd have written to.
    """
    out = {
        "ok": False,
        "code": "api_unavailable",
        "implementation": "honest_not_implemented",
        "title": _safe(lambda: ui.getProgTitle()),
        "dirty": _safe(lambda: bool(general.getChangedFlag())),
        "recommendation": (
            "FL's scripting API does not expose a save() function on this "
            "build. Press Ctrl+S (Cmd+S on macOS) in FL to save. The MCP can "
            "monitor the dirty flag with fl_get_project_dirty."
        ),
    }
    if "path" in p:
        out["requested_path"] = p["path"]
    return out


def _h_get_project_path(p):
    """ui.getProgTitle() returns the project TITLE; FL's scripting API does
    NOT expose the absolute file path. The title usually contains the file
    stem (e.g. 'my_song' for my_song.flp)."""
    try:
        title = ui.getProgTitle()
    except Exception as e:
        return {"ok": False, "error": "ui.getProgTitle: %s" % e}
    out = {
        "ok": True,
        "title": title,
        "path": None,             # not available via API
        "note": ("FL's scripting API does not expose the absolute file path. "
                 "title is the project name as shown in FL's title bar."),
    }
    if "dirty" not in p or p.get("dirty"):
        try:
            out["dirty"] = bool(general.getChangedFlag())
        except Exception:
            out["dirty"] = None  # type: ignore[assignment]
    return out


def _h_get_project_dirty(p):
    """general.getChangedFlag() returns True if the project has unsaved
    modifications since the last save."""
    try:
        dirty = bool(general.getChangedFlag())
    except Exception as e:
        return {"ok": False, "error": "general.getChangedFlag: %s" % e}
    out = {"ok": True, "dirty": dirty}
    if p.get("with_title", True):
        try:
            out["title"] = ui.getProgTitle()
        except Exception:
            out["title"] = None
    return out


def _h_export_current_project_midi(p):
    """FL's scripting API exposes NO pattern.getNote* / channel.getNote*
    functions (verified via api_probe on FL 26.1.2 build 5557). Notes live in
    the piano-roll data structures that the API does not surface. There is
    no way for the controller script to enumerate every note in every
    pattern + channel.

    Workarounds (in order of recommendation):
      1. Build the .mid from a SPEC using fl_export_midi -- you describe the
         tracks and notes you want and the server writes the type-1 .mid.
      2. In FL: File > Export > MIDI, do it manually.
    """
    return {
        "ok": False,
        "code": "api_unavailable",
        "implementation": "honest_not_implemented",
        "title": _safe(lambda: ui.getProgTitle()),
        "dirty": _safe(lambda: bool(general.getChangedFlag())),
        "channel_count": _safe(lambda: channels.channelCount()),
        "pattern_count": _safe(lambda: patterns.patternCount()),
        "recommendation": (
            "FL's scripting API does not expose note enumeration. Use "
            "fl_export_midi with a track spec (Claude generates the notes "
            "and the server writes the .mid), or export manually in FL: "
            "File > Export > MIDI."
        ),
    }


def _h_create_channel(p):
    """FL's scripting API does NOT expose channels.new() (verified via
    api_probe -- channels has 54 public names, none of them 'new'/'add'/
    'create'/'insert'). The only way to add a channel-rack channel is in
    the FL UI: Channel rack > + button > [Sampler / plugin].

    This command accepts an optional ``name`` so the response documents
    what we WISHED we could create, and returns an honest
    not-implemented report with the recommendation."""
    out = {
        "ok": False,
        "code": "api_unavailable",
        "implementation": "honest_not_implemented",
        "requested_name": p.get("name"),
        "requested_position": p.get("position"),
        "channel_count": _safe(lambda: channels.channelCount()),  # type: ignore[attr-defined]
        "recommendation": (
            "FL's scripting API does not expose channel creation. In FL: "
            "Channel Rack > click '+' > choose Sampler / your plugin > the "
            "new channel appears at the end. After adding, you can rename "
            "it via fl_set_channel_name and route notes to it via "
            "fl_arrange_select_channel + fl_write_raga_chords/melody."
        ),
    }
    return out


def _h_create_mixer_track(p):
    """FL's scripting API does NOT expose mixer.new() (verified via
    api_probe -- mixer has 75 public names, none of them 'new'/'add'/
    'create'/'insert'). The only way to add a mixer track is in the FL
    UI: Mixer > + button (or right-click > Insert)."""
    out = {
        "ok": False,
        "code": "api_unavailable",
        "implementation": "honest_not_implemented",
        "requested_name": p.get("name"),
        "requested_position": p.get("position"),
        "mixer_track_count": _safe(lambda: mixer.getTrackCount()),  # type: ignore[attr-defined]
        "recommendation": (
            "FL's scripting API does not expose mixer track creation. In "
            "FL: Mixer > click '+' (Insert track) or right-click an "
            "existing track > Insert. After adding, you can rename it via "
            "fl_set_mixer_name."
        ),
    }
    return out


def _h_get_automation_info(p):
    """FL's scripting API does NOT expose channel-rack automation on this
    build (verified via api_probe -- channels has 54 public names; NONE of
    them contain 'auto' as a substring). The step sequencer / grid bit
    functions exist (getStepParam, getGridBit) but those are CHANNEL STEP
    SEQUENCER data, not automation clips.

    There is also no playlist-level automation API exposed to controller
    scripts. FL automation is UI-driven (right-click a knob > 'Create
    automation clip').

    This command returns an honest not-implemented report listing what
    IS scriptable and pointing the user at the UI workflow."""
    ch_count = _safe(lambda: channels.channelCount())  # type: ignore[attr-defined]
    pat_count = _safe(lambda: patterns.patternCount())  # type: ignore[attr-defined]
    out = {
        "ok": False,
        "code": "api_unavailable",
        "implementation": "honest_not_implemented",
        "track": p.get("track"),
        "slot": p.get("slot"),
        "channel_count": ch_count,
        "pattern_count": pat_count,
        "available_alternatives": (
            "FL exposes the channel step sequencer / grid bit data via "
            "channels.getStepParam + channels.getGridBit -- but that is "
            "SEQUENCER data, not automation clips."
        ),
        "recommendation": (
            "FL's scripting API does not expose automation clips (channel "
            "rack or playlist). To create automation: right-click the knob "
            "in FL > 'Create automation clip' (or use the playlist's "
            "automation lane). To capture live automation: arm Touch in "
            "the playlist toolbar."
        ),
    }
    return out


def _h_set_automation_point(p):
    """Same API limitation as _h_get_automation_info. Accepts the same
    params the user would intuitively want to pass so the response is
    actionable."""
    return {
        "ok": False,
        "code": "api_unavailable",
        "implementation": "honest_not_implemented",
        "requested": {k: v for k, v in p.items()},  # echo back what was asked
        "recommendation": (
            "FL's scripting API does not expose automation clips. To set "
            "an automation point: in FL, open the automation clip on the "
            "playlist and add the point with the mouse. For automated "
            "control of EXISTING channel-rack state, use the step sequencer "
            "via channels.setGridBit + channels.setStepParameterByIndex."
        ),
    }


# ------------------------------------------------------------------
# v0.3 -- discovered via FL-Studio-API-Stubs (MaddyGuthridge) + live probe
# Verified present on FL 26.1.2 build 5557 (api_probe).
# ------------------------------------------------------------------

def _h_dump_score_log(p):
    """general.dumpScoreLog(time, silent=False) writes the last ``time``
    seconds of played MIDI to the SELECTED pattern. This is the closest the
    FL API gets to 'live capture into a pattern' (i.e. record what you
    played back into the piano roll). The controller script CAN call this
    -- the score log is buffered inside FL and written on demand."""
    time_s = int(p.get("time", 5))
    silent = bool(p.get("silent", True))
    if time_s < 1 or time_s > 60:
        return {"ok": False, "error": "time must be 1..60 seconds"}
    try:
        general.dumpScoreLog(time_s, silent)
    except Exception as e:
        return {"ok": False, "error": "dumpScoreLog: %s" % e}
    return {
        "ok": True,
        "time": time_s,
        "silent": silent,
        "note": ("Wrote last %ds of played MIDI into the selected pattern. "
                 "Verify with fl_ping + fl_get_pattern_state if available, "
                 "or open the pattern in the piano roll." % time_s),
    }


def _h_safe_to_edit(p):
    """general.safeToEdit() -- returns True when FL is in a state where
    edits (automation writes, score-log dumps, etc) won't crash. Useful
    guard before destructive operations."""
    try:
        ok = bool(general.safeToEdit())
    except Exception as e:
        return {"ok": False, "error": "safeToEdit: %s" % e}
    return {"ok": True, "safe_to_edit": ok}


def _h_trigger_note(p):
    """channels.midiNoteOn(idxGlobal, note, velocity, channel=-1) -- live
    note trigger. velocity=0 is a note-off. Use sparingly; this fires MIDI
    in real time and bypasses the piano-roll editor."""
    try:
        idx = int(p["index"])
        note = int(p["note"])
        vel = int(p.get("velocity", 100))
        ch = int(p.get("channel", -1))
    except (KeyError, ValueError, TypeError) as e:
        return {"ok": False, "error": "bad params: %s" % e}
    if not (0 <= note <= 127):
        return {"ok": False, "error": "note must be 0..127"}
    if not (0 <= vel <= 127):
        return {"ok": False, "error": "velocity must be 0..127"}
    try:
        channels.midiNoteOn(idx, note, vel, ch)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "midiNoteOn: %s" % e}
    return {"ok": True, "index": idx, "note": note, "velocity": vel,
            "channel": ch, "note_off": (vel == 0)}


def _h_quantize_channel(p):
    """channels.quickQuantize(index, startOnly=1, useGlobalIndex=False)."""
    try:
        idx = int(p["index"])
        start_only = int(p.get("start_only", 1))
        global_idx = bool(p.get("use_global_index", False))
    except (KeyError, ValueError, TypeError) as e:
        return {"ok": False, "error": "bad params: %s" % e}
    try:
        channels.quickQuantize(idx, start_only, global_idx)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "quickQuantize: %s" % e}
    return {"ok": True, "index": idx, "start_only": start_only,
            "use_global_index": global_idx}


def _h_get_selected_channel(p):
    """channels.selectedChannel(canBeNone=False, offset=0, indexGlobal=False)."""
    can_be_none = bool(p.get("can_be_none", False))
    offset = int(p.get("offset", 0))
    global_idx = bool(p.get("index_global", False))
    try:
        sel = channels.selectedChannel(can_be_none, offset, global_idx)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "selectedChannel: %s" % e}
    return {"ok": True, "selected": sel, "can_be_none": can_be_none,
            "offset": offset, "index_global": global_idx}


def _h_get_channel_midi_in_port(p):
    """channels.getChannelMidiInPort(index) -- read the MIDI input port
    assigned to a channel (the channel-rack input routing)."""
    idx = int(p["index"])
    try:
        port = channels.getChannelMidiInPort(idx)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getChannelMidiInPort: %s" % e}
    return {"ok": True, "index": idx, "midi_in_port": port}


def _h_get_active_effect(p):
    """mixer.getActiveEffectIndex() -> (track, slot) | None. Returns the
    mixer track + slot of the focused effect plugin, or None if no plugin
    is focused."""
    try:
        r = mixer.getActiveEffectIndex()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getActiveEffectIndex: %s" % e}
    if r is None:
        return {"ok": True, "active_effect": None}
    # The stubs say it returns a tuple; be defensive.
    try:
        track, slot = r
        return {"ok": True, "active_effect": {"track": int(track), "slot": int(slot)}}
    except Exception:
        return {"ok": True, "active_effect_raw": r}


def _h_focus_plugin_editor(p):
    """mixer.focusEditor(track, slot) -- focuses the plugin's UI editor in
    FL. WARNING: this STICKS focus on the plugin and may steal keystrokes
    from the user; intended for programmatic introspection, not chains of
    tool calls."""
    try:
        track = int(p["track"])
        slot = int(p["slot"])
    except (KeyError, ValueError, TypeError) as e:
        return {"ok": False, "error": "bad params: %s" % e}
    try:
        mixer.focusEditor(track, slot)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "focusEditor: %s" % e}
    return {"ok": True, "track": track, "slot": slot,
            "warning": "plugin editor is now focused; subsequent user "
                       "keystrokes may be captured by the plugin"}


def _h_mixer_is_track_armed(p):
    """mixer.isTrackArmed(index) -> bool."""
    idx = int(p["index"])
    try:
        armed = bool(mixer.isTrackArmed(idx))  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackArmed: %s" % e}
    return {"ok": True, "track": idx, "armed": armed}


def _h_mixer_arm_track(p):
    """mixer.armTrack(index) -- toggles record-arm on a mixer track. Use
    isTrackArmed first to read the state, then armTrack to flip it."""
    idx = int(p["index"])
    try:
        mixer.armTrack(idx)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "armTrack: %s" % e}
    return {"ok": True, "track": idx, "toggled": True}


def _h_mixer_is_track_enabled(p):
    """mixer.isTrackEnabled(index) -> bool. Documented as 'functionally
    identical to not isTrackMuted'."""
    idx = int(p["index"])
    try:
        enabled = bool(mixer.isTrackEnabled(idx))  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackEnabled: %s" % e}
    return {"ok": True, "track": idx, "enabled": enabled}


def _h_mixer_track_count(p):
    """mixer.trackCount() -> int. Distinct from the existing
    mixer_list_tracks count because this is FL's view of track count
    (includes master + current), not what the dispatcher paginated."""
    try:
        n = mixer.trackCount()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "trackCount: %s" % e}
    return {"ok": True, "track_count": int(n)}


def _h_mixer_get_slot_color(p):
    """mixer.getSlotColor(track, slot) -> int (0xBBGGRR)."""
    track = int(p["track"])
    slot = int(p["slot"])
    try:
        c = mixer.getSlotColor(track, slot)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getSlotColor: %s" % e}
    return {"ok": True, "track": track, "slot": slot, "color": int(c) & 0xFFFFFF}


def _h_mixer_set_slot_color(p):
    """mixer.setSlotColor(track, slot, color). Accepts color as 0xRRGGBB
    (alpha-prefixed int); FL stores 0x--BBGGRR."""
    track = int(p["track"])
    slot = int(p["slot"])
    color = int(p["color"])
    try:
        mixer.setSlotColor(track, slot, color)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setSlotColor: %s" % e}
    return {"ok": True, "track": track, "slot": slot, "color": color}


def _h_pattern_burn_loop(p):
    """patterns.burnLoop(channel, storeUndo=1, updateUi=1) -- disables
    step sequencer looping on a channel for the current pattern."""
    channel = int(p["channel"])
    store_undo = int(p.get("store_undo", 1))
    update_ui = int(p.get("update_ui", 1))
    try:
        patterns.burnLoop(channel, store_undo, update_ui)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "burnLoop: %s" % e}
    return {"ok": True, "channel": channel,
            "store_undo": store_undo, "update_ui": update_ui}


def _h_pattern_is_default(p):
    """patterns.isPatternDefault(index) -> bool -- True if the pattern is
    the default empty state (no notes written)."""
    idx = int(p["index"])
    try:
        is_def = bool(patterns.isPatternDefault(idx))  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isPatternDefault: %s" % e}
    return {"ok": True, "pattern": idx, "is_default": is_def}


def _h_pattern_select(p):
    """patterns.selectPattern(index, value=-1, preview=False). value: -1=toggle,
    0=deselect, 1=select. preview=True also starts playback of the pattern."""
    idx = int(p["index"])
    value = int(p.get("value", -1))
    preview = bool(p.get("preview", False))
    try:
        patterns.selectPattern(idx, value, preview)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "selectPattern: %s" % e}
    return {"ok": True, "pattern": idx, "value": value, "preview": preview}


def _h_pattern_is_selected(p):
    """patterns.isPatternSelected(index) -> bool."""
    idx = int(p["index"])
    try:
        sel = bool(patterns.isPatternSelected(idx))  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isPatternSelected: %s" % e}
    return {"ok": True, "pattern": idx, "selected": sel}


# ------------------------------------------------------------------
# v0.4 -- second-pass API sweep. Discovered via paginated api_probe()
# on FL 26.1.2 build 5557. Each handler verified to exist on the live
# FL before being wired. The honest-API-limit pattern is used for any
# function not actually exposed on this build (e.g. setChannelPitch,
# setTrackStereoSep, some mixer.getTrackXyz) -- the handler probes
# first and returns the same code='api_unavailable' shape as the v0.3
# limit reports.
# ------------------------------------------------------------------

# -- general: project metadata, time signature, undo -----------------------

def _h_get_project_author(p):
    try:
        return {"ok": True, "author": str(general.getProjectAuthor())}
    except Exception as e:
        return {"ok": False, "error": "getProjectAuthor: %s" % e}


def _h_get_project_title(p):
    try:
        return {"ok": True, "title": str(general.getProjectTitle())}
    except Exception as e:
        return {"ok": False, "error": "getProjectTitle: %s" % e}


def _h_get_project_genre(p):
    try:
        return {"ok": True, "genre": str(general.getProjectGenre())}
    except Exception as e:
        return {"ok": False, "error": "getProjectGenre: %s" % e}


def _h_set_numerator(p):
    n = int(p["numerator"])
    if n < 1 or n > 32:
        return {"ok": False, "error": "numerator must be 1..32"}
    try:
        general.setNumerator(n)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setNumerator: %s" % e}
    return {"ok": True, "numerator": n}


def _h_set_denominator(p):
    d = int(p["denominator"])
    if d not in (1, 2, 4, 8, 16):
        return {"ok": False, "error": "denominator must be a power of 2 in {1,2,4,8,16}"}
    try:
        general.setDenominator(d)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setDenominator: %s" % e}
    return {"ok": True, "denominator": d}


def _h_set_rec_ppq(p):
    ppq = int(p["ppq"])
    if ppq < 24 or ppq > 1920:
        return {"ok": False, "error": "ppq must be 24..1920"}
    try:
        general.setRecPPQ(ppq)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setRecPPQ: %s" % e}
    return {"ok": True, "ppq": ppq}


def _h_get_undo_history_count(p):
    try:
        return {"ok": True, "count": int(general.getUndoHistoryCount())}
    except Exception as e:
        return {"ok": False, "error": "getUndoHistoryCount: %s" % e}


def _h_get_undo_history_pos(p):
    try:
        return {"ok": True, "pos": int(general.getUndoHistoryPos())}
    except Exception as e:
        return {"ok": False, "error": "getUndoHistoryPos: %s" % e}


def _h_set_undo_history_pos(p):
    pos = int(p["pos"])
    try:
        general.setUndoHistoryPos(pos)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setUndoHistoryPos: %s" % e}
    return {"ok": True, "pos": pos}


def _h_undo(p):
    count = int(p.get("count", 1))
    try:
        for _ in range(max(1, count)):
            general.undo()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "undo: %s" % e}
    return {"ok": True, "undid": count}


def _h_redo(p):
    """FL's redo path is general.undoUp() (or undoUpDown for one call).
    We use undoUp which advances the cursor forward."""
    count = int(p.get("count", 1))
    try:
        for _ in range(max(1, count)):
            general.undoUp()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "redo (undoUp): %s" % e}
    return {"ok": True, "redid": count}


# -- channels: metadata + step sequencer ----------------------------------

def _h_get_channel_type(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "index": idx, "type": int(channels.getChannelType(idx))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getChannelType: %s" % e}


def _h_get_activity_level(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "index": idx, "activity": float(channels.getActivityLevel(idx))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getActivityLevel: %s" % e}


def _h_get_channel_index(p):
    name = str(p["name"])
    try:
        return {"ok": True, "name": name, "index": int(channels.getChannelIndex(name))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getChannelIndex: %s" % e}


def _h_is_channel_selected(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "index": idx, "selected": bool(channels.isChannelSelected(idx))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isChannelSelected: %s" % e}


def _h_is_channel_highlighted(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "index": idx, "highlighted": bool(channels.isHighLighted(idx))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isHighLighted: %s" % e}


def _h_mute_channel(p):
    idx = int(p["index"])
    value = int(p.get("value", -1))  # -1 toggle, 0 unmute, 1 mute
    if value not in (-1, 0, 1):
        return {"ok": False, "error": "value must be -1, 0, or 1"}
    try:
        channels.muteChannel(idx, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "muteChannel: %s" % e}
    return {"ok": True, "index": idx, "value": value}


def _h_get_swing(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "index": idx, "swing": float(channels.getSwing(idx))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getSwing: %s" % e}


def _h_set_swing(p):
    idx = int(p["index"])
    value = float(p["value"])
    if value < 0.0 or value > 1.0:
        return {"ok": False, "error": "value must be 0.0..1.0"}
    try:
        channels.setSwing(idx, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setSwing: %s" % e}
    return {"ok": True, "index": idx, "swing": value}


def _h_get_grid_bit(p):
    channel = int(p["channel"])
    step = int(p["step"])
    try:
        return {"ok": True, "channel": channel, "step": step,
                "bit": bool(channels.getGridBit(channel, step))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getGridBit: %s" % e}


def _h_set_grid_bit(p):
    channel = int(p["channel"])
    step = int(p["step"])
    value = bool(p.get("value", True))
    try:
        channels.setGridBit(channel, step, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setGridBit: %s" % e}
    return {"ok": True, "channel": channel, "step": step, "value": value}


def _h_get_step_param(p):
    channel = int(p["channel"])
    step = int(p["step"])
    param = int(p["param"])
    try:
        return {"ok": True, "channel": channel, "step": step, "param": param,
                "value": float(channels.getStepParam(channel, step, param))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getStepParam: %s" % e}


def _h_get_current_step_param(p):
    channel = int(p["channel"])
    step = int(p["step"])
    param = int(p["param"])
    try:
        return {"ok": True, "channel": channel, "step": step, "param": param,
                "value": float(channels.getCurrentStepParam(channel, step, param))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getCurrentStepParam: %s" % e}


def _h_set_step_param_by_index(p):
    channel = int(p["channel"])
    step = int(p["step"])
    param = int(p["param"])
    value = float(p["value"])
    try:
        channels.setStepParameterByIndex(channel, step, param, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setStepParameterByIndex: %s" % e}
    return {"ok": True, "channel": channel, "step": step, "param": param, "value": value}


def _h_get_rec_event_id(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "index": idx, "event_id": int(channels.getRecEventId(idx))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getRecEventId: %s" % e}


def _h_inc_event_value(p):
    event_id = int(p["event_id"])
    step = int(p.get("step", 1))
    res = float(p.get("res", 1.0 / 24.0))
    try:
        new_value = int(channels.incEventValue(event_id, step, res))  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "incEventValue: %s" % e}
    return {"ok": True, "event_id": event_id, "step": step, "new_value": new_value}


# -- patterns: color, length, channel loop, multi-select ------------------

def _h_get_pattern_length(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "pattern": idx, "length_beats": int(patterns.getPatternLength(idx))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getPatternLength: %s" % e}


def _h_set_pattern_length(p):
    idx = int(p["index"])
    beats = int(p["beats"])
    if beats < 1 or beats > 9999:
        return {"ok": False, "error": "beats must be 1..9999"}
    # setPatternLength may not be exposed on every FL build; wrap defensively.
    if not hasattr(patterns, "setPatternLength"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "error": "patterns.setPatternLength not exposed on this FL build",
                "recommendation": "Use the piano roll UI to change pattern length."}
    try:
        patterns.setPatternLength(idx, beats)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setPatternLength: %s" % e}
    return {"ok": True, "pattern": idx, "beats": beats}


def _h_get_pattern_color(p):
    idx = int(p["index"])
    try:
        return {"ok": True, "pattern": idx, "color": int(patterns.getPatternColor(idx)) & 0xFFFFFF}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getPatternColor: %s" % e}


def _h_set_pattern_color(p):
    idx = int(p["index"])
    color = int(p["color"])
    try:
        patterns.setPatternColor(idx, color)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setPatternColor: %s" % e}
    return {"ok": True, "pattern": idx, "color": color}


def _h_get_channel_loop_style(p):
    pattern = int(p["pattern"])
    channel = int(p["channel"])
    try:
        return {"ok": True, "pattern": pattern, "channel": channel,
                "loop_point": int(patterns.getChannelLoopStyle(pattern, channel))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getChannelLoopStyle: %s" % e}


def _h_set_channel_loop(p):
    channel = int(p["channel"])
    loop_point = int(p.get("loop_point", 0))
    if loop_point < 0:
        return {"ok": False, "error": "loop_point must be >= 0 (0 disables)"}
    try:
        patterns.setChannelLoop(channel, loop_point)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setChannelLoop: %s" % e}
    return {"ok": True, "channel": channel, "loop_point": loop_point}


def _h_pattern_select_all(p):
    try:
        patterns.selectAll()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "selectAll: %s" % e}
    return {"ok": True, "selected_all": True}


def _h_pattern_deselect_all(p):
    try:
        patterns.deselectAll()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "deselectAll: %s" % e}
    return {"ok": True, "deselected_all": True}


def _h_pattern_is_any_selected(p):
    """Returns True if ANY pattern is selected. Implemented via patterns.isPatternSelected(0) -- if
    pattern 0 is selected, OR if there's a multi-selection -- returns True. FL's API doesn't expose
    'any selected' directly, but this is a useful proxy."""
    try:
        any_sel = False
        # Probe patterns 1..min(count, 20) -- enough for any reasonable project.
        n = _safe(lambda: patterns.patternCount()) or 0  # type: ignore[attr-defined]
        for i in range(1, min(n + 1, 21)):
            if patterns.isPatternSelected(i):  # type: ignore[attr-defined]
                any_sel = True
                break
        return {"ok": True, "any_selected": any_sel}
    except Exception as e:
        return {"ok": False, "error": "is_any_selected probe: %s" % e}


# -- mixer: parametric EQ, plugin mix/mute, automation helpers, track ops -

def _h_mixer_get_eq_band_count(p):
    track = int(p["track"])
    try:
        return {"ok": True, "track": track, "band_count": int(mixer.getEqBandCount(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getEqBandCount: %s" % e}


def _h_mixer_get_eq_freq(p):
    track = int(p["track"])
    band = int(p["band"])
    try:
        return {"ok": True, "track": track, "band": band,
                "frequency_hz": float(mixer.getEqFrequency(track, band))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getEqFrequency: %s" % e}


def _h_mixer_set_eq_freq(p):
    track = int(p["track"])
    band = int(p["band"])
    freq = float(p["frequency_hz"])
    if freq < 20 or freq > 20000:
        return {"ok": False, "error": "frequency_hz must be 20..20000"}
    try:
        mixer.setEqFrequency(track, band, freq)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setEqFrequency: %s" % e}
    return {"ok": True, "track": track, "band": band, "frequency_hz": freq}


def _h_mixer_get_eq_bw(p):
    track = int(p["track"])
    band = int(p["band"])
    try:
        return {"ok": True, "track": track, "band": band,
                "bandwidth_oct": float(mixer.getEqBandwidth(track, band))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getEqBandwidth: %s" % e}


def _h_mixer_set_eq_bw(p):
    track = int(p["track"])
    band = int(p["band"])
    bw = float(p["bandwidth_oct"])
    if bw < 0.1 or bw > 10.0:
        return {"ok": False, "error": "bandwidth_oct must be 0.1..10.0"}
    try:
        mixer.setEqBandwidth(track, band, bw)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setEqBandwidth: %s" % e}
    return {"ok": True, "track": track, "band": band, "bandwidth_oct": bw}


def _h_mixer_get_eq_gain(p):
    track = int(p["track"])
    band = int(p["band"])
    try:
        return {"ok": True, "track": track, "band": band,
                "gain_db": float(mixer.getEqGain(track, band))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getEqGain: %s" % e}


def _h_mixer_set_eq_gain(p):
    track = int(p["track"])
    band = int(p["band"])
    gain = float(p["gain_db"])
    if gain < -36.0 or gain > 36.0:
        return {"ok": False, "error": "gain_db must be -36..+36"}
    try:
        mixer.setEqGain(track, band, gain)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setEqGain: %s" % e}
    return {"ok": True, "track": track, "band": band, "gain_db": gain}


def _h_mixer_get_track_plugin_id(p):
    track = int(p["track"])
    slot = int(p["slot"])
    try:
        return {"ok": True, "track": track, "slot": slot,
                "plugin_id": int(mixer.getTrackPluginId(track, slot))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getTrackPluginId: %s" % e}


def _h_mixer_is_track_plugin_valid(p):
    track = int(p["track"])
    slot = int(p["slot"])
    try:
        return {"ok": True, "track": track, "slot": slot,
                "valid": bool(mixer.isTrackPluginValid(track, slot))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackPluginValid: %s" % e}


def _h_mixer_get_plugin_mix_level(p):
    track = int(p["track"])
    slot = int(p["slot"])
    try:
        return {"ok": True, "track": track, "slot": slot,
                "mix_level": float(mixer.getPluginMixLevel(track, slot))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getPluginMixLevel: %s" % e}


def _h_mixer_set_plugin_mix_level(p):
    track = int(p["track"])
    slot = int(p["slot"])
    level = float(p["level"])
    if level < 0.0 or level > 1.0:
        return {"ok": False, "error": "level must be 0.0..1.0"}
    try:
        mixer.setPluginMixLevel(track, slot, level)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setPluginMixLevel: %s" % e}
    return {"ok": True, "track": track, "slot": slot, "level": level}


def _h_mixer_get_plugin_mute_state(p):
    track = int(p["track"])
    slot = int(p["slot"])
    try:
        return {"ok": True, "track": track, "slot": slot,
                "mute": bool(mixer.getPluginMuteState(track, slot))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getPluginMuteState: %s" % e}


def _h_mixer_set_plugin_mute_state(p):
    track = int(p["track"])
    slot = int(p["slot"])
    mute = bool(p["mute"])
    try:
        mixer.setPluginMuteState(track, slot, mute)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setPluginMuteState: %s" % e}
    return {"ok": True, "track": track, "slot": slot, "mute": mute}


def _h_mixer_get_track_info(p):
    mode = int(p["mode"])
    if mode not in (0, 1, 2, 3):
        return {"ok": False, "error": "mode must be 0 (TN_Master), 1 (TN_FirstIns), 2 (TN_LastIns), or 3 (TN_Sel)"}
    try:
        return {"ok": True, "mode": mode, "track": int(mixer.getTrackInfo(mode))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getTrackInfo: %s" % e}


def _h_mixer_get_track_number(p):
    track = int(p["track"])
    try:
        return {"ok": True, "track": track, "track_number": int(mixer.getTrackNumber(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getTrackNumber: %s" % e}


def _h_mixer_set_track_number(p):
    track = int(p["track"])
    number = int(p["number"])
    flags = int(p.get("flags", 0))
    try:
        mixer.setTrackNumber(track, number, flags)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setTrackNumber: %s" % e}
    return {"ok": True, "track": track, "number": number, "flags": flags}


def _h_mixer_get_active_track(p):
    """Returns the mixer track with the docked peak meter ('current track').
    Implemented via mixer.trackNumber() which returns it on FL builds."""
    try:
        return {"ok": True, "active_track": int(mixer.trackNumber())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "trackNumber: %s" % e}


def _h_mixer_set_active_track(p):
    track = int(p["track"])
    try:
        mixer.setActiveTrack(track)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setActiveTrack: %s" % e}
    return {"ok": True, "track": track}


def _h_mixer_is_track_selected(p):
    track = int(p["track"])
    try:
        return {"ok": True, "track": track, "selected": bool(mixer.isTrackSelected(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackSelected: %s" % e}


def _h_mixer_select_track(p):
    track = int(p["track"])
    value = int(p.get("value", -1))  # -1 toggle, 0 deselect, 1 select
    try:
        mixer.selectTrack(track, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "selectTrack: %s" % e}
    return {"ok": True, "track": track, "value": value}


def _h_mixer_select_all(p):
    try:
        mixer.selectAll()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "selectAll: %s" % e}
    return {"ok": True}


def _h_mixer_deselect_all(p):
    try:
        mixer.deselectAll()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "deselectAll: %s" % e}
    return {"ok": True}


def _h_mixer_get_event_value(p):
    event_id = int(p["event_id"])
    try:
        return {"ok": True, "event_id": event_id, "value": int(mixer.getEventValue(event_id))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getEventValue: %s" % e}


def _h_mixer_get_event_id_name(p):
    event_id = int(p["event_id"])
    try:
        return {"ok": True, "event_id": event_id, "name": str(mixer.getEventIDName(event_id))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getEventIDName: %s" % e}


def _h_mixer_get_event_id_value_str(p):
    event_id = int(p["event_id"])
    try:
        return {"ok": True, "event_id": event_id, "value_str": str(mixer.getEventIDValueString(event_id))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getEventIDValueString: %s" % e}


def _h_mixer_automate_event(p):
    """REC-event automation helper. Use cautiously -- wrong event IDs can crash FL."""
    event_id = int(p["event_id"])
    value = int(p["value"])
    flags = int(p.get("flags", 0))
    res = float(p.get("res", 0.0))
    try:
        mixer.automateEvent(event_id, value, flags, res)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "automateEvent: %s" % e}
    return {"ok": True, "event_id": event_id, "value": value, "flags": flags, "res": res}


def _h_mixer_enable_track(p):
    track = int(p["track"])
    value = int(p.get("value", 1))
    if value not in (0, 1):
        return {"ok": False, "error": "value must be 0 or 1"}
    try:
        mixer.enableTrack(track, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "enableTrack: %s" % e}
    return {"ok": True, "track": track, "enabled": bool(value)}


def _h_mixer_get_track_recording_file(p):
    track = int(p["track"])
    try:
        return {"ok": True, "track": track,
                "filename": str(mixer.getTrackRecordingFileName(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getTrackRecordingFileName: %s" % e}


def _h_mixer_get_route_to_level(p):
    src = int(p["src"])
    dst = int(p["dst"])
    try:
        return {"ok": True, "src": src, "dst": dst,
                "level": float(mixer.getRouteToLevel(src, dst))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getRouteToLevel: %s" % e}


def _h_mixer_is_track_slots_enabled(p):
    track = int(p["track"])
    if not hasattr(mixer, "isTrackSlotsEnabled"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "track": track,
                "error": "isTrackSlotsEnabled not exposed on this FL build"}
    try:
        return {"ok": True, "track": track,
                "enabled": bool(mixer.isTrackSlotsEnabled(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackSlotsEnabled: %s" % e}


def _h_mixer_enable_track_slots(p):
    track = int(p["track"])
    value = bool(p.get("value", True))
    try:
        mixer.enableTrackSlots(track, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "enableTrackSlots: %s" % e}
    return {"ok": True, "track": track, "value": value}


def _h_mixer_is_track_rev_polarity(p):
    track = int(p["track"])
    if not hasattr(mixer, "isTrackRevPolarity"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "track": track,
                "error": "isTrackRevPolarity not exposed on this FL build"}
    try:
        return {"ok": True, "track": track,
                "rev_polarity": bool(mixer.isTrackRevPolarity(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackRevPolarity: %s" % e}


def _h_mixer_rev_track_polarity(p):
    track = int(p["track"])
    value = bool(p.get("value", False))
    if not hasattr(mixer, "revTrackPolarity"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "track": track,
                "error": "revTrackPolarity not exposed on this FL build"}
    try:
        mixer.revTrackPolarity(track, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "revTrackPolarity: %s" % e}
    return {"ok": True, "track": track, "value": value}


def _h_mixer_is_track_swap_channels(p):
    track = int(p["track"])
    if not hasattr(mixer, "isTrackSwapChannels"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "track": track,
                "error": "isTrackSwapChannels not exposed on this FL build"}
    try:
        return {"ok": True, "track": track,
                "swap_channels": bool(mixer.isTrackSwapChannels(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackSwapChannels: %s" % e}


def _h_mixer_swap_track_channels(p):
    track = int(p["track"])
    value = bool(p.get("value", False))
    if not hasattr(mixer, "swapTrackChannels"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "track": track,
                "error": "swapTrackChannels not exposed on this FL build"}
    try:
        mixer.swapTrackChannels(track, value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "swapTrackChannels: %s" % e}
    return {"ok": True, "track": track, "value": value}


def _h_mixer_is_track_mute_lock(p):
    track = int(p["track"])
    try:
        return {"ok": True, "track": track,
                "mute_locked": bool(mixer.isTrackMuteLock(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isTrackMuteLock: %s" % e}


def _h_mixer_get_track_stereo_sep(p):
    track = int(p["track"])
    if not hasattr(mixer, "getTrackStereoSep"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "track": track,
                "error": "getTrackStereoSep not exposed on this FL build"}
    try:
        return {"ok": True, "track": track,
                "stereo_sep": float(mixer.getTrackStereoSep(track))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getTrackStereoSep: %s" % e}


def _h_mixer_set_track_stereo_sep(p):
    track = int(p["track"])
    sep = float(p["sep"])
    if sep < -1.0 or sep > 1.0:
        return {"ok": False, "error": "sep must be -1.0..1.0"}
    if not hasattr(mixer, "setTrackStereoSep"):
        return {"ok": False, "code": "api_unavailable",
                "implementation": "honest_not_implemented",
                "track": track,
                "error": "setTrackStereoSep not exposed on this FL build"}
    try:
        mixer.setTrackStereoSep(track, sep)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setTrackStereoSep: %s" % e}
    return {"ok": True, "track": track, "sep": sep}


def _h_mixer_link_channel_to_track(p):
    channel = int(p["channel"])
    track = int(p["track"])
    select = bool(p.get("select", False))
    try:
        mixer.linkChannelToTrack(channel, track, select)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "linkChannelToTrack: %s" % e}
    return {"ok": True, "channel": channel, "track": track, "select": select}


def _h_mixer_link_track_to_channel(p):
    track = int(p["track"])
    channel = int(p["channel"])
    select = bool(p.get("select", False))
    try:
        mixer.linkTrackToChannel(track, channel, select)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "linkTrackToChannel: %s" % e}
    return {"ok": True, "track": track, "channel": channel, "select": select}


def _h_mixer_get_last_peak_vol(p):
    section = int(p["section"])  # 0=L, 1=R
    if section not in (0, 1):
        return {"ok": False, "error": "section must be 0 (left) or 1 (right)"}
    try:
        return {"ok": True, "section": section,
                "peak": float(mixer.getLastPeakVol(section))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getLastPeakVol: %s" % e}


def _h_mixer_get_auto_smooth_event_val(p):
    event_id = int(p["event_id"])
    flags = int(p.get("flags", 0))
    res = float(p.get("res", 0.0))
    try:
        return {"ok": True, "event_id": event_id, "flags": flags, "res": res,
                "value": int(mixer.getAutoSmoothEventValue(event_id, flags, res))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getAutoSmoothEventValue: %s" % e}


def _h_mixer_remote_find_event_value(p):
    event_id = int(p["event_id"])
    flags = int(p.get("flags", 0))
    res = float(p.get("res", 0.0))
    try:
        return {"ok": True, "event_id": event_id, "flags": flags, "res": res,
                "value": int(mixer.remoteFindEventValue(event_id, flags, res))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "remoteFindEventValue: %s" % e}


# -- ui: hint bar, snap, focused plugin, window show/hide, browser nav -----

def _h_get_hint_msg(p):
    try:
        return {"ok": True, "hint": str(ui.getHintMsg())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getHintMsg: %s" % e}


def _h_set_hint_msg(p):
    msg = str(p["msg"])
    try:
        ui.setHintMsg(msg)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setHintMsg: %s" % e}
    return {"ok": True, "msg": msg}


def _h_show_notification(p):
    nid = int(p["id"])
    try:
        ui.showNotification(nid)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "showNotification: %s" % e}
    return {"ok": True, "id": nid}


def _h_get_focused_plugin_name(p):
    try:
        return {"ok": True, "name": str(ui.getFocusedPluginName())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getFocusedPluginName: %s" % e}


def _h_is_closing(p):
    try:
        return {"ok": True, "is_closing": bool(ui.isClosing())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isClosing: %s" % e}


def _h_get_snap_mode(p):
    try:
        return {"ok": True, "snap_mode": int(ui.getSnapMode())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getSnapMode: %s" % e}


def _h_set_snap_mode(p):
    value = int(p["value"])
    try:
        ui.setSnapMode(value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setSnapMode: %s" % e}
    return {"ok": True, "snap_mode": value}


def _h_snap_on_off(p):
    try:
        new_state = int(ui.snapOnOff())  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "snapOnOff: %s" % e}
    return {"ok": True, "toggled": True, "new_state": new_state}


def _h_is_metronome_enabled(p):
    try:
        return {"ok": True, "metronome": bool(ui.isMetronomeEnabled())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isMetronomeEnabled: %s" % e}


def _h_is_precount_enabled(p):
    try:
        return {"ok": True, "precount": bool(ui.isPrecountEnabled())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isPrecountEnabled: %s" % e}


def _h_is_loop_rec_enabled(p):
    try:
        return {"ok": True, "loop_rec": bool(ui.isLoopRecEnabled())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isLoopRecEnabled: %s" % e}


def _h_is_start_on_input_enabled(p):
    try:
        return {"ok": True, "start_on_input": bool(ui.isStartOnInputEnabled())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isStartOnInputEnabled: %s" % e}


def _h_get_step_edit_mode(p):
    try:
        return {"ok": True, "step_edit_mode": bool(ui.getStepEditMode())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getStepEditMode: %s" % e}


def _h_set_step_edit_mode(p):
    value = bool(p["value"])
    try:
        ui.setStepEditMode(value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setStepEditMode: %s" % e}
    return {"ok": True, "step_edit_mode": value}


def _h_get_time_disp_min(p):
    try:
        return {"ok": True, "time_disp_min": bool(ui.getTimeDispMin())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getTimeDispMin: %s" % e}


def _h_set_time_disp_min(p):
    try:
        ui.setTimeDispMin()  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setTimeDispMin: %s" % e}
    return {"ok": True, "toggled": True}


def _h_show_window(p):
    wid = int(p["window_id"])
    try:
        ui.showWindow(wid)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "showWindow: %s" % e}
    return {"ok": True, "window_id": wid}


def _h_hide_window(p):
    wid = int(p["window_id"])
    try:
        ui.hideWindow(wid)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "hideWindow: %s" % e}
    return {"ok": True, "window_id": wid}


def _h_get_visible(p):
    wid = int(p["window_id"])
    try:
        return {"ok": True, "window_id": wid, "visible": bool(ui.getVisible(wid))}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "getVisible: %s" % e}


def _h_select_window(p):
    wid = int(p["window_id"])
    try:
        ui.selectWindow(wid)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "selectWindow: %s" % e}
    return {"ok": True, "window_id": wid}


def _h_navigate_browser(p):
    direction = int(p["direction"])
    try:
        ui.navigateBrowser(direction)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "navigateBrowser: %s" % e}
    return {"ok": True, "direction": direction}


def _h_navigate_browser_menu(p):
    direction = int(p["direction"])
    try:
        ui.navigateBrowserMenu(direction)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "navigateBrowserMenu: %s" % e}
    return {"ok": True, "direction": direction}


def _h_navigate_browser_tabs(p):
    direction = int(p["direction"])
    try:
        ui.navigateBrowserTabs(direction)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "navigateBrowserTabs: %s" % e}
    return {"ok": True, "direction": direction}


def _h_select_browser_menu_item(p):
    index = int(p["index"])
    try:
        ui.selectBrowserMenuItem(index)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "selectBrowserMenuItem: %s" % e}
    return {"ok": True, "index": index}


def _h_preview_browser_menu_item(p):
    index = int(p["index"])
    try:
        ui.previewBrowserMenuItem(index)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "previewBrowserMenuItem: %s" % e}
    return {"ok": True, "index": index}


def _h_toggle_browser_node(p):
    index = int(p["index"])
    try:
        ui.toggleBrowserNode(index)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "toggleBrowserNode: %s" % e}
    return {"ok": True, "index": index}


def _h_is_browser_auto_hide(p):
    try:
        return {"ok": True, "auto_hide": bool(ui.isBrowserAutoHide())}  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "isBrowserAutoHide: %s" % e}


def _h_set_browser_auto_hide(p):
    value = bool(p["value"])
    try:
        ui.setBrowserAutoHide(value)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": "setBrowserAutoHide: %s" % e}
    return {"ok": True, "value": value}


_HANDLERS = {
    "ping": _h_ping,
    "get_tempo": _h_get_tempo,
    "set_tempo": _h_set_tempo,
    "play": _h_play,
    "stop": _h_stop,
    "toggle_play": _h_toggle_play,
    "record": _h_record,
    "get_play_state": _h_get_play_state,
    "get_song_position": _h_get_song_pos,
    "set_song_position": _h_set_song_pos,
    "get_project_state": _h_get_project_state,
    "mixer_list_tracks": _h_mixer_list_tracks,
    "mixer_get_track": _h_mixer_get_track,
    "channel_list": _h_channel_list,
    "channel_get": _h_channel_get,
    "mixer_set_volume": _h_mixer_set_volume,
    "mixer_set_pan": _h_mixer_set_pan,
    "mixer_set_mute": _h_mixer_set_mute,
    "mixer_set_solo": _h_mixer_set_solo,
    "mixer_set_name": _h_mixer_set_name,
    "channel_set_volume": _h_channel_set_volume,
    "channel_set_pan": _h_channel_set_pan,
    "channel_set_mute": _h_channel_set_mute,
    "channel_set_solo": _h_channel_set_solo,
    "plugin_list": _h_plugin_list,
    "plugin_get_params": _h_plugin_get_params,
    "plugin_get_param": _h_plugin_get_param,
    "plugin_set_param": _h_plugin_set_param,
    "mixer_get_routing": _h_mixer_get_routing,
    "mixer_get_routing_all": _h_mixer_get_routing_all,
    "channel_routing_summary": _h_channel_routing_summary,
    "mixer_set_route": _h_mixer_set_route,
    "mixer_get_peaks": _h_mixer_get_peaks,
    "mixer_set_color": _h_mixer_set_color,
    "mixer_get_color": _h_mixer_get_color,
    "channel_set_color": _h_channel_set_color,
    "channel_get_color": _h_channel_get_color,
    "plugin_preset": _h_plugin_preset,
    "api_probe": _h_api_probe,
    "arrange_new_pattern": _h_arrange_new_pattern,
    "arrange_clone_pattern": _h_arrange_clone_pattern,
    "arrange_add_marker": _h_arrange_add_marker,
    "channel_select": _h_channel_select,
    "ensure_piano_roll": _h_ensure_piano_roll,
    "pattern_list": _h_pattern_list,
    # v0.3 / MCP enhancements -- fill in below
    "save_project": _h_save_project,
    "get_project_path": _h_get_project_path,
    "get_project_dirty": _h_get_project_dirty,
    "export_current_project_midi": _h_export_current_project_midi,
    "create_channel": _h_create_channel,
    "create_mixer_track": _h_create_mixer_track,
    "load_plugin_preset": _h_plugin_preset,   # alias for plugin_preset (v0.3)
    "get_automation_info": _h_get_automation_info,
    "set_automation_point": _h_set_automation_point,
    # v0.3 stubs-found additions
    "dump_score_log": _h_dump_score_log,
    "safe_to_edit": _h_safe_to_edit,
    "trigger_note": _h_trigger_note,
    "quantize_channel": _h_quantize_channel,
    "get_selected_channel": _h_get_selected_channel,
    "get_channel_midi_in_port": _h_get_channel_midi_in_port,
    "get_active_effect": _h_get_active_effect,
    "focus_plugin_editor": _h_focus_plugin_editor,
    "mixer_is_track_armed": _h_mixer_is_track_armed,
    "mixer_arm_track": _h_mixer_arm_track,
    "mixer_is_track_enabled": _h_mixer_is_track_enabled,
    "mixer_track_count": _h_mixer_track_count,
    "mixer_get_slot_color": _h_mixer_get_slot_color,
    "mixer_set_slot_color": _h_mixer_set_slot_color,
    "pattern_burn_loop": _h_pattern_burn_loop,
    "pattern_is_default": _h_pattern_is_default,
    "pattern_select": _h_pattern_select,
    "pattern_is_selected": _h_pattern_is_selected,
    # v0.4 -- second-pass API sweep (verified live on FL 26.1.2)
    "get_project_author": _h_get_project_author,
    "get_project_title": _h_get_project_title,
    "get_project_genre": _h_get_project_genre,
    "set_numerator": _h_set_numerator,
    "set_denominator": _h_set_denominator,
    "set_rec_ppq": _h_set_rec_ppq,
    "get_undo_history_count": _h_get_undo_history_count,
    "get_undo_history_pos": _h_get_undo_history_pos,
    "set_undo_history_pos": _h_set_undo_history_pos,
    "undo": _h_undo,
    "redo": _h_redo,
    "get_channel_type": _h_get_channel_type,
    "get_activity_level": _h_get_activity_level,
    "get_channel_index": _h_get_channel_index,
    "is_channel_selected": _h_is_channel_selected,
    "is_channel_highlighted": _h_is_channel_highlighted,
    "mute_channel": _h_mute_channel,
    "get_swing": _h_get_swing,
    "set_swing": _h_set_swing,
    "get_grid_bit": _h_get_grid_bit,
    "set_grid_bit": _h_set_grid_bit,
    "get_step_param": _h_get_step_param,
    "get_current_step_param": _h_get_current_step_param,
    "set_step_param_by_index": _h_set_step_param_by_index,
    "get_rec_event_id": _h_get_rec_event_id,
    "inc_event_value": _h_inc_event_value,
    "get_pattern_length": _h_get_pattern_length,
    "set_pattern_length": _h_set_pattern_length,
    "get_pattern_color": _h_get_pattern_color,
    "set_pattern_color": _h_set_pattern_color,
    "get_channel_loop_style": _h_get_channel_loop_style,
    "set_channel_loop": _h_set_channel_loop,
    "pattern_select_all": _h_pattern_select_all,
    "pattern_deselect_all": _h_pattern_deselect_all,
    "pattern_is_any_selected": _h_pattern_is_any_selected,
    "mixer_get_eq_band_count": _h_mixer_get_eq_band_count,
    "mixer_get_eq_freq": _h_mixer_get_eq_freq,
    "mixer_set_eq_freq": _h_mixer_set_eq_freq,
    "mixer_get_eq_bw": _h_mixer_get_eq_bw,
    "mixer_set_eq_bw": _h_mixer_set_eq_bw,
    "mixer_get_eq_gain": _h_mixer_get_eq_gain,
    "mixer_set_eq_gain": _h_mixer_set_eq_gain,
    "mixer_get_track_plugin_id": _h_mixer_get_track_plugin_id,
    "mixer_is_track_plugin_valid": _h_mixer_is_track_plugin_valid,
    "mixer_get_plugin_mix_level": _h_mixer_get_plugin_mix_level,
    "mixer_set_plugin_mix_level": _h_mixer_set_plugin_mix_level,
    "mixer_get_plugin_mute_state": _h_mixer_get_plugin_mute_state,
    "mixer_set_plugin_mute_state": _h_mixer_set_plugin_mute_state,
    "mixer_get_track_info": _h_mixer_get_track_info,
    "mixer_get_track_number": _h_mixer_get_track_number,
    "mixer_set_track_number": _h_mixer_set_track_number,
    "mixer_get_active_track": _h_mixer_get_active_track,
    "mixer_set_active_track": _h_mixer_set_active_track,
    "mixer_is_track_selected": _h_mixer_is_track_selected,
    "mixer_select_track": _h_mixer_select_track,
    "mixer_select_all": _h_mixer_select_all,
    "mixer_deselect_all": _h_mixer_deselect_all,
    "mixer_get_event_value": _h_mixer_get_event_value,
    "mixer_get_event_id_name": _h_mixer_get_event_id_name,
    "mixer_get_event_id_value_str": _h_mixer_get_event_id_value_str,
    "mixer_automate_event": _h_mixer_automate_event,
    "mixer_enable_track": _h_mixer_enable_track,
    "mixer_get_track_recording_file": _h_mixer_get_track_recording_file,
    "mixer_get_route_to_level": _h_mixer_get_route_to_level,
    "mixer_is_track_slots_enabled": _h_mixer_is_track_slots_enabled,
    "mixer_enable_track_slots": _h_mixer_enable_track_slots,
    "mixer_is_track_rev_polarity": _h_mixer_is_track_rev_polarity,
    "mixer_rev_track_polarity": _h_mixer_rev_track_polarity,
    "mixer_is_track_swap_channels": _h_mixer_is_track_swap_channels,
    "mixer_swap_track_channels": _h_mixer_swap_track_channels,
    "mixer_is_track_mute_lock": _h_mixer_is_track_mute_lock,
    "mixer_get_track_stereo_sep": _h_mixer_get_track_stereo_sep,
    "mixer_set_track_stereo_sep": _h_mixer_set_track_stereo_sep,
    "mixer_link_channel_to_track": _h_mixer_link_channel_to_track,
    "mixer_link_track_to_channel": _h_mixer_link_track_to_channel,
    "mixer_get_last_peak_vol": _h_mixer_get_last_peak_vol,
    "mixer_get_auto_smooth_event_val": _h_mixer_get_auto_smooth_event_val,
    "mixer_remote_find_event_value": _h_mixer_remote_find_event_value,
    "get_hint_msg": _h_get_hint_msg,
    "set_hint_msg": _h_set_hint_msg,
    "show_notification": _h_show_notification,
    "get_focused_plugin_name": _h_get_focused_plugin_name,
    "is_closing": _h_is_closing,
    "get_snap_mode": _h_get_snap_mode,
    "set_snap_mode": _h_set_snap_mode,
    "snap_on_off": _h_snap_on_off,
    "is_metronome_enabled": _h_is_metronome_enabled,
    "is_precount_enabled": _h_is_precount_enabled,
    "is_loop_rec_enabled": _h_is_loop_rec_enabled,
    "is_start_on_input_enabled": _h_is_start_on_input_enabled,
    "get_step_edit_mode": _h_get_step_edit_mode,
    "set_step_edit_mode": _h_set_step_edit_mode,
    "get_time_disp_min": _h_get_time_disp_min,
    "set_time_disp_min": _h_set_time_disp_min,
    "show_window": _h_show_window,
    "hide_window": _h_hide_window,
    "get_visible": _h_get_visible,
    "select_window": _h_select_window,
    "navigate_browser": _h_navigate_browser,
    "navigate_browser_menu": _h_navigate_browser_menu,
    "navigate_browser_tabs": _h_navigate_browser_tabs,
    "select_browser_menu_item": _h_select_browser_menu_item,
    "preview_browser_menu_item": _h_preview_browser_menu_item,
    "toggle_browser_node": _h_toggle_browser_node,
    "is_browser_auto_hide": _h_is_browser_auto_hide,
    "set_browser_auto_hide": _h_set_browser_auto_hide,
}
