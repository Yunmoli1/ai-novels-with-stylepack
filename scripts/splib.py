# -*- coding: utf-8 -*-
"""StylePack 共享库：编码探测、文本切分、风格指标计算、指纹比对。

仅依赖 Python 标准库。所有函数输入/输出均为 str（UTF-8）。
被 fp_extract / fp_check / ingest / validate_pack / export_pack 共用。
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------- 常量

PACK_FILES = [
    "pack.json",
    "card.md",
    "profile.md",
    "fingerprint.json",
    "exemplars.md",
    "lexicon.md",
    "limits.md",
]

PROFILE_SECTIONS = [
    "三百字精华",
    "叙事视角与人称",
    "句式与节奏",
    "词汇与用典",
    "对话风格",
    "场景与结构",
    "情感与氛围",
    "生成指导",
    "禁用清单",
]

# v0.13.17：英文包用英文节名（同一结构，语言随包）。校验两种都认——
# 结构是契约，节名只是标签，故不做互译，也不强求中文节名。
PROFILE_SECTIONS_EN = [
    "300-Word Essence",
    "Narrative POV and Person",
    "Sentence Rhythm",
    "Diction and Allusion",
    "Dialogue",
    "Scene and Structure",
    "Emotion and Atmosphere",
    "Generation Guidance",
    "Ban List",
]

# v0.3 思想层：thought.md（可选包文件）。六节为模型蒸馏内容；
# motif_stats 节由 motif_count.py 脚本产出（advisory，永不进判定）。
THOUGHT_SECTIONS = [
    "选题地平线",
    "立意动作",
    "观察清单",
    "意象系统",
    "价值姿态",
    "禁区",
]

THOUGHT_SECTIONS_EN = [
    "Subject Horizon",
    "Stance Actions",
    "Observation Checklist",
    "Image System",
    "Value Stance",
    "Forbidden Zone",
]
MOTIF_STATS_SECTION = "motif_stats"
MOTIF_LIST_RE = re.compile(r"^motif 词表[:：]\s*(.+?)\s*$", re.M)


def parse_motif_list(thought_text: str) -> list[str]:
    """从 thought.md 的「motif 词表：」行解析词项（、/，/, 分隔）。"""
    m = MOTIF_LIST_RE.search(thought_text)
    if not m:
        return []
    return [w.strip() for w in re.split(r"[、，,\s]+", m.group(1)) if w.strip()]


def parse_motif_stats(thought_text: str) -> dict[str, float]:
    """解析 thought.md motif_stats 节的 | motif | 次/千字 | 表。"""
    m = re.search(rf"^##\s+{MOTIF_STATS_SECTION}\s*$", thought_text, flags=re.M)
    if not m:
        return {}
    stats: dict[str, float] = {}
    body = re.split(r"^##\s+", thought_text[m.end():], flags=re.M)[0]
    for name, rate in re.findall(r"^\|\s*([^|\s]+)\s*\|\s*([\d.]+)\s*\|$", body, flags=re.M):
        stats[name] = float(rate)
    return stats


def count_motifs(text: str, motifs: list[str], lang: str = "zh") -> dict[str, float]:
    """各 motif 在文本中的频率（advisory 用途，任何基于它的判定都属古德哈特面，
    故此函数只服务参考输出）。

    - 中文（默认）：次/千字，纯子串计数（与中文包的千字口径一致）。
    - 英文：次/千词，词边界匹配——中文按「字」计量，英文的对应单位是「词」
      （与 fingerprint 的 punctuation_per_1k 等英文指标同量纲）；子串计数会把
      hand 算进 hands / handsome，故英文走 \\b 边界。
    """
    if not text:
        return {w: 0.0 for w in motifs}
    if lang == "en":
        words = len(_WORD_RE.findall(text))
        if not words:
            return {w: 0.0 for w in motifs}
        lowered = text.lower()
        out: dict[str, float] = {}
        for w in motifs:
            pat = rf"(?<![a-z]){re.escape(w.lower())}(?![a-z])"
            out[w] = round(len(re.findall(pat, lowered)) / words * 1000, 3)
        return out
    return {w: round(text.count(w) / len(text) * 1000, 3) for w in motifs}

CJK = r"\u4e00-\u9fff"
CJK_RE = re.compile(rf"[{CJK}]")

PUNCT_KEYS = ["，", "。", "？", "！", "；", "：", "、", "…", "—", "“", "”", "《", "》", "（", "）"]

DIALOGUE_STARTERS = "“\"「‘‘"

SENT_END = "。！？!?…"
_SENT_RE = re.compile(rf"[^{SENT_END}\n]*[{SENT_END}]+|[^{SENT_END}\n]+$")
_REDO_RE = re.compile(rf"([{CJK}])\1")
_FOURGRAM_RE = re.compile(rf"[{CJK}]{{4}}")

# ---------------------------------------------------------------- 语言层（v0.13.17）
# 语言是包的属性：中文单位=非空白字符，英文单位=词。指标名保持不变，
# 由 metrics["unit"] 标明量纲；英文指标不带 top_chars/fourgram（置空）。
LANG_ZH = "zh"
LANG_EN = "en"
LANG_SUPPORTED = (LANG_ZH, LANG_EN)
CJK_LANG_BOUNDARY = 0.15   # 非空白字符中 CJK 占比 ≥ 此值 → 判中文

_WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?")
_EN_ABBR_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|St|Jr|Sr|Prof|Capt|Col|Gen|Rev|Hon|Lt|Sgt|Cmdr|etc|e\.g|i\.e|vs|No)\.",
    re.IGNORECASE,
)
_EN_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])[\"'\u201d\u2019]?\s+(?=[\"'\u201c\u2018]?[A-Z0-9\u2014])")
EN_PUNCT_KEYS = [",", ".", ";", ":", "!", "?", "\u2014", "\u2013", "\u2026",
                 "(", ")", "\u201c", "\u201d"]
EN_DIALOGUE_STARTERS = "\u201c\"'\u2018"
EN_DELTA_MIN_WORDS = 400     # 英文短文：低于 400 词 Delta 不进判定
EN_DELTA_STABLE_WORDS = 600  # 400–600 词进判定但标「置信中」

# 常见网文广告 / 站点水印行（ingest 清洗用；按行匹配，命中即丢弃）
AD_PATTERNS = [
    re.compile(p)
    for p in [
        r"^\s*(本章未完|未完待续|作者的话|PS[:：]|ps[:：])",
        r"^\s*(最新章节|本书来自|首发于|请记住本书|最快更新|正版首发)",
        r"^\s*(求收藏|求推荐|求月票|求订阅|求鲜花|求打赏)",
        r"(https?://|www\.)",
        r"(笔趣阁|顶点小说|看书网|书友群|无弹窗|手机阅读|天才一秒|一秒记住)",
        r"^\s*[-=_*·——]{3,}\s*$",
    ]
]

CHAPTER_RE = re.compile(
    r"^\s*(?!"
    r".*[。”]\s*$"          # 以引号/句号收尾的是正文回顾句，不是章节标题
    r")(?:"
    r"第\s*[0-9〇零一二三四五六七八九十百千万两]+\s*[章回节卷部篇][^\n]{0,40}"
    r"|Chapter\s+\d+[^\n]{0,60}"
    r"|(?:序章|楔子|引子|尾声|后记|终章|番外)[^\n]{0,30}"
    r")\s*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------- 编码与读取


def detect_and_decode(data: bytes) -> tuple[str, str]:
    """探测编码并解码。返回 (text, encoding_name)。顺序：BOM > UTF-8 > GB18030 > Big5。"""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8(replace)"


def read_text(path: str | Path) -> tuple[str, str]:
    data = Path(path).read_bytes()
    return detect_and_decode(data)


def detect_lang(text: str) -> str:
    """按非空白字符中 CJK 占比判语言（护栏用，不做语种识别）。

    中文正文 CJK 占比通常 >0.6，英文正文 <0.02（题名/人名夹少量汉字也不越界）；
    边界 0.15 是两者之间的宽安全区。空文本按 zh（与历史行为一致）。
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return LANG_ZH
    cjk = sum(1 for c in chars if CJK_RE.match(c))
    return LANG_ZH if cjk / len(chars) >= CJK_LANG_BOUNDARY else LANG_EN


def normalize_lang(lang: str | None, text: str = "") -> str:
    """把 lang 归一成 zh / en；None、auto、空 → 用 text 判定。"""
    if not lang or lang == "auto":
        return detect_lang(text)
    low = str(lang).strip().lower().replace("_", "-")
    base = low.split("-")[0]
    return base if base in LANG_SUPPORTED else LANG_ZH


# ---------------------------------------------------------------- 切分


def split_paragraphs(text: str) -> list[str]:
    """非空行即段落（中文 txt 的普遍约定）。"""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in split_paragraphs(text):
        for m in _SENT_RE.finditer(para):
            s = m.group(0).strip()
            if s:
                out.append(s)
    return out


def _clen(s: str) -> int:
    return sum(1 for c in s if not c.isspace())


def split_sentences_en(text: str) -> list[str]:
    """英文断句：按段落切，缩写点先占位，再按句末标点 + 大写开头切。"""
    out: list[str] = []
    for para in split_paragraphs(text):
        t = _EN_ABBR_RE.sub(lambda m: m.group(0)[:-1] + "\x00", para)
        t = re.sub(r"\s+", " ", t).strip()
        for part in _EN_SENT_SPLIT_RE.split(t):
            s = part.replace("\x00", ".").strip()
            if s and _WORD_RE.search(s):
                out.append(s)
    return out


def words_of(text: str) -> list[str]:
    """英文词序列（含撇号/右单引号内的缩写，如 don't / don’t）。"""
    return _WORD_RE.findall(text)


def _wlen(s: str) -> int:
    return len(_WORD_RE.findall(s))


def word_rates(text: str, words: list[str]) -> dict[str, float]:
    """各词在文本中的频率（次/千词），供英文 Burrows Delta 使用。"""
    toks = [w.lower() for w in _WORD_RE.findall(text)]
    if not toks:
        return {w: 0.0 for w in words}
    cnt = Counter(toks)
    return {w: cnt.get(w, 0) / len(toks) * 1000 for w in words}


def _percentile(sorted_vals: list[int | float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return float(sorted_vals[idx])


def is_dialogue_para(para: str) -> bool:
    return bool(para) and para[0] in DIALOGUE_STARTERS


_QUOTE_PAIRS = re.compile(r"[“\"]([^”\"]*)[”\"]|「([^」]*)」")


def quote_chars_len(text: str) -> int:
    total = 0
    for m in _QUOTE_PAIRS.finditer(text):
        total += len(m.group(1) or m.group(2) or "")
    return total


_EN_QUOTE_RE = re.compile(r'"([^"\n]*)"|“([^”\n]*)”')


def quote_chars_len_en(text: str) -> int:
    """英文引号内字符数：逐段配对双引号（直/弯），跨行不配对。

    中文用的 _QUOTE_PAIRS 允许跨行，英文里一处未闭合就会把整章吞成一段
    （实测可虚高到 0.9），故按段落分别配对，只计成对区间。
    """
    total = 0
    for para in text.splitlines():
        for m in _EN_QUOTE_RE.finditer(para):
            total += len(m.group(1) or m.group(2) or "")
    return total


# ---------------------------------------------------------------- 指标


def _metrics_zh(text: str) -> dict:
    """中文指标（v0.13.17 前的 compute_metrics 原实现，逐字节不变）。"""
    paras = split_paragraphs(text)
    sents = split_sentences(text)
    sent_lens = sorted(_clen(s) for s in sents)
    para_lens = sorted(_clen(p) for p in paras)
    chars_total = _clen(text)

    def per_1k(n: int) -> float:
        return round(n / chars_total * 1000, 3) if chars_total else 0.0

    punct_counter = Counter(c for c in text if c in PUNCT_KEYS)
    cjk_chars = CJK_RE.findall(text)
    top_chars = [
        {"char": ch, "per_1k": per_1k(n)}
        for ch, n in Counter(cjk_chars).most_common(30)
    ]

    grams = Counter(g for g in _FOURGRAM_RE.findall(text) if grams_ok(g))
    fourgram_top = [g for g, n in grams.most_common(40) if n >= 2][:20]

    dialogue_paras = sum(1 for p in paras if is_dialogue_para(p))

    return {
        "chars_total": chars_total,
        "sentence_length": {
            "count": len(sents),
            "mean": round(sum(sent_lens) / len(sent_lens), 2) if sent_lens else 0.0,
            "p25": round(_percentile(sent_lens, 0.25), 1),
            "p50": round(_percentile(sent_lens, 0.50), 1),
            "p75": round(_percentile(sent_lens, 0.75), 1),
        },
        "paragraph": {
            "count": len(paras),
            "p50_len": round(_percentile(para_lens, 0.50), 1),
            "dialogue_para_ratio": round(dialogue_paras / len(paras), 3) if paras else 0.0,
        },
        "quote_char_ratio": round(quote_chars_len(text) / chars_total, 3) if chars_total else 0.0,
        "punctuation_per_1k": {ch: per_1k(n) for ch, n in sorted(punct_counter.items())},
        "reduplication_per_1k": per_1k(len(_REDO_RE.findall(text))),
        "top_chars": top_chars,
        "fourgram_top": fourgram_top,
    }


def _metrics_en(text: str) -> dict:
    """英文指标：单位=词（sentence_length / paragraph.p50_len / punctuation_per_1k）。

    与中文同构（键名一致，供 compare_metrics/阈值树复用），差异：
    - 句长、段长按词计；顶层 unit="word"、words_total 为词数
    - punctuation_per_1k 用 ASCII/排版标点；top_chars/fourgram_top 置空，
      改出 top_words / bigram_top（英文的「字频」对应物）
    - reduplication 不适用，恒 0.0（不进英文阈值树）
    """
    paras = split_paragraphs(text)
    sents = split_sentences_en(text)
    sent_lens = sorted(_wlen(s) for s in sents)
    para_lens = sorted(_wlen(p) for p in paras)
    chars_total = _clen(text)
    words = words_of(text)
    n_words = len(words)

    def per_1k(n: int) -> float:
        return round(n / n_words * 1000, 3) if n_words else 0.0

    punct_counter = Counter(c for c in text if c in EN_PUNCT_KEYS)
    low = [w.lower() for w in words]
    top_words = [{"word": w, "per_1k": per_1k(n)}
                 for w, n in Counter(low).most_common(30)]
    bigrams = Counter(zip(low, low[1:]))
    bigram_top = [f"{a} {b}" for (a, b), n in bigrams.most_common(40) if n >= 2][:20]
    dialogue_paras = sum(1 for p in paras if p and p[0] in EN_DIALOGUE_STARTERS)

    return {
        "chars_total": chars_total,
        "words_total": n_words,
        "unit": "word",
        "sentence_length": {
            "count": len(sents),
            "mean": round(sum(sent_lens) / len(sent_lens), 2) if sent_lens else 0.0,
            "p25": round(_percentile(sent_lens, 0.25), 1),
            "p50": round(_percentile(sent_lens, 0.50), 1),
            "p75": round(_percentile(sent_lens, 0.75), 1),
        },
        "paragraph": {
            "count": len(paras),
            "p50_len": round(_percentile(para_lens, 0.50), 1),
            "dialogue_para_ratio": round(dialogue_paras / len(paras), 3) if paras else 0.0,
        },
        "quote_char_ratio": round(quote_chars_len_en(text) / chars_total, 3) if chars_total else 0.0,
        "punctuation_per_1k": {ch: per_1k(n) for ch, n in sorted(punct_counter.items())},
        "reduplication_per_1k": 0.0,
        "top_chars": [],
        "fourgram_top": [],
        "top_words": top_words,
        "bigram_top": bigram_top,
    }


def compute_metrics(text: str, lang: str | None = LANG_ZH) -> dict:
    """计算风格指纹原始指标（嵌套结构，与 fingerprint.json 的 metrics 对齐）。

    lang 默认 zh（历史行为逐字节不变）；"auto" 按 CJK 占比判定。
    英文返回同构指标，unit="word"。
    """
    if normalize_lang(lang, text) == LANG_EN:
        return _metrics_en(text)
    return _metrics_zh(text)


def grams_ok(g: str) -> bool:
    return True  # 占位：四字格已由正则保证全 CJK


# ---------------------------------------------------------------- 指纹比对


def iter_target_leaves(node, path=()):
    """深度优先遍历 metrics 树，产出 (path_tuple, leaf)；叶 = 含 target 的 dict。"""
    if isinstance(node, dict):
        if "target" in node:
            yield path, node
        else:
            for k, v in node.items():
                yield from iter_target_leaves(v, path + (k,))


def get_path(metrics: dict, path) -> "float | None":
    node = metrics
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node if isinstance(node, (int, float)) else None


def compare_metrics(actual: dict, fingerprint: dict) -> list[dict]:
    """逐叶比对，返回行列表。叶字段：target + tolerance_abs 或 tolerance_rel。"""
    rows = []
    for path, leaf in iter_target_leaves(fingerprint.get("metrics", {})):
        target = leaf["target"]
        act = get_path(actual, path)
        if act is None:
            rows.append({"path": ".".join(path), "target": target, "actual": None,
                         "tolerance": None, "diff": None, "ok": False, "note": "指标缺失"})
            continue
        if "tolerance_abs" in leaf:
            tol = leaf["tolerance_abs"]
            ok = abs(act - target) <= tol
        elif "tolerance_rel" in leaf:
            rel = leaf["tolerance_rel"]
            if target == 0:
                ok = act == 0
                tol = 0.0
            else:
                tol = abs(target) * rel
                ok = abs(act - target) <= tol
        else:
            ok, tol = True, None
        rows.append({"path": ".".join(path), "target": target, "actual": act,
                     "tolerance": tol, "diff": round(act - target, 3), "ok": bool(ok),
                     "note": ""})
    return rows


def all_ok(rows: list[dict]) -> bool:
    return bool(rows) and all(r["ok"] for r in rows)


def baseline_diff(rows: list[dict], baseline: dict) -> list[dict]:
    """本次 vs 基线实测指标的逐项对比（基线为某次 --save-metrics 的输出）。

    回归 = 该指标基线在容差内、本次超出容差（revise 模式的回滚依据）。
    """
    out = []
    for r in rows:
        if r["actual"] is None:
            continue
        base = get_path(baseline, tuple(r["path"].split(".")))
        if not isinstance(base, (int, float)):
            continue
        tol = r["tolerance"]
        base_ok = (abs(base - r["target"]) <= tol) if tol is not None else True
        out.append({
            "path": r["path"],
            "baseline": base,
            "actual": r["actual"],
            "delta": round(r["actual"] - base, 3),
            "regression": bool(base_ok and not r["ok"]),
        })
    return out


# ---------------------------------------------------------------- 语料清洗


def strip_ads(text: str) -> tuple[str, int]:
    """按行丢弃广告/水印行。返回 (clean_text, removed_count)。"""
    kept, removed = [], 0
    for line in text.splitlines():
        if any(p.search(line) for p in AD_PATTERNS):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed


_FENCE_RE = re.compile(r"^\s*```")
_SIG_RE = re.compile(r"^\s*[·•]\s*.{1,12}\s*[·•]\s*$")


def unwrap_text(text: str) -> tuple[str, int]:
    """合并硬换行排版（旧电子版常见）：空行分段的块内各行直接拼接；
    剔除代码围栏行与「·作者·」居中署名行。返回 (text, dropped_lines)。"""
    blocks: list[str] = []
    cur: list[str] = []
    dropped = 0
    for line in text.splitlines():
        s = line.strip().strip("\u3000").strip()
        if _FENCE_RE.match(s) or _SIG_RE.match(s):
            dropped += 1
            continue
        if s:
            cur.append(s)
        elif cur:
            blocks.append("".join(cur))
            cur = []
    if cur:
        blocks.append("".join(cur))
    return "\n\n".join(blocks), dropped


def split_chapters(text: str) -> list[tuple[str, str]]:
    """按章节标题切分；无标题则整体作为单一章节。返回 [(title, body)]。"""
    chapters: list[tuple[str | None, list[str]]] = []
    cur_title: str | None = None
    cur: list[str] = []

    def flush():
        body = "\n".join(cur).strip()
        if cur_title is not None or body:
            chapters.append((cur_title, cur.copy()))

    for line in text.splitlines():
        m = CHAPTER_RE.match(line)
        if m:
            flush()
            cur_title, cur = m.group(0).strip(), []
        else:
            cur.append(line)
    flush()

    result = []
    for i, (title, lines) in enumerate(chapters, 1):
        body = "\n".join(lines).strip()
        if not body and not title:
            continue
        if title is None:
            first = next((l.strip() for l in lines if l.strip()), "")
            title = first if 0 < len(first) <= 30 else f"第{i}部分"
            body = "\n".join(l for l in lines if l.strip() != first).strip()
        result.append((title, body))
    return result


# ---------------------------------------------------------------- Burrows Delta

def char_rates(text: str, chars: list[str]) -> dict[str, float]:
    """给定字符集合在 text 中的频率（次/千字）。空文本返回全 0（不除零）。"""
    total = _clen(text)
    want = set(chars)
    if not total:
        return {c: 0.0 for c in chars}
    cnt = Counter(c for c in text if c in want)
    return {c: (cnt.get(c, 0) / total * 1000) for c in chars}


def build_delta_profile(samples: list[str], top_n: int = 150,
                        lang: str | None = LANG_ZH) -> dict:
    """Burrows Delta 作者档案：最高频词的 (均值, 标准差) 表。

    中文按 CJK 字（键 "chars"，与原档案逐字节兼容）；英文按词（键 "words"，
    单位 次/千词）。samples = 语料中的各作品/章节文本；至少 2 个样本标准差
    才有意义，单样本时 std 置 1e-4（距离退化为均值偏差）。
    """
    use_lang = normalize_lang(lang, "\n\n".join(samples))
    if use_lang == LANG_EN:
        agg_w: Counter = Counter()
        for s in samples:
            agg_w.update(w.lower() for w in words_of(s))
        keys = [w for w, _ in agg_w.most_common(top_n)]
        rates = [word_rates(s, keys) for s in samples]
        prof: dict[str, list[float]] = {}
        for c in keys:
            vals = [r[c] for r in rates]
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals) if len(vals) > 1 else 0.0
            std = round(var ** 0.5, 4)
            prof[c] = [round(mean, 4), std if std > 0 else 1e-4]
        return {"words": prof, "n_samples": len(samples), "top_n": len(keys),
                "unit": "word"}

    agg: Counter = Counter()
    for s in samples:
        agg.update(c for c in s if CJK_RE.match(c))
    chars = [c for c, _ in agg.most_common(top_n)]
    rates_c = [char_rates(s, chars) for s in samples]
    prof_c: dict[str, list[float]] = {}
    for c in chars:
        vals = [r[c] for r in rates_c]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals) if len(vals) > 1 else 0.0
        std = round(var ** 0.5, 4)
        prof_c[c] = [round(mean, 4), std if std > 0 else 1e-4]  # 仅防除零，不改既有数值
    return {"chars": prof_c, "n_samples": len(samples), "top_n": len(chars)}


def delta_distance(text: str, profile: dict, lang: str | None = None) -> float:
    """候选文本对作者档案的 Burrows Delta 距离（各 z-score 绝对值均值，越小越像）。

    档案含 "words" 键 → 英文词级；否则按中文 CJK 字级（历史行为不变）。
    """
    if "words" in profile:
        keys = list(profile["words"].keys())
        if not keys:
            return 999.0
        rates = word_rates(text, keys)
        diffs = [abs((rates[c] - mean) / std)
                 for c, (mean, std) in profile["words"].items()]
        return round(sum(diffs) / len(diffs), 3) if diffs else 999.0
    chars = list(profile.get("chars", {}).keys())
    if not chars:
        return 999.0
    rates_c = char_rates(text, chars)
    diffs = []
    for c, (mean, std) in profile["chars"].items():
        diffs.append(abs((rates_c[c] - mean) / std))
    return round(sum(diffs) / len(diffs), 3) if diffs else 999.0


# ---------------------------------------------------------------- 文体分层

GENRE_DIALOGUE_BOUNDARY = 0.15   # 段首引号段占比 ≥ 此值 → narrative 信号
GENRE_QUOTE_BOUNDARY = 0.12      # 引号字占比 ≥ 此值 → narrative 信号（对话嵌入叙述段的小说靠它识别）
GENRE_CONFIDENCE_MARGIN = 0.10   # 判定信号距边界不足此值 → 置信度 medium
DELTA_MIN_CHARS = 800            # 低于此字数 Delta 不进判定（短文统计噪声）
DELTA_STABLE_CHARS = 1200        # 低于此字数 Delta 标"置信中"


def detect_genre(text: str, lang: str | None = None) -> dict:
    """文体检测：双信号启发式——段首引号段占比、引号字占比，任一越界即 narrative。

    实测（luxun+zhuziqing 语料）：小说 引号字占比 19.7–28.4%，散文 0–2.1%，
    边界 0.12 居间；《背影》（含对话的散文）8.1% 落在模糊带，由置信度如实表达。
    lang 决定引号统计方式与段首对话起始符（英文逐段配对双引号；默认按文本判定）。
    返回 {genre, dialogue_para_ratio, quote_char_ratio, confidence}。
    """
    use_lang = normalize_lang(lang, text)
    starters = EN_DIALOGUE_STARTERS if use_lang == LANG_EN else DIALOGUE_STARTERS
    paras = split_paragraphs(text)
    dr = (round(sum(1 for p in paras if p and p[0] in starters) / len(paras), 3)
          if paras else 0.0)
    total = _clen(text)
    qchars = quote_chars_len_en(text) if use_lang == LANG_EN else quote_chars_len(text)
    qr = round(qchars / total, 3) if total else 0.0
    d_dist = abs(dr - GENRE_DIALOGUE_BOUNDARY)
    q_dist = abs(qr - GENRE_QUOTE_BOUNDARY)
    if dr >= GENRE_DIALOGUE_BOUNDARY or qr >= GENRE_QUOTE_BOUNDARY:
        genre = "narrative"
        if dr >= GENRE_DIALOGUE_BOUNDARY and qr >= GENRE_QUOTE_BOUNDARY:
            dist = max(d_dist, q_dist)   # 双信号同向 → 取较强者
        else:
            dist = d_dist if dr >= GENRE_DIALOGUE_BOUNDARY else q_dist
    else:
        genre = "essay"
        dist = min(d_dist, q_dist)       # 双信号均未越界 → 离边界最近的那个做主
    conf = "high" if dist >= GENRE_CONFIDENCE_MARGIN else "medium"
    # 连续值一并给出：报告可展示距边界的 margin，软化决策留给后续调参
    return {"genre": genre, "dialogue_para_ratio": dr, "quote_char_ratio": qr,
            "confidence": conf, "boundary_margin": round(dist, 3)}


def derive_thresholds(samples: list[str], lang: str | None = LANG_ZH) -> dict:
    """从层内各篇实测推导阈值树：target = 层内合并文本的指标值，
    tolerance_abs = 1.2 × 层内各篇对该值的最大偏离（下限按指标类别）。

    固定比例容差会被罕见指标的跨篇波动击穿（真迹挂自己层线），
    故容差必须来自数据：线 = 真迹观测包络再放宽 20%。层内各篇都没出现的
    稀疏标点不入树（合并占比 < 0.5/千字），避免「指标缺失」误杀。

    lang 决定量纲与标点白名单：中文（默认，历史行为不变）/ 英文（单位=词，
    标点为 ASCII 常用集，reduplication 不进树——英文无叠字指标）。
    """
    use_lang = normalize_lang(lang, "\n\n".join(samples))
    pooled = compute_metrics("\n\n".join(samples), use_lang)
    per_work = [compute_metrics(s, use_lang) for s in samples]
    if use_lang == LANG_EN:
        tree = {
            "sentence_length": {k: {"target": pooled["sentence_length"][k]}
                                for k in ("p25", "p50", "p75")},
            "paragraph": {
                "p50_len": {"target": pooled["paragraph"]["p50_len"]},
                "dialogue_para_ratio": {"target": pooled["paragraph"]["dialogue_para_ratio"]},
            },
            "quote_char_ratio": {"target": pooled["quote_char_ratio"]},
            "punctuation_per_1k": {ch: {"target": v}
                                   for ch, v in pooled["punctuation_per_1k"].items()
                                   if ch in (",", ".", ";", ":", "!", "?", "\u2014", "\u2026")
                                   and v >= 0.5},
        }
        floors = {"sentence_length": 1.5, "p50_len": 2.0, "dialogue_para_ratio": 0.03,
                  "quote_char_ratio": 0.03, "punctuation_per_1k": 0.3}
    else:
        tree = {
            "sentence_length": {k: {"target": pooled["sentence_length"][k]}
                                for k in ("p25", "p50", "p75")},
            "paragraph": {
                "p50_len": {"target": pooled["paragraph"]["p50_len"]},
                "dialogue_para_ratio": {"target": pooled["paragraph"]["dialogue_para_ratio"]},
            },
            "quote_char_ratio": {"target": pooled["quote_char_ratio"]},
            "punctuation_per_1k": {ch: {"target": v}
                                   for ch, v in pooled["punctuation_per_1k"].items()
                                   if ch in ("…", "—", "？", "！", "；") and v >= 0.5},
            "reduplication_per_1k": {"target": pooled["reduplication_per_1k"]},
        }
        floors = {"sentence_length": 2.0, "p50_len": 2.0, "dialogue_para_ratio": 0.03,
                  "quote_char_ratio": 0.03, "punctuation_per_1k": 0.3,
                  "reduplication_per_1k": 0.5}
    for path, leaf in iter_target_leaves(tree):
        vals = [get_path(pm, path) for pm in per_work]
        # 频率语义下「没写」= 0（键缺失 ≠ 指标缺失），散布必须把 0 计入
        devs = [abs((0.0 if v is None else v) - leaf["target"]) for v in vals]
        dev = max(devs) if devs else 0.0
        floor = floors[path[-1] if path[0] == "paragraph" else path[0]]
        leaf["tolerance_abs"] = max(floor, round(1.2 * dev, 3))
    return tree


def fill_missing_rates(metrics: dict, tree: dict) -> dict:
    """阈值树涉及的频率/占比路径若实测缺失（字符零出现、段落无对话），补 0.0。

    「没写」在频率语义下就是 0，不该按「指标缺失」判死；只在树内路径上补，
    不引入树外噪声键。
    """
    for path, _leaf in iter_target_leaves(tree):
        if get_path(metrics, path) is None:
            node = metrics
            for k in path[:-1]:
                node = node.setdefault(k, {})
            node[path[-1]] = 0.0
    return metrics


def build_genre_layers(named_texts: list[tuple[str, str]], top_n: int = 150,
                       lang: str | None = LANG_ZH) -> dict:
    """按文体分层构建层档案（阈值树 + Delta 档案）。

    named_texts = [(作品名, 文本)]；返回 {"genres": {...}, "assignment": {...}}。
    lang 决定指标量纲（默认 zh，历史行为不变）。
    """
    use_lang = normalize_lang(lang, "\n\n".join(t for _, t in named_texts))
    strata: dict[str, list[tuple[str, str]]] = {}
    assignment: dict[str, dict] = {}
    for name, text in named_texts:
        det = detect_genre(text, lang=lang)
        strata.setdefault(det["genre"], []).append((name, text))
        assignment[name] = det
    genres = {}
    for g, items in strata.items():
        pooled = "\n\n".join(t for _, t in items)
        m = compute_metrics(pooled, use_lang)
        # n=2 的层 Delta 档案是数学退化（总体 std 下任意文本距离恒为 1.0），
        # 不入库——运行时回退混合档案作参考值
        genres[g] = {
            "samples": [n for n, _ in items],
            "chars_total": m["chars_total"],
            "metrics": derive_thresholds([t for _, t in items], lang=use_lang),
            "delta_profile": (build_delta_profile([t for _, t in items], top_n=top_n,
                                                  lang=use_lang)
                              if len(items) >= 3 else None),
        }
    return {"genres": genres, "assignment": assignment}


def leave_one_out(named_texts: list[tuple[str, str]], top_n: int = 150,
                  lang: str | None = LANG_ZH) -> dict:
    """层内留一：层内每篇对其余篇目所建档案算 Delta，最差篇即该层及格线。

    绝不跨层（跨层底线会把散文线拉到小说的高度）。层内 n<3 时留一档案
    退化为单样本（std 无意义），delta_max 置 None 并注明——线待语料扩充。
    返回 {genre: {n, delta_loo: [...], delta_max, delta_p50}}。
    """
    use_lang = normalize_lang(lang, "\n\n".join(t for _, t in named_texts))
    strata: dict[str, list[tuple[str, str]]] = {}
    for name, text in named_texts:
        g = detect_genre(text, lang=lang)["genre"]
        strata.setdefault(g, []).append((name, text))
    out: dict[str, dict] = {}
    for g, items in strata.items():
        rows = []
        for i, (name, text) in enumerate(items):
            others = [t for j, (_, t) in enumerate(items) if j != i]
            if len(others) < 2:
                rows.append({"work": name, "delta": None,
                             "note": f"留一档案仅 {len(others)} 样本，距离不可标定"})
                continue
            prof = build_delta_profile(others, top_n=top_n, lang=use_lang)
            rows.append({"work": name, "delta": delta_distance(text, prof)})
        deltas = sorted(r["delta"] for r in rows if r["delta"] is not None)
        out[g] = {
            "n": len(items),
            "delta_loo": rows,
            "delta_max": deltas[-1] if deltas else None,
            "delta_p50": deltas[len(deltas) // 2] if deltas else None,
        }
        if not deltas:
            out[g]["note"] = "层内 n<3：留一 Delta 线不可标定，待语料扩充后重算"
    return out


def layered_check(text: str, fingerprint: dict, genre: str | None = None,
                  delta_max_override: float | None = None,
                  lang: str | None = None) -> dict:
    """统一验收路径（fp_check CLI 与 MCP fp.check 共用）。

    1) 语言护栏（包语言 vs 文本语言，不匹配即判失败，不进入比对）；
    2) 文体判定（auto 或 --genre 指定）；3) 选对应层阈值（无层降级混合 + 明示）；
    4) 逐项比对；5) Delta 及格线：显式 --delta-max > 层内留一 delta_max（n≥3）；
    短文（<800 字/400 词）Delta 只作参考不进判定；800–1200 字/400–600 词进判定
    但标"置信中"。
    """
    det = detect_genre(text, lang=lang)
    notes: list[str] = []
    pack_lang = normalize_lang(lang or fingerprint.get("language") or LANG_ZH,
                               "").split("-")[0] or LANG_ZH
    text_lang = detect_lang(text)
    if pack_lang != text_lang:
        return {
            "language_mismatch": True,
            "pack_language": pack_lang,
            "text_language": text_lang,
            "ok": False,
            "rows": [],
            "genre": det,
            "layer_used": f"language-guard({pack_lang})",
            "notes": [f"语言不匹配：指纹语言 {pack_lang}，文本语言 {text_lang}——"
                      f"量纲（{'词' if text_lang == LANG_EN else '字'}）与指标口径不同，"
                      f"本次不做验收判定。请用同语言指纹验收，或用 fp_extract --lang "
                      f"{text_lang} 另建指纹。"],
            "chars_total": len(text),
            "metrics": {},
            "delta": None, "delta_line": None, "delta_counted": False,
            "delta_note": "语言不匹配，Delta 不计算",
        }
    genres = fingerprint.get("genres", {})
    g = det["genre"] if genre in (None, "auto") else genre
    if not genres or g == "all":
        tree = fingerprint.get("metrics", {})
        layer_used = "all(混合)"
        prof = fingerprint.get("delta_profile")
        sc = None
    elif g in genres:
        tree = genres[g]["metrics"]
        layer_used = g
        prof = genres[g].get("delta_profile") or fingerprint.get("delta_profile")
        sc = fingerprint.get("self_check", {}).get(g)
    else:
        tree = fingerprint.get("metrics", {})
        layer_used = f"all(混合，包无 {g} 层)"
        prof = fingerprint.get("delta_profile")
        sc = None
        notes.append(f"包无 {g} 层指纹，降级混合阈值")

    metrics = compute_metrics(text, text_lang)
    fill_missing_rates(metrics, tree)
    # compare_metrics(实测, 指纹形)：第二参才是阈值树
    rows = compare_metrics(metrics, {"metrics": tree})

    chars = metrics["chars_total"]
    unit = "词" if text_lang == LANG_EN else "字"
    min_delta = EN_DELTA_MIN_WORDS if text_lang == LANG_EN else DELTA_MIN_CHARS
    stable_delta = (EN_DELTA_STABLE_WORDS if text_lang == LANG_EN
                    else DELTA_STABLE_CHARS)
    delta = None
    line = None
    counted = False
    dnote = ""
    if prof is not None:
        delta = delta_distance(text, prof)
    if chars < min_delta:
        dnote = f"短文（{chars} {unit} < {min_delta}），Delta 仅为参考不进判定"
    elif prof is None:
        dnote = "包无 delta_profile，Delta 不可用"
    elif delta_max_override is not None:
        line, counted = delta_max_override, True
        dnote = "及格线=命令行显式指定"
    elif sc and sc.get("delta_max") is not None:
        line, counted = sc["delta_max"], True
        dnote = f"及格线=层内真迹留一最差篇（{sc['n']} 篇）"
    elif sc is not None:
        dnote = f"该层 n={sc.get('n')}（<3），留一 Delta 线待语料扩充，仅参考"
    else:
        dnote = "该层无 self_check，Delta 仅参考"
    if counted and chars < stable_delta:
        dnote += f"；{unit}数偏少，置信中"
    if counted and delta is not None:
        if line and delta > 0.8 * line:
            dnote += "；已接近及格线（>80%），仅供判读留意，不影响判定"
        rows.append({"path": "delta.distance", "target": line, "actual": delta,
                     "tolerance": line, "diff": round(delta - line, 3),
                     "ok": delta <= line, "note": dnote})

    return {
        "genre": det, "layer_used": layer_used, "notes": notes,
        "chars_total": chars, "rows": rows, "metrics": metrics,
        "delta": delta, "delta_line": line, "delta_counted": counted,
        "delta_note": dnote,
        "ok": all_ok(rows),
    }


# ---------------------------------------------------------------- 调子分区（R1，声明式）
# 语义分工：genres = 可自动检测的文体（检测键）；registers = 声明式调子（声明键）。
# 分组/档案/留一机制与文体层完全同构，只是分组键换成 registers.md 的标签。

def parse_registers_md(text: str) -> dict:
    """解析 registers.md → {"labels": {篇名: 主分区}, "axes": {分区名: 轴},
    "calibration": {分区名: "已标定"|"仅路由"}}。

    篇目总表行格式：| 篇名 | 主分区 | 次分区 | 一句依据 |；除名篇目不在表中，
    天然排除在分区统计之外（仍留在语料与文体层全集基线里）。
    各分区定义块内可用机器行声明标定状态：`标定：已标定（依据…）` /
    `标定：仅路由（依据…）`——R1 检查点的裁决落点，build_delta --registers
    以此为准逐层录取。
    """
    axes: dict[str, str] = {}
    calibration: dict[str, str] = {}
    m = re.search(r"^##\s+分区定义\s*$", text, flags=re.M)
    if m:
        defs = re.split(r"^##\s+", text[m.end():], flags=re.M)[0]
        axis = None
        for line in defs.splitlines():
            h = line.strip()
            if h.startswith("### "):
                axis = h[4:].split("（")[0].strip()
            elif h.startswith("#### ") and axis:
                axes[h[5:].strip()] = axis
        # 标定行归属其上方最近的 #### 分区
        current = None
        for line in defs.splitlines():
            h = line.strip()
            if h.startswith("#### "):
                current = h[5:].strip()
            elif h.startswith("### "):
                current = None
            else:
                cm = re.match(r"^标定[:：]\s*(已标定|仅路由)", h)
                if cm and current:
                    calibration[current] = cm.group(1)
    labels: dict[str, str] = {}
    m = re.search(r"^##\s+篇目总表.*$", text, flags=re.M)
    if m:
        table = re.split(r"^##\s+", text[m.end():], flags=re.M)[0]
        for row in re.findall(r"^\|([^|]+)\|([^|]+)\|", table, flags=re.M):
            name, main = row[0].strip(), row[1].strip()
            if name and main and name != "篇名" and not set(name) <= set("-— "):
                labels[name] = main
    return {"labels": labels, "axes": axes, "calibration": calibration}


def match_labels_to_files(files: list[Path], labels: dict[str, str],
                          read: bool = True) -> tuple[list[tuple[str, str]], list[str]]:
    """把语料文件映射到 registers.md 篇名：文件名 stem 去掉首个 '-' 前缀后
    精确匹配篇名（nahai-孔乙己.txt → 孔乙己）。返回 ([(篇名, 文本)], 未匹配文件)。
    """
    matched: list[tuple[str, str]] = []
    unmatched: list[str] = []
    for f in files:
        stem = f.stem
        name = stem.split("-", 1)[1] if "-" in stem else stem
        if name in labels:
            matched.append((name, f.read_text(encoding="utf-8", errors="replace")
                            if read else ""))
        else:
            unmatched.append(f.name)
    return matched, unmatched


def build_register_layers(named_texts: list[tuple[str, str]], labels: dict[str, str],
                          top_n: int = 150, lang: str | None = LANG_ZH) -> dict:
    """按声明式调子标签分层构建层档案（阈值树 + Delta 档案），结构与 genres 同构。"""
    use_lang = normalize_lang(lang, "\n\n".join(t for _, t in named_texts))
    strata: dict[str, list[tuple[str, str]]] = {}
    for name, text in named_texts:
        strata.setdefault(labels[name], []).append((name, text))
    regs: dict[str, dict] = {}
    for g, items in strata.items():
        pooled = "\n\n".join(t for _, t in items)
        m = compute_metrics(pooled, use_lang)
        regs[g] = {
            "samples": [n for n, _ in items],
            "chars_total": m["chars_total"],
            "metrics": derive_thresholds([t for _, t in items], lang=use_lang),
            "delta_profile": (build_delta_profile([t for _, t in items], top_n=top_n,
                                                  lang=use_lang)
                              if len(items) >= 3 else None),
        }
    return regs


def _build_rate_matrix(named_texts: list[tuple[str, str]],
                       top_n: int = 150) -> tuple[list[str], list[dict[str, float]]]:
    """全局 top-N 字符集 + 各篇字频向量（归因/置换共用的预计算矩阵）。"""
    agg: Counter = Counter()
    for _, t in named_texts:
        agg.update(c for c in t if CJK_RE.match(c))
    chars = [c for c, _ in agg.most_common(top_n)]
    rows = [char_rates(t, chars) for _, t in named_texts]
    return chars, rows


# 度量空间向量：节奏轴的主张（句长 / 对话密度 / 标点）落在这里，字频 Delta 测不到
METRIC_KEYS: list[tuple[str, ...]] = [
    ("sentence_length", "p25"), ("sentence_length", "p50"), ("sentence_length", "p75"),
    ("paragraph", "p50_len"), ("paragraph", "dialogue_para_ratio"),
    ("quote_char_ratio",),
    ("punctuation_per_1k", "？"), ("punctuation_per_1k", "！"),
    ("punctuation_per_1k", "…"), ("punctuation_per_1k", "—"), ("punctuation_per_1k", "；"),
    ("reduplication_per_1k",),
]

# 英文度量向量：量纲=词，标点取 ASCII 常用集，无叠字维（英文无对应指标）
METRIC_KEYS_EN: list[tuple[str, ...]] = [
    ("sentence_length", "p25"), ("sentence_length", "p50"), ("sentence_length", "p75"),
    ("paragraph", "p50_len"), ("paragraph", "dialogue_para_ratio"),
    ("quote_char_ratio",),
    ("punctuation_per_1k", ","), ("punctuation_per_1k", "."),
    ("punctuation_per_1k", ";"), ("punctuation_per_1k", ":"),
    ("punctuation_per_1k", "!"), ("punctuation_per_1k", "?"),
    ("punctuation_per_1k", "—"), ("punctuation_per_1k", "…"),
]


def metric_keys_for(lang: str | None = LANG_ZH) -> list[tuple[str, ...]]:
    """按语言取度量向量键集：zh 沿用 METRIC_KEYS（历史行为不变），en 用 METRIC_KEYS_EN。"""
    return METRIC_KEYS_EN if normalize_lang(lang) == LANG_EN else METRIC_KEYS


def build_metric_matrix(named_texts: list[tuple[str, str]], top_n: int = 150,
                        lang: str | None = LANG_ZH
                        ) -> tuple[list[str], list[dict[str, float]]]:
    """各篇度量向量（全局 z-score）：与字频矩阵同构，供同一套归因/置换机器使用。
    返回 (维度名列表, 各篇向量)——top_n 参数仅为与字频矩阵签名一致，忽略。"""
    keyset = metric_keys_for(lang)
    raw = [compute_metrics(t, lang) for _, t in named_texts]
    keys = ["+".join(k) for k in keyset]
    cols: list[list[float]] = []
    for k in keyset:
        vals = []
        for m in raw:
            node = m
            for step in k:
                node = node.get(step, {}) if isinstance(node, dict) else {}
            v = node if isinstance(node, (int, float)) else 0.0
            vals.append(float(v))
        n = len(named_texts)
        mean = sum(vals) / n if n else 0.0
        var = sum((v - mean) ** 2 for v in vals) / n if n else 0.0
        std = (var ** 0.5) or 1e-6
        cols.append([(v - mean) / std for v in vals])
    rows = [{key: cols[j][i] for j, key in enumerate(keys)} for i in range(n)]
    return keys, rows


def attribution_detail(named_texts: list[tuple[str, str]], labels: dict[str, str],
                       top_n: int = 150,
                       matrix: tuple[list[str], list[dict[str, float]]] | None = None
                       ) -> dict:
    """层间归因（留一）明细：每篇对自身层其余篇目建档案，与兄弟层档案比 Delta
    距离，最近层为自身层即判对。字符集取全体语料全局 top-N（同一基准，
    归因比较才公平——与存档 profile 的子集自带 top-N 刻意不同，见 Case I）。
    层内其余 <2 篇的篇目跳过。返回 {"rate", "judged", "per_group"}。"""
    chars, rows = matrix if matrix is not None else _build_rate_matrix(named_texts, top_n)

    strata: dict[str, list[int]] = {}
    for i, (name, _) in enumerate(named_texts):
        strata.setdefault(labels[name], []).append(i)

    group_profiles = {g: _profile_from_rows(rows, chars, idxs)
                      for g, idxs in strata.items()}
    per_group = {g: {"judged": 0, "correct": 0} for g in strata}
    for g, idxs in strata.items():
        for i in idxs:
            others = [j for j in idxs if j != i]
            if len(others) < 2 or len(strata) < 2:
                continue
            own = _profile_from_rows(rows, chars, others)
            d_own = _dist_from_rates(rows[i], own)
            d_others = min(_dist_from_rates(rows[i], p)
                           for gg, p in group_profiles.items() if gg != g)
            per_group[g]["judged"] += 1
            if d_own < d_others:
                per_group[g]["correct"] += 1
    judged = sum(v["judged"] for v in per_group.values())
    correct = sum(v["correct"] for v in per_group.values())
    return {"rate": (round(correct / judged, 4) if judged else 0.0),
            "judged": judged, "per_group": per_group}


def attribution_rate(named_texts: list[tuple[str, str]], labels: dict[str, str],
                     top_n: int = 150,
                     matrix: tuple[list[str], list[dict[str, float]]] | None = None
                     ) -> tuple[float, int]:
    d = attribution_detail(named_texts, labels, top_n=top_n, matrix=matrix)
    return d["rate"], d["judged"]


def _profile_from_rows(rows: list[dict[str, float]], chars: list[str],
                       idxs: list[int]) -> dict:
    """对预计算的字频矩阵行子集建档案——数学与 build_delta_profile 完全一致
    （均值 / 总体 std / 4 位舍入 / 1e-4 防除零），只是省去重复全文计数。"""
    prof: dict[str, list[float]] = {}
    n = len(idxs)
    for c in chars:
        vals = [rows[i][c] for i in idxs]
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n if n > 1 else 0.0
        std = round(var ** 0.5, 4)
        prof[c] = [round(mean, 4), std if std > 0 else 1e-4]
    return {"chars": prof, "n_samples": n, "top_n": len(chars)}


def _dist_from_rates(rate_row: dict[str, float], profile: dict) -> float:
    diffs = [abs((rate_row[c] - m) / s) for c, (m, s) in profile["chars"].items()]
    return round(sum(diffs) / len(diffs), 3) if diffs else 999.0


def permutation_test(named_texts: list[tuple[str, str]], labels: dict[str, str],
                     n_perm: int = 1000, seed: int = 20260930, top_n: int = 150,
                     matrix: tuple[list[str], list[dict[str, float]]] | None = None
                     ) -> dict:
    """置换检验：把标签随机重排（各层规模不变）N 次 → 归因率零假设分布。
    p = 零假设中 ≥ 观察值的比例（单侧）。返回观测率、p 值与零假设摘要；
    固定种子保证换机重跑可复现（r3 审查 #1）。"""
    det = attribution_detail(named_texts, labels, top_n=top_n, matrix=matrix)
    observed, judged = det["rate"], det["judged"]
    rng = random.Random(seed)
    names = [n for n, _ in named_texts]
    # 层规模（按首次出现顺序，保证与 attribution_rate 的分组键一致）
    seen: dict[str, int] = {}
    for n in names:
        seen[labels[n]] = seen.get(labels[n], 0) + 1
    sizes = list(seen.items())
    all_names = names[:]
    null: list[float] = []
    for _ in range(n_perm):
        rng.shuffle(all_names)
        perm_labels: dict[str, str] = {}
        idx = 0
        for g, size in sizes:
            for _ in range(size):
                perm_labels[all_names[idx]] = g
                idx += 1
        null.append(attribution_detail(named_texts, perm_labels, top_n=top_n,
                                       matrix=matrix)["rate"])
    p = round(sum(1 for r in null if r >= observed) / len(null), 4) if null else 1.0
    return {"observed": observed, "judged": judged, "p": p,
            "null_mean": round(sum(null) / len(null), 4) if null else None,
            "null_max": max(null) if null else None,
            "n_perm": n_perm, "seed": seed,
            "per_group": det["per_group"]}





def force_utf8_stdio() -> None:
    """入口统一调用：把标准流重配为 UTF-8。

    Windows 默认 cp936 控制台/管道下，emoji 报告与 ensure_ascii=False 的 JSON
    载荷会 UnicodeEncodeError 或被按本地代码页污染。reconfigure 仅 3.7+ 的
    TextIOWrapper 提供，流被宿主替换时静默跳过；errors 容错保输出不断流。
    """
    for stream, err in ((sys.stdout, "replace"), (sys.stderr, "replace"),
                        (sys.stdin, "strict")):
        try:
            stream.reconfigure(encoding="utf-8", errors=err)
        except (AttributeError, ValueError, OSError):
            pass


def load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(obj, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def collect_text_files(inputs: list[str | Path]) -> list[Path]:
    """把文件/目录参数展开为文本文件列表（.txt/.md，按文件名排序）。"""
    files: list[Path] = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            files.extend(sorted(q for q in p.rglob("*") if q.suffix.lower() in (".txt", ".md")))
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(f"路径不存在：{p}")
    return files
