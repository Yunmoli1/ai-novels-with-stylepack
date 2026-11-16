# -*- coding: utf-8 -*-
"""build_delta：为风格包构建 Burrows Delta 作者档案（写入 fingerprint.json）。

用法：
    python scripts/build_delta.py <语料目录> --pack <风格包目录> [--top-n 150] [--layered]

语料目录的每个 .txt/.md 文件视为一个样本。默认仅重建顶层混合 delta_profile；
--layered 额外做三件事（v0.2.3 分层指纹）：
  1. 按文体分层（段首引号段 + 引号字占比双信号检测）写入 genres.*.metrics / delta_profile
  2. 层内留一算真迹及格线写入 self_check（n<3 的层线置空并注明）
  3. 打印分层归属与及格线，供建档人工复核

指纹内容发生实际变化时，自动联动升 pack.json 的 version（patch 位）与 updated，
并在 changelog 追加一条重建记录——防止「指纹已更新、元数据还是旧版」的版本误导。
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import splib  # noqa: E402


def _bump_pack_meta(pack: Path, reason: str) -> None:
    """指纹变了就联动 pack.json：patch 位 +1、刷新 updated、changelog 追加。"""
    pj = pack / "pack.json"
    if not pj.is_file():
        return
    meta = splib.load_json(pj)
    today = datetime.date.today().isoformat()
    old = str(meta.get("version", "0.0.0"))
    parts = old.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        parts[2] = str(int(parts[2]) + 1)
        meta["version"] = ".".join(parts)
    meta["updated"] = today
    meta.setdefault("changelog", []).append(
        {"version": meta.get("version", old), "date": today, "changes": reason})
    splib.dump_json(meta, pj)
    print(f"  pack.json 版本联动：{old} → {meta.get('version')}（{reason}）")


def main() -> int:
    splib.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="构建 Burrows Delta 档案（可选分层指纹）")
    ap.add_argument("corpus", help="语料目录（每文件 = 一个样本）")
    ap.add_argument("--pack", required=True, help="风格包目录")
    ap.add_argument("--top-n", type=int, default=150)
    ap.add_argument("--lang", default="auto", choices=["auto", "zh", "en"],
                    help="语料语言：auto=按 CJK 占比自动判定（默认），zh/en 强制；"
                         "决定指纹 language、量纲（字/词）与 Delta 档案类型")
    ap.add_argument("--layered", action="store_true",
                    help="按文体分层重建：genres 阈值树 + 分层 delta_profile + 层内留一 self_check")
    ap.add_argument("--exclude", nargs="*", default=[], metavar="NAME",
                    help="剔除样本（文件名或 stem，可多个）——离群章剔除后重算")
    args = ap.parse_args()

    files = splib.collect_text_files([args.corpus])
    if args.exclude:
        excl = set(args.exclude)
        kept = [f for f in files if f.stem not in excl and f.name not in excl]
        print(f"已剔除 {len(files) - len(kept)} 个样本：{', '.join(sorted(excl))}")
        files = kept
    if len(files) < 1:
        print("错误：语料目录没有文本文件", file=sys.stderr)
        return 2
    named = [(f.stem, splib.read_text(f)[0]) for f in files]
    corpus_text = "\n\n".join(t for _, t in named)
    use_lang = splib.normalize_lang(args.lang, corpus_text)
    unit = "词" if use_lang == splib.LANG_EN else "字"
    print(f"语料语言：{use_lang}（单位={unit}）")
    profile = splib.build_delta_profile([t for _, t in named], top_n=args.top_n,
                                        lang=use_lang)

    pack = Path(args.pack)
    fp_path = pack / "fingerprint.json"
    fingerprint = splib.load_json(fp_path) if fp_path.is_file() else {}  # 全新包目录直接可用
    fingerprint["delta_profile"] = profile
    fingerprint["language"] = use_lang
    fingerprint.setdefault("notes", "")
    loo = None
    layers = None
    if args.layered:
        layers = splib.build_genre_layers(named, top_n=args.top_n, lang=use_lang)
        loo = splib.leave_one_out(named, top_n=args.top_n, lang=use_lang)
        fingerprint["genres"] = layers["genres"]
        fingerprint["self_check"] = loo
        # 顶层混合 metrics（带容差）+ 完整实测快照——v0.7.2：新蒸馏包不过
        # fp_check 的混合层就从来没被写过，validate 会因无容差叶拒绝定稿
        fingerprint["metrics"] = splib.derive_thresholds([t for _, t in named],
                                                         lang=use_lang)
        fingerprint["reference"] = splib.compute_metrics(corpus_text, use_lang)

    # 内容变更检测 + 单次写盘 + 元数据联动
    new_text = json.dumps(fingerprint, ensure_ascii=False, indent=2) + "\n"
    old_bytes = fp_path.read_bytes() if fp_path.is_file() else None
    changed = old_bytes != new_text.encode("utf-8")
    fp_path.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"Delta 档案已写入 {fp_path}")
    print(f"  样本数 {profile['n_samples']}，高频{unit} {profile['top_n']} 个")
    if not changed:
        print("  指纹内容无变化，pack.json 版本不动")

    if args.layered and layers is not None:
        print("  分层归属：")
        for name, det in layers["assignment"].items():
            print(f"    {name} → {det['genre']}（段首引号段 {det['dialogue_para_ratio']:.0%}，"
                  f"引号字占比 {det['quote_char_ratio']:.0%}，置信 {det['confidence']}）")
        for g, layer in layers["genres"].items():
            m = layer["metrics"]
            p50 = m["sentence_length"]["p50"]["target"]
            dl = m["paragraph"]["dialogue_para_ratio"]["target"]
            print(f"  层 {g}：{len(layer['samples'])} 篇 "
                  f"（{('、'.join(layer['samples']))}），句长 P50 {p50}，对话段占比 {dl}")
            sc = (loo or {}).get(g, {})
            if sc.get("delta_max") is not None:
                print(f"    留一及格线：delta_max={sc['delta_max']}"
                      f"（p50={sc.get('delta_p50')}，n={sc['n']}）")
            else:
                print(f"    留一及格线：不可标定（{sc.get('note', 'n<3')}），该层 Delta 暂不进判定")
        print(f"分层指纹已写入 {fp_path}")

    if changed:
        _bump_pack_meta(pack, "分层指纹重建" if args.layered else "Delta 档案重建")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
