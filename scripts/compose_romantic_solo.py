"""Generate a 16-bar romantic solo for Romantic Keys on channel 5 of FL.

Form:
  Bars 1-4:  intro  -- sustained chord tones (pad-style), gentle attack
  Bars 5-8:  verse A -- melody enters, simple stepwise line
  Bars 9-12: verse B -- melody lifts, longer phrases, a high C6
  Bars 13-16: outro -- melody resolves to a long held C5

Key: C Aeolian (C D Eb F G Ab Bb)
Tempo: 78 BPM, 4/4
Velocity: 0.55..0.85 (Romantic Keys is a nylon/EP; too loud sounds harsh)
"""
import os
import sys

# Connect to the daemon
os.environ['FLSTUDIO_MCP_TRANSPORT'] = 'tcp'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from fl_studio_mcp.connection import get_bridge  # noqa
from fl_studio_mcp import protocol as P  # noqa

b = get_bridge()

# -----------------------------------------------------------------------------
# C Aeolian (C D Eb F G Ab Bb) -- MIDI note numbers in C4..C6 range
# MIDI 60 = C4 in FL's octave numbering
# -----------------------------------------------------------------------------
# C4=60  D4=62  Eb4=63  F4=65  G4=67  Ab4=68  Bb4=70
# C5=72  D5=74  Eb5=75  F5=77  G5=79  Ab5=80  Bb5=82
# C6=84

VEL_PAD = 0.55
VEL_MELODY = 0.75
VEL_PEAK = 0.85

# -----------------------------------------------------------------------------
# INTRO: bars 1-4 -- held chord tones (4/4, one note per bar, whole notes)
# Cm: Eb5 | Ab: C5 | Fm: Ab4 | G7: F5
# -----------------------------------------------------------------------------
intro = [
    # (pitch, time_bars, length_bars, velocity)
    (75, 0.0, 4.0, VEL_PAD),     # bar 1: Eb5
    (72, 4.0, 4.0, VEL_PAD),     # bar 2: C5
    (68, 8.0, 4.0, VEL_PAD),     # bar 3: Ab4
    (77, 12.0, 4.0, VEL_PAD),    # bar 4: F5
]

# -----------------------------------------------------------------------------
# VERSE A: bars 5-8 -- simple stepwise melody over | Cm | Ab | Fm | G7 |
# (we're writing absolute time_bars from bar 5 = time 16)
# -----------------------------------------------------------------------------
# Bar 5 (Cm): C5 D5 Eb5 D5 C5 -1 (rest) -1 -1 -- gentle figure, half notes
verse_a = [
    (72, 16.0, 1.0, VEL_MELODY),    # C5
    (74, 17.0, 1.0, VEL_MELODY),    # D5
    (75, 18.0, 1.0, VEL_MELODY),    # Eb5
    (74, 19.0, 1.0, VEL_MELODY),    # D5
    (72, 20.0, 1.0, VEL_MELODY),    # C5 (held)
    # Bar 6 (Ab): Eb5 -1 C5 -1 | half-note figure
    (75, 21.0, 2.0, VEL_MELODY),    # Eb5 (half)
    (72, 23.0, 1.0, VEL_MELODY),    # C5
    # Bar 7 (Fm): F5 G5 Ab5 G5 -- peak phrase fragment
    (77, 24.0, 1.0, VEL_PEAK),      # F5
    (79, 25.0, 1.0, VEL_PEAK),      # G5
    (80, 26.0, 1.0, VEL_PEAK),      # Ab5 (the climax of the phrase)
    (79, 27.0, 1.0, VEL_PEAK),      # G5
    # Bar 8 (G7): F5 Eb5 D5 C5 -- descent to tonic
    (77, 28.0, 1.0, VEL_MELODY),    # F5
    (75, 29.0, 1.0, VEL_MELODY),    # Eb5
    (74, 30.0, 1.0, VEL_MELODY),    # D5
    (72, 31.0, 1.0, VEL_MELODY),    # C5
]

# -----------------------------------------------------------------------------
# VERSE B: bars 9-12 -- melody lifts, longer phrases
# Cm | Ab | Fm | G7 | (time 32..47)
# -----------------------------------------------------------------------------
verse_b = [
    # Bar 9 (Cm): Eb5 G5 Eb5 G5 -- oscillating, lifts register
    (75, 32.0, 2.0, VEL_PEAK),      # Eb5 (half)
    (79, 34.0, 2.0, VEL_PEAK),      # G5 (half)
    # Bar 10 (Ab): C6 -1 Bb5 Ab5 G5 -- the big peak
    (84, 36.0, 1.0, VEL_PEAK),      # C6 (the high point!)
    (82, 37.0, 1.0, VEL_PEAK),      # Bb5
    (80, 38.0, 1.0, VEL_PEAK),      # Ab5
    (79, 39.0, 1.0, VEL_PEAK),      # G5
    # Bar 11 (Fm): Ab5 C6 Bb5 Ab5 -- sustain a high note
    (80, 40.0, 1.0, VEL_PEAK),      # Ab5
    (84, 41.0, 1.0, VEL_PEAK),      # C6 (held high)
    (82, 42.0, 1.0, VEL_PEAK),      # Bb5
    (80, 43.0, 1.0, VEL_PEAK),      # Ab5
    # Bar 12 (G7): G5 Bb5 C6 -1 -- the resolution
    (79, 44.0, 1.0, VEL_MELODY),    # G5
    (82, 45.0, 1.0, VEL_MELODY),    # Bb5
    (84, 46.0, 1.0, VEL_PEAK),      # C6
    (72, 47.0, 1.0, VEL_MELODY),    # C5 (the descent!)
]

# -----------------------------------------------------------------------------
# OUTRO: bars 13-16 -- resolves to long C5
# Ab | G7 | Cm | Cm | (time 48..63)
# -----------------------------------------------------------------------------
outro = [
    # Bar 13 (Ab): C5 Eb5 -1 C5
    (72, 48.0, 1.0, VEL_MELODY),    # C5
    (75, 49.0, 1.0, VEL_MELODY),    # Eb5
    (72, 50.0, 2.0, VEL_MELODY),    # C5 (held)
    # Bar 14 (G7): -1 Bb5 -1 D5
    (82, 52.0, 1.0, VEL_MELODY),    # Bb5
    (74, 53.0, 1.0, VEL_MELODY),    # D5
    # Bar 15 (Cm): G5 -1 Eb5 C5 (anticipating the resolution)
    (79, 56.0, 1.0, VEL_MELODY),    # G5
    (75, 57.0, 1.0, VEL_MELODY),    # Eb5
    (72, 58.0, 1.0, VEL_MELODY),    # C5
    (72, 59.0, 1.0, VEL_MELODY),    # C5
    # Bar 16 (Cm): long C5 -- resolution
    (72, 60.0, 4.0, VEL_PAD),      # final C5 (whole note, gentle)
]

# Combine
all_notes = intro + verse_a + verse_b + outro

# Convert to the format fl_write_raga_melody expects:
# {"pitch": int, "time_bars": float, "length_bars": float, "velocity": float}
note_dicts = [
    {"pitch": p, "time_bars": t, "length_bars": l, "velocity": v}
    for (p, t, l, v) in all_notes
]

print(f"Total notes: {len(note_dicts)}")
print(f"Bar span: 0..{max(n['time_bars'] + n['length_bars'] for n in note_dicts):.2f}")
print(f"Pitch range: {min(n['pitch'] for n in note_dicts)}..{max(n['pitch'] for n in note_dicts)} (MIDI)")

# -----------------------------------------------------------------------------
# Select channel 5 (Romantic) + ensure piano roll is open
# -----------------------------------------------------------------------------
r = b.call(P.CMD_CHANNEL_SELECT, {'channel': 5}, timeout=6.0)
print(f"\nselect ch 5: {r}")
r = b.call(P.CMD_ENSURE_PIANO_ROLL, {}, timeout=6.0)
print(f"ensure piano roll: {r}")

# Write the notes
print("\n=== Writing notes ===")
# Extend pattern to cover the full song span + headroom
max_bar = max(n['time_bars'] + n['length_bars'] for n in note_dicts)
pattern_beats = int(max_bar * 4) + 8  # 4 beats/bar + 2 bars headroom
print(f"Pattern span: {max_bar:.0f} bars -> extending to {pattern_beats} beats")
r = b.call(P.CMD_SET_PATTERN_LENGTH, {'index': 1, 'beats': pattern_beats}, timeout=6.0)
print(f"  set_pattern_length: {r}")

# apply_notes takes the MCP-side: (notes, mode, trigger, quantize, snap_ends)
r = b.apply_notes(note_dicts, mode='replace', trigger=True, quantize=None, snap_ends=False)
print(f"apply_notes result: {r}")

# -----------------------------------------------------------------------------
# Verify by reading back
# -----------------------------------------------------------------------------
print("\n=== Verify ===")
r = b.call(P.CMD_GET_PROJECT_STATE, {}, timeout=6.0)
print(f"final project state: {r}")
