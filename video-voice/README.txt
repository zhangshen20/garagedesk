GarageDesk demo voice-over - generated 2026-10-26

MODEL
  Resemble AI Chatterbox (chatterbox-tts 0.1.7, the latest on PyPI), the original English model, on Apple M4 GPU (MPS).
  I used this one rather than Chatterbox Turbo because Turbo ignores exaggeration/cfg_weight, and those
  settings are what give the relaxed, conversational pacing.
  Settings: exaggeration 0.5, cfg_weight 0.4, temperature 0.8, repetition_penalty 1.2, min_p 0.05.
  (cfg 0.3 was tried on n02/n08; it barely changed the pace, so I stayed on 0.4.)
  Output: 24 kHz, mono, 16-bit WAV. Resemble's imperceptible Perth watermark is embedded by the library.

VOICES
  NARRATOR (n01-n13): Chatterbox's built-in default voice (warm, mid-low, neutral/US-leaning accent).
  OWNER (o01-o08): zero-shot clone from a 19.6 s public-domain LibriVox clip of Graham Dunlop reading
    "The North Wind and the Sun" in an Australian accent. See SOURCES.txt for the source and licence.
    Speaker-embedding similarity of the owner takes to that reference is 0.84-0.94, and about 0.6 to the
    narrator, so the two voices are clearly different people. Median pitch is about 110-118 Hz (male).
    Note: the accent is "general Australian reading voice", not broad ocker. It is a reading voice made
    casual by the settings, so it sounds like a calm bloke, not a radio announcer.

POST-PROCESSING (scripts/finalize.py)
  - Chatterbox runs sentences together (about 0.15 s gaps), which made the narration sound rushed.
    At every sentence end found by Whisper word timestamps, I widened the existing silence to 0.45 s
    (only where there was already a real gap, so no cut lands mid-sound). The speech itself is untouched.
  - Leading/trailing silence trimmed to 0.15 s with 10 ms fades.
  - Loudness normalised to -16 LUFS integrated, -1.5 dBTP ceiling (the raw output clipped slightly).
  - Every final file was transcribed back with Whisper large-v3-turbo (mlx-whisper). All 21 picked files
    read back word-perfect (only differences: "$350" for "three fifty", "labor" spelling, punctuation).

FILES
  n01.wav ... n13.wav, o01.wav ... o08.wav  = the picks (use these)
  n01_a/_b ... n13_a/_b                     = two narrator takes per line, as requested
  extra_takes/                              = extra retakes for n10 and n13 (see below)

PICKS (I mostly took the more relaxed / longer take when both were clean)
  n01 = a   n02 = b   n03 = a   n04 = a   n05 = b   n06 = a   n07 = a
  n08 = a   n09 = b   n10 = extra take f   n11 = a   n12 = b   n13 = extra take e
  o01-o08: best of 3 owner takes (o05/o07 see below)

PROBLEMS AND FIXES
  - n02 take a says "car is done" instead of "car's done" -> picked take b.
  - n06 b and n07 b run the sentences together -> picked take a.
  - n10 takes a/b: "Parts too" came out as "Part 2"/"Hearts 2" and take a said "Jess" for "yes".
    I regenerated with punctuation only ("Parts, too. ... and yes, sends it."), same words. Take f is clean.
  - n13: a/b had no pause between the three short sentences, which made the tagline flat. Take e has a
    natural break and reads back perfectly. extra_takes/n13_stitched.wav joins three separate sentences
    with 0.45 s gaps for a punchier ending, but Whisper hears "GarageDesk" there as "The Raj Desk", so
    listen before using it.
  - o05/o07 "Yes.": Chatterbox hallucinates on one-word text with this voice (13 takes gave things like
    "It's going, so." or plain gibberish). Fix: I generated "Yes. That is right, mate." / "Yes. Go on then."
    and cut out the first word at the natural pause (scripts/cut_first.py). The results are clean 0.6 s "Yes."
  - o01 reads the rego as "A B C, one two three" smoothly (Whisper writes it as "ABC123").
  - No Australian speaker exists in the EdAcc corpus, so the owner reference came from LibriVox instead.

REPRODUCE
  venv/ (Chatterbox, Python 3.11) and whisper-venv/ (mlx-whisper). Scripts are in scripts/:
  gen.py (TTS), finalize.py (pauses, trim, loudness, read-back check), cut_first.py, check.py, spk.py.
  preview_all_lines.mp3                     = all picks in storyboard order with 0.6 s gaps, for a quick listen
