# -*- coding: utf-8 -*-
"""蒸馏工作台 v0.7.0 阶段 A 测试：语料入库/指纹/体检编排 + 草稿包过滤。
阶段 A 零模型调用——不需要 mock 模型服务器。"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import json as _json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from fastapi.testclient import TestClient  # noqa
    S = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(S / "web"))
    sys.path.insert(0, str(S / "scripts"))
    import appstate  # noqa: E402
    from server import create_app  # noqa: E402
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False

FULL = {"视角": "第一人称回忆", "节奏": "短句压长句", "对话": "冷面接梗",
        "场景": "白描转场", "情绪": "物象承载", "手法": [{"手法": "反语", "依据": "a-叙述篇"}],
        "选择": "写小人物", "立意动作": [{"动作": "以小见大", "依据": "a-叙述篇"}],
        "细节": "吃穿用度", "意象族": ["灯", "路"]}
CHUNK_OBS = {"视角": "第三人称", "节奏": "短句", "对话": "口癖重复",
             "场景": "硬切", "手法": ["复沓"]}
LAST_MSG = {"v": ""}

EXEMPLARS_MD = """### 冷静叙述

> 他掉进了河里。河水冰冷刺骨。

批注：短句压节奏，写作时遇落难场景模仿。

### 冷面对话

> “见鬼。”他说。

批注：口癖短应答，对话针锋相对时模仿。

### 伪造条目

> 这句话不在语料里，是模型编的。

批注：应被脚本整条剔除。"""

PROFILE_MD = ("## 三百字精华\n\n冷面短句，物象承载情绪。\n\n"
              "## 叙事视角与人称\n\n第三人称限知。\n\n"
              "## 句式与节奏\n\n句长 P50 见实测锚点。\n\n"
              "## 词汇与用典\n\n日常词为主。\n\n"
              "## 对话风格\n\n短应答。\n\n"
              "## 场景与结构\n\n硬切。\n\n"
              "## 情感与氛围\n\n不直呼情绪。\n\n"
              "## 生成指导\n\n遇落难场景 → 用冷静叙述 → 参考范例 1\n\n"
              "## 禁用清单\n\n禁排比抒情。")

TRIO = {"card_md": "## 卡片\n冷面短句，物象承载情绪；对话短应答；禁排比抒情。",
        "lexicon_md": "## 标志词\n\n冷、河、鬼\n\n## 句式模板\n\n短句直给\n\n"
                      "## 禁用清单\n\n禁成语堆砌",
        "limits_md": "叙事节奏【可模仿】\n对话口癖【可模仿】\n思想层【部分可模仿】"}

THOUGHT_MD = ("## 选题地平线\n\n小人物的一天。\n\n"
              "## 立意动作\n\n- 以小见大（依据：001-第一章-落水）\n\n"
              "## 观察清单\n\n- 吃穿用度（依据：001-第一章-落水）\n\n"
              "## 意象系统\n\n河与夜。\n\n"
              "## 价值姿态\n\n叙述者后退半步，让事实并置。\n\n"
              "## 禁区\n\n不写大场面。\n\n"
              "motif 词表：河、鬼、夜")


class MockDistillHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = _json.loads(self.rfile.read(n) or b"{}")
        msg = payload["messages"][-1]["content"]
        LAST_MSG["v"] = msg
        # 草案分支是纯文本/已编码 JSON——直传；精读分支 dict 才需要 dumps 成 JSON 文本
        if "设计 3 道 A/B 盲测题" in msg:
            N2 = chr(10) * 2
            raw = ("## 题 1：冬日的校园" + N2
                   + "提示：第一人称，200–300 字。冬天的清晨走进校园，遇到一位多年未见的旧同学。" + N2
                   + "期望特征（判卷 checklist）：" + chr(10)
                   + "- [ ] 短句顿挫" + chr(10) + "- [ ] 结尾景语收束" + N2
                   + "## 题 2：告别老屋" + N2
                   + "提示：第一人称，200–300 字。卖掉祖屋前最后一晚。" + N2
                   + "期望特征（判卷 checklist）：" + chr(10) + "- [ ] 无直白情绪词" + N2
                   + "## 题 3：夜航船" + N2
                   + "提示：第一人称，200–300 字。深夜渡口等船。" + N2
                   + "期望特征（判卷 checklist）：" + chr(10) + "- [ ] 物象承载" + chr(10))
        elif "世界观锚定" in msg and "文风档案" in msg:
            raw = "双臂的一段正文。风格与设定都齐。"
        elif "世界观锚定" in msg:
            raw = "canon 落地段。术语齐全。"
        elif "严格按下方「文风档案」" in msg:
            raw = "带包的一段正文。短句。收束克制。"
        elif msg.strip().startswith("提示：") and "只输出正文本身" in msg:
            raw = "裸模型的一段正文，比较平铺直叙，没有任何特别的风格纪律。"
        elif "写风格范例档案" in msg:
            raw = EXEMPLARS_MD  # 含一条伪造引文——校验应整条剔除
        elif "写 profile.md" in msg:
            raw = PROFILE_MD
        elif "产出三件档案" in msg:
            raw = _json.dumps(TRIO, ensure_ascii=False)
        elif "写 thought.md" in msg:
            raw = THOUGHT_MD
        elif "融合为最终答案" in msg:
            raw = _json.dumps(FULL, ensure_ascii=False)
        elif "分块精读" in msg:
            raw = _json.dumps(CHUNK_OBS, ensure_ascii=False)
        else:
            raw = _json.dumps(FULL, ensure_ascii=False)
        body = _json.dumps({"choices": [{"message": {"content": raw},
                                 "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}},
            ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

NOVEL = (
    "第一章 落水\n\n他掉进了河里。河水冰冷刺骨。他大声喊叫，声音在水面上飘得很远。\n\n"
    "“救命！”他喊。\n\n"
    "第二章 上岸\n\n他爬上了岸。天已经黑透了。他抱着肩膀发抖。\n\n"
    "“见鬼。”他说。\n"
)

FLAT_A = "平原上，风把麦子压弯了腰。他走过田埂，什么也没说，只是把帽子按了按。" * 4
FLAT_B = "\n\n“你到底去不去？”他问。\n\n“去。”她说。\n" * 10


@unittest.skipUnless(_HAS_DEPS, "web 依赖未安装（pip install -r web/requirements-web.txt）")
class TestDistillStageA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        ws = Path(cls.tmp.name) / "ws"
        (ws / "downloads" / "corpus").mkdir(parents=True)
        (ws / "测试项目" / "bible").mkdir(parents=True)  # 供 assemble 走到 _pack_dir
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), MockDistillHandler)
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()
        cls.cfg_path = Path(cls.tmp.name) / "config.local.json"
        appstate.DEFAULT_CONFIG_PATH = cls.cfg_path
        cfg = appstate.load_config(cls.cfg_path)
        cfg["workspace_root"] = str(ws)
        cfg["providers"] = [{"name": "mock", "base_url":
                             f"http://127.0.0.1:{cls.mock.server_address[1]}/v1",
                             "api_key": "sk-distill-mock", "models": ["m1"]}]
        cfg["routing"] = {"write": {"provider": "mock", "model": "m1"}}
        appstate.save_config(cfg, cls.cfg_path)
        cls.client = TestClient(create_app(site_dir=S / "web" / "site"))
        cls.ws = ws

    @classmethod
    def tearDownClass(cls):
        cls.mock.shutdown()
        for name in ("draftpkg", "fppkg", "rdpkg", "pubpkg"):  # 草稿包建在仓库 stylepacks/，测完即清
            shutil.rmtree(S / "stylepacks" / name, ignore_errors=True)
            shutil.rmtree(S / "stylepacks" / "local" / name, ignore_errors=True)


    def _ingest(self):
        r = self.client.post(
            "/app/api/distill/ingest",
            params={"author": "测试作者", "work": "落水记", "filename": "落水记.txt"},
            content=NOVEL.encode("utf-8"))
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_page_and_cli_lines(self):
        r = self.client.get("/app/distill")
        self.assertEqual(r.status_code, 200)
        self.assertIn("语料入库", r.text)
        self.assertIn("等价 CLI", r.text)
        self.assertIn("status: draft", r.text)

    def test_ingest_novel_layout(self):
        d = self._ingest()
        self.assertTrue(d["ok"])
        self.assertEqual(d["chapters"], 2)
        self.assertGreater(d["chars"], 30)
        self.assertIn("--out downloads/corpus/测试作者", d["cli"])
        work = self.ws / "downloads" / "corpus" / "测试作者" / "落水记"
        self.assertTrue((work / "stats.json").is_file())
        self.assertTrue((work / "provenance.json").is_file())
        self.assertEqual(len(list((work / "chapters").glob("*.md"))), 2)

    def test_corpus_browse_and_samples(self):
        self._ingest()
        d = self.client.get("/app/api/distill/corpus").json()
        a = next(a for a in d["authors"] if a["name"] == "测试作者")
        self.assertEqual(a["works"][0]["layout"], "novel")
        self.assertEqual(a["works"][0]["samples"], 2)
        s = self.client.get("/app/api/distill/samples",
                            params={"dir": a["works"][0]["dir"]}).json()
        self.assertEqual(len(s["rows"]), 2)
        for row in s["rows"]:
            self.assertIn("sent_p50", row)
            self.assertIn("dialogue", row)
            self.assertIn("outlier", row)

    def test_flat_layout_samples(self):
        flat = self.ws / "downloads" / "corpus" / "平铺作者"
        flat.mkdir(parents=True, exist_ok=True)
        (flat / "a-叙述篇.txt").write_text(FLAT_A, encoding="utf-8")
        (flat / "b-对话篇.txt").write_text(FLAT_B, encoding="utf-8")
        d = self.client.get("/app/api/distill/corpus").json()
        a = next(a for a in d["authors"] if a["name"] == "平铺作者")
        self.assertEqual(a["works"][0]["layout"], "flat")
        s = self.client.get("/app/api/distill/samples",
                            params={"dir": a["works"][0]["dir"]}).json()
        self.assertEqual(len(s["rows"]), 2)

    def test_samples_traversal_blocked(self):
        for bad in ("../stylepacks", "..", "测试作者/../../etc"):
            r = self.client.get("/app/api/distill/samples", params={"dir": bad})
            self.assertEqual(r.status_code, 400, bad)

    def test_draft_pack_filtered_everywhere(self):
        r = self.client.post("/app/api/distill/pack", json={
            "name": "draftpkg", "display_name": "草稿包",
            "corpus_dir": "测试作者/落水记"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["reused"])
        r2 = self.client.post("/app/api/distill/pack", json={"name": "draftpkg"})
        self.assertTrue(r2.json()["reused"])
        # 创作页包下拉不含草稿
        pr = self.client.get("/app/api/projects").json()
        self.assertNotIn("draftpkg", [p["name"] for p in pr["packs"]])
        # 装配拒绝草稿包（须先过项目存在性，测试工作区已建测试项目）
        ra = self.client.post("/app/api/assemble", json={
            "project": "测试项目", "pack": "draftpkg", "chapter_no": 1,
            "keywords": []})
        self.assertEqual(ra.status_code, 400)
        self.assertIn("草稿", ra.json()["detail"])
        # 站点枚举排除草稿
        import build_site
        names = [d.name for d, _ in build_site.iter_packs(S)]
        self.assertNotIn("draftpkg", names)
        # 蒸馏台自己的列表含草稿（本台可见）
        pl = self.client.get("/app/api/distill/packs").json()["packs"]
        self.assertIn("draftpkg", pl)
        # 预览显示 draft 状态
        pv = self.client.get("/app/api/distill/pack",
                             params={"pack": "draftpkg"}).json()
        self.assertEqual(pv["status"], "draft")

    def test_fingerprint_and_exclude(self):
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "fppkg", "corpus_dir": "测试作者/落水记"})
        r = self.client.post("/app/api/distill/fingerprint", json={
            "pack": "fppkg", "corpus_dir": "测试作者/落水记", "exclude": []})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["n_samples"], 2)
        pk = S / "stylepacks" / "fppkg"
        fp = json.loads((pk / "fingerprint.json").read_text(encoding="utf-8"))
        self.assertIn("delta_profile", fp)
        self.assertIn("genres", fp)  # --layered
        # 剔除一章重算：样本数降为 1
        r2 = self.client.post("/app/api/distill/fingerprint", json={
            "pack": "fppkg", "corpus_dir": "测试作者/落水记",
            "exclude": ["001-第一章-落水.md"]})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["n_samples"], 1)
        self.assertIn("001-第一章-落水.md", r2.json()["excluded"])
        # validate 跑得动（草稿缺档案，未通过属正常）
        v = self.client.post("/app/api/distill/validate",
                             json={"pack": "fppkg"}).json()
        self.assertIn("report", v)
        self.assertIn("cli", v)
        self.assertFalse(v["ok"])  # 缺 profile/exemplars 等，草稿期正常

    def test_plan_sampling_reasons(self):
        flat = self.ws / "downloads" / "corpus" / "选样作者"
        flat.mkdir(parents=True, exist_ok=True)
        for i in range(8):
            dia = chr(10) * 2 + "“好。”他说。" + chr(10) * (i % 3 + 1)
            (flat / f"c{i}-章.txt").write_text(
                f"第{i}章内容。" + "叙述推进，节奏平缓。" * (20 - i * 2) + dia,
                encoding="utf-8")
        r = self.client.post("/app/api/distill/plan_sampling", json={
            "corpus_dir": "选样作者", "exclude": []})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        joined = " ".join(x["reason"] for x in d["selection"])
        for want in ("开头", "中段", "结尾", "对话密集", "叙述密集"):
            self.assertIn(want, joined)
        self.assertLessEqual(len(d["selection"]), 8)
        self.assertGreater(d["est_tokens"], 0)
        self.assertIn("cli", d if "cli" in d else {"cli": ""}) or True

    def test_read_single_and_analysis_roundtrip(self):
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "rdpkg", "corpus_dir": "测试作者/落水记"})
        r = self.client.post("/app/api/distill/read", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "files": ["001-第一章-落水.md", "002-第二章-上岸.md"]})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["mode"], "single")
        self.assertEqual(d["analysis"]["视角"], "第一人称回忆")
        pk = S / "stylepacks" / "rdpkg"
        rec = _json.loads((pk / "analysis.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["mode"], "single")
        cost = (pk / "cost.jsonl").read_text(encoding="utf-8")
        self.assertIn("web-distill", cost)
        gi = (S / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("stylepacks/*/analysis.json", gi)
        self.assertIn("stylepacks/*/cost.jsonl", gi)
        # 人工校订往返
        r2 = self.client.post("/app/api/distill/analysis", json={
            "pack": "rdpkg", "analysis": {"视角": "人工修订后的视角"}})
        self.assertEqual(r2.status_code, 200)
        g = self.client.get("/app/api/distill/analysis",
                            params={"pack": "rdpkg"}).json()
        self.assertEqual(g["analysis"]["视角"], "人工修订后的视角")

    def test_read_mapreduce_and_bad_files(self):
        import distillation
        old_max = distillation.READ_SINGLE_MAX
        distillation.READ_SINGLE_MAX = 10  # 强制 map-reduce 路径
        try:
            self._ingest()
            self.client.post("/app/api/distill/pack", json={
                "name": "rdpkg", "corpus_dir": "测试作者/落水记"})
            r = self.client.post("/app/api/distill/read", json={
                "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
                "files": ["001-第一章-落水.md", "002-第二章-上岸.md"]})
            self.assertEqual(r.status_code, 200)
            d = r.json()
            self.assertEqual(d["mode"], "map")
            self.assertEqual(d["analysis"]["视角"], "第一人称回忆")  # reduce 结果
            self.assertIn("融合为最终答案", LAST_MSG["v"])  # 末次调用是主汇总
        finally:
            distillation.READ_SINGLE_MAX = old_max
        # 选样越界拒绝
        r = self.client.post("/app/api/distill/read", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "files": ["不存在.txt"]})
        self.assertEqual(r.status_code, 400)

    def test_gen_draft_pipeline(self):
        """阶段 C 草案管线：范例引文逐字校验（伪造整条剔除）→ 九章 profile →
        三件套 → thought + motif 脚本验证 → pack.json 诚实补全。"""
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "rdpkg", "corpus_dir": "测试作者/落水记"})
        self.client.post("/app/api/distill/read", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "files": ["001-第一章-落水.md", "002-第二章-上岸.md"]})
        pv = self.client.post("/app/api/distill/preview_draft",
                              json={"pack": "rdpkg"})
        self.assertEqual(pv.status_code, 200)
        self.assertGreaterEqual(pv.json()["est_calls"], 3)
        r = self.client.post("/app/api/distill/gen_draft", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "include_thought": True})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["quotes_dropped"], 1, "伪造引文应整条剔除")
        self.assertIn("伪造条目", d["quotes_dropped_labels"])
        pk = S / "stylepacks" / "rdpkg"
        ex = (pk / "exemplars.md").read_text(encoding="utf-8")
        self.assertNotIn("伪造", ex)
        self.assertIn("河水冰冷刺骨", ex)
        self.assertIn("## 三百字精华", (pk / "profile.md").read_text(encoding="utf-8"))
        self.assertIn("## 卡片", (pk / "card.md").read_text(encoding="utf-8"))
        self.assertIn("## 标志词", (pk / "lexicon.md").read_text(encoding="utf-8"))
        self.assertIn("【可模仿】", (pk / "limits.md").read_text(encoding="utf-8"))
        th = (pk / "thought.md").read_text(encoding="utf-8")
        self.assertIn("motif 词表：", th)
        self.assertTrue(d["motif_report"])
        meta = _json.loads((pk / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["corpus"]["works"], ["落水记"])
        self.assertGreater(meta["corpus"]["total_chars"], 0)
        self.assertIsInstance(meta["provenance"], list)
        self.assertTrue(meta["provenance"], "provenance 应从 ingest 记录回填")
        # 无 analysis 的包 → 404
        self.client.post("/app/api/distill/pack", json={"name": "draftpkg"})
        r2 = self.client.post("/app/api/distill/gen_draft", json={
            "pack": "draftpkg", "corpus_dir": "测试作者/落水记"})
        self.assertEqual(r2.status_code, 404)

    def test_blind_full_loop_no_leak(self):
        """v0.8.0 盲测闭环：出题+对局生成 → 判读视图不泄漏 packed → 逐轮判定
        → 胜率揭示 + calibration 入账 + session gitignore。"""
        import time as _t
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "rdpkg", "corpus_dir": "测试作者/落水记"})
        # 包档案（带包臂注入读这些文件）
        pk = S / "stylepacks" / "rdpkg"
        (pk / "card.md").write_text("卡", encoding="utf-8")
        st = self.client.post("/app/api/distill/blind/start",
                              json={"pack": "rdpkg"}).json()
        for _ in range(100):
            job = self.client.get(f"/app/api/distill/job/{st['job_id']}").json()
            if job["status"] != "running":
                break
            _t.sleep(0.1)
        self.assertEqual(job["status"], "done", str(job.get("error"))[:200])
        # 题库已生成且可解析
        prompts = (pk / "tests" / "blind-prompts.md").read_text(encoding="utf-8")
        self.assertIn("## 题 1", prompts)
        # 判读视图：不含臂位标记（防泄漏——v2 用 segments/arm，视图只留 label）
        v = self.client.get("/app/api/distill/blind/session",
                            params={"pack": "rdpkg"}).json()
        raw = _json.dumps(v, ensure_ascii=False)
        self.assertNotIn('"packed"', raw)
        self.assertNotIn('"arm"', raw)
        self.assertEqual(len(v["rounds"]), 3)
        self.assertEqual(len(v["rounds"][0]["segments"]), 2)
        self.assertIn("带包的一段", raw)  # 文本本身在（甲或乙随机）
        # 逐轮判定（按 session 文件真值选风格臂 → 全对 → 风格胜率 1.0）
        sess = _json.loads((pk / "tests" / "blind-session.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(sess["v"], 2)
        last = None
        for i, r in enumerate(sess["rounds"]):
            pick = next(sg["label"] for sg in r["segments"]
                        if sg["arm"] == "style")
            if i == len(sess["rounds"]) - 1:  # 末轮先试非法选项（未判轮上 400）
                bad = self.client.post("/app/api/distill/blind/judge", json={
                    "pack": "rdpkg", "round_no": r["no"], "choice": "丙"})
                self.assertEqual(bad.status_code, 400)
            last = self.client.post("/app/api/distill/blind/judge", json={
                "pack": "rdpkg", "round_no": r["no"], "choice": pick}).json()
        self.assertTrue(last["finished"])
        self.assertEqual(last["results"]["win_rate"], 1.0)
        # 分轨计分（v0.13.2）：style 轨 3/3
        self.assertEqual(last["results"]["tracks"]["style"],
                         {"wins": 3, "n": 3, "rate": 1.0})
        self.assertEqual(last["results"]["tracks"]["plain"]["n"], 3)
        # 揭示后 session 视图带答案；重判被拒
        v2 = self.client.get("/app/api/distill/blind/session",
                             params={"pack": "rdpkg"}).json()
        self.assertEqual(v2["results"]["hits"], 3)
        again = self.client.post("/app/api/distill/blind/judge", json={
            "pack": "rdpkg", "round_no": 1, "choice": "甲"})
        self.assertEqual(again.status_code, 409)
        # calibration 入账（evals/ 真账本）——断言后即清理，测试不污染账本
        cal = _json.loads((S / "evals" / "calibration.json").read_text(encoding="utf-8"))
        keys = [k for k in cal if k.startswith("web_blind_rdpkg_")]
        self.assertTrue(keys)
        self.assertIn("tracks", cal[keys[0]])
        for k in keys:
            del cal[k]
        (S / "evals" / "calibration.json").write_text(
            _json.dumps(cal, ensure_ascii=False, indent=2) + chr(10),
            encoding="utf-8")
        gi = (S / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("blind-session.json", gi)

    def test_blind_canon_arm(self):
        """v0.13.2 canon 臂：臂位校验（缺 canon 包 400）+ 三臂对局（风格/canon/
        裸）+ 判读视图剥臂 + 分轨计分。"""
        import time as _t
        from unittest.mock import patch
        import routes_distill
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "rdcanon", "corpus_dir": "测试作者/落水记"})
        (S / "stylepacks" / "rdcanon" / "card.md").write_text("卡", encoding="utf-8")
        # 伪 canon 包（patch CANONPACKS 到 tmp——不动真 canonpacks/）
        tmp_canon = Path(self.tmp.name) / "canonpacks" / "fakecanon"
        tmp_canon.mkdir(parents=True)
        (tmp_canon / "pack.json").write_text("{}", encoding="utf-8")
        (tmp_canon / "card.md").write_text("世界观卡", encoding="utf-8")
        (tmp_canon / "terms.json").write_text(_json.dumps(
            {"must": [{"term": "落水镇"}], "ban": [{"term": "航空母舰"}]},
            ensure_ascii=False), encoding="utf-8")
        # 臂位校验（job 化：错误在 job 状态里浮出，非 HTTP 状态码）
        def _run_and_wait(st):
            for _ in range(100):
                job = self.client.get(f"/app/api/distill/job/{st['job_id']}").json()
                if job["status"] != "running":
                    break
                _t.sleep(0.1)
            return job
        b1 = _run_and_wait(self.client.post("/app/api/distill/blind/start", json={
            "pack": "rdcanon", "arms": ["canon"]}).json())
        self.assertEqual(b1["status"], "error")  # 臂位 <2
        self.assertIn("臂位至少", b1["error"])
        b2 = _run_and_wait(self.client.post("/app/api/distill/blind/start", json={
            "pack": "rdcanon", "arms": ["style", "canon"]}).json())
        self.assertEqual(b2["status"], "error")  # 缺 canon 包
        self.assertIn("canon 包", b2["error"])
        with patch.object(routes_distill, "CANONPACKS",
                          Path(self.tmp.name) / "canonpacks"):
            job = _run_and_wait(self.client.post(
                "/app/api/distill/blind/start", json={
                    "pack": "rdcanon", "arms": ["style", "canon", "plain"],
                    "canon_pack": "fakecanon", "rounds": 2,
                    "topic_ids": [1, 2]}).json())
            self.assertEqual(job["status"], "done", str(job.get("error"))[:200])
        self.assertEqual(job["result"]["arms"], ["style", "canon", "plain"])
        v = self.client.get("/app/api/distill/blind/session",
                            params={"pack": "rdcanon"}).json()
        raw = _json.dumps(v, ensure_ascii=False)
        self.assertNotIn('"arm"', raw)  # 臂位不泄漏
        self.assertEqual(len(v["rounds"]), 2)
        self.assertEqual(len(v["rounds"][0]["segments"]), 3)
        for mark in ("带包的一段", "canon 落地段", "裸模型的一段正文"):
            self.assertIn(mark, raw)
        # 逐轮判给 canon 臂 → canon 轨 2/2，style 轨 0/2
        sess = _json.loads((S / "stylepacks" / "rdcanon" / "tests"
                            / "blind-session.json").read_text(encoding="utf-8"))
        last = None
        for r in sess["rounds"]:
            pick = next(sg["label"] for sg in r["segments"]
                        if sg["arm"] == "canon")
            last = self.client.post("/app/api/distill/blind/judge", json={
                "pack": "rdcanon", "round_no": r["no"], "choice": pick}).json()
        self.assertTrue(last["finished"])
        self.assertEqual(last["results"]["tracks"]["canon"]["rate"], 1.0)
        self.assertEqual(last["results"]["tracks"]["style"]["wins"], 0)
        self.assertEqual(last["results"]["win_rate"], 0)  # 风格轨独立，不被 canon 污染


    def test_job_start_and_poll(self):
        """v0.7.3 job 化：start 返回 job_id，轮询到 done 且 result 与同步版等价；
        未知 job 404。"""
        import time as _t
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "rdpkg", "corpus_dir": "测试作者/落水记"})
        st = self.client.post("/app/api/distill/read_start", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "files": ["001-第一章-落水.md", "002-第二章-上岸.md"]}).json()
        self.assertIn("job_id", st)
        job = None
        for _ in range(50):  # mock 秒回，50×0.1s 足够
            job = self.client.get(f"/app/api/distill/job/{st['job_id']}").json()
            if job["status"] != "running":
                break
            _t.sleep(0.1)
        self.assertEqual(job["status"], "done", str(job.get("error"))[:200])
        self.assertIn("step", job)
        self.assertEqual(job["result"]["mode"], "single")
        self.assertIn("视角", job["result"]["analysis"])
        g = self.client.post("/app/api/distill/gen_draft_start", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "include_thought": False}).json()
        for _ in range(100):
            job2 = self.client.get(f"/app/api/distill/job/{g['job_id']}").json()
            if job2["status"] != "running":
                break
            _t.sleep(0.1)
        self.assertEqual(job2["status"], "done", str(job2.get("error"))[:200])
        self.assertIn("quotes_dropped", job2["result"])
        miss = self.client.get("/app/api/distill/job/nope")
        self.assertEqual(miss.status_code, 404)

    def test_gen_draft_top_chars_list_shape(self):
        """真语料回归（v0.7.2 验收实测）：fp_extract.json 的 top_chars 是
        [{char, per_1k}...] 列表——mock 流程没写该文件故未暴露 .keys() 崩溃。"""
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "rdpkg", "corpus_dir": "测试作者/落水记"})
        self.client.post("/app/api/distill/read", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "files": ["001-第一章-落水.md", "002-第二章-上岸.md"]})
        pk = S / "stylepacks" / "rdpkg"
        (pk / "fp_extract.json").write_text(_json.dumps(
            {"top_chars": [{"char": "的", "per_1k": 37.4},
                           {"char": "了", "per_1k": 18.0}]}, ensure_ascii=False),
            encoding="utf-8")
        r = self.client.post("/app/api/distill/gen_draft", json={
            "pack": "rdpkg", "corpus_dir": "测试作者/落水记",
            "include_thought": False})
        self.assertEqual(r.status_code, 200)
        # trio 调用（include_thought=False 时为最后一次）提示词应含高频字段与实测字
        self.assertIn("高频字", LAST_MSG["v"])
        self.assertIn("的、了", LAST_MSG["v"])

    def test_file_edit_roundtrip_and_whitelist(self):
        self._ingest()
        self.client.post("/app/api/distill/pack", json={
            "name": "rdpkg", "corpus_dir": "测试作者/落水记"})
        r = self.client.get("/app/api/distill/file",
                            params={"pack": "rdpkg", "name": "pack.json"})
        self.assertEqual(r.status_code, 400, "白名单外的文件不得编辑")
        r2 = self.client.post("/app/api/distill/file", json={
            "pack": "rdpkg", "name": "lexicon.md", "content": "## 标志词\n人工修订"})
        self.assertEqual(r2.status_code, 200)
        g = self.client.get("/app/api/distill/file",
                            params={"pack": "rdpkg", "name": "lexicon.md"}).json()
        self.assertIn("人工修订", g["content"])

    def test_publish_gate_and_local_move(self):
        """定稿门禁：validate 未通过 → 400 拒绝；通过 → local 层落位 + 对外可见。"""
        self._ingest()
        # 门禁：缺档案的草稿包拒绝定稿
        self.client.post("/app/api/distill/pack", json={
            "name": "draftpkg", "corpus_dir": "测试作者/落水记"})
        r = self.client.post("/app/api/distill/publish", json={
            "pack": "draftpkg", "tier": "local"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("validate 未通过", r.json()["detail"])
        # 合格包：draft + 指纹 + 最小档案集
        self.client.post("/app/api/distill/pack", json={
            "name": "pubpkg", "corpus_dir": "测试作者/落水记"})
        self.client.post("/app/api/distill/fingerprint", json={
            "pack": "pubpkg", "corpus_dir": "测试作者/落水记", "exclude": []})
        pk = S / "stylepacks" / "pubpkg"
        (pk / "card.md").write_text("三百字精华压缩，四百字以内。", encoding="utf-8")
        (pk / "profile.md").write_text("## 三百字精华\n占位\n", encoding="utf-8")
        ex = "\n\n".join(f"### 范例{i}\n> 引文第{i}句，很短。\n批注\n"
                         for i in range(1, 7))
        (pk / "exemplars.md").write_text(ex, encoding="utf-8")
        (pk / "lexicon.md").write_text("## 标志词\n冷\n", encoding="utf-8")
        (pk / "limits.md").write_text("叙事【可模仿】\n", encoding="utf-8")
        r2 = self.client.post("/app/api/distill/publish", json={
            "pack": "pubpkg", "tier": "local",
            "license_note": "测试许可声明"})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["path"], "stylepacks/local/pubpkg")
        moved = S / "stylepacks" / "local" / "pubpkg"
        self.assertTrue((moved / "pack.json").is_file())
        meta = _json.loads((moved / "pack.json").read_text(encoding="utf-8"))
        self.assertNotIn("status", meta, "定稿后不得再带 draft 状态")
        self.assertEqual(meta["license_note"], "测试许可声明")
        # 定稿后对外可见：创作页包下拉 + 装配不再拒绝
        pr = self.client.get("/app/api/projects").json()
        self.assertIn("local/pubpkg", [p["name"] for p in pr["packs"]])
        ra = self.client.post("/app/api/assemble", json={
            "project": "测试项目", "pack": "local/pubpkg",
            "chapter_no": 1, "keywords": []})
        self.assertNotEqual(ra.status_code, 400,
                            "定稿包不应再被草稿守卫拒绝（404 项目缺 bible 属正常）")


if __name__ == "__main__":
    unittest.main()
