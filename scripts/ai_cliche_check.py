# -*- coding: utf-8 -*-
"""ai_cliche_check：AI 腔检测（v0.13.16，创作环第四道 advisory 门；v0.13.17 加英文）。

用法：
    python scripts/ai_cliche_check.py <文本> [--pack <风格包目录>] [--lang auto|zh|en]

两层判定：
  词汇级 = scripts/ai_cliche_words.txt（三档：口头禅/句式模板/意象套话，可扩充）。
  结构级 = scripts/ai_cliche_patterns.txt（tier4「版面棘轮」：破折号/引号对/超短行，
           按 per1k、ratio、chain、count 四种量纲判定；可扩充，无需改代码）。
包级豁免：风格包 limits.md `## AI 腔豁免` 节逐行词——该作者本就常用的词免报。
  英文用同目录 *_en.txt：词表按词边界、大小写不敏感匹配，密度单位「次/千词」；
  结构级只留「省略号（…）」与「直引号残留」两条（中文的破折号棘轮到英文是反的，
  理由写在 ai_cliche_patterns_en.txt 头部）。

判定（advisory，不是门；退出码 0=通过 1=偏高 2=参数错）：
  词汇密度（中文次/千字、英文次/千词，三档合计，豁免扣除）按语言取阈值：
    中文 < 1.0 通过；1.0–2.0 提示；> 2.0 警告。
    英文 < 0.6 通过；0.6–1.2 提示；> 1.2 警告（英文表覆盖面窄，阈值单独标定，
    见 VOCAB_BY_LANG）。
  结构级每条规则各自 提示/警告 阈值，取最坏一条并入总判定。
  --lang auto（默认）：有 --pack 时读 pack.json 的 language；否则按文本判断
  （拉丁字母占多数→en，否则 zh）。
零第三方依赖；引擎层纪律同 fp_check（提案是模型的，数字是脚本的）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import splib  # noqa: E402

WORDS_PATH = Path(__file__).parent / "ai_cliche_words.txt"
PATTERNS_PATH = Path(__file__).parent / "ai_cliche_patterns.txt"
WORDS_PATH_EN = Path(__file__).parent / "ai_cliche_words_en.txt"
PATTERNS_PATH_EN = Path(__file__).parent / "ai_cliche_patterns_en.txt"
TIERS = ("tier1", "tier2", "tier3")
TIER_NAMES = {"tier1": "口头禅", "tier2": "句式模板", "tier3": "意象套话"}
KINDS = ("per1k", "ratio", "chain", "count")
UNITS = {"per1k": "次/千字", "ratio": "处/句", "chain": "行", "count": "次"}
UNITS_EN = {"per1k": "次/千词", "ratio": "处/句", "chain": "行", "count": "次"}
LEVEL_ORDER = {"ok": 0, "notice": 1, "warn": 2}
# (提示线, 警告线)：中文单位次/千字；英文次/千词（英文词表覆盖率低，单独标定）
VOCAB_BY_LANG = {"zh": (1.0, 2.0), "en": (0.6, 1.2)}
VOCAB_NOTICE = VOCAB_BY_LANG["zh"][0]   # 兼容旧引用
VOCAB_WARN = VOCAB_BY_LANG["zh"][1]


def pack_language(pack: Path | None) -> str:
    """读风格包 pack.json 的 language（缺省 zh，非法值回落 zh）。"""
    if not pack:
        return "zh"
    pj = Path(pack) / "pack.json"
    try:
        import json
        lang = str(json.loads(pj.read_text(encoding="utf-8")).get("language", "zh")).lower()
    except Exception:
        return "zh"
    return lang if lang in ("zh", "en") else "zh"


def detect_lang(text: str, pack: Path | None = None) -> str:
    """auto 判定：包语言优先（有 --pack），否则按拉丁字母占非空白字符的比例。"""
    if pack:
        return pack_language(pack)
    letters = len(re.findall(r"[A-Za-z]", text))
    others = len(re.sub(r"\s", "", text)) or 1
    return "en" if letters / others >= 0.5 else "zh"


def words_path_for(lang: str) -> Path:
    return WORDS_PATH_EN if lang == "en" else WORDS_PATH


def patterns_path_for(lang: str) -> Path:
    return PATTERNS_PATH_EN if lang == "en" else PATTERNS_PATH


def units_for(lang: str) -> dict[str, str]:
    return UNITS_EN if lang == "en" else UNITS


def count_hits(text: str, word: str, lang: str = "zh") -> int:
    """中文按子串计（与 v0.13.16 一致）；英文按词边界、大小写不敏感。"""
    if lang != "en":
        return text.count(word)
    pat = r"(?<![A-Za-z])" + re.escape(word.lower()) + r"(?![A-Za-z])"
    return len(re.findall(pat, text.lower()))


def load_words(extra_path: Path | None = None,
               lang: str = "zh") -> dict[str, list[str]]:
    """解析词表文件（## tierN 分节，每行一词，# 注释忽略）。"""
    words: dict[str, list[str]] = {t: [] for t in TIERS}
    for path in ([words_path_for(lang)] + ([extra_path] if extra_path else [])):
        if not path or not path.is_file():
            continue
        tier = None
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("## "):
                t = s[3:].strip().split()[0] if s[3:].strip() else ""
                tier = t if t in TIERS else None
            elif s and not s.startswith("#") and tier:
                words[tier].append(s)
    return words


def load_patterns(path: Path | None = None, lang: str = "zh") -> list[dict]:
    """解析结构级规则表（6 列 | 分隔，见 ai_cliche_patterns.txt 头部说明）。"""
    src = Path(path) if path else patterns_path_for(lang)
    rules: list[dict] = []
    if not src.is_file():
        return rules
    by_id: dict[str, dict] = {}
    for line in src.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cols = [c.strip() for c in s.split("|")]
        if len(cols) < 5:
            continue
        rid, kind, expr = cols[0], cols[1], cols[2]
        if not rid or kind not in KINDS or not expr:
            continue
        try:
            notice = float(cols[3]) if cols[3] else 1.0
            warn = float(cols[4]) if cols[4] else notice * 2
        except ValueError:
            continue
        if warn < notice:
            warn = notice
        if kind == "chain":
            try:
                expr = int(float(expr))
            except ValueError:
                continue
        else:
            try:
                re.compile(expr)
            except re.error:
                continue
        by_id[rid] = {"id": rid, "kind": kind, "expr": expr,
                      "notice": notice, "warn": warn,
                      "name": cols[5] if len(cols) > 5 and cols[5] else rid,
                      "note": cols[6] if len(cols) > 6 and cols[6] else ""}
    return list(by_id.values())


def load_pack_exemptions(pack: Path | None) -> set[str]:
    """limits.md 的 `## AI 腔豁免` 节：逐行词。"""
    if not pack:
        return set()
    limits = Path(pack) / "limits.md"
    if not limits.is_file():
        return set()
    out: set[str] = set()
    in_sec = False
    for line in limits.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_sec = "AI 腔豁免" in s
        elif in_sec and s.startswith(("-", "*", "·")):
            w = s.lstrip("-*· ").strip()
            if w:
                out.add(w)
    return out


def _longest_short_line_chain(text: str, limit: int) -> int:
    """最长连续「短行」链：空行不算断开，长度 ≤ limit 记为短行。"""
    best = cur = 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if splib._clen(s) <= limit:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


def check_structures(text: str, rules: list[dict], lang: str = "zh") -> list[dict]:
    """逐条结构级规则测量：返回 [{id, name, kind, value, hits, notice, warn, level}]。

    lang="en" 时 per1k 的分母用词数（与词表密度同量纲），中文仍用字符数。
    """
    if lang == "en":
        denom = len(splib._WORD_RE.findall(text)) or 1
    else:
        denom = splib._clen(text) or 1
    n_sent = max(1, len(splib.split_sentences(text)))
    out: list[dict] = []
    for r in rules:
        kind = r["kind"]
        if kind == "chain":
            hits = _longest_short_line_chain(text, r["expr"])
            value = float(hits)
        else:
            hits = len(re.findall(r["expr"], text))
            if kind == "per1k":
                value = round(hits / denom * 1000, 2)
            elif kind == "ratio":
                value = round(hits / n_sent, 3)
            else:
                value = float(hits)
        level = ("warn" if value >= r["warn"]
                 else "notice" if value >= r["notice"] else "ok")
        out.append({"id": r["id"], "name": r["name"], "kind": kind,
                    "value": value, "hits": int(hits), "note": r.get("note", ""),
                    "notice": r["notice"], "warn": r["warn"], "level": level})
    return out


def check(text: str, words: dict[str, list[str]],
          exempt: set[str], patterns: list[dict] | None = None,
          lang: str = "zh") -> dict:
    """返回 {density, per_tier, hits, structure, verdict, chars, words, unit}。

    patterns=None 时只做词汇级（保持 v0.9.1 的调用方式可用）；
    传入规则表时总判定 = 词汇级与结构级中较坏者。
    lang="en"：按词边界计数、分母用词数、阈值取 VOCAB_BY_LANG["en"]、豁免大小写不敏感。
    """
    total_chars = splib._clen(text) or 1
    n_words = len(splib._WORD_RE.findall(text)) or 1
    denom = n_words if lang == "en" else total_chars
    exempt_norm = {e.lower() for e in exempt} if lang == "en" else exempt
    per_tier: dict[str, dict[str, int]] = {}
    hits = 0
    for tier in TIERS:
        per_tier[tier] = {}
        for w in words.get(tier, []):
            key = w.lower() if lang == "en" else w
            if key in exempt_norm:
                continue
            n = count_hits(text, w, lang)
            if n:
                per_tier[tier][w] = n
                hits += n
    density = round(hits / denom * 1000, 2)
    notice, warn = VOCAB_BY_LANG.get(lang, VOCAB_BY_LANG["zh"])
    verdict = ("ok" if density < notice
               else "warn" if density > warn else "notice")
    structure = check_structures(text, patterns or [], lang)
    for item in structure:
        if LEVEL_ORDER[item["level"]] > LEVEL_ORDER[verdict]:
            verdict = item["level"]
    return {"density": density, "per_tier": per_tier, "hits": hits,
            "structure": structure, "verdict": verdict, "chars": total_chars,
            "words": n_words, "lang": lang,
            "unit": "次/千词" if lang == "en" else "次/千字",
            "notice": notice, "warn": warn}


def main() -> int:
    splib.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="AI 腔检测（advisory）")
    ap.add_argument("input", help="待检文本（.txt/.md）")
    ap.add_argument("--pack", default=None, help="风格包目录（读 limits.md 豁免节）")
    ap.add_argument("--lang", default="auto", choices=("auto", "zh", "en"),
                    help="语言（auto=有 --pack 读 pack.json，否则按文本判断）")
    ap.add_argument("--patterns", default=None,
                    help="结构级规则表（默认按语言选 scripts/ai_cliche_patterns*.txt）")
    args = ap.parse_args()
    src = Path(args.input)
    if not src.is_file():
        print(f"错误：文件不存在：{src}", file=sys.stderr)
        return 2
    text, _ = splib.read_text(src)
    if not text.strip():
        print("错误：文本为空", file=sys.stderr)
        return 2
    pack_dir = Path(args.pack) if args.pack else None
    lang = (args.lang if args.lang != "auto" else detect_lang(text, pack_dir))
    words = load_words(lang=lang)
    exempt = load_pack_exemptions(pack_dir)
    patterns = load_patterns(Path(args.patterns) if args.patterns else None, lang)
    r = check(text, words, exempt, patterns, lang)
    mark = {"ok": "✅", "notice": "⚠️", "warn": "❌"}[r["verdict"]]
    s_levels = [i["level"] for i in r["structure"]]
    s_verdict = max(s_levels, key=lambda x: LEVEL_ORDER[x]) if s_levels else "ok"
    s_mark = {"ok": "✅", "notice": "⚠️", "warn": "❌"}[s_verdict]
    size = (f"{r['words']} 词" if lang == "en" else f"{r['chars']} 字")
    print(f"AI 腔检测（{lang}）：{mark} 词汇密度 {r['density']} {r['unit']}"
          f"（命中 {r['hits']} 处/{size}；阈值 通过<{r['notice']} / "
          f"提示≤{r['warn']} / 警告>{r['warn']}）｜结构级 {s_mark}")
    if exempt:
        print(f"包级豁免：{len(exempt)} 词（limits.md·AI 腔豁免）")
    for tier in TIERS:
        if r["per_tier"][tier]:
            detail = "、".join(f"{w}×{n}" for w, n in
                               sorted(r["per_tier"][tier].items(),
                                      key=lambda kv: -kv[1]))
            print(f"  [{TIER_NAMES[tier]}] {detail}")
    units = units_for(lang)
    for item in r["structure"]:
        unit = units[item["kind"]]
        print(f"  [{item['name']}] {item['value']} {unit}"
              f"（提示≥{item['notice']:g} / 警告≥{item['warn']:g}）")
    return 0 if r["verdict"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
