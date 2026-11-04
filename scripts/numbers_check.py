# -*- coding: utf-8 -*-
"""numbers_check：正文数字 vs 硬数字表口径对照（v0.11.1 B-3，advisory 报不拦）。

三分类纪律（项目管理/计划书/工作台v0.12-量产连跑-设计设想.md §5.1）：
- 表内口径：正文须出现同值；约略词（约/近/余/许/成/上/下/多/几）修饰的同值、
  或"一万两千多"式取整形式（±20%）也算合规；
- 表外数字：不在任何口径且未豁免 → 报告（人工裁决：落账 / 进豁免清单 / 改文）；
  ≥100 标"设定级候选"（连跑模式据此升级停+裁决），<100 标"场景级"；
- 豁免：约略数量词（十几/成千上万）、账本 `## 豁免数字` 节列出的值。

报告不拦截交付（人工模式"报不拦"）；章节文件按标题行、时间（hh:mm）、
小数、千位分隔符自动降噪。中文数字（三千五百/一万两千/二十五/一万二）
与阿拉伯数字双解析。

用法：
    python scripts/numbers_check.py <章节.md> --ledger <硬数字表.md> --chapter 210
    python scripts/numbers_check.py <项目目录> --ledger <硬数字表.md> --all
退出码：0=无发现；1=有发现项（advisory）；2=输入错误。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ZH_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
ZH_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
HEDGE = set("约近余许成上下多几")
SEC_PAT = re.compile(r"^## 弧(\d+)《(.+?)》（第(\d+)-(\d+)章）", re.M)
ROW_PAT = re.compile(r"^\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|\s*$", re.M)
FREE_PAT = re.compile(r"^##\s*豁免数字", re.M)
ZH_SEQ = re.compile(r"[零〇一二两三四五六七八九十百千万亿]+")
AR_PAT = re.compile(r"(\d[\d,，_]*)([万亿千百])?")
SUFS = {"万": 10000, "亿": 100000000, "千": 1000, "百": 100}


def zh_to_int(s: str):
    """中文数字 → int；不成形返回 None。支持 三千五百/一万两千/二十五/一万二。"""
    if len(s) == 1 and s in ZH_UNIT:
        return ZH_UNIT[s]
    total = section = num = 0
    last_unit = 1
    elide_ok = True  # "一万二"=12000 的省略位；"三千五百零六"的零使其失效
    for ch in s:
        if ch in ZH_DIGIT:
            num = ZH_DIGIT[ch]
            if num == 0:
                elide_ok = False
        elif ch in ZH_UNIT:
            u = ZH_UNIT[ch]
            if u >= 10000:
                total += (section + num) * u
                section = num = 0
            else:
                section += (num or 1) * u
                num = 0
            last_unit = u
        else:
            return None
    if num:
        section += num * (last_unit // 10) if (last_unit > 1 and elide_ok) else num
    return (total + section) or None


def _hedged(text: str, s: int, e: int) -> bool:
    """约略词邻接（前后各 1 字）：约39 / 39余 / 十几 / 成千上万。"""
    before = text[s - 1] if s > 0 else ""
    after = text[e] if e < len(text) else ""
    return before in HEDGE or after in HEDGE


def extract_numbers(text: str, zh_min: int = 11, ar_min: int = 2) -> list[dict]:
    """抽取数字（值/位置/是否约略）。标题行跳过；时间 hh:mm、小数以等长空格
    预剔除（保下标）。中文数字 zh_min（<11 视为场景级噪声）、阿拉伯 ar_min。"""
    spans, pos = [], 0
    for line in text.splitlines(keepends=True):
        spans.append((pos, pos + len(line), line.lstrip().startswith("#")))
        pos += len(line)

    def heading(p: int) -> bool:
        return any(a <= p < b and h for a, b, h in spans)

    t = re.sub(r"\d{1,2}:\d{2}", lambda m: " " * len(m.group(0)), text)
    t = re.sub(r"\d+\.\d+", lambda m: " " * len(m.group(0)), t)
    out: list[dict] = []
    for m in AR_PAT.finditer(t):
        digits = re.sub(r"[,，_]", "", m.group(1))
        if not digits:
            continue
        v = int(digits) * (SUFS[m.group(2)] if m.group(2) else 1)
        if v < ar_min or heading(m.start()):
            continue
        out.append({"v": v, "s": m.start(), "e": m.end(), "raw": m.group(0),
                    "hedged": _hedged(t, m.start(), m.end())})
    for m in ZH_SEQ.finditer(t):
        v = zh_to_int(m.group(0))
        if v is None or v < zh_min or heading(m.start()):
            continue
        out.append({"v": v, "s": m.start(), "e": m.end(), "raw": m.group(0),
                    "hedged": _hedged(t, m.start(), m.end())})
    out.sort(key=lambda x: x["s"])
    return out


def parse_ledger(text: str, chapter: int | None) -> tuple[list, set]:
    """→ (口径项 [(name, value, raw)], 豁免值 set)。chapter=None 收全部弧节。"""
    values: list[tuple[str, int, str]] = []
    fm = FREE_PAT.search(text)
    free_start = fm.start() if fm else len(text)
    free: set[int] = set()
    if fm:
        nxt = re.search(r"^## ", text[fm.end():], re.M)
        seg = text[fm.end(): fm.end() + nxt.start()] if nxt else text[fm.end():]
        for x in extract_numbers(seg, zh_min=1, ar_min=1):
            free.add(x["v"])
    secs = list(SEC_PAT.finditer(text))
    for i, m in enumerate(secs):
        if chapter is not None and not (
                int(m.group(3)) <= chapter <= int(m.group(4))):
            continue
        end = secs[i + 1].start() if i + 1 < len(secs) else len(text)
        if free_start > m.start():
            end = min(end, free_start)
        for r in ROW_PAT.finditer(text[m.end():end]):
            name = r.group(1).strip()
            if name == "账目" or set(name) <= {"-", " ", ":"}:
                continue  # 表头/分隔行
            for x in extract_numbers(r.group(2), zh_min=1, ar_min=1):
                values.append((name, x["v"], x["raw"]))
    return values, free


def check_chapter(text: str, values: list, free: set) -> list[str]:
    findings: list[str] = []

    def compliant(v: int, nums: list[dict]) -> bool:
        if any(x["v"] == v for x in nums):
            return True
        return any(x["hedged"] and abs(x["v"] - v) <= max(v * 0.2, 5)
                   for x in nums)

    # 合规匹配用全量抽取（zh_min=1：口径"每夜三下"的 3 要能对上正文"三下"）；
    # 表外报告用过滤抽取（zh_min=11/ar_min=2：小数字多为场景噪声）
    nums_all = extract_numbers(text, zh_min=1, ar_min=1)
    nums = extract_numbers(text)
    for name, v, raw in values:
        if v not in free and not compliant(v, nums_all):
            findings.append(f"[口径缺失] {name}={raw}（{v}）：正文未出现该值"
                            "（含约略/取整形式）——改正文或改账本，禁止圆稿")
    led_vals = {v for _, v, _ in values}
    reported: set[int] = set()
    for x in nums:
        if x["v"] in led_vals or x["v"] in free or x["hedged"] \
                or x["v"] in reported:
            continue
        reported.add(x["v"])
        ctx = text[max(0, x["s"] - 14): x["e"] + 14].replace("\n", " ")
        level = "设定级候选" if x["v"] >= 100 else "场景级"
        findings.append(f"[表外·{level}] {x['raw']}（{x['v']}）：「…{ctx}…」"
                        "——真设定请落账硬数字表；垃圾数字进豁免清单")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="正文数字 vs 硬数字表口径对照（advisory 报不拦）")
    ap.add_argument("target", help="章节文件；--all 时为项目目录")
    ap.add_argument("--ledger", required=True, help="硬数字表.md 路径")
    ap.add_argument("--chapter", type=int, default=None, help="当前章号（弧节定位）")
    ap.add_argument("--all", action="store_true",
                    help="全量回扫 target/manuscript/*.md（账本回扫 retroscan）")
    args = ap.parse_args()
    ledger = Path(args.ledger)
    if not ledger.is_file():
        print(f"硬数字表不存在：{ledger}——跳过对照")
        return 0
    ltext = ledger.read_text(encoding="utf-8", errors="replace")
    tp = Path(args.target)
    if args.all:
        ms = tp / "manuscript"
        files = sorted(ms.glob("*.md")) if ms.is_dir() else []
        if not files:
            print("manuscript/ 无章节——跳过回扫")
            return 0
    else:
        if not tp.is_file():
            print(f"章节文件不存在：{tp}", file=sys.stderr)
            return 2
        files = [tp]
    total = 0
    for f in files:
        if args.all:
            mm = re.match(r"(\d+)", f.stem)
            values, free = parse_ledger(ltext, int(mm.group(1)) if mm else None)
        else:
            values, free = parse_ledger(ltext, args.chapter)
        if not values and not free:
            if args.all:
                continue
            print("账本无覆盖本章的弧节/豁免节——跳过对照（开弧后自动生效）")
            return 0
        findings = check_chapter(f.read_text(encoding="utf-8", errors="replace"),
                                 values, free)
        total += len(findings)
        if args.all:
            print(f"\n== {f.name}：" + ("✓ 无发现" if not findings
                                        else f"{len(findings)} 项"))
        for line in findings:
            print(line)
    print("\n" + (f"全量回扫完成：{len(files)} 章，共 {total} 项发现" if args.all
                   else ("数字对照完成：✓ 无发现项" if not total else
                         f"数字对照完成：⚠ {total} 项发现（advisory，人工裁决）")))
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
