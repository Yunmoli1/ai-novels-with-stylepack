<div align="center">

# StylePack

**Open-source writing engine that gives any AI the style of a specific author.**

Quantified fingerprints · Self-contained style packs · Local workbench · Verifiable

[![CI](https://github.com/Yunmoli1/ai-novels-with-stylepack/actions/workflows/ci.yml/badge.svg)](https://github.com/Yunmoli1/ai-novels-with-stylepack/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-3776ab.svg)](https://www.python.org)
[![Engine: 0 deps](https://img.shields.io/badge/engine-0%20dependencies-green.svg)](README.md)

[Quick start](#quick-start) · [中文文档](README.md)

</div>

---

StylePack distills an author into a **self-contained style pack**: quantitative
fingerprints + generative guidance + annotated exemplar quotes. Load on demand,
verify after every chapter — "does it feel like the author" becomes a
**measurable metric**.

```
ingest corpus → fingerprint checkup → close reading → human review → publish
   → assemble → streaming generation → 4 advisory gates → deliver & account
   → memory registration → feedback loop
```

## Three seconds: packed vs. unpacked

Same model, same prompt — "write a winter market scene". Left is the model's
default style; right is the same model with a Lu Xun style pack pasted in
(real archived blind-test arms, excerpted; the style markers — final 罢,
大约/未必 hedging, circular repetition — live in the Chinese original):

> **Default style**: The winter market opens before dawn. A biting wind pours
> in from the street corner; vendors shrink their necks, hands tucked into
> sleeves... The deal finally closes, money changes hands, and everyone falls
> silent, melting back into the crowd.

> **With the Lu Xun pack**: The stalls line the street: vegetables, and beyond
> the vegetables, more vegetables... An old woman guards half a basket of eggs.
> Someone picks one up, holds it against the sky: "How much?" She raises three
> fingers and says nothing — as if speaking would crack the egg... The market
> will likely open again tomorrow; yet tomorrow the vegetables may be fresher,
> the people no livelier — truly, no livelier.

**Why not just tell the model "write like Lu Xun"?** One archived blind test
(prompt: "dusk") answered with numbers — Burrows Delta author distance,
lower = closer to Lu Xun:

| Lu Xun originals (in-corpus) | AI, told to imitate | AI with style pack | Zhu Ziqing (wrong-author control) |
|:---:|:---:|:---:|:---:|
| 0.87–1.04 | 1.69 | 1.54 | 2.36 |

The ordering is exactly right, and the pack pulled the model 0.16 closer —
but still **outside the true-corpus envelope**, and the tool tells you so
honestly. "Does it feel like the author" becomes a number, not a vibe:
which dimensions match and which fall short is itemized in every report.

## Local workbench

Full workflow without touching a terminal (Windows): double-click
`启动工作台.bat`, plug in your own API key, then distill new authors, write
chapters, and run blind tests. Listens on 127.0.0.1 only; keys never leave
your machine.

| Creation loop | Distillation |
|---|---|
| ![Create](docs/images/workbench-create.jpg) | ![Distill](docs/images/workbench-distill.jpg) |

What-you-see-is-what-gets-sent assembly preview → collaborative premise →
beat sheet → streaming generation → four gates (fingerprint / borrowed-lines /
AI-cliché / ending check) → revise-by-report / fragment rewrite → delivery
with automatic cost accounting. Six-step web distillation closes the loop for
"adding a new author"; blind-test win rate before publishing; draft packs
stay invisible to consumers until validated and published.

## Features

- **Verifiable** — sentence-length / dialogue-ratio / punctuation /
  reduplication metrics with tolerances + Burrows Delta author distance;
  borrowed-line check; AI-cliché detector; web blind-test win rates
- **Self-contained** — `export` a single-file pack, paste into any bare agent chat
- **Three front-ends, one engine** — local workbench · Agent Skills & MCP
  (12 skills + 10 memory tools) · CLI (every web button prints its CLI equivalent)
- **Long-form memory** — chapter digests / entity changes / foreshadowing with
  risk-graded quarantine merges; World-Info-style assembly (resident entries /
  recursive association / priority-trimmed budget)
- **Honest packs** — corpus provenance, sampling and confidence recorded;
  limits.md states which dimensions can't be imitated; per-chapter cost ledger
  includes real retry spend
- **Zero-dependency engine** — scripts/ and the MCP server use only the Python
  standard library (3.8+); web/ isolates fastapi/uvicorn/httpx/jinja2

## Quick start

**A. Local workbench (easiest)**

```bash
git clone https://github.com/Yunmoli1/ai-novels-with-stylepack.git
cd stylepack
# double-click 启动工作台.bat (auto-installs web deps, opens the browser)
# onboarding: API key → model → new project → first chapter
```

**B. Agent host (Claude Code / Codex-like)** — install the skills, follow
`style-setup`; see docs/adapters/.

**C. No host at all**

```bash
python scripts/export_pack.py stylepacks/luxun --out my.stylepack.md
# paste my.stylepack.md into any chat: "write a winter market scene in this style"
```

Public-domain sample packs included: **Lu Xun** (62 pieces, with tone registers)
and **Zhu Ziqing**. Full manual: [docs/usage.md](docs/usage.md) (Chinese).

## Principles

1. A plugin never changes the model — only the context it sees and the
   procedures it follows.
2. A pack is an operating manual, not a lab report — description
   (fingerprint) + generation (guidance) + demonstration (exemplars).
3. Models propose, scripts verify — verbatim quote checks, motif frequency
   validation, fingerprint comparison; generated claims are never trusted.
4. The repo ships no corpora — public-domain samples and short quotes only
   (≤200 chars); full texts never enter the repository.
5. Every paid action is previewed before it runs — costs are accounted
   per chapter, retries included.

## License

[Apache-2.0](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for pack
submissions and the copyright discipline.

中文文档：[README.md](README.md)
