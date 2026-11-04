# -*- coding: utf-8 -*-
"""names_check：专名总账门（三模态合并；v0.12.1 欠账补完，设想 §5.2 设定门）。

模态（可组合，均 advisory 报不拦；连跑由工作台升级红停）：
① 出场统计（原有，语料级）：--names bible/names.json
   每个人名（含 aliases）出现次数 + 零出现警告——**多章/全量对照用**，
   单章门禁勿用（单章必然大量零出现，会全员误报）；
② 禁用变体（新，家法：灾厄前线 整合/names_check.sh，弧二实战验证）：
   --variants bible/专名表.tsv（正名<TAB>禁用变体1|变体2，# 注释）——
   正文出现禁用变体 = 疑似错写。形近/音近变体由作者养表（不做自动 NER：
   中文零依赖 NER 不可靠，误报会淹没批量）；
③ 人物状态门（新，J8 判定代理）：--characters bible/characters.md
   卡面「状态：死亡（第N章）/离场（第N章）」→ 死亡/离场者正名或别名
   出现在**引号外叙述**（“”内对话=提及，豁免）→ 停等人裁决
   （回忆/他人提及合法：核对后改卡面状态或改正文，禁止圆稿）；
④ 卡面禁语（§5.2 人物·言行，黄级）：卡面「禁语：词1|词2」（从不说的话/词）
   → 正文出现即记（角色语音段与禁词同现的精确判定不做——按同现报，黄级
   供人扫，不默认红停）。

用法：
    python scripts/names_check.py <章节.md|目录...> [--names names.json]
        [--variants 专名表.tsv] [--characters characters.md]
退出码：0=无发现；1=有发现项（零出现/变体/状态冲突）；2=输入错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import splib  # noqa: E402

STATUS_PAT = re.compile(r"状态[:：]\s*(死亡|离场)[（(]第(\d+)章[）)]")
TABOO_PAT = re.compile(r"禁语[:：]\s*(\S.*)")  # 块内首个「禁语：」（不要求行首）
DIALOG_PAT = re.compile(r"“[^”]*”")  # J8：引号内=提及，豁免


def load_variants(path: Path) -> list[tuple[str, str]]:
    """专名表.tsv → [(正名, 禁用变体)]。"""
    out = []
    if not path.is_file():
        return out
    for line in splib.read_text(path)[0].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "\t" not in line:
            continue
        canon, bad = line.split("\t", 1)
        canon = canon.strip()
        for v in bad.split("|"):
            v = v.strip()
            if v:
                out.append((canon, v))
    return out


def load_status(characters_path: Path) -> list[dict]:
    """characters.md 卡面 → [{name, state, ch, taboo}]（状态门+禁语门数据）。"""
    out = []
    if not characters_path.is_file():
        return out
    text = splib.read_text(characters_path)[0]
    if "## " not in text:
        return out
    for b in text.split("\n## "):
        body = b if b.startswith("## ") else "## " + b
        title = body.splitlines()[0].lstrip("# ").strip()
        if not title:
            continue
        m = STATUS_PAT.search(body)
        t = TABOO_PAT.search(body)
        if m or t:
            out.append({"name": title,
                        "state": m.group(1) if m else "",
                        "ch": int(m.group(2)) if m else 0,
                        "taboo": [w.strip() for w in t.group(1).split("|")
                                  if w.strip()] if t else []})
    return out


def check_variants(full: str, variants: list[tuple[str, str]]) -> list[str]:
    findings = []
    for canon, bad in variants:
        n = full.count(bad)
        if n:
            i = full.find(bad)
            ctx = full[max(0, i - 12): i + len(bad) + 12].replace("\n", " ")
            findings.append(f"[专名错写] “{bad}”（正名：{canon}）×{n}：「…{ctx}…」"
                            "——改正文或养表（若为合法新词，移出禁用列）")
    return findings


def check_status(text: str, statuses: list[dict],
                 aliases: dict[str, list[str]]) -> list[str]:
    """单章状态门+禁语门：状态冲突（红级）与禁语同现（黄级）→ 发现项。"""
    findings = []
    narr = DIALOG_PAT.sub(lambda m: "＂" * len(m.group(0)), text)
    for st in statuses:
        if st["state"]:
            for nm in [st["name"], *aliases.get(st["name"], [])]:
                if len(nm) < 2 or nm not in narr:
                    continue
                i = narr.find(nm)
                ctx = text[max(0, i - 12): i + len(nm) + 12].replace("\n", " ")
                findings.append(
                    f"[状态冲突] {st['state']}者「{nm}」（第{st['ch']}章{st['state']}）"
                    f"出现于叙述：「…{ctx}…」——回忆/他人提及？核对后改卡面状态或改正文")
                break  # 每人报一处即可
        for w in st.get("taboo", []):
            if w in text:
                i = text.find(w)
                ctx = text[max(0, i - 12): i + len(w) + 12].replace("\n", " ")
                findings.append(f"[禁语·黄] 「{w}」（{st['name']} 从不说的话/词）："
                                f"「…{ctx}…」——确认是否人设崩，或养表放宽")
    return findings


def main() -> int:
    splib.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="专名总账门（出场统计/禁用变体/人物状态）")
    ap.add_argument("inputs", nargs="+", help="正文文件或目录")
    ap.add_argument("--names", default="",
                    help="bible/names.json（模态①出场统计+零出现，语料级）")
    ap.add_argument("--variants", default="",
                    help="bible/专名表.tsv（模态②禁用变体）")
    ap.add_argument("--characters", default="",
                    help="bible/characters.md（模态③人物状态门）")
    ap.add_argument("--namesjson", default="",
                    help="names.json（状态门别名来源；与 --names 同源可省）")
    args = ap.parse_args()

    files = splib.collect_text_files(args.inputs)
    if not files:
        print("错误：未找到正文文件", file=sys.stderr)
        return 2
    full = "\n".join(splib.read_text(f)[0] for f in files)
    findings: list[str] = []

    if args.variants:
        findings += check_variants(full, load_variants(Path(args.variants)))

    statuses = load_status(Path(args.characters)) if args.characters else []
    if statuses:
        aliases: dict[str, list[str]] = {}
        nj = args.namesjson or args.names
        if nj and Path(nj).is_file():
            try:
                for x in json.loads(Path(nj).read_text(encoding="utf-8")
                                    ).get("names", []):
                    if isinstance(x, dict) and str(x.get("name", "")).strip():
                        aliases[str(x["name"]).strip()] = [
                            str(a).strip() for a in x.get("aliases", [])
                            if str(a).strip()]
            except (OSError, ValueError):
                pass
        for f in files:  # 状态门按章定位（叙述出现=本章在场）
            findings += check_status(splib.read_text(f)[0], statuses, aliases)

    zero = 0
    if args.names:
        data = splib.load_json(args.names)
        people = data.get("names", []) if isinstance(data, dict) else data
        rows = []
        for person in people:
            variants = [person["name"]] + person.get("aliases", [])
            counts = {v: len(re.findall(re.escape(v), full)) for v in variants}
            total = sum(counts.values())
            if total == 0:
                zero += 1
            rows.append((person["name"], counts, total))
        for name, counts, total in rows:
            detail = "，".join(f"{v}×{c}" for v, c in counts.items() if c)
            print(f"{name}: 共 {total} 次" + (f"（{detail}）" if detail else "  ⚠️ 全文未出现"))
        print(f"\n人名总数 {len(rows)}，零出现 {zero}")

    for line in findings:
        print(line)
    total_issues = len(findings) + (zero if args.names else 0)
    print("\n" + ("专名总账门：✓ 无发现项" if not total_issues else
                  f"专名总账门：⚠ {total_issues} 项发现（advisory，人工裁决）"))
    return 1 if total_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
