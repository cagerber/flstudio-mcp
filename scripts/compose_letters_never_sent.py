"""Build the 'Letters Never Sent' romantic ballad .mid (C Aeolian, 78 BPM, 4/4, 20 bars).

This drives the same path the fl_export_midi tool uses (fl_studio_mcp.music.midi_export.write_midi).
It produces one type-1 .mid with 4 named tracks (Lead, Chords, Bass, Drums) that Anton imports
into FL Studio, assigns Romantic Keys VSTi (and the existing 808 kit) to, and plays.

Form (20 bars, 4/4 @ 78 BPM):
  Intro   (1-4)  : | Cm  | Ab  | Fm  | G7 |
  Verse   (5-8)  : | Cm  | Ab  | Eb  | Bb |
  Chorus  (9-12) : | Cm  | Ab  | Fm  | G7 |
  Bridge  (13-16): | Ab  | G7  | Cm  | Ab |
  Outro   (17-20): | Cm  | Ab  | Fm  | Cm |

Bar numbers in the file spec are 0-based; the song starts at start_bars=0.
"""
from __future__ import annotations

import os
import sys

# Use the editable install we already have
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fl_studio_mcp.music.midi_export import write_midi  # noqa: E402


# -----------------------------------------------------------------------------
# Scale + chord notes (C Aeolian / natural minor)
# -----------------------------------------------------------------------------
# MIDI: C4=60, C5=72. Romantic Keys nylon/EP lives in C4..C6 territory.
SCALE = ["C", "D", "Eb", "F", "G", "Ab", "Bb"]               # C Aeolian
ROOTS = {n: 60 + i for i, n in enumerate(["C", "C#", "D", "Eb", "E", "F",
                                           "F#", "G", "Ab", "A", "Bb", "B"])}


def chord(tonic_midi: int, kind: str) -> list[int]:
    """Return MIDI pitches for a triad in C Aeolian."""
    # Intervals (semitones from root) for each chord kind used here
    intervals = {
        "m":   [0, 3, 7],
        "maj": [0, 4, 7],
        "dim": [0, 3, 6],
        "aug": [0, 4, 8],
        "7":   [0, 4, 7, 10],      # dominant 7
        "m7":  [0, 3, 7, 10],
        "maj7":[0, 4, 7, 11],
    }
    return [tonic_midi + i for i in intervals[kind]]


# -----------------------------------------------------------------------------
# Chord progression (one chord per bar, 1 bar = 4 beats at 78 BPM = ~3.08s)
# -----------------------------------------------------------------------------
# Each entry: (bar_index_0based, root_note_name, kind, octave_offset_from_C4)
#   octave_offset 0 = root around C4 (60), -1 = octave down.
PROGRESSION = [
    # Intro 1-4
    (0,  "C",  "m",   0),
    (1,  "Ab", "maj", 0),
    (2,  "F",  "m",   0),
    (3,  "G",  "7",   0),
    # Verse 5-8
    (4,  "C",  "m",   0),
    (5,  "Ab", "maj", 0),
    (6,  "Eb", "maj", 0),
    (7,  "Bb", "maj", 0),
    # Chorus 9-12 (same as Intro for symmetry, but fuller voicing + melody lift)
    (8,  "C",  "m",   0),
    (9,  "Ab", "maj", 0),
    (10, "F",  "m",   0),
    (11, "G",  "7",   0),
    # Bridge 13-16: lift up the octave for tension
    (12, "Ab", "maj", 1),
    (13, "G",  "7",   0),
    (14, "C",  "m",   0),
    (15, "Ab", "maj", 1),
    # Outro 17-20: wind down
    (16, "C",  "m",   0),
    (17, "Ab", "maj", 0),
    (18, "F",  "m",   0),
    (19, "C",  "m",   0),
]


def bar_to_chord(bar_idx: int) -> tuple[str, str, int]:
    for b, r, k, o in PROGRESSION:
        if b == bar_idx:
            return r, k, o
    raise KeyError(f"no chord at bar {bar_idx}")


# -----------------------------------------------------------------------------
# Note helpers
# -----------------------------------------------------------------------------
VEL_LO = 0.55   # ~70 -- soft, intimate
VEL_MD = 0.71   # ~90 -- normal
VEL_HI = 0.87   # ~110 -- chorus peaks


def note(pitch: int, start_bars: float, length_bars: float, velocity: float = VEL_MD) -> dict:
    return {"pitch": int(pitch), "start_bars": float(start_bars),
            "length_bars": float(length_bars), "velocity": float(velocity)}


# -----------------------------------------------------------------------------
# CHORDS track
# -----------------------------------------------------------------------------
# Voicing: build chord tones from root up an octave + fifth on top. Hold whole bar
# except intro/outro where chords are half-bar (let the bass voice the change).
def build_chords_track() -> dict:
    notes = []
    for bar_idx, root, kind, octv in PROGRESSION:
        root_midi = ROOTS[root] + (12 * octv)
        # Voicing: root (root_midi), 3rd (root+3or4), 5th (root+7), 3rd-up-an-oct (root+15or16)
        # For a 7th chord we use the 7th tone on top instead.
        if kind == "maj":
            tones = [root_midi, root_midi + 4, root_midi + 7, root_midi + 12 + 4]
        elif kind == "m":
            tones = [root_midi, root_midi + 3, root_midi + 7, root_midi + 12 + 3]
        elif kind == "7":
            tones = [root_midi, root_midi + 4, root_midi + 7, root_midi + 10]
        else:
            tones = [root_midi, root_midi + 4, root_midi + 7, root_midi + 12]

        # Bar length. In intro+outro we split the bar (1.5 beats chord, 0.5 beat breath, 2 beats chord)
        # to give a "phrase breath" feel.
        section_start_bar = bar_idx
        if bar_idx in (0, 1, 16, 17, 18, 19):
            # half-bar voicing with a tiny lift
            notes.append(note(tones[0], section_start_bar + 0.00, 1.75, VEL_LO))
            notes.append(note(tones[1], section_start_bar + 0.00, 1.75, VEL_LO))
            notes.append(note(tones[2], section_start_bar + 0.00, 1.75, VEL_LO))
            notes.append(note(tones[3], section_start_bar + 0.00, 1.75, VEL_LO))
            notes.append(note(tones[0], section_start_bar + 2.00, 2.00, VEL_LO))
            notes.append(note(tones[1], section_start_bar + 2.00, 2.00, VEL_LO))
            notes.append(note(tones[2], section_start_bar + 2.00, 2.00, VEL_LO))
            notes.append(note(tones[3], section_start_bar + 2.00, 2.00, VEL_LO))
        else:
            # full-bar pad
            notes.append(note(tones[0], section_start_bar + 0.00, 4.00, VEL_MD))
            notes.append(note(tones[1], section_start_bar + 0.00, 4.00, VEL_MD))
            notes.append(note(tones[2], section_start_bar + 0.00, 4.00, VEL_MD))
            notes.append(note(tones[3], section_start_bar + 0.00, 4.00, VEL_MD))

    # Chorus (bars 9-12) -- add a 9th color note for lift (Eb over Cm, Bb over Ab, C over Fm, F over G7)
    chorus_colors = {8: "Eb", 9: "Bb", 10: "C", 11: "F"}
    for bar_idx, color in chorus_colors.items():
        # Color note on the "and-of-2" beat, lasts a beat
        color_midi = ROOTS[color] + 12   # octave up
        notes.append(note(color_midi, bar_idx + 1.5, 0.5, VEL_HI))

    return {"name": "Chords", "channel": 1, "notes": notes}


# -----------------------------------------------------------------------------
# BASS track (root + 5th, half notes, low octave)
# -----------------------------------------------------------------------------
def build_bass_track() -> dict:
    notes = []
    for bar_idx, root, kind, _octv in PROGRESSION:
        root_midi = ROOTS[root] - 12  # one octave below C4
        fifth = root_midi + 7 if kind != "dim" else root_midi + 6
        seventh = root_midi + 10 if kind == "7" else None

        # Beat 1 + beat 3 = root, beat 2 + beat 4 = fifth (or 7th for V7)
        upper = seventh if seventh is not None else fifth
        notes.append(note(root_midi, bar_idx + 0.0, 2.0, VEL_HI))
        notes.append(note(upper,    bar_idx + 2.0, 2.0, VEL_HI))

        # In the bridge (bars 13-16), drop the bass a little for breath
        if 12 <= bar_idx <= 15:
            notes.append(note(root_midi - 12, bar_idx + 0.0, 2.0, VEL_MD))  # ghost sub

    return {"name": "Bass", "channel": 2, "notes": notes}


# -----------------------------------------------------------------------------
# LEAD MELODY track
# -----------------------------------------------------------------------------
# Intro: one long held note over each chord (breathing pad style), Eb5 over Cm, etc.
# Verse: simple stepwise line, climbs in the second half
# Chorus: peak at G5-Ab5, "the hook"
# Bridge: lifted octave, ornaments
# Outro: long held notes resolving to C
#
# Pitches: scale degrees in C Aeolian. Reference: C5=72.
# Chord tones per bar (root in this voicing, in C5 octave where possible):
#   Cm   -> Eb/G, melody centers on Eb5(75) and G5(79)
#   Ab   -> C/Eb, melody on C5(72), Eb5(75)
#   Fm   -> Ab/C, melody on Ab5(80), C6(84)
#   Eb   -> G/Bb, melody on G5(79), Bb5(82)
#   Bb   -> D/F, melody on D5(74), F5(77)
#   G7   -> B/F, melody on B5(83), F5(77)
def build_lead_track() -> dict:
    notes = []
    # ---- Intro (bars 1-4): one sustained tone per bar, with a tiny grace ----
    intro = [
        (0, [72], VEL_MD),     # Cm  -> C5 (whole bar, breath tone)
        (1, [75], VEL_MD),     # Ab  -> Eb5
        (2, [77], VEL_MD),     # Fm  -> F5
        (3, [79], VEL_MD),     # G7  -> G5 (resolve target)
    ]
    for bar_idx, pitches, vel in intro:
        for p in pitches:
            notes.append(note(p, bar_idx + 0.0, 4.0, vel))

    # ---- Verse (bars 5-8): gentle stepwise line ----
    # Bar 5 (Cm):  Eb5 - G5 - Eb5 - G5 (half notes), "where the morning used to find you"
    notes.append(note(75, 4.0, 0.5, VEL_MD))     # Eb5
    notes.append(note(79, 4.5, 0.5, VEL_MD))     # G5
    notes.append(note(75, 5.0, 1.0, VEL_MD))     # Eb5 (hold)
    notes.append(note(72, 6.0, 1.0, VEL_LO))     # C5 (descend)
    notes.append(note(70, 7.0, 1.0, VEL_LO))     # Bb4 (almost rest)
    # Bar 6 (Ab):  C5 - Eb5 - C5 - Eb5
    notes.append(note(72, 8.0, 1.0, VEL_MD))
    notes.append(note(75, 9.0, 1.0, VEL_MD))
    notes.append(note(72, 10.0, 1.0, VEL_MD))
    notes.append(note(75, 11.0, 1.0, VEL_MD))
    # Bar 7 (Eb):  G5 - Bb5 - G5 - F5
    notes.append(note(79, 12.0, 1.0, VEL_HI))
    notes.append(note(82, 13.0, 1.0, VEL_HI))
    notes.append(note(79, 14.0, 1.0, VEL_MD))
    notes.append(note(77, 15.0, 1.0, VEL_MD))
    # Bar 8 (Bb):  D5 - F5 - D5 - Eb5
    notes.append(note(74, 16.0, 1.0, VEL_MD))
    notes.append(note(77, 17.0, 1.0, VEL_MD))
    notes.append(note(74, 18.0, 1.0, VEL_LO))
    notes.append(note(75, 19.0, 1.0, VEL_LO))

    # ---- Chorus (bars 9-12): hook + lift ----
    # "Letters never sent, words I never said" -- singable line, climbs.
    # Bar 9 (Cm):  G5 - Ab5 - G5 - Eb5 (hook start)
    notes.append(note(79, 20.0, 1.0, VEL_HI))
    notes.append(note(80, 21.0, 1.0, VEL_HI))
    notes.append(note(79, 22.0, 1.0, VEL_HI))
    notes.append(note(75, 23.0, 1.0, VEL_MD))
    # Bar 10 (Ab): C6 (peak) - Bb5 - Ab5 - G5
    notes.append(note(84, 24.0, 1.0, VEL_HI))
    notes.append(note(82, 25.0, 1.0, VEL_HI))
    notes.append(note(80, 26.0, 1.0, VEL_HI))
    notes.append(note(79, 27.0, 1.0, VEL_MD))
    # Bar 11 (Fm): Ab5 - C6 - Bb5 - Ab5
    notes.append(note(80, 28.0, 1.0, VEL_HI))
    notes.append(note(84, 29.0, 1.0, VEL_HI))
    notes.append(note(82, 30.0, 1.0, VEL_HI))
    notes.append(note(80, 31.0, 1.0, VEL_HI))
    # Bar 12 (G7): F5 - G5 - B5 - C6 (lift into bridge)
    notes.append(note(77, 32.0, 1.0, VEL_MD))
    notes.append(note(79, 33.0, 1.0, VEL_HI))
    notes.append(note(83, 34.0, 1.0, VEL_HI))
    notes.append(note(84, 35.0, 1.0, VEL_HI))

    # ---- Bridge (bars 13-16): tension, then release ----
    # Bar 13 (Ab high): Eb6 - D6 - C6 - Bb5 (descending ornament)
    notes.append(note(87, 36.0, 0.5, VEL_HI))
    notes.append(note(86, 36.5, 0.5, VEL_HI))
    notes.append(note(84, 37.0, 1.0, VEL_HI))
    notes.append(note(82, 38.0, 2.0, VEL_HI))
    # Bar 14 (G7): D5 - F5 - G5 - Ab5 (lifted bass, tension)
    notes.append(note(74, 40.0, 1.0, VEL_HI))
    notes.append(note(77, 41.0, 1.0, VEL_HI))
    notes.append(note(79, 42.0, 1.0, VEL_HI))
    notes.append(note(80, 43.0, 1.0, VEL_HI))
    # Bar 15 (Cm): G5 - Eb5 - C5 - G4 (resolve DOWN to octave lower, sigh)
    notes.append(note(79, 44.0, 1.0, VEL_MD))
    notes.append(note(75, 45.0, 1.0, VEL_MD))
    notes.append(note(72, 46.0, 1.0, VEL_MD))
    notes.append(note(67, 47.0, 1.0, VEL_LO))
    # Bar 16 (Ab high): Eb5 - C5 - Ab4 - Eb5 (whisper to land)
    notes.append(note(75, 48.0, 1.0, VEL_LO))
    notes.append(note(72, 49.0, 1.0, VEL_LO))
    notes.append(note(68, 50.0, 1.0, VEL_LO))
    notes.append(note(75, 51.0, 1.0, VEL_LO))

    # ---- Outro (bars 17-20): long tones fading back to C ----
    outro = [
        (16, [72], VEL_MD),    # Cm  -> C5
        (17, [75], VEL_LO),    # Ab  -> Eb5
        (18, [77], VEL_LO),    # Fm  -> F5
        (19, [72], VEL_MD),    # Cm  -> C5 (home, full bar)
    ]
    for bar_idx, pitches, vel in outro:
        for p in pitches:
            notes.append(note(p, bar_idx + 0.0, 4.0, vel))

    return {"name": "Lead", "channel": 0, "notes": notes}


# -----------------------------------------------------------------------------
# DRUMS track (subtle guide -- Romantic Keys song, the 808 kit is already loaded)
# -----------------------------------------------------------------------------
# 808 Kick (channel 9 / GM drum map note 36), 808 Snare (note 38),
# 808 Clap (note 39), 808 HiHat (note 42 closed, 46 open).
# Pattern: soft brush-kit ballad. Kick on 1+3, snare on 2+4 light,
# closed hat 8ths, open hat at phrase ends. Quiet in intro/outro.
def build_drums_track() -> dict:
    notes = []
    for bar_idx in range(20):
        is_intro_outro = bar_idx < 4 or bar_idx >= 16
        vel_kick = 0.55 if is_intro_outro else 0.71
        vel_snare = 0.55 if is_intro_outro else 0.71
        vel_hat = 0.40 if is_intro_outro else 0.55

        # Kick on 1 and 3
        notes.append(note(36, bar_idx + 0.0, 0.5, vel_kick))
        notes.append(note(36, bar_idx + 2.0, 0.5, vel_kick))
        # Snare/clap on 2 and 4
        notes.append(note(38, bar_idx + 1.0, 0.5, vel_snare))
        notes.append(note(39, bar_idx + 3.0, 0.5, vel_snare * 0.85))
        # Closed hat 8ths
        for beat in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
            notes.append(note(42, bar_idx + beat, 0.25, vel_hat))
        # Open hat at the end of every other bar for swing
        if bar_idx % 2 == 1:
            notes.append(note(46, bar_idx + 3.75, 0.25, vel_hat * 0.9))

    return {"name": "Drums", "channel": 9, "notes": notes}


# -----------------------------------------------------------------------------
# Build + write
# -----------------------------------------------------------------------------
def main() -> str:
    tracks = [
        build_chords_track(),
        build_bass_track(),
        build_lead_track(),
        build_drums_track(),
    ]
    out_dir = os.path.join(os.path.expanduser("~"), ".flstudio-mcp", "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "letters_never_sent.mid")
    write_midi(tracks, bpm=78.0, path=out_path, beats_per_bar=4)
    note_count = sum(len(t["notes"]) for t in tracks)
    size = os.path.getsize(out_path)
    print(f"wrote: {out_path}")
    print(f"tracks: {len(tracks)}  notes: {note_count}  size: {size} bytes")
    print(f"track summary:")
    for t in tracks:
        print(f"  - {t['name']:7s}  ch={t['channel']:2d}  {len(t['notes'])} notes")
    return out_path


if __name__ == "__main__":
    main()