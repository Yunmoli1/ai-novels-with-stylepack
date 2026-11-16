# -*- coding: utf-8 -*-
"""borrow_check：草稿 vs 风格包范例的整句搬运初筛（问题总账 2.3/遗留 #8 的机器初筛层）。

用法：
    python scripts/borrow_check.py <草稿文件> --pack <风格包目录> [--min-len 12]

原理：exemplars.md 每条引文规范化（去空白与标点、跳过省略号）后切成
min_len 字滑窗集合；草稿同样规范化后滑窗，命中即报——命中 = 草稿与
某条范例存在 ≥min_len 字的逐字重叠，是"表层借句/整句搬运"的强信号。
命中区间向两侧延展至不再是任何引文的子串，报告最大重叠。

定位：**初筛不是终判**。≥12 个汉字逐字重叠几乎不可能是巧合，但判官式的
"化用/骨架雷同"仍靠盲测与人工判读兜底（盲测两败同因：整句搬运名篇
结尾被判"表层仿写"）。exit 0=未命中 1=命中 2=用法错误——可作交付自检
的可选门，不强制进判定（advisory 纪律同 motif：永不修改任何包文件）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import splib  # noqa: E402

HeadRe = re.compile(r"^###\s*(\d+)\.\s*(.+?)\s*$")


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """规范化（只保留 CJK/字母/数字，去空白与标点），并保留原文下标映射。"""
    kept: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        if ("\u3400" <= ch <= "\u9fff") or ch.isalnum():
            kept.append(ch)
            idx.append(i)
    return "".join(kept), idx


def find_borrows_words(draft: str, quotes: list[tuple[int, str, str]],
                       min_words: int) -> list[dict]:
    """英文路径：按词切窗（默认 5 词），返回命中词区间 [{start,end,len,nums}]。

    英文按字符切 12 字窗≈2 个词，巧合命中概率高且漏掉真正搬运；改按词计，
    与中文「≥12 字逐字重叠」同义（一个词的信息量≈2–3 个汉字）。
    """
    norm_quotes: list[tuple[int, list[str]]] = []
    shingle_owner: dict[tuple[str, ...], set[int]] = {}
    for num, _t, q in quotes:
        nq = [w.lower() for w in splib.words_of(q)]
        norm_quotes.append((num, nq))
        for i in range(max(0, len(nq) - min_words + 1)):
            shingle_owner.setdefault(tuple(nq[i:i + min_words]), set()).add(num)
    nd = [w.lower() for w in splib.words_of(draft)]

    def _in_any_quote(seq: list[str]) -> bool:
        n = len(seq)
        for _num, nq in norm_quotes:
            for k in range(len(nq) - n + 1):
                if nq[k:k + n] == seq:
                    return True
        return False

    spans: list[list[int]] = []
    i = 0
    while i + min_words <= len(nd):
        if tuple(nd[i:i + min_words]) in shingle_owner:
            end = i + min_words
            while end < len(nd) and _in_any_quote(nd[i:end + 1]):
                end += 1
            spans.append([i, end])
            i = end
        else:
            i += 1
    return [{"start": s, "end": e, "len": e - s,
             "nums": sorted({n for k in range(s, e - min_words + 1)
                             for n in shingle_owner.get(tuple(nd[k:k + min_words]), ())})}
            for s, e in spans]


def load_exemplar_quotes(pack: Path) -> list[tuple[int, str, str]]:
    """[(编号, 标题, 引文原文)]——exemplars.md 的 `> ` 引用块逐条取。"""
    path = pack / "exemplars.md"
    if not path.is_file():
        raise FileNotFoundError(f"{path} 不存在：borrow_check 依赖 exemplars.md 引文")
    quotes: list[tuple[int, str, str]] = []
    num, title, buf = 0, "", []
    for line in splib.read_text(path)[0].splitlines():
        head = HeadRe.match(line.strip())
        if head:
            num, title, buf = int(head.group(1)), head.group(2), []
        elif line.strip().startswith(">"):
            buf.append(line.strip().lstrip(">").strip())
        elif buf and not line.strip():
            if "".join(buf):
                quotes.append((num, title, "".join(buf)))
            buf = []
    if buf and "".join(buf):
        quotes.append((num, title, "".join(buf)))
    return quotes


def find_borrows(draft: str, quotes: list[tuple[int, str, str]],
                 min_len: int) -> list[dict]:
    """返回命中列表 [{start,end,len,nums}]（start/end 为规范化下标）。"""
    norm_quotes: list[tuple[int, str]] = []
    shingle_owner: dict[str, set[int]] = {}
    for num, _t, q in quotes:
        nq, _ = _normalize_with_map(q)
        norm_quotes.append((num, nq))
        for i in range(max(0, len(nq) - min_len + 1)):
            shingle_owner.setdefault(nq[i:i + min_len], set()).add(num)

    nd, _idx = _normalize_with_map(draft)
    spans: list[list[int]] = []
    i = 0
    while i + min_len <= len(nd):
        if nd[i:i + min_len] in shingle_owner:
            end = i + min_len
            while end < len(nd) and any(
                    nd[i:end + 1] in nq for _n, nq in norm_quotes):
                end += 1
            spans.append([i, end])
            i = end
        else:
            i += 1
    return [{"start": s, "end": e, "len": e - s,
             "nums": sorted({n for k in range(s, e - min_len + 1)
                             for n in shingle_owner.get(nd[k:k + min_len], ())})}
            for s, e in spans]


def main() -> int:
    splib.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="草稿 vs 范例整句搬运初筛")
    ap.add_argument("draft", help="草稿文件（.txt/.md）")
    ap.add_argument("--pack", required=True, help="风格包目录（读 exemplars.md）")
    ap.add_argument("--min-len", type=int, default=12,
                    help="命中阈值：中文逐字重叠的最短字数（默认 12）")
    ap.add_argument("--min-words", type=int, default=5,
                    help="命中阈值：英文逐词重叠的最短词数（默认 5）")
    ap.add_argument("--lang", default="auto", choices=["auto", "zh", "en"],
                    help="草稿语言：auto=按 CJK 占比自动判定（默认）")
    args = ap.parse_args()

    draft_path = Path(args.draft)
    if not draft_path.is_file():
        print(f"错误：草稿文件不存在：{draft_path}", file=sys.stderr)
        return 2
    try:
        quotes = load_exemplar_quotes(Path(args.pack))
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    if not quotes:
        print("错误：exemplars.md 未解析到任何引文", file=sys.stderr)
        return 2

    draft = splib.read_text(draft_path)[0]
    use_lang = splib.normalize_lang(args.lang, draft)
    if use_lang == splib.LANG_EN:
        words = splib.words_of(draft)
        hits = find_borrows_words(draft, quotes, args.min_words)
        print(f"borrow_check：草稿 {len(words)} 词 vs 范例 {len(quotes)} 条"
              f"（阈值 ≥{args.min_words} 词逐词重叠）")
        if not hits:
            print("未发现整句搬运信号 ✅")
            return 0
        print(f"发现 {len(hits)} 处疑似借句：")
        for h in hits:
            orig = " ".join(words[h["start"]:h["end"]])
            owners = "、".join(f"范例 {n}" for n in h["nums"])
            shown = orig[:80] + ("…" if len(orig) > 80 else "")
            print(f"  [{h['len']} 词 → {owners}] {shown}")
        print("初筛信号仅供人工判读；化用/骨架雷同不在本工具射程内。")
        return 1

    _nd, idx = _normalize_with_map(draft)
    hits = find_borrows(draft, quotes, args.min_len)

    print(f"borrow_check：草稿 {len(draft)} 字 vs 范例 {len(quotes)} 条"
          f"（阈值 ≥{args.min_len} 字逐字重叠）")
    if not hits:
        print("未发现整句搬运信号 ✅")
        return 0

    print(f"发现 {len(hits)} 处疑似借句：")
    for h in hits:
        orig = draft[idx[h["start"]]:idx[h["end"] - 1] + 1]
        owners = "、".join(f"范例 {n}" for n in h["nums"])
        shown = orig[:40] + ("…" if len(orig) > 40 else "")
        print(f"  [{h['len']} 字 → {owners}] {shown}")
    print("初筛信号仅供人工判读；化用/骨架雷同不在本工具射程内。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
