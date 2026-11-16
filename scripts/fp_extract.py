# -*- coding: utf-8 -*-
"""fp_extract：对语料计算风格指纹原始指标。

用法：
    python scripts/fp_extract.py <语料文件或目录...> [--json OUT.json] [--lang auto|zh|en]

输出人类可读摘要；--json 同时写出完整指标（含 top_chars / fourgram_top、
英文的 top_words / bigram_top），供建档时人工选取 target 与容差，生成
fingerprint.json。--lang 默认 auto：按 CJK 占比自动判定（中文语料行为不变）。

中文单位=字（句长/段长按非空白字符计）；英文单位=词（sentence_length、
paragraph.p50_len、punctuation_per_1k 全按词计）。两条链路指标键名同构，
共用阈值树与比对器。

零第三方依赖（可选增强：若环境装有 jieba，中文语料将附加词频统计）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import splib  # noqa: E402


def main() -> int:
    splib.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="计算风格指纹原始指标")
    ap.add_argument("inputs", nargs="+", help="语料文件或目录（.txt/.md）")
    ap.add_argument("--json", dest="json_out", help="完整指标输出 JSON 路径")
    ap.add_argument("--lang", default="auto", choices=["auto", "zh", "en"],
                    help="语料语言：auto=按 CJK 占比自动判定（默认），zh/en 强制")
    ap.add_argument("--delta-profile", action="store_true",
                    help="附带 Burrows Delta 作者档案（每个输入文件为一个样本），"
                         "随 JSON 输出，可经 build_delta 合入风格包")
    ap.add_argument("--genre-layers", action="store_true",
                    help="附带文体分层预览：每个输入文件的 auto 判定与分层归属"
                         "（正式写入指纹用 build_delta.py --layered）")
    ap.add_argument("--exclude", nargs="*", default=[], metavar="NAME",
                    help="剔除样本（文件名或 stem，可多个）——离群章剔除后重算")
    args = ap.parse_args()

    files = splib.collect_text_files(args.inputs)
    if args.exclude:
        excl = set(args.exclude)
        kept = [f for f in files if f.stem not in excl and f.name not in excl]
        print(f"已剔除 {len(files) - len(kept)} 个样本：{', '.join(sorted(excl))}")
        files = kept
    if not files:
        print("错误：未找到任何 .txt/.md 文件", file=sys.stderr)
        return 2

    parts = []
    encs = set()
    named = []
    for f in files:
        text, enc = splib.read_text(f)
        encs.add(enc)
        parts.append(text)
        named.append((f.stem, text))
    full = "\n\n".join(parts)
    use_lang = splib.normalize_lang(args.lang, full)
    unit = "词" if use_lang == splib.LANG_EN else "字"
    m = splib.compute_metrics(full, use_lang)
    m["language"] = use_lang

    print(f"文件数：{len(files)}（编码：{', '.join(sorted(encs))}）")
    print(f"语言：{use_lang}（单位={unit}）")
    if use_lang == splib.LANG_EN:
        print(f"总词数：{m['words_total']}（字符 {m['chars_total']}）")
    else:
        print(f"总字符数：{m['chars_total']}")

    if args.genre_layers:
        print("文体分层预览（判据：对话段占比 ≥0.15 → narrative）:")
        for name, text in named:
            det = splib.detect_genre(text, lang=use_lang)
            print(f"  {name} → {det['genre']}（对话段占比 {det['dialogue_para_ratio']:.0%}，"
                  f"置信 {det['confidence']}）")
        print()
    s, p = m["sentence_length"], m["paragraph"]
    print(f"句子：{s['count']} 句，长度 P25/P50/P75 = {s['p25']}/{s['p50']}/{s['p75']}，"
          f"均值 {s['mean']}（{unit}）")
    print(f"段落：{p['count']} 段，P50 长度 {p['p50_len']}（{unit}），"
          f"对话段落占比 {p['dialogue_para_ratio']:.1%}")
    if use_lang == splib.LANG_EN:
        print(f"引号内容占比：{m['quote_char_ratio']:.1%}")
    else:
        print(f"引号内容占比：{m['quote_char_ratio']:.1%}；"
              f"叠词率：{m['reduplication_per_1k']}/千字")
    punct = "  ".join(f"{ch}={v}" for ch, v in m["punctuation_per_1k"].items())
    print(f"标点/千{unit}：{punct}")
    if use_lang == splib.LANG_EN:
        print(f"高频词 top10：{' '.join(w['word'] for w in m['top_words'][:10])}")
        if m["bigram_top"]:
            print(f"高频二元组：{' / '.join(m['bigram_top'][:10])}")
    else:
        print(f"高频字 top10：{' '.join(c['char'] for c in m['top_chars'][:10])}")
        if m["fourgram_top"]:
            print(f"高频四字组：{' / '.join(m['fourgram_top'][:10])}")

    if use_lang != splib.LANG_EN:
        try:
            import jieba  # type: ignore
            words = [w for w in jieba.lcut(full) if len(w) >= 2 and splib.CJK_RE.fullmatch(w)]
            from collections import Counter
            top_words = Counter(words).most_common(30)
            m["top_words_jieba"] = [{"word": w, "count": n} for w, n in top_words]
            print(f"[jieba 增强] 高频词 top10：{' / '.join(w for w, _ in top_words[:10])}")
        except ImportError:
            pass

    if args.delta_profile:
        m["delta_profile"] = splib.build_delta_profile(parts, lang=use_lang)
        prof_key = "words" if use_lang == splib.LANG_EN else "chars"
        print(f"[Delta] 档案：{m['delta_profile']['top_n']} 高频{unit} × "
              f"{m['delta_profile']['n_samples']} 样本")
        assert prof_key in m["delta_profile"]

    if args.json_out:
        splib.dump_json(m, args.json_out)
        print(f"完整指标已写入：{args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
