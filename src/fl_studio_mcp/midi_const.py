"""Mirror of FL Studio's Shared\\Python\\Lib\\midi.py and utils.py.

This module re-exports the constants and helper functions that FL Studio
ships at::

    C:\\Program Files\\Image-Line\\FL Studio [version]\\Shared\\Python\\Lib\\midi.py
    C:\\Program Files\\Image-Line\\FL Studio [version]\\Shared\\Python\\Lib\\utils.py

These files are present in FL's own Python install but NOT in the
python3.13 environment where our server runs. The controller script
(device_FLStudioMCP.py) imports them directly from FL; the server cannot.
So we mirror the relevant constants here, kept in sync with the
FL-Studio-API-Stubs reference at
https://github.com/MaddyGuthridge/FL-Studio-API-Stubs.

Whenever FL adds new constants, update this file. The script and the
server are expected to stay in lockstep.

Only the constants used by the MCP server are mirrored. See the FL
Stubs for the full reference.
"""
from __future__ import annotations

# =====================================================================
# MIDI codes (midi.MIDI_*)
# =====================================================================
MIDI_NOTEON = 0x90
MIDI_NOTEOFF = 0x80
MIDI_KEYAFTERTOUCH = 0xA0
MIDI_CONTROLCHANGE = 0xB0
MIDI_PROGRAMCHANGE = 0xC0
MIDI_CHANAFTERTOUCH = 0xD0
MIDI_PITCHBEND = 0xE0
MIDI_SYSTEMMESSAGE = 0xF0
MIDI_BEGINSYSEX = 0xF0
MIDI_MTCQUARTERFRAME = 0xF1
MIDI_SONGPOSPTR = 0xF2
MIDI_SONGSELECT = 0xF3
MIDI_ENDSYSEX = 0xF7
MIDI_TIMINGCLOCK = 0xF8
MIDI_START = 0xFA
MIDI_CONTINUE = 0xFB
MIDI_STOP = 0xFC
MIDI_ACTIVESENSING = 0xFE
MIDI_SYSTEMRESET = 0xFF

# =====================================================================
# processMIDIEvent flags (midi.PME_*)
# =====================================================================
PME_LiveInput = 1
PME_System = 1 << 1
PME_System_Safe = 1 << 2
PME_PreviewNote = 1 << 3
PME_FromHost = 1 << 4
PME_FromMIDI = 1 << 5
PME_FromScript = 1 << 6

# =====================================================================
# playlist.triggerLiveClip flags (midi.TLC_*)
# =====================================================================
TLC_MuteOthers = 1
TLC_Fill = 1 << 1
TLC_Queue = 1 << 2
TLC_Release = 1 << 5
TLC_NoPlayCheck = 1 << 6
TLC_NoHardwareUpdate = 1 << 30
TLC_SecondPass = 1 << 31
TLC_ColumnMode = 1 << 7
TLC_WeakColumnMode = 1 << 8
TLC_TriggerCheckColumnMode = 1 << 9
TLC_TrackSnap = 0 << 3
TLC_GlobalSnap = 1 << 3
TLC_NoSnap = 2 << 3
TLC_SubNum_Normal = 0 << 16
TLC_SubNum_ClipPos = 1 << 16
TLC_SubNum_GroupNum = 2 << 16
TLC_SubNum_Read = 3 << 16
TLC_SubNum_Leave = 4 << 16

# =====================================================================
# Playing modes (midi.PM_*)
# =====================================================================
PM_Stopped = 0
PM_Playing = 1
PM_Precount = 2

# =====================================================================
# REC event flags for processRECEvent (midi.REC_*)
# =====================================================================
REC_UpdateValue = 1 << 0
REC_GetValue = 1 << 1
REC_ShowHint = 1 << 2
REC_UpdatePlugLabel = 1 << 3
REC_UpdateControl = 1 << 4
REC_FromMIDI = 1 << 5
REC_Store = 1 << 6
REC_SetChanged = 1 << 7
REC_SetTouched = 1 << 8
REC_Init = 1 << 9
REC_NoLink = 1 << 10
REC_InternalCtrl = 1 << 11
REC_PlugReserved = 1 << 12
REC_Smoothed = 1 << 13
REC_NoLastTweaked = 1 << 14
REC_NoSaveUndo = 1 << 15

REC_InitStore = REC_Init | REC_Store
REC_MIDIController = (REC_UpdateValue | REC_UpdateControl | REC_ShowHint |
                      REC_InitStore | REC_SetChanged | REC_SetTouched | REC_FromMIDI)
REC_Controller = (REC_UpdateValue | REC_UpdateControl | REC_ShowHint |
                   REC_InitStore | REC_SetChanged | REC_SetTouched)
REC_SetAll = (REC_UpdateValue | REC_UpdateControl | REC_InitStore |
                REC_SetChanged | REC_SetTouched)
REC_Control = (REC_UpdateValue | REC_ShowHint | REC_InitStore |
                 REC_SetChanged | REC_UpdatePlugLabel | REC_SetTouched)
REC_Visual = REC_GetValue | REC_UpdateControl | REC_UpdatePlugLabel
REC_FromMixThread = REC_UpdateValue
REC_PlugCallback = REC_InitStore | REC_SetChanged | REC_SetTouched
REC_FromInternalCtrl = REC_UpdateValue | REC_FromMIDI | REC_InternalCtrl
REC_AnyInternalCtrl = REC_InternalCtrl | REC_Smoothed

# =====================================================================
# Per-channel REC event IDs (midi.REC_Chan_*)
# These are the OFFSETS that channels.getRecEventId(channel) returns
# the BASE for; add one to compute a specific property's event id.
# =====================================================================
REC_MaxChan = 4096
REC_ItemRange = 0x20000

REC_Chan_First = 0
REC_Chan_Last = REC_MaxChan * REC_ItemRange - 1
REC_Chan_Vol = REC_Chan_First       # channel volume
REC_Chan_Pan = REC_Chan_First + 1   # channel pan
REC_Chan_FCut = REC_Chan_First + 2  # channel filter cutoff
REC_Chan_FRes = REC_Chan_First + 3  # channel filter resonance
REC_Chan_Pitch = REC_Chan_First + 4  # channel pitch (semi-tones)
REC_Chan_FType = REC_Chan_First + 5  # channel filter type
REC_Chan_PortaTime = REC_Chan_First + 6  # portamento time
REC_Chan_Mute = REC_Chan_First + 7   # channel mute
REC_Chan_FXTrack = REC_Chan_First + 8  # which mixer track this channel routes to
REC_Chan_GateTime = REC_Chan_First + 9  # gate time
REC_Chan_Crossfade = REC_Chan_First + 10
REC_Chan_TimeOfs = REC_Chan_First + 11   # time offset
REC_Chan_SwingMix = REC_Chan_First + 12  # per-channel swing mix
REC_Chan_SmpOfs = REC_Chan_First + 13    # sample offset
REC_Chan_StretchTime = REC_Chan_First + 14  # stretch

# Per-channel arpeggiator (offsets from base)
REC_Chan_Arp_First = REC_Chan_First + 0x300
REC_Chan_Arp_Chord = REC_Chan_Arp_First + 2
REC_Chan_Arp_Time = REC_Chan_Arp_First + 3
REC_Chan_Arp_Gate = REC_Chan_Arp_First + 4
REC_Chan_Arp_Repeat = REC_Chan_Arp_First + 5

# Per-channel envelope
REC_Chan_Env_First = REC_Chan_First + 0x1000
REC_Chan_Env_LFO_First = REC_Chan_Env_First + 9
REC_Chan_Env_MA = REC_Chan_Env_First + 8
REC_Chan_Env_LFOA = REC_Chan_Env_First + 11

# Per-channel note (note-on / note-off)
REC_Chan_Note_First = REC_Chan_First + 0x4000
REC_Chan_NoteOn = REC_Chan_Note_First
REC_Chan_NoteMask = 0xFFFFFFF0

# Channel NAME maps: (name, offset_in_Rec_Chan_*) for typed tools.
REC_CHAN_PROPERTIES = {
    "volume":         REC_Chan_Vol,
    "pan":            REC_Chan_Pan,
    "filter_cutoff":  REC_Chan_FCut,
    "filter_resonance": REC_Chan_FRes,
    "pitch":          REC_Chan_Pitch,
    "filter_type":    REC_Chan_FType,
    "portamento_time": REC_Chan_PortaTime,
    "mute":           REC_Chan_Mute,
    "fx_track":       REC_Chan_FXTrack,
    "gate_time":      REC_Chan_GateTime,
    "crossfade":      REC_Chan_Crossfade,
    "time_offset":    REC_Chan_TimeOfs,
    "swing_mix":      REC_Chan_SwingMix,
    "sample_offset":  REC_Chan_SmpOfs,
    "stretch_time":   REC_Chan_StretchTime,
    "arpeggiator_chord":  REC_Chan_Arp_Chord,
    "arpeggiator_time":   REC_Chan_Arp_Time,
    "arpeggiator_gate":   REC_Chan_Arp_Gate,
    "arpeggiator_repeat": REC_Chan_Arp_Repeat,
    "envelope_ma":    REC_Chan_Env_MA,
    "envelope_lfo_a": REC_Chan_Env_LFOA,
}

# =====================================================================
# Mixer track REC event IDs (midi.REC_Mixer_*)
# These offsets add to channels.getRecEventId(track_index) for a
# specific mixer track, OR you can pass them directly to
# general.processRECEvent with the proper base.
# =====================================================================
REC_Plug_General_First = 0x1000
REC_Plug_First = 0x8000
REC_PluginBase = 0x100 * 0x80
REC_PluginRange = 0x80 * 0x80

REC_Mixer_First = REC_Plug_General_First + 0x40
REC_Mixer_Last = REC_Mixer_First + 0x800 - 1
REC_Mixer_Vol = REC_Mixer_First + 0x80      # mixer track volume
REC_Mixer_Pan = REC_Mixer_Vol + 1           # mixer track pan
REC_Mixer_SS = REC_Mixer_Vol + 2            # mixer track stereo separation

# EQ (8 bands, 3 properties each)
REC_Mixer_EQ_First = REC_Mixer_Vol + 0x10
REC_Mixer_EQ_Last = REC_Mixer_EQ_First + 8 * 3 - 1
REC_Mixer_EQ_Gain = REC_Mixer_EQ_First      # band 0..7 (stride 1)
REC_Mixer_EQ_Freq = REC_Mixer_EQ_First + 8 # band 0..7
REC_Mixer_EQ_Q = REC_Mixer_EQ_First + 8 * 2
REC_Mixer_EQ_Type = REC_Mixer_EQ_First + 8 * 3  # 0..5 per stubs

# =====================================================================
# Global REC event IDs (midi.REC_Global_*) -- base for transport
# =====================================================================
REC_Global_First = 0x4000 * REC_ItemRange
REC_MainVol = REC_Global_First
REC_MainShuffle = REC_Global_First + 1
REC_MainPitch = REC_Global_First + 2
REC_Tempo = REC_Global_First + 5  # FL stores BPM * 1000 internally

# =====================================================================
# Special RECs (midi.REC_Special, REC_StartStop, etc.)
# =====================================================================
REC_Special = -1
REC_StartStop = REC_Special              # 0=Stop, 1=Start
REC_SongPosition = REC_Special - 1       # get/set song position (in bars)
REC_SongLength = REC_Special - 2         # get song length (in bars)
REC_LastTweakedFirst = -32
REC_LastTweakedLast = REC_LastTweakedFirst + 1
REC_Proj_First = REC_Special - 0x100

# =====================================================================
# Harmonic scales (midi.HARMONICSCALE_*)
# =====================================================================
HARMONICSCALE_MAJOR = 0
HARMONICSCALE_HARMONICMINOR = 1
HARMONICSCALE_MELODICMINOR = 2
HARMONICSCALE_WHOLETONE = 3
HARMONICSCALE_DIMINISHED = 4
HARMONICSCALE_MAJORPENTATONIC = 5
HARMONICSCALE_MINORPENTATONIC = 6
HARMONICSCALE_JAPINSEN = 7
HARMONICSCALE_MAJORBEBOP = 8
HARMONICSCALE_DOMINANTBEBOP = 9
HARMONICSCALE_BLUES = 10
HARMONICSCALE_ARABIC = 11
HARMONICSCALE_ENIGMATIC = 12
HARMONICSCALE_NEAPOLITAN = 13
HARMONICSCALE_NEAPOLITANMINOR = 14
HARMONICSCALE_HUNGARIANMINOR = 15
HARMONICSCALE_DORIAN = 16
HARMONICSCALE_PHRYGIAN = 17
HARMONICSCALE_LYDIAN = 18
HARMONICSCALE_MIXOLYDIAN = 19
HARMONICSCALE_AEOLIAN = 20
HARMONICSCALE_LOCRIAN = 21
HARMONICSCALE_CHROMATIC = 22
HARMONICSCALE_LAST = 22

# String-name lookup (case-insensitive). The typed compose tool picks
# from this; the controller script just gets the integer.
SCALE_NAME_TO_INT = {
    "major":            HARMONICSCALE_MAJOR,
    "harmonic_minor":   HARMONICSCALE_HARMONICMINOR,
    "melodic_minor":    HARMONICSCALE_MELODICMINOR,
    "whole_tone":       HARMONICSCALE_WHOLETONE,
    "diminished":       HARMONICSCALE_DIMINISHED,
    "major_pentatonic": HARMONICSCALE_MAJORPENTATONIC,
    "minor_pentatonic": HARMONICSCALE_MINORPENTATONIC,
    "japanese":         HARMONICSCALE_JAPINSEN,
    "major_bebop":      HARMONICSCALE_MAJORBEBOP,
    "dominant_bebop":   HARMONICSCALE_DOMINANTBEBOP,
    "blues":            HARMONICSCALE_BLUES,
    "arabic":           HARMONICSCALE_ARABIC,
    "enigmatic":        HARMONICSCALE_ENIGMATIC,
    "neapolitan":       HARMONICSCALE_NEAPOLITAN,
    "neapolitan_minor": HARMONICSCALE_NEAPOLITANMINOR,
    "hungarian_minor":  HARMONICSCALE_HUNGARIANMINOR,
    "dorian":           HARMONICSCALE_DORIAN,
    "phrygian":         HARMONICSCALE_PHRYGIAN,
    "lydian":           HARMONICSCALE_LYDIAN,
    "mixolydian":       HARMONICSCALE_MIXOLYDIAN,
    "aeolian":          HARMONICSCALE_AEOLIAN,
    "locrian":          HARMONICSCALE_LOCRIAN,
    "chromatic":        HARMONICSCALE_CHROMATIC,
}
SCALE_INT_TO_NAME = {v: k for k, v in SCALE_NAME_TO_INT.items()}

# =====================================================================
# Channel types (midi.CT_*) -- values returned by channels.getChannelType()
# =====================================================================
CT_Sampler = 0
CT_TS404 = 1
CT_GenPlug = 2
CT_Layer = 3
CT_AudioClip = 4
CT_AutoClip = 5

CHANNEL_TYPE_NAME_TO_INT = {
    "sampler":     CT_Sampler,
    "ts404":       CT_TS404,
    "generator":   CT_GenPlug,
    "layer":       CT_Layer,
    "audio_clip":  CT_AudioClip,
    "auto_clip":   CT_AutoClip,
}
CHANNEL_TYPE_INT_TO_NAME = {v: k for k, v in CHANNEL_TYPE_NAME_TO_INT.items()}

# =====================================================================
# Step parameters (midi.pPitch, pVelocity, etc.) -- the `param` arg
# of channels.getStepParam / setStepParameterByIndex
# =====================================================================
pPitch = 0
pVelocity = 1
pRelease = 2
pFinePitch = 3
pPan = 4
pModX = 5
pModY = 6
pShift = 7
pRepeat = 8

STEP_PARAM_NAME_TO_INT = {
    "pitch":     pPitch,
    "velocity":  pVelocity,
    "release":   pRelease,
    "fine_pitch": pFinePitch,
    "pan":       pPan,
    "mod_x":     pModX,
    "mod_y":     pModY,
    "shift":     pShift,
    "repeat":    pRepeat,
}
STEP_PARAM_INT_TO_NAME = {v: k for k, v in STEP_PARAM_NAME_TO_INT.items()}

# =====================================================================
# Snap modes (midi.Snap_*)
# =====================================================================
Snap_Default = -2
Snap_Line = 0
Snap_Cell = 1
Snap_None = 3
Snap_SixthStep = 4
Snap_FourthStep = 5
Snap_ThirdStep = 6
Snap_HalfStep = 7
Snap_Step = 8
Snap_SixthBeat = 9
Snap_FourthBeat = 10
Snap_ThirdBeat = 11
Snap_HalfBeat = 12
Snap_Beat = 13
Snap_Bar = 14
Snap_Events = 16
Snap_Markers = 17

SNAP_NAME_TO_INT = {
    "line":         Snap_Line,
    "cell":         Snap_Cell,
    "none":         Snap_None,
    "1/6_step":     Snap_SixthStep,
    "1/4_step":     Snap_FourthStep,
    "1/3_step":     Snap_ThirdStep,
    "1/2_step":     Snap_HalfStep,
    "1/2 step":     Snap_HalfStep,
    "half step":    Snap_HalfStep,
    "step":         Snap_Step,
    "1/6_beat":     Snap_SixthBeat,
    "1/4_beat":     Snap_FourthBeat,
    "1/4 beat":     Snap_FourthBeat,
    "quarter beat": Snap_FourthBeat,
    "1/3_beat":     Snap_ThirdBeat,
    "1/3 beat":     Snap_ThirdBeat,
    "1/2_beat":     Snap_HalfBeat,
    "1/2 beat":     Snap_HalfBeat,
    "half beat":    Snap_HalfBeat,
    "beat":         Snap_Beat,
    "bar":          Snap_Bar,
    "events":       Snap_Events,
    "markers":      Snap_Markers,
}
SNAP_INT_TO_NAME = {v: k for k, v in SNAP_NAME_TO_INT.items()}

# =====================================================================
# Mixer track IDs (midi.TN_*)
# =====================================================================
TN_Master = 0
TN_FirstIns = 1
TN_LastIns = 2
TN_Sel = 3

# =====================================================================
# Window indexes (midi.wid*). For ui.showWindow / hideWindow / selectWindow.
# =====================================================================
widMixer = 0
widChannelRack = 1
widPlaylist = 2
widPianoRoll = 3
widBrowser = 4
widPlugin = 5
widPluginEffect = 6
widPluginGenerator = 7
widPluginPicker = 8

WINDOW_NAME_TO_INT = {
    "mixer":        widMixer,
    "channel_rack": widChannelRack,
    "playlist":     widPlaylist,
    "piano_roll":   widPianoRoll,
    "browser":      widBrowser,
    "plugin":       widPlugin,
    "plugin_effect": widPluginEffect,
    "plugin_generator": widPluginGenerator,
    "plugin_picker": widPluginPicker,
}
WINDOW_INT_TO_NAME = {v: k for k, v in WINDOW_NAME_TO_INT.items()}

# =====================================================================
# EQ type (used with REC_Mixer_EQ_Type)
# =====================================================================
# (per FL-Studio-API-Stubs; FL's actual integers)
EQ_TYPE_NAMES = {
    0: "lp",         # low-pass
    1: "hp",         # high-pass
    2: "lp_shelf",   # low-shelf
    3: "hp_shelf",   # high-shelf
    4: "peaking",    # peaking
    5: "notch",      # notch
}
EQ_TYPE_NAME_TO_INT = {
    "lp":           0,
    "low_pass":     0,
    "lowpass":      0,
    "hp":           1,
    "high_pass":    1,
    "highpass":     1,
    "lp_shelf":     2,
    "low_shelf":    2,
    "lowshelf":     2,
    "hp_shelf":     3,
    "high_shelf":   3,
    "highshelf":    3,
    "peaking":      4,
    "peak":         4,
    "notch":        5,
    "band_stop":    5,
    "bandstop":     5,
}

# =====================================================================
# Event editor modes
# =====================================================================
EE_EE = 0   # event editor
EE_PR = 1   # piano roll
EE_PL = 2   # playlist

# =====================================================================
# Routing modes
# =====================================================================
RM_Song = 0
RM_Pattern = 1
RM_Mixer = 2

# =====================================================================
# Song tick options
# =====================================================================
ST_Int = 0
ST_Beat = 1


# =====================================================================
# utils.py helpers (pure-python, no FL state)
# =====================================================================
def GetNoteName(NoteNum: int) -> str:
    """MIDI note number -> 'C4', 'F#5', etc."""
    _NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    NoteNum += 1200
    return _NAMES[NoteNum % 12] + str((NoteNum // 12) - 100)


def ColorToRGB(Color: int) -> tuple:
    """FL color int (0x--BBGGRR) -> (R, G, B)."""
    return ((Color >> 16) & 0xFF, (Color >> 8) & 0xFF, Color & 0xFF)


def RGBToColor(R: int, G: int, B: int) -> int:
    return (R << 16) | (G << 8) | B


def VolTodB(Value: float) -> float:
    """FL's volume curve (0..1) -> dB. 0.0 = -infinity, 1.0 = 0 dB."""
    import math
    Value = (math.exp(Value * math.log(11)) - 1) * 0.1
    if Value == 0:
        return 0.0
    return round(math.log10(Value) * 20, 1)


def resolve(name: str, table: dict, what: str):
    """Look up a name (case-insensitive, with _/. /- treated equivalently)
    in a NAME->INT dict. Returns the int. Raises ValueError with a helpful
    message if not found."""
    def norm(s): return s.lower().replace(" ", "").replace("-", "").replace("_", "").replace(".", "")
    target = norm(name)
    # exact match (normalized)
    for k, v in table.items():
        if norm(k) == target:
            return v
    # word-overlap match: split both into word-pieces, count overlap
    def words(s): return [w for w in s.replace("-", " ").replace("_", " ").replace(".", " ").lower().split() if w]
    target_words = set(words(name))
    candidates = []
    for k, v in table.items():
        kw = set(words(k))
        if not target_words or not kw:
            continue
        # All target words appear in k, OR all k words appear in target.
        if target_words <= kw or kw <= target_words:
            candidates.append((k, v))
    if candidates:
        # Pick the LONGEST matching key (most specific match) -- a
        # "half beat" query should match "half_beat" (12), not "beat" (13).
        candidates.sort(key=lambda kv: -len(kv[0]))
        return candidates[0][1]
    # final fallback: substring match
    matches = [k for k in table if target in norm(k) or norm(k) in target]
    if len(matches) == 1:
        return table[matches[0]]
    raise ValueError(f"unknown {what}: {name!r}. Valid: {sorted(table.keys())}")


def resolve_scale(name_or_int):
    if isinstance(name_or_int, int):
        if name_or_int not in SCALE_INT_TO_NAME:
            raise ValueError(f"unknown scale int: {name_or_int}")
        return name_or_int
    return resolve(name_or_int, SCALE_NAME_TO_INT, "scale")


def resolve_channel_type(name_or_int):
    if isinstance(name_or_int, int):
        if name_or_int not in CHANNEL_TYPE_INT_TO_NAME:
            raise ValueError(f"unknown channel type int: {name_or_int}")
        return name_or_int
    return resolve(name_or_int, CHANNEL_TYPE_NAME_TO_INT, "channel_type")


def resolve_step_param(name_or_int):
    if isinstance(name_or_int, int):
        if name_or_int not in STEP_PARAM_INT_TO_NAME:
            raise ValueError(f"unknown step param int: {name_or_int}")
        return name_or_int
    return resolve(name_or_int, STEP_PARAM_NAME_TO_INT, "step_param")


def resolve_snap(name_or_int):
    if isinstance(name_or_int, int):
        if name_or_int not in SNAP_INT_TO_NAME and not (0 <= name_or_int <= 17):
            raise ValueError(f"unknown snap int: {name_or_int}")
        return name_or_int
    return resolve(name_or_int, SNAP_NAME_TO_INT, "snap")


def resolve_window(name_or_int):
    if isinstance(name_or_int, int):
        if name_or_int not in WINDOW_INT_TO_NAME:
            raise ValueError(f"unknown window int: {name_or_int}")
        return name_or_int
    return resolve(name_or_int, WINDOW_NAME_TO_INT, "window")


def resolve_eq_type(name_or_int):
    if isinstance(name_or_int, int):
        if name_or_int not in EQ_TYPE_NAMES:
            raise ValueError(f"unknown eq type int: {name_or_int}")
        return name_or_int
    return resolve(name_or_int, EQ_TYPE_NAME_TO_INT, "eq_type")


def resolve_chan_property(name):
    """Channel REC_Chan_* property name -> offset int."""
    return resolve(name, REC_CHAN_PROPERTIES, "channel_property")
