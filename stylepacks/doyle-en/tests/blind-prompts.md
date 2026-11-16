# Doyle (en) — A/B blind prompts (tests)

> Usage: see the style-calibrate skill. Fixed prompt per item; generate one passage with
> the pack and one without, shuffle the labels, and let a reader pick blind. Score the
> picked-with-pack rate, not the prose's quality.

## Prompt 1: The client at dusk

Prompt: first person, 250–350 words. It is dusk; the lamps are being lighted; a client
climbs the stairs to the sitting-room and puts a small wooden box on the table.

Checklist:
- [ ] First sentence fixes the hour by light or weather, not by a clock
- [ ] The client is entered by measurement (height; weight change; condition of boots)
- [ ] At least one exact number (inches, pounds, shillings, a price)
- [ ] Speech at least 50% of the paragraph count; attribution is `said`/`asked`
- [ ] One interruption by em dash; no ellipsis anywhere
- [ ] Curly quotation marks only

## Prompt 2: The advertisement

Prompt: first person, 250–350 words. A paragraph in the agony column of the evening paper
sends the narrator and his companion to an address in a shabby-genteel square.

Checklist:
- [ ] The newspaper paragraph is quoted or paraphrased in one sentence, no more
- [ ] The address is named and the route given in one sentence (cab, then walk)
- [ ] One Latin or legal tag in italics, at most
- [ ] No interior access to the companion's mind — he is observed and quoted only
- [ ] Ends on a dry remark or a new small question, not a moral

## Prompt 3: The locked room

Prompt: first person, 250–350 words. A door that was locked from the inside is opened;
the narration inventories the room before anyone interprets it.

Checklist:
- [ ] At least five concrete objects recorded without commentary (fire, gasogene, window,
      bell-pull, a mark on the floor)
- [ ] Interpretation deferred to dialogue and marked as provisional (`It appears that ...`,
      `I fancy ...`)
- [ ] Sentences short: median under 20 words, with two or more single-clause sentences
- [ ] No named emotion; fear shown by a hand, a candle or a voice
- [ ] British spelling throughout (`-ise`, `grey`, `colour`)

## Prompt 4: Breakfast and a small puzzle

Prompt: first person, 250–350 words. At breakfast a trivial domestic puzzle is resolved in
three sentences of deduction before the coffee is cold.

Checklist:
- [ ] The conclusion is stated before its reason, in the same breath
- [ ] The chain is delivered as a question or a series of short declaratives
- [ ] One aphorism, at most, and it is laughed off by the speaker
- [ ] The narrator confesses a small failure once (`I confess`, `I fancy`)
- [ ] The last line deflates the scene — no summary, no theme

## Scoring

Win rate = times the with-pack passage is chosen / valid rounds ("neither" is not counted
in the denominator). At least 70%: the pack is mature. 50–70%: iterate with
style-feedback. Below 50%: check that the pack was actually attached, then re-read
`limits.md` before blaming the prompt.