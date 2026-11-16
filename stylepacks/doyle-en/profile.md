# Arthur Conan Doyle — style profile (en)

> Measured on eleven calibration samples (105,301 words) of Doyle's short fiction.
> Every figure is a rate per 1,000 words unless it says otherwise; tolerances live in
> `fingerprint.json` and are what a generated text is scored against.

## 300-Word Essence

A case is told by a man who is not the detective. Watson writes after the fact, in the
first person, with a recorder's patience and a companion's small vanities; he is allowed
to be slower than the reader and is never allowed to be cleverer than Holmes. The prose
is plain, declarative and fast. It runs on short sentences — five words at the first
quartile, eleven at the median — and it earns a long one only when a deduction has to be
laid out link by link, or when a street has to be inventoried: fog, gaslight, a
dun-coloured row of houses, a window that looms like a dark blur.

Dialogue does most of the work. Two thirds of the paragraphs carry speech, and the
speech is interrupted rather than described: an em dash cuts a sentence, a question is
answered by a single word. People are entered into a room by their measurements — six
feet six inches, seven and a half pounds, a hat that has been brushed three times — and
their feelings are entered by their bodies. Nobody announces an emotion; the hand, the
wet boot and the flickering lamp do the announcing, and the narrator steps back with a
dry remark.

The world is late-Victorian London read as evidence: cabs, telegraph boys, a gasogene,
a fire in the grate, the evening paper's agony column. Money is counted in sovereigns and
half-crowns. Virtue belongs to method, not to morals: the criminal is another puzzle, the
punishment is an epilogue, and the last line of a case is usually a joke, a shrug, or a
door closing on something that will never be explained.

Instructions in one breath: keep the sentence short, the noun concrete, the verb plain,
the emotion physical, the ending dry; make the reader feel that the truth was lying on
the table the whole time.

## Narrative POV and Person

First person, past tense, retrospective. Watson refers to himself as `I` (28.9/1k), `my`
(9.6) and `me` (6.1) at roughly three times the rate the detective appears as `he`
(13.9): the book is a memoir, not a biography of Holmes. The narrator knows the ending
before he begins ("I have seldom heard him mention her under any other name") and is not
afraid to say so — suspense is made by withholding the reader's understanding, never by
hiding the teller's.

Watson never enters Holmes's head. Holmes is observed, quoted, occasionally described as
a machine or a bloodhound, and whenever he explains himself it is out loud, in his own
words, in a monologue the narrator merely punctuates with `I cried`, `I said` or a
question. The reverse is not true: the reader is given Watson's interior freely,
including his embarrassment ("I was always oppressed with a sense of my own stupidity").

Second person appears only inside dialogue (`you` 14.1/1k), almost always Holmes
instructing Watson or a client. Narration does not address the reader. The implied
listener is a friend of the pair, slightly slower than Holmes, who needs the explanation
and is trusted to enjoy it.

Point of view never moves. There is no scene the narrator did not witness or have
reported to him, and the one exception is always flagged ("I have since heard from
Lestrade...").

## Sentence Rhythm

Short, front-loaded, mostly subject-verb-object. Sentence length: 5 words at p25, 11 at
the median, 20 at p75, mean 14.4 — but the fingerprint's sentence splitter groups harder
(median 13, mean 15.8), so treat anything between 11 and 16 as the true centre.

The default sentence is a statement of fact with one modifier: `The man was very tall.`
`It was a cold morning.` `He shook his head.` Coordination with `and` is common and
unfussy; subordination is rare (although 0.09/1k, because 0.22/1k), and where it appears
it comes at the end of the sentence, not the front. `But` opens sentences constantly
(6.15/1k — the highest single word after the article-function set), `then` (3.5) and
`now` (2.2) do the sequencing work that a modern writer would give to adverbs.

Commas are dense (72.7/1k) and carry the long lists and the appositions; semicolons are
rare (1.9/1k) and used for the one place where two statements must be welded — usually a
deduction and its consequence. Colons are almost absent (0.5/1k) and appear only before
an inventory. There is no ellipsis anywhere: zero `…`, zero `...` in 105,301 words. A
sentence that trails off does so with a dash (1.8/1k), and a sentence that is cut off is
cut off by the next speaker.

The long sentence, when it comes, is a chain: three to five clauses, each one a
verified detail, ending on the conclusion. It is never ornamental and never runs
backwards. The rhythm of a passage is therefore: short, short, short, short, one long
chain, short.

## Diction and Allusion

Concrete nouns, plain verbs, almost no adjectives of evaluation. The article-function
words dominate exactly as in ordinary English (`the` 53.4, `and` 28.8, `to` 25.7, `of`
25.0, `a` 24.9, `in` 16.8, `that` 16.7, `it` 16.2, `was` 13.8, `his` 10.8, `is` 10.5) —
the texture that marks this register is the layer just below them: `upon` (4.32) is used
*more* often than `on`, `quite` (1.0) and `however` (1.0) and `yet` (0.8) and `still`
(0.8) and `rather` (0.6) and `indeed` (0.6) and `pray` (0.4) and `singular` (0.3) and
`at once` (0.3) and `no doubt` (0.5). `Very` (3.8) is the one intensifier allowed, and it
is used flatly.

Register markers, with raw counts in the 105,301-word sample: `of course` (51), `no doubt`
(50), `pray` (42), `at once` (34), `singular` (33), `remarkable` (21), `quite so` (19),
`extraordinary` (19), `I am sure` (18), `I fancy` (12), `I confess` (11), `tut` (8),
`good heavens` (5), `my dear Watson` (5), `a trifle` (4), `it appears that` (3), `in the
meantime` (3), `by Jove` (2), `the deuce` (1). Titles and addresses are formal: `Mr`,
`Dr`, `sir`, `madam`.

Allusion is light and functional. Latin and legal tags are set in italics and left
untranslated (`_locus standi_`, `_carte blanche_`, `_incognito_`) — only 38 italic spans
in the whole sample, roughly one per 2,800 words, so use them as a seasoning, not a
habit. Shakespeare, the Bible, the racing page, the agony column, Lombroso and Bertillon
are quoted or name-dropped as shared furniture; nobody explains them.

Names are plain and dated: Baker Street, Brixton Road, Lauriston Gardens, Briony Lodge.
Numbers are exact and always spelled out in a way a clerk would write — `seven and a half
pounds`, `six feet six inches`, `half a crown a packet`, `three days`.

## Dialogue

Dialogue is the engine: 87% of paragraphs contain speech (`dialogue_para_ratio` 0.869).
Quotation marks are curly, never straight — zero `"` in 105,301 words. A speech that
runs past a paragraph break opens with `“` and does not close (26.2 opens to 22.1
closes; 17% of paragraphs are off by exactly one open), which is a typesetting
convention of the period and should be reproduced as `“` at the start of each continued
paragraph with no closing mark until the speech ends.

Attribution is boring on purpose. Of 881 attribution verbs, `said` accounts for 486
(55%); then `asked` 88, `cried` 68, `remarked` 64, `answered` 56, `returned` 36,
`observed` 22, `whispered` 16, `continued` 14, `shouted` 9, `muttered` 4, `ejaculated` 4
(a period tic: use once at most), `replied` 3, `exclaimed` 3, `added` 3. The tag is
normally `said Holmes` — inverted, surname only, no adverb. Adverbs of manner in tags
are rare; the manner is carried by the words.

Questions are frequent (7.0/1k) and short. Exclamations exist (3.3/1k) and are allowed —
Doyle's people cry out, laugh and exclaim — but they belong to the speaker, never to
narration. Single-word replies are a signature: `Seven!` `No.` `Quite so.` (0.18/1k).
Interruption is an em dash, not a trail-off. A speaker who is cut off gets no closing
quote in the typeset original; in regeneration, prefer a dash and a new speaker.

## Scene and Structure

One chapter, one case. The standard five beats: (1) the client is announced and
recites — often a long, quoted, first-person narrative that occupies a third of the
chapter; (2) the inspection, usually a single room or a single street, in which the
detective measures and the narrator wonders; (3) the plan or the trap, given to the
reader only as much as Watson is given; (4) the explanation monologue, which retells the
chapter in order and is allowed to be long; (5) the exit — a joke, a shrug, a cab, or a
line that closes the case while opening a smaller mystery.

Scenes are rooms and streets. A change of scene is a cab ride in one sentence (26 `cab`,
4 `brougham`, 6 `hansom` per 105,301 words — transport is named but not described). The
hour is kept by light and weather: `It was already dusk, and the lamps were just being
lighted`; `A thick fog rolled down between the lines of dun-coloured houses`. Weather is
not mood-setting, it is staging: it tells the reader what can and cannot be seen.

The fair-play contract is absolute. Every clue needed for the solution is shown before
the solution, usually twice, the second time in passing. The narrator may miss it; the
reader may miss it; the detective may not invent it afterwards. When Doyle cheats, he
cheats by withholding a fact that Watson did not witness, and he says so.

## Emotion and Atmosphere

Emotion is physical, brief, and immediately undercut. Fear is a wet palm, a candle that
shakes, a face that goes the colour of clay; then Watson makes a joke or Holmes makes an
observation, and the scene moves. Admiration is stated plainly and without irony (`I
could not help laughing`, `I was filled with admiration`). Holmes's coldness is played
for comedy, never for cruelty; his vanity is quoted, not judged.

Grief, horror and squalor get one flat sentence each. A corpse is described as furniture
with a detail attached; a ruined woman is described by her clothes; a villain is
described by his physique. The narration never lingers, never analyses, and never
explains what the reader should feel.

Atmosphere is atmosphere of evidence: gaslight, fog, the smell of a cheap cigar, the
sound of a hansom on wet stones. The vocabulary of feeling is small — `dread`, `horror`,
`amazement`, `sympathy` — and each appears once or twice per case, never in a paragraph
of its own.

## Generation Guidance

| when the scene is | reach for | exemplar |
| --- | --- | --- |
| a client entering | measure the body and the clothes before a single word of dialogue | 6 |
| the detective concluding | give the number first, then the chain, in separate short sentences | 2, 3 |
| the reader needs the method | one maxim, in dialogue, one sentence, no gloss | 4, 5 |
| the scene moving outdoors | fix the hour with light, fog or lamps | 7, 8 |
| action about to start | cut to clipped orders, strip adjectives | 9 |
| the tension needs release | one dry joke, usually Holmes laughing at his own metaphor | 10 |
| the narrator must confess | admit density, keep dignity, one sentence | 11 |
| the case ending | deflate it, or end on an unresolved trifle | 12, 13 |

Length habit: a case runs 6,000–9,000 words; a scene 300–800; a paragraph 2–5 sentences
(paragraph median 20 words in dialogue-heavy passages). Keep the ratio: roughly one part
narration to two parts speech.

## Ban List

- American spellings: `color`, `gray`, `honor`, `realize` (the samples run 55 `-ise` to 13
  `-ize`, 24 `grey` to 0 `gray`, 19 `colour`).
- Straight quotation marks, and any ellipsis (`...` or `…`): both are absent from the
  samples and instantly break the period.
- Said-bookisms: `intoned`, `smirked`, `hissed`, `chuckled`, `quipped`, `breathed`,
  `growled`. Attribution is `said`, `asked`, `cried`, `remarked`, `answered`.
- Modern idiom and register: `okay`, `guy`, `awesome`, `contact` as a verb, `I need you
  to`, `let's do this`, `no worries`, `partner`, managerial jargon of any kind.
- Psychologising adverbs and abstract feeling-nouns: `incredibly`, `utterly`,
  `profoundly`, `trauma`, `closure`, `energy` in the therapeutic sense.
- Naming an emotion the body has already shown (`he was terrified` after the shaking
  hand), and any sentence that explains the moral of the case.
- Present-tense narration, stream of consciousness, and any interior access to Holmes.
- Anachronism: fingerprints as routine, telephones, forensics, psychology as a
  discipline, American money.
- Em dashes used as commas. A dash here either interrupts a speech or appends an
  afterthought at the end of a sentence; it is not decoration.