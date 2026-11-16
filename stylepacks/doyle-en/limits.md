# Arthur Conan Doyle — limits (en)

> What this pack can carry, what it can only half carry, and where the numbers come
> from. Read this before quoting a delta score to anyone.

## What transfers cleanly

- **The sentence machine.** Median 13 words, p25 5, p75 20, comma-heavy, no ellipsis, one
  long chain per page. A text written to these numbers reads as period prose immediately.
- **The pronoun mix.** First-person retrospective narration at `I` 28.9 / `my` 9.6,
  detective at `he` 13.9, reader-in-dialogue at `you` 14.1. Getting this wrong is the
  fastest way to sound modern.
- **The function-word layer.** `the`/`and`/`of`/`a`/`to` proportions plus the Victorian
  connective set (`upon` above `on`, `quite`, `however`, `yet`, `rather`, `indeed`,
  `pray`). Measured, stable across all eleven samples.
- **Dialogue mechanics.** Curly quotes, `said` at 55% of attributions, inverted tags,
  single-word replies, em dash for interruption, 17% of paragraphs opening a speech that
  continues.
- **Scene beats.** Client recital, inspection, trap, explanation, deflating exit. This is
  structural and can be re-pointed at new characters without loss.

## What transfers only partially

- **Dialogue share.** 87% of paragraphs contain speech — true of a consultation scene,
  false of an action scene or a letter. Apply it where two people are in a room, then
  drop it; a whole story at 87% becomes a transcript.
- **The fog and gaslight inventory.** It is period-correct but scene-bound: usable for
  London streets, wrong for a country house in daylight. Keep the *function* (weather
  fixes what can be seen) and swap the props.
- **The long quoted recital.** A third of a chapter in a client's own voice works in a
  serialised magazine story; in a short modern piece it needs cutting and paraphrasing.
- **The formal address.** `Pray take a seat`, `your Majesty`, `my dear Watson` carry rank
  and period. Use where the social relation exists; do not sprinkle for flavour.
- **Aphorism density.** One maxim per case in Doyle. More than that reads as pastiche, and
  the delta score will not tell you — it measures surface, not taste.

## What does not transfer

- **The canon machinery.** Holmes, Watson, Baker Street, Lestrade: this pack describes a
  manner, not a licence to reuse characters and plots from the stories.
- **Period prejudice.** The samples carry the casual racism, class contempt and
  criminological jargon of their era (Lombroso, physiognomy, "the criminal type"). The
  fingerprint does not ask for it; do not reproduce it.
- **Serial length.** Chapters here run 6,000–9,000 words because magazines paid by the
  instalment. Any modern use should compress.
- **Char-level metrics.** `top_chars`, `fourgram_top` and `reduplication_per_1k` are empty
  or zero in this fingerprint because they are Chinese-script metrics. Their absence is
  not a gap in coverage.

## Honest notes for the user

**Acceptance line.** Eleven leave-one-out samples score delta 0.816–1.331 (median 0.944);
the worst, 1.331, is the pass line stored as `self_check.narrative.delta_max`. Anything
under 1.33 is inside Doyle's own variation.

**Same-author holdout.** *The Hound of the Baskervilles* (59,636 words, not in the
samples) scores **delta 0.649** and passes 12 of 14 structural rows. The two failures are
`paragraph.dialogue_para_ratio` (target 0.869) and the comma rate — a novel has more
narration than a short story, so the tuning is visibly short-story-shaped.

**Other Victorian authors** (should fail, mostly): Dickens 1.20, Stoker 1.26, Wilde 1.29,
Melville 1.61, Twain 1.64, Austen 1.69 and 1.83, Carroll 1.92. Only the first three sit
under the line, and they fail 4–6 of the 14 rows each — delta alone is a coarse gate, the
row-level checks are what actually separate authors.

**AI baseline.** Twelve chapters of machine-written Victorian pastiche score delta
2.79–3.55 and fail 9–11 of 14 rows. Separation from Doyle is roughly 3–4×.

**Short text.** Under 400 words nothing is scored; 400–600 words are marked medium
confidence. Do not judge a paragraph.

**Sampling.** 105,301 words in eleven contiguous chunks of roughly 9,000 words from one
Gutenberg edition. The last chunk is short, and its leave-one-out score (1.331) is what
sets the line — so the line is slightly inflated by sample size, not by style.

**What the score does not measure.** Plot logic, period accuracy of facts, whether the
story is any good, and whether a reader would notice the pastiche. Those need a human.

## AI 腔豁免

These are Doyle-native words and phrases that a future English AI-cliché list is likely to
flag. They are attested at the rates given and must not be treated as machine tics.
Counts per 105,301 words in parentheses.

- of course (51)
- no doubt (50)
- pray (42)
- at once (34)
- singular (33)
- remarkable (21)
- quite so (19)
- extraordinary (19)
- I am sure (18)
- however (107)
- quite (107)
- indeed (62)
- certainly (45)
- suddenly (47)
- rather (64)
- perhaps (63)
- very (399)
- well (201)