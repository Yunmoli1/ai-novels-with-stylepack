# -*- coding: utf-8 -*-
"""英文语言层行为锁定：语言判定 / 英文指标 / 词级 Delta / 语言护栏 / CLI。

对应 v0.13.17「语言是包的属性」：中文路径逐字节不变（由既有 195 用例锁定），
本文件只覆盖英文链路与不匹配护栏。零网络、零第三方依赖。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

S = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(S / "scripts"))

import splib  # noqa: E402
from test_gbk_console import _run  # noqa: E402

EN_A = (
    "Mr. Smith walked into the room and saw a letter on the desk. He picked it up "
    "slowly, turned it over, and began to read. The rain kept falling outside. "
    "\"Who sent this?\" he asked the empty room. Nobody answered him."
)
EN_B = (
    "The house stood at the end of the lane, quiet and grey. She had not slept "
    "for two nights. Every sound in the hall made her look up, and every shadow "
    "seemed to move. \"I should go,\" she said, but she did not move at all."
)
ZH_A = "他走进屋里，看见桌上摆着一封信。他拿起信，拆开看了起来。窗外一直在下雨。"


class TestDetectLang(unittest.TestCase):
    def test_zh_en_and_mixed(self):
        self.assertEqual(splib.detect_lang(ZH_A), "zh")
        self.assertEqual(splib.detect_lang(EN_A), "en")
        # 中文为主 + 少量英文台词 → 仍判中文（语言判定是整篇口径）
        self.assertEqual(splib.detect_lang(ZH_A + " \"OK.\" "), "zh")

    def test_normalize_lang(self):
        self.assertEqual(splib.normalize_lang(None, EN_A), "en")
        self.assertEqual(splib.normalize_lang("auto", EN_A), "en")
        self.assertEqual(splib.normalize_lang("zh-CN", ""), "zh")
        self.assertEqual(splib.normalize_lang("en-US", ""), "en")


class TestEnglishMetrics(unittest.TestCase):
    def test_unit_is_word_and_sentences_split_on_period(self):
        m = splib.compute_metrics(EN_A, "en")
        self.assertEqual(m["unit"], "word")
        self.assertEqual(m["words_total"], len(splib.words_of(EN_A)))
        # 句号分句：整段不是一句（中文旧实现会把它当一句）
        self.assertGreaterEqual(m["sentence_length"]["count"], 4)
        self.assertLess(m["sentence_length"]["mean"], 30)
        self.assertEqual(m["reduplication_per_1k"], 0.0)
        self.assertEqual(m["top_chars"], [])

    def test_abbreviation_does_not_split(self):
        sents = splib.split_sentences_en("Mr. Smith arrived. He sat down.")
        self.assertEqual(len(sents), 2)

    def test_top_words_and_ascii_punctuation(self):
        m = splib.compute_metrics(EN_A, "en")
        self.assertTrue(m["top_words"])
        self.assertIn(".", m["punctuation_per_1k"])
        self.assertNotIn("。", m["punctuation_per_1k"])

    def test_chinese_metrics_unchanged(self):
        m = splib.compute_metrics(ZH_A, "zh")
        self.assertNotIn("unit", m)
        self.assertEqual(m["sentence_length"]["count"], 3)
        self.assertEqual(m["reduplication_per_1k"], m["reduplication_per_1k"])
        self.assertTrue(m["top_chars"])


class TestEnglishThresholdsAndDelta(unittest.TestCase):
    def test_threshold_tree_has_no_reduplication(self):
        tree = splib.derive_thresholds([EN_A, EN_B], lang="en")
        self.assertNotIn("reduplication_per_1k", tree)
        self.assertIn("punctuation_per_1k", tree)
        self.assertTrue(all(k in (",", ".", ";", ":", "!", "?", "—", "…")
                            for k in tree["punctuation_per_1k"]))
        for path, leaf in splib.iter_target_leaves(tree):
            self.assertIn("tolerance_abs", leaf)

    def test_word_level_delta_profile(self):
        prof = splib.build_delta_profile([EN_A, EN_B], top_n=20, lang="en")
        self.assertEqual(prof["unit"], "word")
        self.assertIn("words", prof)
        self.assertNotIn("chars", prof)
        d1 = splib.delta_distance(EN_A, prof)
        d2 = splib.delta_distance("Completely different words appear here now.", prof)
        self.assertLess(d1, d2)
        # 中文档案仍走字级（向后兼容）
        zprof = splib.build_delta_profile([ZH_A, ZH_A + ZH_A], top_n=20)
        self.assertIn("chars", zprof)

    def test_metric_matrix_language_keys(self):
        keys_en, rows = splib.build_metric_matrix([("a", EN_A), ("b", EN_B)], lang="en")
        self.assertEqual(len(keys_en), 14)
        self.assertNotIn("reduplication_per_1k", keys_en)
        self.assertEqual(len(rows), 2)
        keys_zh, _ = splib.build_metric_matrix([("a", ZH_A), ("b", ZH_A)], lang="zh")
        self.assertEqual(len(keys_zh), 12)


class TestEnglishGenre(unittest.TestCase):
    def test_unmatched_quote_does_not_swallow_next_lines(self):
        text = '\"Unclosed line here\n\nNext paragraph \"closed\" here.'
        self.assertEqual(splib.quote_chars_len_en(text), len("closed"))

    def test_dialogue_heavy_english_is_narrative(self):
        text = "\n\n".join(['\"Hello,\" he said.'] * 5
                            + ["The road was empty and the sky was grey."] * 2)
        det = splib.detect_genre(text, lang="en")
        self.assertEqual(det["genre"], "narrative")
        self.assertLess(det["quote_char_ratio"], 0.9)   # 跨行吞并会虚高到接近 1
        self.assertAlmostEqual(det["dialogue_para_ratio"], 5 / 7, places=2)

    def test_plain_english_is_essay(self):
        det = splib.detect_genre("The road was empty.\n\nThe sky was grey.", lang="en")
        self.assertEqual(det["genre"], "essay")


class TestLanguageGuard(unittest.TestCase):
    def _pack(self, lang, corpus):
        return {"language": lang, "metrics": splib.derive_thresholds(corpus, lang=lang),
                "delta_profile": splib.build_delta_profile(corpus, lang=lang)}

    def test_english_text_against_chinese_pack_flagged(self):
        res = splib.layered_check(EN_A, self._pack("zh", [ZH_A, ZH_A + ZH_A]))
        self.assertTrue(res["language_mismatch"])
        self.assertEqual(res["pack_language"], "zh")
        self.assertEqual(res["text_language"], "en")
        self.assertFalse(res["ok"])
        self.assertEqual(res["rows"], [])
        self.assertIn("语言不匹配", res["notes"][0])

    def test_matched_languages_do_not_raise_guard(self):
        res = splib.layered_check(EN_A, self._pack("en", [EN_A, EN_B]))
        self.assertFalse(res.get("language_mismatch", False))
        self.assertTrue(res["rows"])

    def test_legacy_pack_without_language_defaults_to_zh(self):
        res = splib.layered_check(EN_A, {"metrics": splib.derive_thresholds([ZH_A])})
        self.assertTrue(res["language_mismatch"])
        self.assertEqual(res["pack_language"], "zh")


class TestEnglishCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "a.txt").write_text(EN_A + "\n\n" + EN_B, encoding="utf-8")
        (self.dir / "b.txt").write_text(EN_B + "\n\n" + EN_A, encoding="utf-8")

    def test_fp_extract_lang_en_prints_words(self):
        r = _run([sys.executable, str(S / "scripts" / "fp_extract.py"),
                  str(self.dir / "a.txt"), "--lang", "en"])
        self.assertEqual(r.returncode, 0, r.stderr or "")
        self.assertIn("总词数", r.stdout)
        self.assertIn("单位=词", r.stdout)
        self.assertIn("高频词", r.stdout)

    def test_build_delta_writes_language(self):
        pack = self.dir / "pack"
        pack.mkdir()
        r = _run([sys.executable, str(S / "scripts" / "build_delta.py"), str(self.dir),
                  "--pack", str(pack), "--lang", "en", "--layered", "--top-n", "20"])
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        fp = json.loads((pack / "fingerprint.json").read_text(encoding="utf-8"))
        self.assertEqual(fp["language"], "en")
        self.assertIn("words", fp["delta_profile"])
        self.assertNotIn("reduplication_per_1k", fp["metrics"])

    def test_fp_check_guard_and_pass(self):
        pack = self.dir / "pack"
        pack.mkdir()
        _run([sys.executable, str(S / "scripts" / "build_delta.py"), str(self.dir),
              "--pack", str(pack), "--lang", "en", "--layered", "--top-n", "20"])
        ok = _run([sys.executable, str(S / "scripts" / "fp_check.py"), str(pack),
                   str(self.dir / "a.txt")])
        self.assertEqual(ok.returncode, 0, (ok.stdout or "") + (ok.stderr or ""))
        zh = self.dir / "zh.txt"
        zh.write_text(ZH_A * 3, encoding="utf-8")
        bad = _run([sys.executable, str(S / "scripts" / "fp_check.py"), str(pack), str(zh)])
        self.assertEqual(bad.returncode, 1, (bad.stdout or "") + (bad.stderr or ""))
        self.assertIn("[语言不匹配]", bad.stdout)

    def test_borrow_check_word_window(self):
        pack = self.dir / "borrowpack"
        pack.mkdir()
        (pack / "exemplars.md").write_text(
            "# 范例\n\n### 1. 测试\n\n> the quick brown fox jumps over the lazy dog\n",
            encoding="utf-8")
        draft = self.dir / "draft.txt"
        draft.write_text("I saw that the quick brown fox jumps over the lazy dog today.",
                         encoding="utf-8")
        hit = _run([sys.executable, str(S / "scripts" / "borrow_check.py"), str(draft),
                    "--pack", str(pack)])
        self.assertEqual(hit.returncode, 1, (hit.stdout or "") + (hit.stderr or ""))
        self.assertIn("范例 1", hit.stdout)
        clean = self.dir / "clean.txt"
        clean.write_text("She walked home slowly and said nothing to anyone.", encoding="utf-8")
        miss = _run([sys.executable, str(S / "scripts" / "borrow_check.py"), str(clean),
                     "--pack", str(pack)])
        self.assertEqual(miss.returncode, 0, (miss.stdout or "") + (miss.stderr or ""))


class TestWebCreationLang(unittest.TestCase):
    """网页生成环的语言分派：提示词双语 + max_tokens 换算（v0.13.17）。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(S / "web"))
        import creation  # noqa: E402
        import routes_create  # noqa: E402
        cls.creation = creation
        cls.rc = routes_create

    def test_system_prompt_switch(self):
        c = self.creation
        self.assertIs(c.system_prompt("zh"), c.SYSTEM)
        self.assertIs(c.system_prompt("en"), c.SYSTEM_EN)
        self.assertIs(c.system_prompt("en-US"), c.SYSTEM_EN)
        self.assertEqual(c.unit("en"), "words")
        self.assertEqual(c.unit("zh"), "字")

    def test_prompts_have_no_cjk_in_english(self):
        c = self.creation
        ctx = "(assembly context)"
        prompts = [
            c.outline_prompt(3, "Rain", ["a", "b"], ctx, "", lang="en"),
            c.beats_prompt(3, "Rain", {"title": "Rain"}, [], "n", 2500, lang="en"),
            c.prose_prompt(3, "Rain", {"title": "Rain"}, [], "n", "none", ctx,
                           2500, lang="en"),
            c.revise_prompt(3, "Rain", [], ctx, "draft text", "reports", 2500,
                            lang="en"),
            c.ending_check_prompt("Rain", "tail text", lang="en"),
            c.rewrite_prompt(3, "Rain", [], ctx, "draft", "frag", "instruction",
                             lang="en"),
            c.memory_digest_prompt(3, "Rain", [], "text", lang="en"),
        ]
        for text in prompts:
            self.assertFalse([ch for ch in text if "\u4e00" <= ch <= "\u9fff"],
                             text[:80])

    def test_english_length_unit_is_words(self):
        c = self.creation
        en = c.prose_prompt(3, "Rain", {}, [], "n", "none", "(ctx)", 2500, lang="en")
        self.assertIn("2500 words", en)
        zh = c.prose_prompt(3, "雨", {}, [], "n", "none", "(ctx)", 2500)
        self.assertIn("2500 字", zh)
        draft = " ".join(["word"] * 100)
        rev = c.revise_prompt(3, "Rain", [], "(ctx)", draft, "", 100, lang="en")
        self.assertIn("about 100 words", rev)   # 英文按词计数，不按字符
        dig = c.memory_digest_prompt(3, "Rain", [], "text", lang="en")
        self.assertIn("120 words", dig)

    def test_prose_budget_per_language(self):
        rc = self.rc
        cfg = {"prose_max_tokens": 3500}
        self.assertEqual(rc._prose_budget(cfg, 2500, "zh"), 3500)
        self.assertEqual(rc._prose_budget(cfg, 2500, "en"), 3975)
        self.assertEqual(rc._prose_budget(cfg, 0, "en"), 3500)

    def test_pack_language_reads_pack_json(self):
        with tempfile.TemporaryDirectory() as td:
            pdir = Path(td)
            (pdir / "pack.json").write_text('{"language": "en-US"}', encoding="utf-8")
            self.assertEqual(self.rc._pack_language(pdir), "en")
            (pdir / "pack.json").write_text('{"name": "x"}', encoding="utf-8")
            self.assertEqual(self.rc._pack_language(pdir), "zh")
            self.assertEqual(self.rc._pack_language(pdir / "missing"), "zh")


class TestEnglishAiCliche(unittest.TestCase):
    """英文 AI 腔门（v0.13.17 P3）：词边界计数、次/千词、结构级只留省略号与直引号。"""

    # 干净样本：无直引号、无省略号、无词表命中（EN_A 里有 \"...\" 会被直引号规则抓到）
    CLEAN = ("Mr. Smith walked into the room and saw a letter on the desk. "
             "He picked it up slowly and began to read. The rain kept falling outside. "
             "Nobody came to the door that evening.")

    @classmethod
    def setUpClass(cls):
        import ai_cliche_check as acc
        cls.acc = acc
        cls.words = acc.load_words(lang="en")
        cls.pats = acc.load_patterns(lang="en")

    def test_en_tables_loaded(self):
        w = self.words
        self.assertTrue(w["tier1"] and w["tier2"] and w["tier3"])
        self.assertIn("phone", w["tier2"])
        self.assertIn("a testament to", w["tier3"])
        # 英文结构级不照搬中文破折号棘轮（英文侧反向：人类多用、AI 少用）
        self.assertEqual([p["id"] for p in self.pats],
                         ["ellipsis_char", "straight_quote"])
        self.assertEqual(self.acc.VOCAB_BY_LANG["en"], (0.6, 1.2))

    def test_clean_human_english_passes(self):
        r = self.acc.check(self.CLEAN * 3, self.words, set(), self.pats, "en")
        self.assertEqual(r["verdict"], "ok")
        self.assertEqual(r["unit"], "次/千词")

    def test_word_boundary_not_substring(self):
        # 中文表按子串计；英文必须按词边界——"phone" 不能命中 "telephone"/"headphones"
        text = "The telephone rang. He put on his headphones and said nothing."
        r = self.acc.check(text, self.words, set(), self.pats, "en")
        self.assertEqual(r["hits"], 0)
        self.assertEqual(self.acc.count_hits("telephone phone", "phone", "en"), 1)
        self.assertEqual(self.acc.count_hits("telephone phone", "phone", "zh"), 2)

    def test_modern_prop_flags_warn(self):
        text = ("Okay, she said, checking her phone. It was a testament to nothing. "
                + self.CLEAN * 2)
        r = self.acc.check(text, self.words, set(), self.pats, "en")
        self.assertEqual(r["verdict"], "warn")
        self.assertEqual(r["per_tier"]["tier1"].get("okay"), 1)
        self.assertEqual(r["per_tier"]["tier2"].get("phone"), 1)
        self.assertIn("a testament to", r["per_tier"]["tier3"])

    def test_ellipsis_structural_rule(self):
        text = self.CLEAN + " He waited\u2026 and waited\u2026 and waited\u2026 and waited\u2026"
        r = self.acc.check(text, self.words, set(), self.pats, "en")
        self.assertEqual(r["structure"][0]["level"], "warn")
        # 直引号：19 世纪正文应为弯引号（模型直出通常是直引号，这条就是排版提醒）
        r2 = self.acc.check('"Hello," she said. ' * 30, self.words, set(), self.pats, "en")
        self.assertEqual(r2["structure"][1]["level"], "warn")

    def test_exemption_is_case_insensitive(self):
        words = {"tier1": [], "tier2": [], "tier3": ["perhaps"]}
        text = "Perhaps she was right. Perhaps not. " + self.CLEAN
        self.assertEqual(self.acc.check(text, words, set(), None, "en")["hits"], 2)
        # 豁免表大小写不敏感：limits.md 里写 Perhaps 也要免掉 perhaps
        r = self.acc.check(text, words, {"Perhaps"}, None, "en")
        self.assertEqual(r["hits"], 0)

    def test_chinese_path_unchanged(self):
        dirty = "他不禁缓缓抬头，嘴角上扬，月光如水。" + "正常句子。" * 20
        r = self.acc.check(dirty, self.acc.load_words(), set(),
                           self.acc.load_patterns(), "zh")
        self.assertEqual(r["per_tier"]["tier1"].get("不禁"), 1)
        self.assertEqual(r["unit"], "次/千字")
        self.assertGreater(r["density"], 1.0)
        clean = self.acc.check("平实的叙述。" * 50, self.acc.load_words(), set(),
                               self.acc.load_patterns(), "zh")
        self.assertEqual(clean["verdict"], "ok")

    def test_cli_lang_en(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "d.txt"
            f.write_text("Okay, she checked her phone. " + EN_A * 3, encoding="utf-8")
            r = _run([sys.executable, str(S / "scripts" / "ai_cliche_check.py"),
                      str(f), "--lang", "en"])
            self.assertEqual(r.returncode, 1, (r.stdout or "") + (r.stderr or ""))
            self.assertIn("（en）", r.stdout)
            self.assertIn("次/千词", r.stdout)
            clean = Path(td) / "c.txt"
            clean.write_text(self.CLEAN * 3, encoding="utf-8")
            r2 = _run([sys.executable, str(S / "scripts" / "ai_cliche_check.py"),
                       str(clean), "--lang", "en"])
            self.assertEqual(r2.returncode, 0, (r2.stdout or "") + (r2.stderr or ""))

    def test_pack_language_switch(self):
        with tempfile.TemporaryDirectory() as td:
            pdir = Path(td) / "enpack"
            pdir.mkdir()
            (pdir / "pack.json").write_text('{"language": "en"}', encoding="utf-8")
            self.assertEqual(self.acc.pack_language(pdir), "en")
            self.assertEqual(self.acc.detect_lang(EN_A, pdir), "en")
            (pdir / "pack.json").write_text('{"language": "zh"}', encoding="utf-8")
            self.assertEqual(self.acc.detect_lang(EN_A, pdir), "zh")
            self.assertEqual(self.acc.detect_lang(EN_A), "en")
            self.assertEqual(self.acc.detect_lang(ZH_A), "zh")


if __name__ == "__main__":
    unittest.main()
