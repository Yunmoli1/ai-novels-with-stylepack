# -*- coding: utf-8 -*-
"""fp_check：把生成文本的风格指纹与风格包比对，输出验收报告。

用法：
    python scripts/fp_check.py <风格包目录> <文本文件或目录...> \
        [--per-file] [--genre auto|narrative|essay|all] [--json OUT] \
        [--report OUT.md] [--save-metrics OUT.json] [--baseline IN.json] \
        [--delta-max X]

v0.2.3 分层指纹：默认 auto——先检测待测文本文体（对话段占比），再用包中对应层
（genres.<层>）的阈值与 Delta 档案验收；Delta 及格线取层内真迹留一最差篇
（self_check.delta_max，n≥3 才可标定）；无对应层时降级混合阈值并明示。
短文（<800 字）Delta 仅为参考、不进判定；800–1200 字进判定但标"置信中"。
--delta-max 显式覆盖及格线。--per-file 逐文件判定（逐章风格漂移检测）。
--save-metrics / --baseline 仅支持合并模式，与 --per-file 互斥。
退出码：0 = 全部通过；1 = 存在不达标项；2 = 用法错误。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import splib  # noqa: E402


def _pack_language(pack_dir: Path, fingerprint: dict) -> str:
    """包语言：fingerprint.language 优先，其次 pack.json.language，缺省 zh。

    只取主语言子标签（zh-Hans → zh），与 splib.normalize_lang 的口径一致。
    """
    lang = fingerprint.get("language")
    if not lang:
        pj = pack_dir / "pack.json"
        if pj.is_file():
            lang = splib.load_json(pj).get("language")
    return splib.normalize_lang(lang or splib.LANG_ZH)


def _meta_lines(res: dict) -> list[str]:
    det = res["genre"]
    lines = [f"文体判定：{det['genre']}（段首引号段 {det['dialogue_para_ratio']:.0%}，"
             f"引号字占比 {det['quote_char_ratio']:.0%}，置信 {det['confidence']}"
             f"，边界距 {det.get('boundary_margin', 0):.2f}）"
             f"｜阈值层：{res['layer_used']}"]
    for n in res["notes"]:
        lines.append(f"提示：{n}")
    if res["delta"] is not None:
        tail = f"Delta 距离：{res['delta']}"
        if res["delta_counted"]:
            tail += f"｜及格线 {res['delta_line']}（{res['delta_note']}）"
        else:
            tail += f"（{res['delta_note']}）"
        lines.append(tail)
    return lines


def render_report(pack_name: str,
                  results: list[tuple[str, list[dict], list[dict] | None, dict]]) -> str:
    lines = [f"# 风格验收报告：{pack_name}", ""]
    overall_ok = True
    for label, rows, diffs, meta in results:
        if meta.get("language_mismatch"):
            overall_ok = False
            lines.append(f"## {label} —— ⛔ 语言不匹配")
            lines.append("")
            for ln in meta.get("notes", []):
                lines.append(f"> {ln}")
            lines.append("")
            continue
        ok = splib.all_ok(rows)
        overall_ok = overall_ok and ok
        lines.append(f"## {label} —— {'✅ 通过' if ok else '❌ 不达标'}")
        lines.append("")
        for ln in _meta_lines(meta):
            lines.append(f"> {ln}")
        lines.append("")
        lines.append("| 指标 | 目标 | 实际 | 容差 | 偏差 | 判定 |")
        lines.append("|---|---|---|---|---|---|")
        for r in rows:
            act = "缺失" if r["actual"] is None else r["actual"]
            tol = "-" if r["tolerance"] is None else r["tolerance"]
            diff = "-" if r["diff"] is None else r["diff"]
            mark = "✅" if r["ok"] else "❌"
            note = f"（{r['note']}）" if r["note"] else ""
            lines.append(f"| `{r['path']}` | {r['target']} | {act} | {tol} | {diff} | {mark}{note} |")
        if diffs:
            lines.append("")
            lines.append("### 与基线对比")
            lines.append("")
            lines.append("| 指标 | 基线 | 本次 | Δ | 判定 |")
            lines.append("|---|---|---|---|---|")
            for d in diffs:
                mark = "⚠️ 回归" if d["regression"] else "—"
                lines.append(
                    f"| `{d['path']}` | {d['baseline']} | {d['actual']} | {d['delta']} | {mark} |")
        lines.append("")
    verdict = ("全部通过" if overall_ok else
               "存在不达标项，建议按偏差最大的指标修订文本或档案"
               "（语言不匹配时请先用同语言指纹，或用 fp_extract --lang 另建指纹）")
    lines.append(f"> 结论：**{verdict}**")
    return "\n".join(lines) + "\n"


def main() -> int:
    splib.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="风格指纹验收比对（分层指纹版）")
    ap.add_argument("pack", help="风格包目录（含 fingerprint.json）")
    ap.add_argument("inputs", nargs="+", help="待验收文本（.txt/.md）")
    ap.add_argument("--per-file", action="store_true", help="逐文件比对（漂移检测）")
    ap.add_argument("--genre", default="auto",
                    choices=["auto", "narrative", "essay", "all"],
                    help="阈值层选择：auto=按文本自动判定（默认），all=混合阈值")
    ap.add_argument("--json", dest="json_out", help="结果 JSON 输出路径")
    ap.add_argument("--report", dest="report_out", help="Markdown 报告输出路径")
    ap.add_argument("--save-metrics", dest="save_metrics",
                    help="本次实测指标存档路径（供下次 --baseline）")
    ap.add_argument("--baseline", dest="baseline_path",
                    help="上次实测指标存档，逐指标对比回归")
    ap.add_argument("--delta-max", type=float, default=None,
                    help="显式覆盖 Delta 及格线（默认用层内真迹留一线）")
    ap.add_argument("--thought", action="store_true",
                    help="输出 thought.md motif 密度对照（advisory：仅供判读参考，"
                         "不进判定、不影响退出码）")
    args = ap.parse_args()

    pack_dir = Path(args.pack)
    fp_path = pack_dir / "fingerprint.json"
    if not fp_path.is_file():
        print(f"错误：找不到 {fp_path}", file=sys.stderr)
        return 2
    fingerprint = splib.load_json(fp_path)
    pack_lang = _pack_language(pack_dir, fingerprint)
    files = splib.collect_text_files(args.inputs)
    if not files:
        print("错误：未找到任何待验收文本", file=sys.stderr)
        return 2
    empties = [f.name for f in files if not splib.read_text(f)[0].strip()]
    if empties:
        print(f"错误：待验收文本为空（{'、'.join(empties)}）——无内容可比对，"
              f"跳过检查（上游应拦截空稿，此处仅兜底）", file=sys.stderr)
        return 2

    results = []
    label_texts: list[tuple[str, str]] = []
    if args.per_file:
        if args.save_metrics or args.baseline_path:
            print("提示：--save-metrics/--baseline 仅支持合并模式，本次已忽略", file=sys.stderr)
        for f in files:
            text, _ = splib.read_text(f)
            res = splib.layered_check(text, fingerprint, genre=args.genre,
                                      delta_max_override=args.delta_max,
                                      lang=pack_lang)
            results.append((f.name, res["rows"], None, res))
            label_texts.append((f.name, text))
    else:
        parts = [splib.read_text(f)[0] for f in files]
        text = "\n\n".join(parts)
        res = splib.layered_check(text, fingerprint, genre=args.genre,
                                  delta_max_override=args.delta_max,
                                  lang=pack_lang)
        rows = res["rows"]
        diffs = None
        if args.baseline_path:
            baseline = splib.load_json(args.baseline_path)
            diffs = splib.baseline_diff(rows, baseline)
            print(f"    与基线对比（{args.baseline_path}）：")
            for d in diffs:
                mark = "⚠️ 回归" if d["regression"] else "    "
                print(f"    {mark} {d['path']}: 基线 {d['baseline']} → 本次 {d['actual']}（Δ{d['delta']}）")
        if args.save_metrics:
            splib.dump_json(res["metrics"], args.save_metrics)
            print(f"    实测指标已存档：{args.save_metrics}")
        results.append((f"合并 {len(files)} 个文件", rows, diffs, res))
        label_texts.append((f"合并 {len(files)} 个文件", text))

    for label, rows, _, res in results:
        if res.get("language_mismatch"):
            print(f"{label}: ⛔ [语言不匹配] 包语言 {res['pack_language']}，"
                  f"文本语言 {res['text_language']}——未做验收判定")
            for n in res["notes"]:
                print(f"    {n}")
            continue
        ok = splib.all_ok(rows)
        bad = [r for r in rows if not r["ok"]]
        status = "✅ 通过" if ok else f"❌ 不达标（{len(bad)}/{len(rows)} 项）"
        print(f"{label}: {status}")
        for ln in _meta_lines(res):
            print(f"    {ln}")
        for r in bad:
            act = "缺失" if r["actual"] is None else r["actual"]
            print(f"    {r['path']}: 目标 {r['target']}，实际 {act}"
                  + (f"，容差 {r['tolerance']}" if r["tolerance"] is not None else ""))

    # 思想层 advisory（v0.3）：motif 密度对照。永不改变 ok / 退出码。
    if args.thought:
        thought_path = pack_dir / "thought.md"
        if not thought_path.is_file():
            print("提示（--thought）：包无 thought.md，无 motif 对照可输出")
        else:
            ttext = thought_path.read_text(encoding="utf-8")
            motifs = splib.parse_motif_list(ttext)
            corpus_rates = splib.parse_motif_stats(ttext)
            if not motifs:
                print("提示（--thought）：thought.md 缺少「motif 词表：」行")
            else:
                unit = "次/千词" if pack_lang == "en" else "次/千字"
                print(f"motif 密度对照（advisory——意象可堆砌，仅供判读参考，"
                      f"不进判定；单位 {unit}）：")
                for label, txt in label_texts:
                    rates = splib.count_motifs(txt, motifs, lang=pack_lang)
                    cells = "；".join(
                        f"{w} 语料 {corpus_rates.get(w, 0.0):.2f} vs 本文 {rates[w]:.2f}"
                        for w in motifs)
                    print(f"    [{label}] {cells}")

    overall = all(splib.all_ok(rows) for _, rows, _, _ in results)
    if args.json_out:
        splib.dump_json({"pack": str(pack_dir), "results": [
            {"label": l, "rows": rows, "meta": {
                "genre": res["genre"], "layer_used": res["layer_used"],
                "delta": res["delta"], "delta_counted": res["delta_counted"],
                "delta_note": res["delta_note"]}}
            for l, rows, _, res in results]}, args.json_out)
    if args.report_out:
        Path(args.report_out).write_text(
            render_report(pack_dir.name, results), encoding="utf-8", newline="\n")
        print(f"报告已写入：{args.report_out}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
