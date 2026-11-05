# -*- coding: utf-8 -*-
"""web 工作台 v0.6.0 服务端测试：mock 模型 e2e + 红线断言（key/session/绑定）。"""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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

MOCK_KEY = "sk-mock-1234567890"

LAST: dict = {}  # mock 捕获最近一次请求（payload/messages），供断言换算与提示词

PROSE = ("他推门出去，街上正落着细雨。夜色像一层旧棉絮盖在屋顶上，"
         "远处有狗叫了两声，又静了。\n他攥紧了手里的钥匙，指节发白。")

PROSE_REVISED = ("他推开门，细雨扑了一脸。夜色沉沉地压在屋顶上，远处的狗"
                 "叫了两声，又归于沉寂。他把钥匙攥进掌心，指节泛白，"
                 "一步一步走进那条被雨水泡软的巷子。")

OUTLINE = {"options": [
    {"title": "方向A", "angle": "以小见大", "action": "立意1 小物承大情",
     "stance": "克制外化"}], "recommended": 0}
BEATS = {"beats": [{"no": 1, "beat": "承接上章：雨夜归途"},
                   {"no": 2, "beat": "场景：屋内对峙"},
                   {"no": 3, "beat": "钩子：门外脚步"}],
         "tone_note": "不指定", "canon_anchor": "无"}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默
        pass

    def _send(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _send_thinking(self, payload, model):
        """模拟思考型模型：max_tokens 全被推理吃掉，content 空、finish=length。"""
        self._send({"choices": [{"message": {"content": "",
                                             "reasoning_content": "（内部思考，省略……）"},
                                 "finish_reason": "length"}],
                    "model": model,
                    "usage": {"prompt_tokens": 100,
                              "completion_tokens": payload.get("max_tokens", 0)}})

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send({"data": [{"id": "mock-write"}, {"id": "mock-judge"}]})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        LAST["payload"] = payload
        LAST["user_msg"] = payload["messages"][-1]["content"]
        model = payload.get("model", "mock")
        trunc = model == "mock-trunc"  # 截断模型：≤7000 给半截+length，>7000 全文（修订预算 ×2 首试也截断）
        thinking = (model == "mock-think"
                    or (model == "mock-think-once"
                        and payload.get("max_tokens", 0) <= 3500))
        if payload.get("stream"):  # v0.6.4 流式
            if thinking:
                self._send_stream(payload, "", ["（内部思考，省略……）"], "length")
            elif trunc:
                full = self._content_for(LAST["user_msg"])
                cut = payload.get("max_tokens", 0) <= 7000
                self._send_stream(payload, full if not cut else full[:30],
                                  None, "stop" if not cut else "length")
            else:
                self._send_stream(payload, self._content_for(LAST["user_msg"]),
                                  None, "stop")
            return
        if thinking:
            self._send_thinking(payload, model)
            return
        if trunc:
            full = self._content_for(LAST["user_msg"])
            cut = payload.get("max_tokens", 0) <= 7000
            content, fr = (full[:30], "length") if cut else (full, "stop")
        else:
            content, fr = self._content_for(LAST["user_msg"]), "stop"
        self._send({"choices": [{"message": {"content": content},
                                 "finish_reason": fr}],
                    "model": model,
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50}})

    def _content_for(self, user_msg):
        if "记忆登记项" in user_msg:  # v0.9.0 记忆 digest 提取（judge 路由）
            return json.dumps({"digest": "他钓上会说话的鱼，被绑定。",
                               "changes": [{"entity": "韩天宇",
                                            "field": "possession",
                                            "value": "持有大比目鱼",
                                            "note": "绑定情节"}],
                               "foreshadow": ["鱼的来历之谜"]}, ensure_ascii=False)
        if "局部改写" in user_msg:  # v0.9.3 rewrite（含拍子表字样，须先于拍子分支）
            return PROSE_REVISED
        if "验收报告" in user_msg:
            return PROSE_REVISED
        if "只输出正文本身" in user_msg:
            return PROSE
        if "收尾检查" in user_msg:
            return json.dumps({"violation": False, "reason": "物化收束，无立碑/安慰/点题"},
                              ensure_ascii=False)
        if "重掷第" in user_msg:
            return json.dumps({"no": 2, "beat": "重掷后的场景：意外来客"}, ensure_ascii=False)
        if "2–3 个立意方向" in user_msg:
            return json.dumps(OUTLINE, ensure_ascii=False)
        if "拍子表" in user_msg:
            return json.dumps(BEATS, ensure_ascii=False)
        return PROSE

    def _send_stream(self, payload, content, reasoning, finish):
        """OpenAI 风格 SSE chunk 流（delta 分片 + finish + 可选 usage 块）。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def chunk(obj):
            self.wfile.write(b"data: "
                             + json.dumps(obj, ensure_ascii=False).encode("utf-8")
                             + b"\n\n")

        chunk({"choices": [{"delta": {"role": "assistant"}}]})
        for r in (reasoning or []):
            chunk({"choices": [{"delta": {"reasoning_content": r}}]})
        if content:
            step = max(1, len(content) // 3)
            for i in range(0, len(content), step):
                chunk({"choices": [{"delta": {"content": content[i:i + step]}}]})
        chunk({"choices": [{"delta": {}, "finish_reason": finish}]})
        if payload.get("stream_options", {}).get("include_usage"):
            chunk({"choices": [], "usage": {"prompt_tokens": 100,
                   "completion_tokens": payload.get("max_tokens", 0)
                   if finish == "length" else 50}})
        self.wfile.write(b"data: [DONE]\n\n")


@unittest.skipUnless(_HAS_DEPS, "web 依赖未安装（pip install -r web/requirements-web.txt）")
class TestWebServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        cls.mock_port = cls.mock.server_address[1]
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()

        cls.tmp = tempfile.TemporaryDirectory()
        ws = Path(cls.tmp.name) / "ws"
        proj = ws / "测试项目"
        (proj / "bible").mkdir(parents=True)
        (proj / "manuscript").mkdir()
        (proj / "bible" / "characters.md").write_text(
            "## 韩天宇\n主角。性格：贱、怂、精明。\n\n## 大比目鱼\n深渊传奇武器，"
            "蓝发少女形态，老派绅士作派。\n", encoding="utf-8")
        (proj / "manuscript" / "001-开局.md").write_text(
            "雨夜里他第一次见到那把枪。\n枪说自己叫大比目鱼。\n", encoding="utf-8")
        cls.cfg_path = Path(cls.tmp.name) / "config.local.json"
        appstate.DEFAULT_CONFIG_PATH = cls.cfg_path  # 测试注入，不碰真实配置
        cfg = appstate.load_config(cls.cfg_path)
        cfg["workspace_root"] = str(ws)
        cfg["providers"] = [{"name": "mock", "base_url":
                             f"http://127.0.0.1:{cls.mock_port}/v1",
                             "api_key": MOCK_KEY, "models": ["mock-write"]}]
        cfg["routing"] = {"write": {"provider": "mock", "model": "mock-write"},
                          "judge": {"provider": "mock", "model": "mock-judge"}}
        appstate.save_config(cfg, cls.cfg_path)
        cls.client = TestClient(create_app(site_dir=S / "web" / "site"))

    @classmethod
    def tearDownClass(cls):
        cls.mock.shutdown()

    def test_config_sanitized(self):
        r = self.client.get("/app/api/config")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(MOCK_KEY, r.text, "key 泄漏进配置接口")
        view = r.json()
        self.assertTrue(view["providers"][0]["has_key"])
        self.assertNotIn("api_key", view["providers"][0])

    def test_config_stale_rev_rejected(self):
        """乐观锁回归：陈旧页面（旧 rev）提交不得静默覆盖新配置——
        v0.6.0 实测危害：调试方改完路由，用户陈旧页面一次保存就覆盖回去。"""
        d = self.client.get("/app/api/config").json()
        self.assertIn("rev", d, "GET 配置必须带 rev")
        stale = d["rev"] - 1
        r = self.client.post("/app/api/config", json={
            "providers": d["providers"], "routing": {}, "rev": stale})
        self.assertEqual(r.status_code, 409)
        self.assertIn("rev", r.json()["config"])
        # 不带 rev 的写入一律 400（v0.6.0 第三次翻转的根因：旧页面无 rev
        # 仍被兼容接受——兼容路即覆盖之门，故必须硬拒）
        r2 = self.client.post("/app/api/config", json={
            "providers": d["providers"], "routing": d["routing"]})
        self.assertEqual(r2.status_code, 400)
        self.assertIn("rev", r2.json()["detail"])
        # 带当前 rev 的正常保存照常工作，且 key 合并不洗 key
        r3 = self.client.post("/app/api/config", json={
            "providers": d["providers"], "routing": d["routing"], "rev": d["rev"]})
        self.assertEqual(r3.status_code, 200)
        stored = appstate.load_config(self.cfg_path)
        self.assertEqual(stored["providers"][0].get("api_key"), MOCK_KEY,
                         "正常保存把 key 洗掉了")

    def test_empty_key_preserves_stored_key(self):
        """回归锁：saveAll 回传的是脱敏视图（无 api_key）——服务端必须与同名
        供应商合并 key（UI 承诺"留空 = 保持已存 key 不变"），否则每次保存洗 key。"""
        base = {"name": "mock", "base_url": f"http://127.0.0.1:{self.mock_port}/v1",
                "models": ["mock-write"]}  # 无 api_key 字段
        d = self.client.get("/app/api/config").json()
        r = self.client.post("/app/api/config", json={
            "providers": [base], "routing": d["routing"], "rev": d["rev"]})
        self.assertEqual(r.status_code, 200)
        stored = appstate.load_config(self.cfg_path)
        self.assertEqual(stored["providers"][0].get("api_key"), MOCK_KEY,
                         "空 key 提交把已存 key 洗掉了")

    def test_config_gitignored(self):
        gi = (S / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("web/config.local.json", gi)

    def test_test_connection(self):
        r = self.client.post("/app/api/config/test", json={"name": "mock"})
        self.assertTrue(r.json()["ok"])
        self.assertIn("mock-write", r.json()["models"])

    def test_projects_discovered(self):
        r = self.client.get("/app/api/projects")
        names = [p["name"] for p in r.json()["projects"]]
        self.assertIn("测试项目", names)
        self.assertIn("luxun", [p["name"] for p in r.json()["packs"]])

    def test_projects_endpoint_without_local_tier(self):
        """CI 回归锁：CI 无 stylepacks/local/（gitignore），/projects 不得炸——
        v0.6.0 曾因本地有 local 目录掩盖了 iterdir 存在性 bug 而双平台红。"""
        import routes_create
        original = routes_create.STYLEPACKS
        sp = Path(self.tmp.name) / "sp"
        (sp / "fakepack").mkdir(parents=True)
        (sp / "fakepack" / "pack.json").write_text("{}", encoding="utf-8")
        try:
            routes_create.STYLEPACKS = sp  # 有包、无 local/
            r = self.client.get("/app/api/projects")
            self.assertEqual(r.status_code, 200)
            names = [p["name"] for p in r.json()["packs"]]
            self.assertIn("fakepack", names)
            self.assertFalse(any(n.startswith("local/") for n in names),
                             "无 local 层时不得出现 local/ 条目")
        finally:
            routes_create.STYLEPACKS = original

    def test_project_traversal_blocked(self):
        r = self.client.post("/app/api/assemble", json={
            "project": "../stylepacks", "pack": "luxun",
            "chapter_no": 1, "keywords": []})
        self.assertEqual(r.status_code, 400)

    def test_assemble_preview(self):
        r = self.client.post("/app/api/assemble", json={
            "project": "测试项目", "pack": "luxun", "chapter_no": 2,
            "keywords": ["大比目鱼"]})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        kinds = [i["kind"] for i in d["items"]]
        self.assertIn("包·文风档案", kinds)
        # v0.9.2：bible 块带 ·常驻/·命中/·关联 后缀，前缀匹配
        self.assertTrue(any(k.startswith("记忆·人物") for k in kinds), kinds)
        self.assertIn("章节锚定·上一章结尾", kinds)
        self.assertTrue(any("大比目鱼" in i["excerpt"] for i in d["items"]))
        self.assertNotIn("kept_texts", d, "预览不得外带全文")

    def test_creation_e2e(self):
        base = {"project": "测试项目", "pack": "luxun", "chapter_no": 2,
                "title": "夜谈", "keywords": ["大比目鱼"]}
        o = self.client.post("/app/api/outline", json={**base, "user_notes": ""})
        self.assertEqual(o.status_code, 200)
        self.assertEqual(len(o.json()["options"]), 1)
        sid = o.json()["session_id"]

        b = self.client.post("/app/api/beats", json={
            **base, "chosen": OUTLINE["options"][0], "session_id": sid})
        self.assertEqual(len(b.json()["beats"]), 3)

        rr = self.client.post("/app/api/reroll_beat", json={
            **base, "chosen": OUTLINE["options"][0], "beats": BEATS["beats"],
            "index": 2, "session_id": sid})
        self.assertIn("重掷", rr.json()["beat"]["beat"])

        g = self.client.post("/app/api/generate", json={
            **base, "chosen": OUTLINE["options"][0], "beats": BEATS["beats"],
            "tone_note": "不指定", "canon_anchor": "无", "n_drafts": 1,
            "session_id": sid})
        self.assertEqual(g.status_code, 200)
        draft = g.json()["drafts"][0]
        self.assertIn("细雨", draft["text"])
        self.assertIn("fp_check", draft)
        self.assertIn("borrow_check", draft)
        self.assertIn("ai_cliche", draft)  # v0.9.1 第四道 advisory 门

        rv = self.client.post("/app/api/revise", json={
            **base, "chosen": OUTLINE["options"][0], "beats": BEATS["beats"],
            "text": draft["text"],
            "reports": {"fp_check": draft["fp_check"],
                        "borrow_check": draft["borrow_check"]},
            "revision": 0, "session_id": sid})
        self.assertEqual(rv.status_code, 200)
        self.assertIn("细雨", rv.json()["text"])
        self.assertEqual(rv.json()["revision"], 1)
        self.assertIn("fp_check", rv.json())

        e = self.client.post("/app/api/ending_check", json={
            "project": "测试项目", "title": "夜谈",
            "text": draft["text"], "session_id": sid})
        self.assertFalse(e.json()["ending_check"]["violation"])

        s = self.client.post("/app/api/save", json={
            **base, "text": draft["text"], "chosen": OUTLINE["options"][0],
            "beats": BEATS["beats"], "checks": {"ending": e.json()["ending_check"]},
            "usage": draft["usage"], "session_id": sid,
            "assembly_preview": g.json()["assembly_preview"]})
        self.assertEqual(s.status_code, 200)
        ws = Path(self.tmp.name) / "ws" / "测试项目"
        self.assertTrue((ws / "manuscript" / "002-夜谈.md").is_file())
        sessions = list((ws / "sessions").glob("*.json"))
        self.assertEqual(len(sessions), 1)
        self.assertTrue((ws / "sessions" / ".gitignore").is_file())
        record = sessions[0].read_text(encoding="utf-8")
        self.assertNotIn(MOCK_KEY, record, "key 泄漏进会话记录")
        self.assertIn("章节锚定", record, "会话记录缺装配快照（可复判要求）")
        self.assertIn("细雨", record)
        cost = (ws / "style" / "cost.jsonl").read_text(encoding="utf-8")
        self.assertIn("web-create", cost)
        # v0.6.8：会话总账落盘（cost.jsonl 附加字段 + sessions 记录），不再只记最后一稿
        entry = json.loads(cost.strip().splitlines()[-1])
        self.assertIn("session_tokens", entry)
        self.assertGreaterEqual(entry["session_calls"], 5,
                                "总账调用次数未含 outline/beats/生成/修订/判官")
        self.assertGreaterEqual(entry["session_tokens"], entry["tokens"])
        rec = json.loads(record)
        self.assertGreaterEqual(rec["session_totals"]["calls"], 5)

    def _set_write_route(self, model):
        cfg = appstate.load_config(self.cfg_path)
        cfg["routing"]["write"] = {"provider": "mock", "model": model}
        appstate.save_config(cfg, self.cfg_path)

    def test_thinking_model_empty_retries_then_succeeds(self):
        """v0.6.2 回归（真实事故）：思考型模型把 3500 tokens 全花在推理上，
        content 为空、finish=length——chat() 自动加倍预算重试须救回正文，
        且记账含重试消耗、带 retries 诊断字段。"""
        self._set_write_route("mock-think-once")
        try:
            g = self.client.post("/app/api/generate", json={
                "project": "测试项目", "pack": "luxun", "chapter_no": 3,
                "title": "夜谈", "keywords": [], "chosen": OUTLINE["options"][0],
                "beats": BEATS["beats"], "tone_note": "不指定",
                "canon_anchor": "无", "n_drafts": 1, "session_id": "think1"})
            self.assertEqual(g.status_code, 200)
            draft = g.json()["drafts"][0]
            self.assertIn("细雨", draft["text"])
            self.assertEqual(draft["usage"]["retries"], 1)
            self.assertGreaterEqual(draft["usage"]["completion_tokens"], 3500)
            self.assertEqual(draft["usage"]["finish_reason"], "stop")
        finally:
            self._set_write_route("mock-write")

    def test_thinking_model_gives_up_clean(self):
        """加倍重试两次仍空 → 502 带可行动对策；绝不把空稿放进创作环。"""
        self._set_write_route("mock-think")
        try:
            g = self.client.post("/app/api/generate", json={
                "project": "测试项目", "pack": "luxun", "chapter_no": 3,
                "title": "夜谈", "keywords": [], "chosen": OUTLINE["options"][0],
                "beats": BEATS["beats"], "tone_note": "不指定",
                "canon_anchor": "无", "n_drafts": 1, "session_id": "think2"})
            self.assertEqual(g.status_code, 502)
            self.assertIn("空正文", g.json()["detail"])
            self.assertIn("思考", g.json()["detail"])
        finally:
            self._set_write_route("mock-write")

    def test_save_rejects_empty_and_bad_title(self):
        """v0.6.2 事故回归：空稿+空题被交付成 001-.md（0 字节）。
        现在必须：空稿 400；空题落「未命名」；文件名非法字符消毒。"""
        base = {"project": "测试项目", "pack": "luxun", "chapter_no": 4}
        r = self.client.post("/app/api/save",
                             json={**base, "title": "x", "text": "   "})
        self.assertEqual(r.status_code, 400)
        self.assertIn("拒绝交付", r.json()["detail"])
        r2 = self.client.post("/app/api/save",
                              json={**base, "title": "", "text": PROSE})
        self.assertEqual(r2.status_code, 200)
        ms = Path(self.tmp.name) / "ws" / "测试项目" / "manuscript"
        self.assertTrue((ms / "004-未命名.md").is_file())
        self.assertFalse((ms / "004-.md").exists())
        r3 = self.client.post("/app/api/save",
                              json={**base, "title": 'a/b:c"d', "text": PROSE})
        self.assertEqual(r3.status_code, 200)
        self.assertTrue((ms / "004-a_b_c_d.md").is_file())

    def test_fp_check_empty_input_clean(self):
        """空文件给干净报错（退出码 2），不再 ZeroDivisionError traceback——
        v0.6.2 事故：空稿流进 fp_check，判官台显示整屏 Python 堆栈。"""
        import subprocess
        empty = Path(self.tmp.name) / "empty_draft.txt"
        empty.write_text("", encoding="utf-8")
        r = subprocess.run([sys.executable, str(S / "scripts" / "fp_check.py"),
                            str(S / "stylepacks" / "luxun"), str(empty)],
                           capture_output=True, encoding="utf-8",
                           errors="replace", timeout=120)
        out = (r.stdout or "") + (r.stderr or "")
        self.assertEqual(r.returncode, 2)
        self.assertIn("为空", out)
        self.assertNotIn("Traceback", out)

    def test_target_chars_tier_flows_through(self):
        """v0.6.3 字数挡位：显式挡位进拍子/正文提示词；max_tokens 按字数换算
        （1 字≈0.75 token，与 assemble 同口径，只增不减覆盖配置兜底）；
        save 把挡位写入会话记录（复判可知当时目标）。"""
        base = {"project": "测试项目", "pack": "luxun", "chapter_no": 5,
                "title": "夜谈", "keywords": [], "target_chars": 4000}
        b = self.client.post("/app/api/beats",
                             json={**base, "chosen": OUTLINE["options"][0]})
        self.assertEqual(b.status_code, 200)
        self.assertIn("约 4000 字", LAST["user_msg"])
        g = self.client.post("/app/api/generate", json={
            **base, "chosen": OUTLINE["options"][0], "beats": BEATS["beats"],
            "tone_note": "不指定", "canon_anchor": "无", "n_drafts": 1})
        self.assertEqual(g.status_code, 200)
        self.assertIn("约 4000 字", LAST["user_msg"])
        self.assertGreaterEqual(LAST["payload"]["max_tokens"],
                                int(4000 * 0.75) + 600)
        self.assertIn("下限", LAST["user_msg"])  # 篇幅带合格下限/上限
        s = self.client.post("/app/api/save", json={**base, "text": PROSE,
                                                    "usage": {}})
        self.assertEqual(s.status_code, 200)
        recs = list((Path(self.tmp.name) / "ws" / "测试项目"
                     / "sessions").glob("*.json"))
        self.assertTrue(any('"target_chars": 4000' in p.read_text(encoding="utf-8")
                            for p in recs), "挡位未入会话记录")

    def test_target_chars_out_of_range_ignored(self):
        """越界挡位（<300 / >20000）按未指定处理——回退配置兜底，不猜。"""
        g = self.client.post("/app/api/generate", json={
            "project": "测试项目", "pack": "luxun", "chapter_no": 5,
            "title": "夜谈", "keywords": [], "chosen": OUTLINE["options"][0],
            "beats": BEATS["beats"], "tone_note": "不指定",
            "canon_anchor": "无", "n_drafts": 1, "target_chars": 99999})
        self.assertEqual(g.status_code, 200)
        self.assertNotIn("99999", LAST["user_msg"])
        self.assertEqual(LAST["payload"]["max_tokens"], 3500)  # 配置兜底

    def test_create_page_sidebar(self):
        """v0.6.4 生成现场侧栏：页面可达、侧栏在模板中；v0.13.0 起逻辑抽到
        共享 creation.js（与连载台同源），页面只留外链。"""
        r = self.client.get("/app/create")
        self.assertEqual(r.status_code, 200)
        self.assertIn("生成现场", r.text)
        self.assertIn("/static/creation.js", r.text)
        js = self.client.get("/static/creation.js").text
        self.assertIn("generate_stream", js)
        self.assertIn("loadSlot", js)
        self.assertIn("方案槽", r.text)  # v0.6.6

    def test_slots_capture_update_restore(self):
        """v0.6.6 方案槽：装配入槽 → 同指纹复用原槽 → 立意/拍子/上次稿写回
        → 环形驱逐最旧未锁定 → 全锁 409 → 清空后 404。"""
        cap = {"project": "测试项目", "pack": "luxun", "chapter_no": 2,
               "keywords": ["大比目鱼"], "target_chars": 1500, "title": "夜谈"}
        r1 = self.client.post("/app/api/slots/capture", json=cap)
        self.assertEqual(r1.status_code, 200)
        self.assertFalse(r1.json()["reused"])
        sid = r1.json()["slot"]["id"]
        self.assertTrue(r1.json()["slot"]["pack_version"], "槽未记包版本")
        r2 = self.client.post("/app/api/slots/capture", json=cap)
        self.assertTrue(r2.json()["reused"])
        self.assertEqual(r2.json()["slot"]["id"], sid)
        u = self.client.post("/app/api/slots/update", json={
            "project": "测试项目", "slot_id": sid,
            "chosen": OUTLINE["options"][0], "beats": BEATS["beats"],
            "tone_note": "不指定", "canon_anchor": "无",
            "latest_draft": {"text": PROSE, "usage": {}}})
        self.assertEqual(u.status_code, 200)
        s = u.json()["slot"]
        self.assertEqual(s["name"], "方向A", "槽名应自动取立意方向")
        self.assertEqual(len(s["beats"]), 3)
        lst = self.client.get("/app/api/slots",
                              params={"project": "测试项目"}).json()["slots"]
        self.assertIsNotNone(lst[sid - 1])
        for k in range(4):  # 填满 5 槽
            rr = self.client.post("/app/api/slots/capture",
                                  json={**cap, "keywords": [f"kw{k}"]})
            self.assertEqual(rr.status_code, 200)
        for i in range(1, 6):
            self.client.post("/app/api/slots/update",
                             json={"project": "测试项目", "slot_id": i,
                                   "locked": True})
        full = self.client.post("/app/api/slots/capture",
                                json={**cap, "keywords": ["fresh"]})
        self.assertEqual(full.status_code, 409)
        self.assertIn("解锁", full.json()["detail"])
        self.client.post("/app/api/slots/update",
                         json={"project": "测试项目", "slot_id": sid,
                               "locked": False})
        ok = self.client.post("/app/api/slots/capture",
                              json={**cap, "keywords": ["fresh"]})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["slot"]["id"], sid, "应挤掉最旧未锁定槽")
        self.client.post("/app/api/slots/clear",
                         json={"project": "测试项目", "slot_id": sid})
        lst2 = self.client.get("/app/api/slots",
                               params={"project": "测试项目"}).json()["slots"]
        self.assertIsNone(lst2[sid - 1])
        u2 = self.client.post("/app/api/slots/update",
                              json={"project": "测试项目", "slot_id": sid,
                                    "locked": True})
        self.assertEqual(u2.status_code, 404)
        bad = self.client.post("/app/api/slots/update",
                               json={"project": "测试项目", "slot_id": 9,
                                     "locked": True})
        self.assertEqual(bad.status_code, 400)

    def test_slots_traversal_blocked(self):
        r = self.client.get("/app/api/slots", params={"project": "../stylepacks"})
        self.assertEqual(r.status_code, 400)

    def test_save_records_keywords(self):
        """v0.6.6：交付记录带 keywords——历史会话可精确重放装配。"""
        r = self.client.post("/app/api/save", json={
            "project": "测试项目", "pack": "luxun", "chapter_no": 8,
            "title": "夜谈", "keywords": ["大比目鱼", "泰拉币"], "text": PROSE,
            "usage": {}})
        self.assertEqual(r.status_code, 200)
        recs = list((Path(self.tmp.name) / "ws" / "测试项目"
                     / "sessions").glob("*.json"))
        self.assertTrue(any("泰拉币" in p.read_text(encoding="utf-8")
                            for p in recs), "keywords 未入会话记录")

    def test_generation_stream_e2e(self):
        """v0.6.4 流式：SSE 事件齐全、正文逐字到齐、门禁随 draft_done 返回、
        请求带 stream 且挡位进提示词、预算与挡位换算一致。"""
        base = {"project": "测试项目", "pack": "luxun", "chapter_no": 6,
                "title": "夜谈", "keywords": [], "chosen": OUTLINE["options"][0],
                "beats": BEATS["beats"], "tone_note": "不指定",
                "canon_anchor": "无", "n_drafts": 1, "target_chars": 1500}
        r = self.client.post("/app/api/generate_stream", json=base)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.headers["content-type"])
        body = r.text
        for ev in ("event: session", "event: draft_start", "event: delta",
                   "event: draft_done", "event: all_done"):
            self.assertIn(ev, body)
        self.assertIn("细雨", body)
        self.assertIn('"chars"', body)
        self.assertTrue(LAST["payload"].get("stream"))
        self.assertIn("约 1500 字", LAST["user_msg"])
        self.assertEqual(LAST["payload"]["max_tokens"],
                         max(3500, int(1500 * 0.75) + 600))  # 短挡不缩水，兜底

    def test_stream_empty_falls_back_then_errors_clean(self):
        """流式空稿（思考模型）：回退非流加倍链，仍空 → 流内 error 事件带对策，
        绝不吐 draft_done 空稿（连接本身不炸）。"""
        self._set_write_route("mock-think")
        try:
            r = self.client.post("/app/api/generate_stream", json={
                "project": "测试项目", "pack": "luxun", "chapter_no": 6,
                "title": "夜谈", "keywords": [], "chosen": OUTLINE["options"][0],
                "beats": BEATS["beats"], "tone_note": "不指定",
                "canon_anchor": "无", "n_drafts": 1, "session_id": "think3"})
            self.assertEqual(r.status_code, 200)
            body = r.text
            self.assertIn("event: error", body)
            self.assertIn("思考", body)
            self.assertNotIn("event: draft_done", body)
        finally:
            self._set_write_route("mock-write")

    def test_revise_stream_e2e(self):
        """修订流式：revised_done 事件带修订轮次与两道门报告。"""
        r = self.client.post("/app/api/revise_stream", json={
            "project": "测试项目", "pack": "luxun", "chapter_no": 6,
            "title": "夜谈", "keywords": [], "chosen": {},
            "beats": BEATS["beats"], "text": PROSE,
            "reports": {"fp_check": {"exit_code": 1, "report": "句长超差"}},
            "revision": 0, "target_chars": 1500})
        self.assertEqual(r.status_code, 200)
        self.assertIn("event: revised_done", r.text)
        self.assertIn("细雨", r.text)
        self.assertIn('"revision": 1', r.text)
        self.assertIn("fp_check", r.text)

    def test_truncated_revision_retried_longer(self):
        """v0.6.5 事故回归（修订 2500→1099 字）：思考模型推理吃满预算，
        finish=length 的**非空截断**稿曾被视为正常结果放行——现在必须加倍
        重试取完整文本（非流）。"""
        self._set_write_route("mock-trunc")
        try:
            g = self.client.post("/app/api/revise", json={
                "project": "测试项目", "pack": "luxun", "chapter_no": 7,
                "title": "夜谈", "keywords": [], "chosen": {},
                "beats": BEATS["beats"], "text": PROSE,
                "reports": {"fp_check": {"exit_code": 1, "report": "句长超差"}},
                "revision": 0, "target_chars": 2500})
            self.assertEqual(g.status_code, 200)
            self.assertEqual(g.json()["text"], PROSE_REVISED)  # 不是 30 字截断版
            self.assertEqual(g.json()["usage"]["finish_reason"], "stop")
            self.assertEqual(g.json()["usage"]["retries"], 1)
        finally:
            self._set_write_route("mock-write")

    def test_stream_truncated_replaced_with_full(self):
        """流式截断 → 回退整段加倍链拿到全文 → replace 事件替换部分稿。"""
        self._set_write_route("mock-trunc")
        try:
            r = self.client.post("/app/api/generate_stream", json={
                "project": "测试项目", "pack": "luxun", "chapter_no": 7,
                "title": "夜谈", "keywords": [], "chosen": OUTLINE["options"][0],
                "beats": BEATS["beats"], "tone_note": "不指定",
                "canon_anchor": "无", "n_drafts": 1, "target_chars": 2500})
            self.assertEqual(r.status_code, 200)
            body = r.text
            self.assertIn("event: replace", body)
            self.assertIn("细雨", body)
            self.assertNotIn('"finish_reason": "length"', body.split("draft_done")[-1])
        finally:
            self._set_write_route("mock-write")

    def test_revise_prompt_antishrink(self):
        """防缩水条款进提示词：原文约 N 字 / 不得低于下限 / 禁删减凑合规。"""
        r = self.client.post("/app/api/revise", json={
            "project": "测试项目", "pack": "luxun", "chapter_no": 7,
            "title": "夜谈", "keywords": [], "chosen": {},
            "beats": BEATS["beats"], "text": PROSE,
            "reports": {}, "revision": 0, "target_chars": 2500})
        self.assertEqual(r.status_code, 200)
        msg = LAST["user_msg"]
        self.assertIn("原文约", msg)
        self.assertIn("不得低于", msg)
        self.assertIn("严禁靠删情节", msg)

    def test_presets_tones_and_anchors(self):
        """调子/锚点初始选项：registers.md 分区名进 tones；sessions 的
        canon_anchor 进 anchors；无 registers 的包回退通用建议集。"""
        r = self.client.get("/app/api/presets",
                            params={"project": "测试项目", "pack": "luxun"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["tone_source"], "registers")
        self.assertIn("不指定", d["tones"])
        self.assertTrue(any("讽刺" in t or "温情" in t for t in d["tones"]))
        self.assertIn("无", d["anchors"])
        r2 = self.client.get("/app/api/presets", params={"pack": "luxun"})
        self.assertEqual(r2.json()["anchors"], ["无"])  # 无项目 → 只有兜底

    def test_version_in_footer_and_next_chapter(self):
        """v0.7.3：页脚版本号（防旧实例事故）+ 章节号推荐（防锚定失效）。"""
        r = self.client.get("/app/create")
        self.assertIn("v0.", r.text)
        r2 = self.client.get("/app/config")
        self.assertIn("v0.", r2.text)
        ms = Path(self.tmp.name) / "ws" / "章节推荐项目" / "manuscript"
        ms.mkdir(parents=True)  # 独立项目：不与其他测试的交付互相污染
        (ms / "001-开局.md").write_text("x", encoding="utf-8")
        (ms / "005-未来章.md").write_text("x", encoding="utf-8")
        n = self.client.get("/app/api/next_chapter",
                            params={"project": "章节推荐项目"}).json()
        self.assertEqual(n["next"], 6)  # max=5 → 推荐 6
        bad = self.client.get("/app/api/next_chapter",
                              params={"project": "不存在项目"})
        self.assertEqual(bad.status_code, 404)
        bad = self.client.get("/app/api/next_chapter",
                              params={"project": "../stylepacks"})
        self.assertEqual(bad.status_code, 400)

    def test_slot_batches_persist_roundtrip(self):
        """v0.7.3 批次落盘：update 带 drafts → slots 列表可读回 → 恢复依据。"""
        cap = {"project": "测试项目", "pack": "luxun", "chapter_no": 9,
               "keywords": [], "target_chars": 0, "title": "批次"}
        r = self.client.post("/app/api/slots/capture", json=cap).json()
        sid = r["slot"]["id"]
        self.assertEqual(r["slot"]["drafts"], [])
        batches = [
            {"batch": 1, "label": "批1·稿1", "text": PROSE,
             "usage": {"completion_tokens": 50}, "fp_check": None,
             "borrow_check": None, "revision": 0},
            {"batch": 2, "label": "批2·稿1", "text": PROSE_REVISED,
             "usage": {"completion_tokens": 60}, "fp_check": None,
             "borrow_check": None, "revision": 1}]
        u = self.client.post("/app/api/slots/update", json={
            "project": "测试项目", "slot_id": sid, "drafts": batches,
            "latest_draft": batches[-1]})
        self.assertEqual(u.status_code, 200)
        lst = self.client.get("/app/api/slots",
                              params={"project": "测试项目"}).json()["slots"]
        self.assertEqual(len(lst[sid - 1]["drafts"]), 2)
        self.assertEqual(lst[sid - 1]["drafts"][1]["label"], "批2·稿1")

    def test_assemble_world_info(self):
        """v0.9.2 World Info 化：常驻（resident 标记 + core 实体）、递归关联
        （命中块文本里的名字带出未命中块）、优先级裁剪（关联先裁、常驻最后）。"""
        import assemble as asm
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "bible").mkdir()
            (d / "bible" / "characters.md").write_text(
                "# 人物" + chr(10) * 2 + "## 韩天宇" + chr(10)
                + "主角。手持大比目鱼，兜里只有铜币。<!-- resident -->" + chr(10) * 2
                + "## 大比目鱼" + chr(10) + "会说话的武器。搭档。" + chr(10) * 2
                + "## 路人甲" + chr(10) + "无关角色，不该被注入。" + chr(10) * 2
                + "## 集市老板" + chr(10) + "提到韩天宇常来买东西。" + chr(10) * 2
                + "## 铜币" + chr(10) + "通用货币，一枚买一个馒头。" + chr(10),
                encoding="utf-8")
            (d / "bible" / "names.json").write_text(
                json.dumps({"names": [{"name": "大比目鱼", "tier": "core"}]},
                           ensure_ascii=False), encoding="utf-8")
            rows = asm._matched_blocks(d / "bible" / "characters.md",
                                       ["韩天宇"], "记忆·人物",
                                       {"大比目鱼"})
            by_src = {r["source"]: r for r in rows}
            self.assertEqual(by_src["bible/characters.md#韩天宇"]["prio"], 0,
                             "resident 标记块应常驻")
            self.assertEqual(by_src["bible/characters.md#韩天宇"]["kind"],
                             "记忆·人物·常驻")
            self.assertEqual(by_src["bible/characters.md#大比目鱼"]["prio"], 0,
                             "core 实体块应常驻（names.json tier=core）")
            self.assertEqual(by_src["bible/characters.md#集市老板"]["prio"], 1,
                             "块内含关键词=直接命中")
            self.assertEqual(by_src["bible/characters.md#铜币"]["prio"], 2,
                             "递归关联：命中块文本提到铜币→铜币块带入（不在关键词中）")
            self.assertNotIn("bible/characters.md#路人甲", by_src,
                             "未命中且无关联的块不得注入")
            self.assertIn("记忆·人物·常驻", [r["kind"] for r in rows])

    def test_outline_rewrite_export(self):
        """v0.9.3 小件三连：大纲块注入 + next_chapter 提示 / 局部改写
        （片段校验+保留率）/ 导出合并。"""
        import assemble as asm
        self.client.post("/app/api/projects/create", json={"name": "大纲书"})
        ws = Path(self.tmp.name) / "ws" / "大纲书"
        # outline.md：卷 + 当前章概要
        (ws / "outline.md").write_text(
            "## 卷一 落水" + chr(10) * 2 + "### 2 夜谈" + chr(10)
            + "雨夜对峙。" + chr(10) * 2 + "### 3 追踪" + chr(10) + "进城。" + chr(10),
            encoding="utf-8")
        import assemble as _asm
        from pathlib import Path as _P
        # 大纲块：chapter_no=2 → 本章=夜谈、前后章可见
        a = self.client.post("/app/api/assemble", json={
            "project": "大纲书", "pack": "luxun", "chapter_no": 2,
            "keywords": []}).json()
        ol = [i for i in a["items"] if i["kind"] == "大纲·卷内位置"]
        self.assertTrue(ol, "outline 存在且含本章时应注入大纲块")
        self.assertIn("夜谈", ol[0]["excerpt"])
        self.assertIn("追踪", ol[0]["excerpt"])
        # next_chapter 提示（自足：outline 写到第 6 章，manuscript 自造 005）
        msd = ws / "manuscript"
        (msd / "001-开局.md").write_text("x", encoding="utf-8")
        (msd / "005-未来章.md").write_text("x", encoding="utf-8")
        (ws / "outline.md").write_text(
            "## 卷一 落水" + chr(10) * 2 + "### 6 追踪" + chr(10) + "进城。" + chr(10),
            encoding="utf-8")
        n = self.client.get("/app/api/next_chapter",
                            params={"project": "大纲书"}).json()
        self.assertEqual(n["next"], 6)
        self.assertIn("outline.md 已有", n["outline_hint"])
        # 局部改写：片段不在正文 → 400
        bad = self.client.post("/app/api/rewrite", json={
            "project": "大纲书", "pack": "luxun", "chapter_no": 2,
            "title": "夜谈", "text": PROSE, "fragment": "不存在的片段",
            "instruction": "x"})
        self.assertEqual(bad.status_code, 400)
        # 合法片段：mock 返回 PROSE_REVISED；kept_ratio 返回
        ok = self.client.post("/app/api/rewrite", json={
            "project": "大纲书", "pack": "luxun", "chapter_no": 2,
            "title": "夜谈", "text": PROSE, "fragment": "他推门出去",
            "instruction": "更冷一点"})
        self.assertEqual(ok.status_code, 200)
        d = ok.json()
        self.assertIn("细雨", d["text"])
        self.assertIsInstance(d["kept_ratio"], float)
        self.assertIn("ai_cliche", d)
        # 导出：区间 1–2（001-开局 002-夜谈 004-x 已存在）
        (ws / "manuscript" / "001-开局.md").write_text(
            "枪说自己叫大比目鱼。", encoding="utf-8")
        (ws / "manuscript" / "002-夜谈.md").write_text("细雨。", encoding="utf-8")
        ex = self.client.post("/app/api/export", json={
            "project": "大纲书", "chapter_from": 1, "chapter_to": 2})
        self.assertEqual(ex.status_code, 200)
        self.assertIn("枪说自己叫大比目鱼", ex.text)  # 001 内容在
        self.assertIn("attachment", ex.headers["content-disposition"])
        miss = self.client.post("/app/api/export", json={
            "project": "大纲书", "chapter_from": 90, "chapter_to": 99})
        self.assertEqual(miss.status_code, 404)

    def test_ai_cliche_check_script(self):
        """v0.9.1 AI 腔检测：三档计数 + 密度 + 豁免 + 退出码。"""
        import ai_cliche_check as acc
        words = acc.load_words()
        self.assertTrue(words["tier1"] and words["tier2"] and words["tier3"])
        dirty = "他不禁缓缓抬头，嘴角上扬，月光如水。" + "正常句子。" * 20
        r = acc.check(dirty, words, set())
        self.assertEqual(r["per_tier"]["tier1"].get("不禁"), 1)
        self.assertIn("嘴角上扬", r["per_tier"]["tier2"])
        self.assertIn("月光如水", r["per_tier"]["tier3"])
        self.assertGreater(r["density"], 1.0)
        # 豁免：作者本就常用的词免报
        r2 = acc.check(dirty, words, {"不禁", "缓缓", "嘴角上扬", "月光如水"})
        self.assertEqual(r2["hits"], 0)
        clean = acc.check("平实的叙述。" * 50, words, set())
        self.assertEqual(clean["verdict"], "ok")
        # CLI 入口（退出码 1=发现）
        import subprocess, tempfile as _tf
        with _tf.TemporaryDirectory() as td:
            f = Path(td) / "d.txt"
            f.write_text(dirty, encoding="utf-8")
            cli = subprocess.run([sys.executable, str(S / "scripts" / "ai_cliche_check.py"),
                                  str(f)], capture_output=True, encoding="utf-8",
                                 errors="replace", timeout=60)
            self.assertEqual(cli.returncode, 1)
            self.assertIn("AI 腔检测", cli.stdout)

    def test_memory_delta_merge_recap_assembly(self):
        """v0.9.0 记忆接入：交付登记（judge 提取+脚本风险分级）→ 隔离区分组 →
        低风险直合并/中高 force → recap 前情 → 装配注入"记忆·前情提要"块。"""
        base = {"project": "测试项目"}
        r = self.client.post("/app/api/memory/delta", json={
            **base, "chapter_no": 3, "title": "夜谈", "text": PROSE,
            "beats": BEATS["beats"], "session_id": "mem1"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["proposed"])
        self.assertTrue({x["risk"] for x in d["proposed"]})  # 脚本自动分级
        pend = self.client.get("/app/api/memory/pending",
                               params={"project": "测试项目"}).json()
        self.assertGreaterEqual(pend["total"], 2)  # digest + change + 伏笔
        all_ids = [it["id"] for g in pend["groups"].values() for it in g]
        m1 = self.client.post("/app/api/memory/merge",
                              json={**base, "ids": all_ids, "force": False}).json()
        self.assertTrue(m1.get("blocked"), "中/高风险应被 force 门挡住")
        m2 = self.client.post("/app/api/memory/merge",
                              json={**base, "ids": all_ids, "force": True}).json()
        self.assertTrue(m2.get("merged"))
        pend2 = self.client.get("/app/api/memory/pending",
                                params={"project": "测试项目"}).json()
        self.assertEqual(pend2["total"], 0, "合并后隔离区应清空")
        rec = self.client.get("/app/api/memory/recap",
                              params={"project": "测试项目", "n": 3}).json()
        self.assertTrue(any("会说话的鱼" in r0["digest"] for r0 in rec["recent"]))
        self.assertTrue(any("鱼的来历" in f["title"]
                            for f in rec["open_foreshadow"]))
        a = self.client.post("/app/api/assemble", json={
            "project": "测试项目", "pack": "luxun", "chapter_no": 4,
            "keywords": []}).json()
        kinds = [i["kind"] for i in a["items"]]
        self.assertIn("记忆·前情提要", kinds)
        self.assertTrue(any("鱼的来历" in i["excerpt"] for i in a["items"]
                            if i["kind"] == "记忆·前情提要"))
        bad = self.client.get("/app/api/memory/pending",
                              params={"project": "../stylepacks"})
        self.assertEqual(bad.status_code, 400)

    def test_history_sessions_and_costs(self):
        """v0.9.5 历史页：sessions 列表（门禁/总账概览）+ 详情（立意/拍子/预览，
        不搬全文）+ cost 行；文件名穿越拒绝。"""
        r = self.client.get("/app/api/history/sessions",
                            params={"project": "测试项目"})
        self.assertEqual(r.status_code, 200)
        rows = r.json()["sessions"]
        self.assertTrue(rows)
        row = next(x for x in rows if x["chapter_no"] == 2)
        self.assertIn("夜谈", row["title"])
        self.assertIn("fp_ok", row)
        # 详情：立意在、全文不搬（只有预览）
        d = self.client.get("/app/api/history/session_detail",
                            params={"project": "测试项目", "file": row["file"]}).json()
        self.assertEqual(d["chosen"]["title"], "方向A")
        self.assertIn("text_preview", d)
        self.assertNotIn("text", d)
        # 成本行与累计
        c = self.client.get("/app/api/history/costs",
                            params={"project": "测试项目"}).json()
        self.assertTrue(c["rows"])
        self.assertGreater(c["total_tokens"], 0)
        # 穿越
        bad = self.client.get("/app/api/history/session_detail",
                              params={"project": "测试项目", "file": "../../pack.json"})
        self.assertEqual(bad.status_code, 404)
        page = self.client.get("/app/history")
        self.assertEqual(page.status_code, 200)
        self.assertIn("每章消耗", page.text)

    def test_project_create_skeleton_and_pin(self):
        """v0.10.0 新建项目：骨架模板 + 风格包钉扎（版本注头协议）+ 重名 409。"""
        r = self.client.post("/app/api/projects/create", json={
            "name": "新书试验", "pack": "luxun"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["name"], "新书试验")
        ws = Path(self.tmp.name) / "ws" / "新书试验"
        for sub in ("manuscript", "bible", "style", "sessions"):
            self.assertTrue((ws / sub).is_dir(), sub)
        self.assertTrue((ws / "bible" / "characters.md").is_file())
        self.assertTrue((ws / "bible" / "names.json").is_file())
        self.assertTrue((ws / "outline.md").is_file())
        self.assertIn("已钉扎 luxun", "；".join(d["notes"]))
        pinned = (ws / "style" / "pinned-pack.md").read_text(encoding="utf-8")
        self.assertIn("钉扎：luxun v", pinned[:200])
        # discover 能看到 + pinned 解析
        pr = self.client.get("/app/api/projects").json()
        entry = next(x for x in pr["projects"] if x["name"] == "新书试验")
        self.assertEqual(entry["pinned"]["pack"], "luxun")
        # 重名 409；非法名 400
        self.assertEqual(self.client.post("/app/api/projects/create",
            json={"name": "新书试验"}).status_code, 409)
        self.assertEqual(self.client.post("/app/api/projects/create",
            json={"name": "  "}).status_code, 400)

    def test_bible_editor_roundtrip_and_guard(self):
        """v0.10.0 档案编辑器：模板新建 → 读写往返 → JSON 校验拒绝 →
        白名单/穿越拒绝 → canon 钉扎与术语表可编辑。"""
        self.client.post("/app/api/projects/create", json={"name": "档案书"})
        t = self.client.post("/app/api/bible/template",
                             json={"project": "档案书", "kind": "foreshadowing"})
        self.assertEqual(t.status_code, 200)
        self.assertEqual(t.json()["path"], "bible/foreshadowing.md")
        dup = self.client.post("/app/api/bible/template",
                               json={"project": "档案书", "kind": "foreshadowing"})
        self.assertEqual(dup.status_code, 409)
        # 写合法 JSON
        w = self.client.post("/app/api/bible/file", json={
            "project": "档案书", "path": "bible/names.json",
            "content": '{"names": [{"name": "阿一", "tier": "core"}]}'})
        self.assertEqual(w.status_code, 200)
        g = self.client.get("/app/api/bible/file", params={
            "project": "档案书", "path": "bible/names.json"}).json()
        self.assertIn("阿一", g["content"])
        # 非法 JSON 拒绝且不落盘
        bad = self.client.post("/app/api/bible/file", json={
            "project": "档案书", "path": "bible/names.json",
            "content": "{not json"})
        self.assertEqual(bad.status_code, 400)
        g2 = self.client.get("/app/api/bible/file", params={
            "project": "档案书", "path": "bible/names.json"}).json()
        self.assertIn("阿一", g2["content"])
        # 白名单外与穿越拒绝
        self.assertEqual(self.client.post("/app/api/bible/file", json={
            "project": "档案书", "path": "manuscript/001-x.md",
            "content": "x"}).status_code, 400)
        self.assertEqual(self.client.post("/app/api/bible/file", json={
            "project": "档案书", "path": "../../web/config.local.json",
            "content": "x"}).status_code, 400)
        # canon 钉扎 → 术语表出现在档案清单且可编辑
        cp = self.client.get("/app/api/canon_packs").json()["packs"]
        self.assertIn("zhuifang", cp)
        pin = self.client.post("/app/api/pin_canon", json={
            "project": "档案书", "canon_pack": "zhuifang"})
        self.assertEqual(pin.status_code, 200)
        files = self.client.get("/app/api/bible/files",
                                params={"project": "档案书"}).json()["files"]
        self.assertIn("canon/canon-terms.json", files)

    def test_chapter_rename_delete(self):
        """v0.10.0 章节管理：改名保留章号（非法字符消毒/目标冲突 409），
        删除进 .trash 可恢复。"""
        self.client.post("/app/api/projects/create", json={"name": "章节管理书"})
        ms = Path(self.tmp.name) / "ws" / "章节管理书" / "manuscript"
        (ms / "002-夜谈.md").write_text("占位（冲突目标）", encoding="utf-8")
        (ms / "009-旧题.md").write_text("正文", encoding="utf-8")
        r = self.client.post("/app/api/history/chapter_rename", json={
            "project": "章节管理书", "file": "009-旧题.md", "new_title": '新/题:x'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["file"], "009-新_题_x.md")
        self.assertTrue((ms / "009-新_题_x.md").is_file())
        again = self.client.post("/app/api/history/chapter_rename", json={
            "project": "章节管理书", "file": "009-新_题_x.md",
            "new_title": "新_题_x"})
        self.assertEqual(again.status_code, 200)  # 同名幂等
        (ms / "009-占位b.md").write_text("y", encoding="utf-8") if False else None
        ms2 = ms  # 同章号目标冲突：把 009 改成已存在的"占位b"
        (ms2 / "009-占位b.md").write_text("y", encoding="utf-8")
        conf = self.client.post("/app/api/history/chapter_rename", json={
            "project": "章节管理书", "file": "009-新_题_x.md", "new_title": "占位b"})
        self.assertEqual(conf.status_code, 409)  # 目标 009-占位b.md 已存在
        d = self.client.post("/app/api/history/chapter_delete", json={
            "project": "章节管理书", "file": "009-新_题_x.md"})
        self.assertEqual(d.status_code, 200)
        self.assertFalse((ms / "009-新_题_x.md").exists())
        self.assertTrue(list((ms / ".trash").glob("*009-新_题_x.md")),
                        "删除应进 .trash 可恢复")
        miss = self.client.post("/app/api/history/chapter_delete", json={
            "project": "章节管理书", "file": "../../pack.json"})
        self.assertEqual(miss.status_code, 404)

    def test_longform_project_skeleton_and_arc(self):
        """v0.11 阶段 A：长篇项目骨架（防线/宪法/硬数字表/结构化卷纲）+
        开新弧（四字段+数字账落盘）+ longform 标记 + 轻量回归。"""
        r = self.client.post("/app/api/projects/create", json={
            "name": "长篇书", "mode": "longform"})
        self.assertEqual(r.status_code, 200)
        d = "；".join(r.json()["notes"])
        self.assertIn("长篇骨架", d)
        ws = Path(self.tmp.name) / "ws" / "长篇书"
        for f in ("00_写作防线.md", "00_项目宪法.md", "bible/硬数字表.md",
                  "outline.md"):
            self.assertTrue((ws / f).is_file(), f)
        defense = (ws / "00_写作防线.md").read_text(encoding="utf-8")
        self.assertIn("G0", defense) and self.assertIn("预算纪律", defense)
        constitution = (ws / "00_项目宪法.md").read_text(encoding="utf-8")
        self.assertIn("条款由作者填写", constitution)
        # 轻量项目不带长篇骨架
        self.client.post("/app/api/projects/create", json={"name": "轻量书"})
        lw = Path(self.tmp.name) / "ws" / "轻量书"
        self.assertFalse((lw / "00_写作防线.md").exists())
        # projects 标记
        pr = self.client.get("/app/api/projects").json()
        flags = {x["name"]: x["longform"] for x in pr["projects"]}
        self.assertTrue(flags["长篇书"])
        self.assertFalse(flags["轻量书"])
        # 状态端点
        st = self.client.get("/app/api/longform/status",
                             params={"project": "长篇书"}).json()
        self.assertTrue(st["longform"])
        self.assertEqual(st["arcs"], [])
        self.assertEqual(st["next_arc_no"], 1)
        # 开新弧：缺字段 400
        bad = self.client.post("/app/api/longform/arc_create", json={
            "project": "长篇书", "title": "弧", "start": 1, "end": 10,
            "anchors": "", "tension": "x", "hooks": "y"})
        self.assertEqual(bad.status_code, 400)
        # 正常开弧（含硬数字账）
        ok = self.client.post("/app/api/longform/arc_create", json={
            "project": "长篇书", "title": "敲门与旧账", "start": 1, "end": 10,
            "anchors": "锚点甲、锚点乙", "tension": "冲突与代价",
            "hooks": "与弧三勾连", "per_chapter": 3500,
            "numbers": [{"name": "敲声频率", "value": "每夜子时一组三下"},
                        {"name": "旧案人数", "value": "总队39"}]})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["arc_no"], 1)
        outline = (ws / "outline.md").read_text(encoding="utf-8")
        self.assertIn("【弧1·敲门与旧账】（第1-10章）", outline)
        self.assertIn("原作锚点：锚点甲、锚点乙", outline)
        nums = (ws / "bible" / "硬数字表.md").read_text(encoding="utf-8")
        self.assertIn("敲声频率", nums) and self.assertIn("总队39", nums)
        self.assertIn("| 敲声频率 | 每夜子时一组三下 |", nums)
        # 第二弧自动编号 + 章号区间校验
        self.client.post("/app/api/longform/arc_create", json={
            "project": "长篇书", "title": "弧二", "start": 11, "end": 20,
            "anchors": "a", "tension": "b", "hooks": "c"})
        st2 = self.client.get("/app/api/longform/status",
                              params={"project": "长篇书"}).json()
        self.assertEqual([a["no"] for a in st2["arcs"]], [1, 2])
        self.assertEqual(st2["next_arc_no"], 3)
        rng = self.client.post("/app/api/longform/arc_create", json={
            "project": "长篇书", "title": "x", "start": 20, "end": 10,
            "anchors": "a", "tension": "b", "hooks": "c"})
        self.assertEqual(rng.status_code, 400)
        big = self.client.post("/app/api/longform/arc_create", json={
            "project": "长篇书", "title": "x", "start": 1, "end": 99,
            "anchors": "a", "tension": "b", "hooks": "c"})
        self.assertEqual(big.status_code, 400)
        # 轻量项目开弧拒绝
        light = self.client.post("/app/api/longform/arc_create", json={
            "project": "轻量书", "title": "x", "start": 1, "end": 10,
            "anchors": "a", "tension": "b", "hooks": "c"})
        self.assertEqual(light.status_code, 400)
        # 档案编辑器可改防线/宪法（白名单）
        g = self.client.get("/app/api/bible/file",
                            params={"project": "长篇书",
                                    "path": "00_项目宪法.md"})
        self.assertEqual(g.status_code, 200)

    def test_longform_g0_numbers_and_probe(self):
        """v0.11.1 阶段 B：G0 简报端点（弧定位/探针章/图纸确认/衔接默认值）+
        硬数字表当前弧节进装配 + pending_memory + 交付 G0 留痕与数字对照 +
        轻量项目零变化。"""
        self.client.post("/app/api/projects/create", json={
            "name": "简报表", "mode": "longform"})
        self.client.post("/app/api/longform/arc_create", json={
            "project": "简报表", "title": "弧甲", "start": 3, "end": 12,
            "anchors": "锚点P", "tension": "张力Q", "hooks": "勾稽R",
            "numbers": [{"name": "旧案人数", "value": "总队39"},
                        {"name": "敲声", "value": "每夜三下"}]})
        # 弧外章节：longform 但无弧（不受 G0 门管）
        out = self.client.get("/app/api/longform/g0",
                              params={"project": "简报表",
                                      "chapter_no": 1}).json()
        self.assertTrue(out["longform"])
        self.assertIsNone(out["arc"])
        # 弧内：弧定位 + 探针章（前 2 章）+ 简报预填 + 数字表节
        g3 = self.client.get("/app/api/longform/g0",
                             params={"project": "简报表",
                                     "chapter_no": 3}).json()
        self.assertEqual(g3["arc"]["no"], 1)
        self.assertTrue(g3["probe"])
        self.assertIn("锚点P", g3["brief"]["anchor"])
        self.assertIn("1/10", g3["brief"]["arc_pos"])
        self.assertIn("旧案人数", g3["numbers_section"])
        self.assertFalse(g3["arc_confirmed"])
        g5 = self.client.get("/app/api/longform/g0",
                             params={"project": "简报表",
                                     "chapter_no": 5}).json()
        self.assertFalse(g5["probe"])
        self.assertIn("3/10", g5["brief"]["arc_pos"])
        # 图纸确认（G-0.5）：留痕 outline + 状态翻转
        c = self.client.post("/app/api/longform/arc_confirm", json={
            "project": "简报表", "arc_no": 1})
        self.assertEqual(c.status_code, 200)
        outline = (Path(self.tmp.name) / "ws" / "简报表"
                   / "outline.md").read_text(encoding="utf-8")
        self.assertIn("图纸确认", outline)
        g5b = self.client.get("/app/api/longform/g0",
                              params={"project": "简报表",
                                      "chapter_no": 5}).json()
        self.assertTrue(g5b["arc_confirmed"])
        # 硬数字表当前弧节进装配 + pending_memory 字段在场
        a = self.client.post("/app/api/assemble", json={
            "project": "简报表", "pack": "luxun", "chapter_no": 5,
            "keywords": []}).json()
        self.assertIn("规范·硬数字表", [i["kind"] for i in a["items"]])
        self.assertIn("pending_memory", a)
        # 轻量项目：G0 端点 longform=False（表单不出现——回归零变化）
        self.client.post("/app/api/projects/create", json={"name": "简报轻"})
        lw = self.client.get("/app/api/longform/g0",
                             params={"project": "简报轻",
                                     "chapter_no": 1}).json()
        self.assertFalse(lw["longform"])
        # 交付：G0 留痕 + 交付即数字对照（长篇；报不拦）
        sv = self.client.post("/app/api/save", json={
            "project": "简报表", "pack": "luxun", "chapter_no": 5,
            "title": "数字章", "text": "总队三十九人到场。远处亮起一千五百盏灯。",
            "checks": {}, "usage": {},
            "g0": {"anchor": "锚点P", "hero_state": "待命", "arc_pos": "3/10",
                   "foreshadow": "无", "quirks": "无", "ending_hook": "灯下有人",
                   "bridge": "上章钩子"}})
        self.assertEqual(sv.status_code, 200)
        self.assertIn("numbers_check", sv.json())
        self.assertIn("表外", sv.json()["numbers_check"]["report"])
        sess = sorted((Path(self.tmp.name) / "ws" / "简报表"
                       / "sessions").glob("*.json"))
        rec = json.loads(sess[-1].read_text(encoding="utf-8"))
        self.assertEqual(rec["g0"]["ending_hook"], "灯下有人")
        self.assertIn("numbers_check", rec["checks"])

    def test_longform_budget_config_and_ledger_gate(self):
        """v0.11.2 C-1/C-2：budget.json 骨架默认 + GET/POST 乐观锁（死规矩 #10）
        + 拆账强制（409 拦截 / 显式确认越过 / 网页补账后放行）+ 轻量项目无预算层。"""
        self.client.post("/app/api/projects/create", json={
            "name": "预算书", "mode": "longform"})
        ws = Path(self.tmp.name) / "ws" / "预算书"
        self.assertTrue((ws / "style" / "budget.json").is_file())
        g = self.client.get("/app/api/longform/budget",
                            params={"project": "预算书"}).json()
        self.assertEqual(g["chapter_budget"], 150000)
        self.assertEqual(g["rev"], 1)
        bad = self.client.post("/app/api/longform/budget", json={
            "project": "预算书", "chapter_budget": 100, "arc_budget": 5000,
            "halt_multiplier": 2.0, "rev": 99})
        self.assertEqual(bad.status_code, 409)  # 乐观锁
        ok = self.client.post("/app/api/longform/budget", json={
            "project": "预算书", "chapter_budget": 100, "arc_budget": 5000,
            "halt_multiplier": 2.0, "rev": 1})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["rev"], 2)
        neg = self.client.post("/app/api/longform/budget", json={
            "project": "预算书", "chapter_budget": 0, "arc_budget": 5000,
            "halt_multiplier": 2.0, "rev": 2})
        self.assertEqual(neg.status_code, 400)  # 非法值（rev 匹配后才校验值）
        # 拆账强制：手放 001 章（无交付拆账记录）→ 开第 2 章 409
        (ws / "manuscript").mkdir(exist_ok=True)
        (ws / "manuscript" / "001-手放.md").write_text("手放的上一章。\n",
                                                       encoding="utf-8")
        blk = self.client.post("/app/api/assemble", json={
            "project": "预算书", "pack": "luxun", "chapter_no": 2,
            "keywords": []})
        self.assertEqual(blk.status_code, 409)
        self.assertIn("拆账强制", blk.json()["detail"])
        bypass = self.client.post("/app/api/assemble", json={
            "project": "预算书", "pack": "luxun", "chapter_no": 2,
            "keywords": [], "allow_unbilled": True})
        self.assertEqual(bypass.status_code, 200)  # 显式确认越过
        # 网页交付补账（cost.jsonl 落第 1 章行）→ 不带 allow 也放行
        self.client.post("/app/api/save", json={
            "project": "预算书", "pack": "luxun", "chapter_no": 1,
            "title": "补账章", "text": "上一章正文。", "checks": {}, "usage": {}})
        ok2 = self.client.post("/app/api/assemble", json={
            "project": "预算书", "pack": "luxun", "chapter_no": 2,
            "keywords": []})
        self.assertEqual(ok2.status_code, 200)
        # 轻量项目无预算层
        self.client.post("/app/api/projects/create", json={"name": "预算轻"})
        lw = self.client.get("/app/api/longform/budget",
                             params={"project": "预算轻"})
        self.assertEqual(lw.status_code, 400)

    def test_longform_budget_states_and_write_mass(self):
        """v0.11.2 C-3/C-4：预警→止损 429→显式解锁（G4）；分桶拆账；
        write_mass 量产路由（量产走 mass 档/关键章走 write）；看板聚合。"""
        cfg = appstate.load_config(self.cfg_path)
        cfg["routing"]["write_mass"] = {"provider": "mock", "model": "mock-mass"}
        appstate.save_config(cfg, self.cfg_path)
        try:
            self.client.post("/app/api/projects/create", json={
                "name": "三态书", "mode": "longform"})
            self.client.post("/app/api/longform/arc_create", json={
                "project": "三态书", "title": "弧甲", "start": 1, "end": 10,
                "anchors": "a", "tension": "b", "hooks": "c"})
            self.client.post("/app/api/longform/budget", json={
                "project": "三态书", "chapter_budget": 100, "arc_budget": 5000,
                "halt_multiplier": 2.0, "rev": 1})
            g0 = {"anchor": "a", "hero_state": "b", "arc_pos": "c",
                  "foreshadow": "d", "quirks": "e", "ending_hook": "f",
                  "bridge": "g", "chapter_type": "mass"}
            sid = "budget-e2e"
            base = {"project": "三态书", "pack": "luxun", "chapter_no": 1,
                    "title": "章", "beats": [], "chosen": {}, "session_id": sid,
                    "n_drafts": 1}
            r1 = self.client.post("/app/api/generate", json={**base, "g0": g0})
            self.assertEqual(r1.status_code, 200)
            b1 = r1.json()["budget"]
            self.assertEqual(b1["state"], "warning")  # 150 ≥ 100，< 200
            self.assertEqual(b1["breakdown"]["gen"], 150)
            self.assertEqual(LAST["payload"]["model"], "mock-mass")  # 量产路由
            r2 = self.client.post("/app/api/generate", json={**base, "g0": g0})
            self.assertEqual(r2.status_code, 200)  # 闸在调用前：本轮 150 < 200 放行
            self.assertEqual(r2.json()["budget"]["state"], "halt")  # 调后 300 ≥ 200
            self.assertEqual(r2.json()["budget"]["breakdown"]["gen"], 300)
            r3 = self.client.post("/app/api/generate", json={**base, "g0": g0})
            self.assertEqual(r3.status_code, 429)  # 下一轮调用前 300 ≥ 200 → 止损闸
            self.assertIn("止损闸", r3.json()["detail"])
            r4 = self.client.post("/app/api/generate", json={
                **base, "g0": g0, "allow_over_budget": True})
            self.assertEqual(r4.status_code, 200)  # 显式确认解锁（G4）
            # 关键章永远走高档写作模型
            sid2 = "budget-key"
            self.client.post("/app/api/generate", json={
                "project": "三态书", "pack": "luxun", "chapter_no": 2,
                "title": "章", "beats": [], "chosen": {},
                "session_id": sid2, "n_drafts": 1,
                "g0": dict(g0, chapter_type="key")})
            self.assertEqual(LAST["payload"]["model"], "mock-write")
            # 交付 → 看板弧聚合（session_totals 记账口径）
            self.client.post("/app/api/save", json={
                "project": "三态书", "pack": "luxun", "chapter_no": 1,
                "title": "看板章", "text": "正文。", "checks": {},
                "usage": {}, "session_id": sid})
            bd = self.client.get("/app/api/history/board",
                                 params={"project": "三态书"}).json()
            self.assertTrue(bd["longform"])
            self.assertEqual(bd["chapter_budget"], 100)
            a1 = bd["arcs"][0]
            self.assertEqual(a1["no"], 1)
            self.assertGreater(a1["spend"], 0)
            self.assertEqual(a1["state"], "normal")  # 450 < 5000
            self.assertEqual(a1["chapters"][0]["chapter_no"], 1)
        finally:
            cfg = appstate.load_config(self.cfg_path)
            cfg["routing"].pop("write_mass", None)
            appstate.save_config(cfg, self.cfg_path)

    def test_longform_arcanet_handover_blueprint(self):
        """v0.11.3 阶段 D：漂移网指令包+归档（永不覆盖）、交接汇总草稿+落盘、
        图纸 hash 检测（外部改动→变更旗→回扫→再确认清除）。"""
        self.client.post("/app/api/projects/create", json={
            "name": "治理书", "mode": "longform"})
        self.client.post("/app/api/longform/arc_create", json={
            "project": "治理书", "title": "弧甲", "start": 1, "end": 5,
            "anchors": "锚点X", "tension": "张力Y", "hooks": "勾稽Z",
            "numbers": [{"name": "旧案人数", "value": "总队39"}]})
        ws = Path(self.tmp.name) / "ws" / "治理书"
        # 首次 g0：基线自动建，无变更（开弧已同步基线）
        g0v = self.client.get("/app/api/longform/g0",
                              params={"project": "治理书",
                                      "chapter_no": 1}).json()
        self.assertEqual(g0v["blueprint_changed"], [])
        # 外部直改 outline.md → 变更旗亮起（§5.3 防线4：hash 检测）
        outline = ws / "outline.md"
        outline.write_text(outline.read_text(encoding="utf-8")
                           + chr(10) + "<!-- 外部手改 -->", encoding="utf-8")
        g0v2 = self.client.get("/app/api/longform/g0",
                               params={"project": "治理书",
                                       "chapter_no": 1}).json()
        self.assertIn("outline.md", g0v2["blueprint_changed"])
        rs = self.client.post("/app/api/longform/retroscan",
                              json={"project": "治理书"}).json()
        self.assertIn("exit_code", rs) and self.assertIn("report", rs)
        rc = self.client.post("/app/api/longform/blueprint_confirm",
                              json={"project": "治理书"})
        self.assertEqual(rc.status_code, 200)
        g0v3 = self.client.get("/app/api/longform/g0",
                               params={"project": "治理书",
                                       "chapter_no": 1}).json()
        self.assertEqual(g0v3["blueprint_changed"], [])  # 再确认清除
        # 漂移网指令包（清单模式）+ 404
        net = self.client.get("/app/api/longform/arcanet",
                              params={"project": "治理书", "arc_no": 1}).json()
        self.assertIn("弧1《弧甲》", net["prompt"])
        self.assertIn("旧案人数", net["prompt"])
        self.assertIn("第 1-5 章", net["prompt"])
        self.assertIn("清单", net["prompt"])
        self.assertIn("三分诊断", net["prompt"])
        nf = self.client.get("/app/api/longform/arcanet",
                             params={"project": "治理书", "arc_no": 9})
        self.assertEqual(nf.status_code, 404)
        # 归档 + 撞名不覆盖
        a1 = self.client.post("/app/api/longform/arcanet/archive", json={
            "project": "治理书", "arc_no": 1, "report": "复检：通过"})
        a2 = self.client.post("/app/api/longform/arcanet/archive", json={
            "project": "治理书", "arc_no": 1, "report": "复检：通过（复跑）"})
        self.assertEqual(a1.status_code, 200)
        self.assertEqual(a2.status_code, 200)
        self.assertNotEqual(a1.json()["file"], a2.json()["file"])
        rep_dir = ws / "整合" / "一致性报告"
        self.assertEqual(len(list(rep_dir.glob("弧1-漂移网-*.md"))), 2)
        # 交付一章（带 G0 钩子）→ 交接汇总：进度/钩子/弧状态/落盘
        self.client.post("/app/api/save", json={
            "project": "治理书", "pack": "luxun", "chapter_no": 1,
            "title": "交接章", "text": "正文若干。", "checks": {},
            "usage": {}, "g0": {"anchor": "a", "hero_state": "b",
                                "arc_pos": "c", "foreshadow": "d",
                                "quirks": "e", "ending_hook": "门外有脚步",
                                "bridge": "g"}})
        ho = self.client.get("/app/api/longform/handover",
                             params={"project": "治理书"}).json()
        md = ho["markdown"]
        self.assertIn("## 一、进度", md)
        self.assertIn("门外有脚步", md)
        self.assertIn("图纸未确认", md)
        self.assertIn("漂移网已归档", md)
        self.assertIn("## 四、未回收伏笔", md)
        hs = self.client.post("/app/api/longform/handover/save", json={
            "project": "治理书", "markdown": md})
        self.assertEqual(hs.status_code, 200)
        self.assertTrue(any(ws.glob("00_交接汇总-草稿-*.md")))
        # 轻量项目：弧末工具全部拒绝
        self.client.post("/app/api/projects/create", json={"name": "治理轻"})
        for method, url, payload in (
                ("GET", "/app/api/longform/arcanet", None),
                ("GET", "/app/api/longform/handover", None)):
            r = (self.client.get(url, params={"project": "治理轻",
                                              "arc_no": 1})
                 if method == "GET" else self.client.post(url, json=payload))
            self.assertEqual(r.status_code, 400, url)
        r = self.client.post("/app/api/longform/retroscan",
                             json={"project": "治理轻"})
        self.assertEqual(r.status_code, 400)

    def test_longform_batch_plan(self):
        """v0.12 量产连跑·规划器：简报自动产出（钩子链/探针/关键章标记/
        预检数据）+ 边界校验（弧外/已交付/超硬顶）+ 交付带预算态 + 账本
        session 字段。循环本体在前端（J1），服务端只出计划表。"""
        self.client.post("/app/api/projects/create", json={
            "name": "连跑书", "mode": "longform"})
        self.client.post("/app/api/longform/arc_create", json={
            "project": "连跑书", "title": "弧甲", "start": 1, "end": 10,
            "anchors": "锚点甲、锚点乙", "tension": "张力", "hooks": "勾稽"})
        # 边界：弧外 / 超硬顶
        self.assertEqual(self.client.get(
            "/app/api/longform/batch/plan",
            params={"project": "连跑书", "start": 0, "count": 5}).status_code, 400)
        self.assertEqual(self.client.get(
            "/app/api/longform/batch/plan",
            params={"project": "连跑书", "start": 1, "count": 11}).status_code, 400)
        # 正常计划：5 行、探针前 2、简报字段齐、预估/路由预检在场
        p1 = self.client.get("/app/api/longform/batch/plan",
                             params={"project": "连跑书",
                                     "start": 1, "count": 5}).json()
        self.assertEqual([r["chapter_no"] for r in p1["rows"]],
                         [1, 2, 3, 4, 5])
        self.assertTrue(p1["rows"][0]["probe"]) and self.assertTrue(p1["rows"][1]["probe"])
        self.assertFalse(p1["rows"][2]["probe"])
        self.assertEqual(p1["rows"][0]["brief"]["chapter_type"], "mass")
        self.assertIn("锚点甲", p1["rows"][0]["brief"]["anchor"])
        self.assertIn("弧1《弧甲》", p1["rows"][0]["brief"]["arc_pos"])
        self.assertEqual(p1["estimate_tokens"], 0)
        self.assertFalse(p1["write_mass"])
        # 已交付章不可作起点
        ws = Path(self.tmp.name) / "ws" / "连跑书"
        (ws / "manuscript").mkdir(exist_ok=True)
        (ws / "manuscript" / "001-在先.md").write_text("已有章。\n",
                                                       encoding="utf-8")
        self.assertEqual(self.client.get(
            "/app/api/longform/batch/plan",
            params={"project": "连跑书", "start": 1, "count": 5}).status_code, 400)
        # 交付带预算态 + 账本 session 字段 + 钩子链跨行
        sv = self.client.post("/app/api/save", json={
            "project": "连跑书", "pack": "luxun", "chapter_no": 1,
            "title": "链头", "text": "正文若干。", "checks": {}, "usage": {},
            "session_id": "bp-s1",
            "g0": {"anchor": "a", "hero_state": "b", "arc_pos": "c",
                   "foreshadow": "d", "quirks": "e",
                   "ending_hook": "门外有脚步", "bridge": "g"}})
        self.assertEqual(sv.status_code, 200)
        self.assertIn("budget", sv.json())
        cost = (ws / "style" / "cost.jsonl").read_text(encoding="utf-8")
        self.assertIn('"session"', cost)
        p2 = self.client.get("/app/api/longform/batch/plan",
                             params={"project": "连跑书",
                                     "start": 2, "count": 3}).json()
        self.assertEqual(p2["rows"][0]["chapter_no"], 2)
        self.assertTrue(p2["rows"][0]["probe"])  # 章 2 仍是探针（前 2 章）
        # 服务端把前章真实钩子接到批内第一章；后续行由前端钩子链（人工填钩子）接续
        self.assertEqual(p2["rows"][0]["brief"]["bridge"], "门外有脚步")
        self.assertEqual(p2["rows"][1]["brief"]["bridge"], "")
        self.assertFalse(p2["rows"][1]["probe"])
        # 弧末自动标关键章（J4）
        p3 = self.client.get("/app/api/longform/batch/plan",
                             params={"project": "连跑书",
                                     "start": 9, "count": 5}).json()
        self.assertTrue(p3["clamped"])  # 9-10 被弧末截断
        self.assertEqual([r["chapter_no"] for r in p3["rows"]], [9, 10])
        self.assertEqual(p3["rows"][1]["brief"]["chapter_type"], "key")
        self.assertEqual(p3["rows"][1]["key_reason"], "弧末章")
        # 轻量项目拒绝
        self.client.post("/app/api/projects/create", json={"name": "连跑轻"})
        self.assertEqual(self.client.get(
            "/app/api/longform/batch/plan",
            params={"project": "连跑轻", "start": 1, "count": 5}).status_code, 400)

    def test_names_check_and_trend(self):
        """v0.12.1 欠账补完：names_check 三模态（禁用变体/人物状态门+引号豁免/
        卡面禁语黄级/零出现向后兼容）+ 交付带 names_check + 批后趋势报告归档。"""
        import subprocess
        nck = S / "scripts" / "names_check.py"
        ws = Path(self.tmp.name) / "ws" / "专名账"
        (ws / "bible").mkdir(parents=True, exist_ok=True)
        (ws / "manuscript").mkdir(exist_ok=True)
        tsv = ws / "bible" / "专名表.tsv"
        tsv.write_text("# 注释行\n陈曦\t陈熙|陈稀\n", encoding="utf-8", newline="\n")
        (ws / "bible" / "characters.md").write_text(
            "## 老王\n车夫。状态：死亡（第3章）\n\n## 阿静\n琴师。禁语：没关系\n",
            encoding="utf-8", newline="\n")
        (ws / "bible" / "names.json").write_text(
            '{"names": [{"name": "老王", "tier": "core", "aliases": ["王老"]},'
            ' {"name": "孔乙己", "tier": "minor", "aliases": []}]}',
            encoding="utf-8", newline="\n")
        args = ["--variants", str(tsv), "--characters",
                str(ws / "bible" / "characters.md"),
                "--namesjson", str(ws / "bible" / "names.json")]
        # 干净稿：正名在场、死者不出现、禁语不出现
        good = ws / "manuscript" / "001-甲.md"
        good.write_text("陈曦点头，收起了琴。\n", encoding="utf-8", newline="\n")
        r = subprocess.run([sys.executable, str(nck), str(good), *args],
                           capture_output=True, encoding="utf-8",
                           errors="replace")
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        # 违规稿：错写 + 死者叙述出现 + 禁语同现
        bad = ws / "manuscript" / "002-乙.md"
        bad.write_text("陈熙点头。老王也来了。阿静笑着说：没关系。\n",
                       encoding="utf-8", newline="\n")
        r2 = subprocess.run([sys.executable, str(nck), str(bad), *args],
                            capture_output=True, encoding="utf-8",
                            errors="replace")
        out2 = (r2.stdout or "") + (r2.stderr or "")
        self.assertEqual(r2.returncode, 1, out2)
        self.assertIn("[专名错写]", out2)
        self.assertIn("[状态冲突]", out2)
        self.assertIn("[禁语·黄]", out2)
        # 引号豁免（J8）：死者只在对话中被提及 → 状态门放行
        memo = ws / "manuscript" / "003-丙.md"
        memo.write_text("“老王当年赶车最稳。”他回忆道。\n",
                        encoding="utf-8", newline="\n")
        r3 = subprocess.run([sys.executable, str(nck), str(memo), *args],
                            capture_output=True, encoding="utf-8",
                            errors="replace")
        self.assertEqual(r3.returncode, 0, (r3.stdout or "") + (r3.stderr or ""))
        # 零出现向后兼容（模态①原契约：孔乙己全文未出现 → 1）
        r4 = subprocess.run([sys.executable, str(nck), str(good),
                             "--names", str(ws / "bible" / "names.json")],
                            capture_output=True, encoding="utf-8",
                            errors="replace")
        self.assertEqual(r4.returncode, 1)
        self.assertIn("零出现 2", r4.stdout or "")
        # Web：长篇交付带 names_check（连跑书有 001 章）
        sv = self.client.post("/app/api/save", json={
            "project": "连跑书", "pack": "luxun", "chapter_no": 2,
            "title": "专名章", "text": "正文。", "checks": {}, "usage": {}})
        self.assertEqual(sv.status_code, 200)
        self.assertIn("names_check", sv.json())
        # 批后趋势报告：归档 + 轻量 400
        tr = self.client.post("/app/api/longform/batch/report", json={
            "project": "连跑书", "pack": "luxun", "start": 1, "end": 1})
        self.assertEqual(tr.status_code, 200)
        self.assertIn("file", tr.json())
        self.assertTrue((Path(self.tmp.name) / "ws" / "连跑书" / "整合"
                         / "趋势报告").is_dir())
        lw = self.client.post("/app/api/longform/batch/report", json={
            "project": "连跑轻", "pack": "luxun", "start": 1, "end": 1})
        self.assertEqual(lw.status_code, 400)

    def test_serial_page_and_tree(self):
        """v0.13.0：连载管理台页面 + 共享 creation.js 抽取（create 页零内联）
        + 文件树（来源标注/子目录/灰标）+ 预览截断 + traversal 拦截 + 下载
        + 资源管理器逃生门（patch 不真开）。"""
        from unittest.mock import patch
        import routes_serial
        # 共享脚本可达且 create 页已改为外链（单章页零内联——双入口同源）
        r = self.client.get("/static/creation.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("async function doAssemble", r.text)
        cr = self.client.get("/app/create")
        self.assertEqual(cr.status_code, 200)
        self.assertIn("/static/creation.js", cr.text)
        self.assertNotIn("async function doAssemble", cr.text)
        # 连载台页面：三栏壳关键件齐
        pg = self.client.get("/app/serial")
        self.assertEqual(pg.status_code, 200)
        for mark in ("项目文件树", "step_g0", "sumcard", "budgetbox",
                     "serial-grid", "/static/creation.js"):
            self.assertIn(mark, pg.text)
        # 树：顶层目录 + 来源标注
        t = self.client.get("/app/api/serial/tree",
                            params={"project": "测试项目"}).json()
        names = {e["name"] for e in t["entries"]}
        self.assertIn("manuscript", names) and self.assertIn("bible", names)
        man = next(e for e in t["entries"] if e["name"] == "manuscript")
        self.assertEqual(man["source"], "交付落盘")
        # 子目录 + 文件条目
        t2 = self.client.get("/app/api/serial/tree",
                             params={"project": "测试项目",
                                     "sub": "manuscript"}).json()
        f = next(e for e in t2["entries"] if e["rel"].startswith("manuscript/001"))
        # 预览（小文件不截断）
        fv = self.client.get("/app/api/serial/file",
                             params={"project": "测试项目",
                                     "path": f["rel"]}).json()
        self.assertIn("大比目鱼", fv["text"])
        self.assertFalse(fv["truncated"])
        # traversal 拦截（树与文件两路）
        for bad in ("../stylepacks", "manuscript/../../x"):
            self.assertEqual(self.client.get(
                "/app/api/serial/tree",
                params={"project": "测试项目", "sub": bad}).status_code, 400, bad)
        self.assertEqual(self.client.get(
            "/app/api/serial/file",
            params={"project": "测试项目",
                    "path": "../../config.local.json"}).status_code, 400)
        # 下载
        dl = self.client.get("/app/api/serial/download",
                             params={"project": "测试项目", "path": f["rel"]})
        self.assertEqual(dl.status_code, 200)
        # 大文件截断
        big = Path(self.tmp.name) / "ws" / "测试项目" / "manuscript" / "099-大.md"
        big.write_text("字" * 40000, encoding="utf-8")
        fv2 = self.client.get("/app/api/serial/file",
                              params={"project": "测试项目",
                                      "path": "manuscript/099-大.md"}).json()
        self.assertTrue(fv2["truncated"])
        big.unlink()
        # 资源管理器逃生门：patch 真实打开，只验守卫与调用
        with patch.object(routes_serial, "_open_folder") as m:
            of = self.client.post("/app/api/serial/open_folder",
                                  json={"project": "测试项目"})
            self.assertEqual(of.status_code, 200)
            m.assert_called_once()
        with patch.object(routes_serial, "_open_folder") as m2:
            bad = self.client.post("/app/api/serial/open_folder",
                                   json={"project": "../x"})
            self.assertEqual(bad.status_code, 400)
            m2.assert_not_called()

    def test_single_page_slimmed(self):
        """v0.13.1 分家第二半：单章页摘除全部长篇件（按钮/面板），长篇项目
        由前端自动跳转连载台；连载台保留全部长篇件。"""
        cr = self.client.get("/app/create").text
        for gone in ("btn_arc", "btn_net", "btn_ho", "btn_batch",
                     'id="step_g0"', 'id="arctools"', 'id="budgetbox"'):
            self.assertNotIn(gone, cr, gone)
        self.assertIn("单章快写", cr)
        self.assertIn('data-page="create"', cr)
        js = self.client.get("/static/creation.js").text
        self.assertIn("maybeRedirectLongform", js)
        self.assertIn("PAGE !== 'serial'", js)
        sr = self.client.get("/app/serial").text
        for kept in ("btn_arc", "btn_batch", 'id="step_g0"',
                     'id="budgetbox"', 'id="arctools"'):
            self.assertIn(kept, sr, kept)
        self.assertIn('data-page="serial"', sr)

    def test_numbers_check_script(self):
        """v0.11.1 B-3：数字对照脚本三分类（口径缺失/表外分级/豁免/约略）+
        --all 回扫 + 中文数字解析单元。"""
        import subprocess
        nck = __import__("numbers_check")
        for raw, want in [("一万二", 12000), ("三千五", 3500), ("二十五", 25),
                          ("三千五百零六", 3506), ("一万两千五百", 12500),
                          ("三十九", 39), ("两百", 200), ("十", 10), ("五", 5)]:
            self.assertEqual(nck.zh_to_int(raw), want, raw)
        ws = Path(self.tmp.name) / "ws" / "数字账"
        (ws / "bible").mkdir(parents=True, exist_ok=True)
        (ws / "manuscript").mkdir(exist_ok=True)
        ledger = ws / "bible" / "硬数字表.md"
        ledger.write_text(
            "# 硬数字表\n\n## 弧1《甲》（第1-10章）\n\n| 账目 | 口径 |\n|---|---|\n"
            "| 旧案人数 | 总队39 |\n| 敲声 | 每夜三下 |\n\n## 豁免数字\n- 666\n",
            encoding="utf-8", newline="\n")
        good = ws / "manuscript" / "001-甲.md"
        good.write_text("总队39人到场。每夜三下，敲了约39下。旧档案编号666。\n"
                        "他又数了十几遍，直到月上中天。\n",
                        encoding="utf-8", newline="\n")
        r = subprocess.run([sys.executable, str(S / "scripts" / "numbers_check.py"),
                            str(good), "--ledger", str(ledger), "--chapter", "1"],
                           capture_output=True, encoding="utf-8",
                           errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        self.assertEqual(r.returncode, 0, out)
        self.assertNotIn("口径缺失", out) and self.assertNotIn("表外", out)
        bad = ws / "manuscript" / "002-乙.md"
        bad.write_text("人群围拢。远处亮起一千五百盏灯。\n",
                       encoding="utf-8", newline="\n")
        r2 = subprocess.run([sys.executable, str(S / "scripts" / "numbers_check.py"),
                             str(bad), "--ledger", str(ledger), "--chapter", "1"],
                            capture_output=True, encoding="utf-8",
                            errors="replace")
        out2 = (r2.stdout or "") + (r2.stderr or "")
        self.assertEqual(r2.returncode, 1, out2)
        self.assertIn("口径缺失", out2)          # 39 未出现
        self.assertIn("表外·设定级候选", out2)   # 1500 ≥100
        self.assertNotIn("666", out2)            # 豁免清单生效
        # --all 回扫（retroscan 模式）
        r3 = subprocess.run([sys.executable, str(S / "scripts" / "numbers_check.py"),
                             str(ws), "--ledger", str(ledger), "--all"],
                            capture_output=True, encoding="utf-8",
                            errors="replace")
        out3 = (r3.stdout or "") + (r3.stderr or "")
        self.assertEqual(r3.returncode, 1, out3)
        self.assertIn("001-甲.md", out3) and self.assertIn("002-乙.md", out3)
        self.assertIn("2 章", out3)

    def test_unconfigured_route_fails_clean(self):
        cfg = appstate.load_config(self.cfg_path)
        cfg["routing"]["write"] = None
        appstate.save_config(cfg, self.cfg_path)
        r = self.client.post("/app/api/outline", json={
            "project": "测试项目", "pack": "luxun", "chapter_no": 2,
            "title": "夜谈", "keywords": []})
        self.assertEqual(r.status_code, 400)
        self.assertIn("模型配置", r.json()["detail"])
        cfg["routing"]["write"] = {"provider": "mock", "model": "mock-write"}
        appstate.save_config(cfg, self.cfg_path)

    def test_extract_json_truncated_repair(self):
        """真实场景回归：立意 2–3 项 JSON 被 max_tokens 截断——修复应救回完整项。"""
        import creation
        good = json.dumps({"options": [
            {"title": "甲", "angle": "角度甲", "action": "立意动作 1",
             "stance": "克制"},
            {"title": "乙", "angle": "角度乙", "action": "立意动作 2",
             "stance": "自省"}], "recommended": 0}, ensure_ascii=False)
        cut = good[:good.index("角度乙") + 3]  # 截断在第二项中间
        fixed = creation.extract_json(cut)
        self.assertEqual(fixed["options"][0]["title"], "甲")
        self.assertEqual(len(fixed["options"]), 2)
        # 尾部悬空逗号 + 截断
        cut2 = good[:good.index('"stance": "自省"')] + '"stance": "自省",'
        fixed2 = creation.extract_json(cut2)
        self.assertEqual(fixed2["options"][1]["stance"], "自省")
        # 围栏 + 完整 JSON 原样可用
        fenced = "```json" + chr(10) + good + chr(10) + "```"
        self.assertEqual(creation.extract_json(fenced), json.loads(good))

    def test_localhost_binding_source(self):
        src = (S / "web" / "launch.py").read_text(encoding="utf-8")
        self.assertIn('host="127.0.0.1"', src)
        self.assertNotIn('("0.0.0.0"', src)


if __name__ == "__main__":
    unittest.main()
