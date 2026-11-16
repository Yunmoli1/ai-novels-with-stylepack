# Arthur Conan Doyle — thought layer (en)

> revision 1 · 2026-11-16 · marker: lead · language: en · pack: doyle-en
> 分工：六节由人编写（依据十一份标定样本与 `fingerprint.json` 的实测值）；
> `motif_stats` 的数值可复现——`motif_count.py` 按包语言选量纲：中文=次/千字（子串），
> 英文=次/千词（词边界）。本包语料 11 篇 105,301 词，剔除线用英文缺省 0.5/千词。
> 表里 fire / money / letter / lamp / cab 低于该线，手工保留（都是年代道具，短篇里出现
> 一次就有用），`--write` 重跑会把它们剔掉——这是唯一的人为差异。

## Subject Horizon

Doyle's stories look at a wrong that can be reasoned away. The subject is never the
murder; it is the *legibility* of a person: a clerk with a red-headed client, a governess
with an offer of employment, a fiancée with a missing bridegroom, a banker with a
misplaced crown. Ordinary professional life — offices, banks, lodgings, colleges,
timetables — is where the strange arrives, and the strange always arrives with a
document: an advertisement, a letter, a will, a newspaper paragraph.

London is treated as an information system: telegraph boys, cab ranks, the agony column,
lodging-house registers, the evening paper. Information is available to anyone who pays
attention, which is why the detective's power is a form of reading rather than a form of
force.

The stable ground under all of it is a friendship between two men who share rooms, work
and danger. That friendship is never analysed, only shown.

Outside the horizon: politics, sex, poverty as an argument, the criminal's childhood, the
detective's private life, and any question about what the empire is doing. Doyle keeps
the frame tight on purpose; the tightness is the style.

## Stance Actions

What the prose actually does, in order of frequency:

- **Measures before it judges.** A person is entered by height, weight, dress, hands.
  Judgement follows the measurement and is usually spoken by Holmes, not the narrator.
- **Reports, then interprets.** Narration gives the fact; the next sentence, in dialogue,
  gives the meaning. The two are never blended into one "he was obviously nervous".
- **Withholds the frame, not the evidence.** The reader is given every clue early and the
  pattern late. Suspense is produced by the reader's own inattention, which the text then
  rewards by showing it back.
- **Concedes before it concludes.** "I confess", "I fancy", "no doubt" — the narrator is
  allowed to be wrong, which makes the eventual rightness credible.
- **Deflates at the end.** A joke, a shrug, a cab. The emotional climax of a case is
  deliberately refused.
- **Refuses to moralise.** No closing paragraph explains what we should think. The last
  sentence is usually domestic or comic.

## Observation Checklist

Things this style records, and the level of detail it records them at:

- **The body.** Height to the inch, weight change to the half-pound, a limp, a scar, the
  condition of the hands, the colour of the face under strain.
- **Clothing.** A brushed sleeve, a worn cuff, wet boots, mud of a particular colour, a
  hat set at an angle, gloves carried rather than worn.
- **Traces.** Cigar ash, sawdust, a cut in the wood, a mark on the wall, a scratch on a
  watch, a stain that is not blood.
- **Money.** Coins and notes in hand, wages, debts, a cheque, the price of a cab, a
  thousand a year — money is a class marker and a motive at once.
- **Time.** Lamps being lighted, dusk, a cold morning, the hour of a train, the interval
  between a scream and a shot.
- **The room.** A gasogene in the corner, a bell-pull, a ventilator, a locked door, a
  window that opens on what it should not.
- **Papers.** Advertisements, letters, diaries, newspaper paragraphs, a note in a
  handwriting that does not match its signature.
- **Rank and address.** A square, a terrace, a lodging-house; accent, servants, the way a
  visitor is announced.

Rule: the checklist is recorded by the narrator without commentary. Interpretation is
spoken aloud, later, by the detective — and it is allowed to be wrong the first time.

## Image System

- **Fog.** Truth obscured but not absent. Fog is never symbolic in the text; it is the
  practical reason a watcher cannot see, and the reader supplies the rest.
- **Lamp and gaslight.** Partial knowledge; what is lit is known, what is not is coming.
- **The locked room.** A closed system that must yield to reasoning. Doyle's favourite
  shape: a space with one door and no exit.
- **The street as a map.** Addresses, cab routes, a walk from one square to another —
  geography as argument.
- **The disguise.** A legible surface that lies. The pleasure is in how well it is read
  and how badly it is trusted.
- **The advertisement.** Truth published in the open, in the one place nobody looks.
- **The double.** The respectable man and the criminal sharing a face; the twin; the
  returned colonial; the man who has been declared dead.
- **Fire.** Domestic safety in the grate; evidence destroyed in the same element.
- **The absence.** The thing that did not happen — the dog that did not bark, the bell
  that did not ring, the letter that was not answered.

## Value Stance

- **Method over virtue.** Intelligence is treated as a moral good, but a cold one. The
  detective is admired for accuracy, not for kindness, and his coldness is comic.
- **Loyalty without irony.** Watson's admiration is stated plainly and never undercut.
- **Pity rationed.** A victim gets one sentence. Grief is not dwelt on, and never
  performed by the narrator.
- **Crime explained, not excused.** Motive is always supplied; sympathy is not.
- **The criminal may be brilliant.** Intellect does not imply goodness, and the story
  takes a quiet pleasure in the criminal's competence.
- **The police are honest and slow.** Official machinery is respected and outpaced.
- **The client is protected.** Shame is handled gently; a woman's reputation is a real
  stake, and the narration does not leer.
- **No sermon.** The moral is left to the reader; the last word is usually a joke.

## Forbidden Zone

- Any interior access to Holmes's mind. He is observed, quoted and inferred — never
  narrated from inside.
- A love plot. Romance is reported in a clause or not at all; marriage is a fact in the
  backstory, never the engine.
- Explicit violence, sexual content, or clinical detail of a corpse.
- Editorialising on society, empire, class or race. The period's prejudices are in the
  source; they are not to be reproduced or amplified.
- Modern psychology, forensics, telephones, or any technology after 1902.
- Sentimentality about a victim, and any final paragraph that explains the lesson.
- Pastiche markers: `Elementary, my dear Watson` (never said in the canon stories),
  deerstalker hats, catchphrases. Use the manner, not the merchandise.

motif 词表：case room door face hand night eyes street friend window fire money letter lamp cab

## motif_stats

| motif | per 1,000 words |
| --- | --- |
| room | 1.62 |
| door | 1.37 |
| face | 1.22 |
| hand | 1.14 |
| night | 1.12 |
| case | 1.11 |
| eyes | 0.83 |
| street | 0.79 |
| friend | 0.75 |
| window | 0.68 |
| fire | 0.43 |
| money | 0.42 |
| letter | 0.28 |
| lamp | 0.27 |
| cab | 0.25 |