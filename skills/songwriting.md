name: songwriting
description: Write song lyrics or a parody with structure, rhyme and meter, plus an AI-music style brief

These are guidelines; break one on purpose when the line hits harder.

1. Ask for or decide: topic, mood, genre, and whether it is original or new words to an existing song.
2. Write the hook first: the one line people will repeat, usually the title. Build everything around it.
3. Pick a structure: Verse/Chorus/Verse/Chorus/Bridge/Chorus (pop), Verse/Verse/Bridge/Verse (ballad),
   or verses only (folk storytelling). Optional: Intro, Pre-Chorus, Outro.
4. Brainstorm raw images, phrases and rhymes before fitting them into lines.
5. Draft. Verses carry story and detail; the chorus carries the feeling; the bridge shifts the viewpoint.
6. Parody: first map the original per line - syllable count, rhyme scheme, stressed beats, held notes.
   Put new stressed syllables on the same beats, match the vowel on long notes, keep a few original lines.
7. Read it aloud in your head line by line. Where the rhythm stumbles, fix the meter.
8. Add section tags in brackets: [Intro] [Verse 1] [Pre-Chorus] [Chorus] [Bridge] [Outro], plus delivery
   tags such as [Whispered] [Belted] [Building Energy]. Max 5-8 tags per section; none that contradict.
9. Write a style brief (under 1000 characters): genre + mood + era + instruments + vocal persona + production,
   then the arc ("starts as a whisper over piano, builds to full band, ends bare"). No artist names.
10. write_file("songs/<title>.txt") with the style brief on top and the tagged lyrics below.

RULES
- Show, do not tell: a concrete image ("your coat still on the hook") beats "I was sad".
- Mix perfect and near rhymes. Never twist word order to land a rhyme. Avoid cliches.
- Parallel lines get matching stressed beats. Contrast sections: quiet before loud, sparse before dense.
- For AI singers: spell out numbers, space acronyms ("A I"), respell hard names as they sound,
  CAPS for louder, "lo-o-ove" for a held note.
- You cannot generate audio. The user pastes the brief and lyrics into their own music tool.

Final answer: title, the style brief, the full tagged lyrics, and the file path.
