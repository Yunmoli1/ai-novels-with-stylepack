# -*- coding: utf-8 -*-
"""mcp_server：StylePack MCP server（stdlib 手写 JSON-RPC 2.0 over stdio）。

只实现 MCP 最小子集：initialize / tools/list / tools/call / ping。
启动：python server/mcp_server.py --project <项目路径>（默认当前目录）
配置方法见 docs/adapters/mcp.md。日志一律走 stderr，stdout 只输出协议消息。

工具纪律（v0.2-计划书）：≤10 个工具；每次返回 ≤2KB；每次调用自动记账
（写 <项目>/style/cost.jsonl，与 cost.py 同账本）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))

import splib  # noqa: E402
import cost  # noqa: E402
from store import Store, fit, RETURN_LIMIT  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "stylepack", "version": "0.2.0"}


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required or []}


class MCPServer:
    def __init__(self, project: Path):
        self.project = Path(project).resolve()
        self.store = Store(self.project)
        self._chars = 0  # 本次工具调用的读取量（记账用）

    # ---- 工具实现（返回 dict；用 self._chars 上报读取量）
    def t_sync(self, args: dict) -> dict:
        self._chars = 0
        return self.store.sync()

    def t_search(self, args: dict) -> dict:
        rows = self.store.search(args.get("query", ""), int(args.get("k", 5)))
        self._chars = sum(len(r["snippet"]) for r in rows)
        return {"results": rows}

    def t_character(self, args: dict) -> dict:
        card = self.store.character(args.get("name", ""))
        self._chars = len(json.dumps(card, ensure_ascii=False)) if card else 0
        return {"card": card} if card else {"card": None,
                                            "hint": "未找到实体；先运行 story.sync"}

    def t_recap(self, args: dict) -> dict:
        data = self.store.recap(int(args.get("n", 3)))
        data["pending_aging"] = self.store.pending_aging()
        self._chars = len(json.dumps(data, ensure_ascii=False))
        return data

    def t_foreshadow(self, args: dict) -> dict:
        rows = self.store.foreshadow(args.get("status"))
        self._chars = sum(len(r["title"]) for r in rows)
        return {"foreshadow": rows}

    def t_propose_delta(self, args: dict) -> dict:
        payload = args.get("payload") or {}
        self._chars = len(json.dumps(payload, ensure_ascii=False))
        return self.store.propose_delta(payload)

    def t_merge_delta(self, args: dict) -> dict:
        ids = args.get("ids")
        self._chars = 0
        return self.store.merge_delta(ids, bool(args.get("force", False)))

    def t_cost_forecast(self, args: dict) -> dict:
        remaining = int(args.get("chapters_remaining", 0))
        done = len(list((self.project / "manuscript").glob("*.md"))) \
            if (self.project / "manuscript").is_dir() else 0
        lines = cost.forecast(self.project, chapters_total=done + remaining)
        self._chars = 0
        return {"forecast": lines}

    @staticmethod
    def _pack_brief(p: Path) -> dict:
        """包清单条目：只给选包要用的字段，控制返回体积。"""
        try:
            pj = json.loads((p / "pack.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"name": p.name}
        has_delta = False
        fp = p / "fingerprint.json"
        if fp.is_file():
            try:
                has_delta = "delta_profile" in json.loads(
                    fp.read_text(encoding="utf-8"))
            except ValueError:
                pass
        return {"name": pj.get("name", p.name),
                "display_name": pj.get("display_name", ""),
                "version": pj.get("version", ""),
                "has_delta_profile": has_delta}

    def t_stylepack_info(self, args: dict) -> dict:
        self._chars = 0
        name = args.get("name", "")
        packs_dir = ROOT / "stylepacks"
        dirs = sorted((p for p in packs_dir.iterdir() if (p / "pack.json").is_file()),
                      key=lambda p: p.name)
        if not name:  # 缺省 = 列出可用包：高频意图走成功路径，不走错误路径
            return {"packs": [self._pack_brief(p) for p in dirs]}
        base = packs_dir / name
        if not (base / "pack.json").is_file():
            # 别名解析：目录名查不到时按 pack.json 的 name / display_name（如"鲁迅"→ luxun）
            for p in dirs:
                try:
                    pj = json.loads((p / "pack.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if name in (pj.get("name"), pj.get("display_name")):
                    base = p
                    break
        if not (base / "pack.json").is_file():
            return {"error": f"找不到风格包：{name}",
                    "available": [self._pack_brief(p) for p in dirs]}
        info = json.loads((base / "pack.json").read_text(encoding="utf-8"))
        # MCP 返回纪律 ≤2KB：changelog 随包增长必然撑爆 info 载荷，
        # 只保留最新一条供模型了解当前版本
        cl = info.get("changelog") or []
        if cl:
            info["changelog_latest"] = cl[-1]
        info.pop("changelog", None)
        fp = base / "fingerprint.json"
        info["has_delta_profile"] = False
        if fp.is_file():
            fj = json.loads(fp.read_text(encoding="utf-8"))
            info["has_delta_profile"] = "delta_profile" in fj
        return {"info": info}

    def t_fp_check(self, args: dict) -> dict:
        pack = Path(args.get("pack", ""))
        text_path = Path(args.get("text_path", ""))
        if not pack.is_absolute():
            pack = self.project / pack
        if not text_path.is_absolute():
            text_path = self.project / text_path
        fingerprint = splib.load_json(pack / "fingerprint.json")
        pack_lang = fingerprint.get("language")
        if not pack_lang:
            pj = pack / "pack.json"
            if pj.is_file():
                pack_lang = json.loads(pj.read_text(encoding="utf-8")).get("language")
        pack_lang = splib.normalize_lang(pack_lang or splib.LANG_ZH)
        files = splib.collect_text_files([text_path])
        text = "\n\n".join(splib.read_text(f)[0] for f in files)
        self._chars = splib._clen(text)
        # v0.2.3：与 CLI fp_check 共用分层验收路径（auto 选层 + 真迹包络 + 短文门槛）
        out = splib.layered_check(text, fingerprint,
                                  genre=args.get("genre"),
                                  delta_max_override=args.get("delta_max"),
                                  lang=pack_lang)
        if out.get("language_mismatch"):
            return {"pack": pack.name, "ok": False,
                    "language_mismatch": True,
                    "pack_language": out["pack_language"],
                    "text_language": out["text_language"],
                    "notes": out["notes"], "rows": []}
        return {"pack": pack.name, "genre": out["genre"], "layer_used": out["layer_used"],
                "ok": out["ok"],
                "rows": [{k: r[k] for k in ("path", "target", "actual", "ok")}
                         for r in out["rows"]],
                "delta": out["delta"], "delta_counted": out["delta_counted"],
                "delta_note": out["delta_note"]}

    # ---- 工具注册表（≤10 个，描述给模型选）
    def tools(self) -> list[dict]:
        return [
            {"name": "story.sync",
             "description": "把 bible/corpus 文件（权威源）导入状态机并重建索引；初始化或 bible 变更后调用",
             "inputSchema": _schema({})},
            {"name": "story.search",
             "description": "全文检索正文与设定（伏笔原文、前文提及），返回路径+片段，绝不返回全文",
             "inputSchema": _schema({"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"])},
            {"name": "story.character",
             "description": "取人物卡：设定摘要+tier+最近 3 条状态（写前加载人物上下文用这个，不读 characters.md 全文）",
             "inputSchema": _schema({"name": {"type": "string"}}, ["name"])},
            {"name": "story.recap",
             "description": "前情提要：最近 n 章摘要+未回收伏笔+pending 滞留与老化提醒（续写前必调）",
             "inputSchema": _schema({"n": {"type": "integer"}})},
            {"name": "story.foreshadow",
             "description": "查伏笔账本（可按 status=planted/closed 过滤）",
             "inputSchema": _schema({"status": {"type": "string"}})},
            {"name": "story.propose_delta",
             "description": "写完一章后登记状态变更（入隔离区）：payload={chapter,digest,changes:[{entity,field,value,risk?}],foreshadow?}",
             "inputSchema": _schema({"payload": {"type": "object"}}, ["payload"])},
            {"name": "story.merge_delta",
             "description": "合并隔离区变更进正式状态：低风险自动合并；中/高风险需用户确认后 force=true",
             "inputSchema": _schema({"ids": {"type": "array", "items": {"type": "integer"}},
                                     "force": {"type": "boolean"}})},
            {"name": "story.cost_forecast",
             "description": "按记账历史+章节进度预测剩余成本（字符量区间）",
             "inputSchema": _schema({"chapters_remaining": {"type": "integer"}},
                                    ["chapters_remaining"])},
            {"name": "stylepack.info",
             "description": "查风格包清单（版本/语料置信度/是否有 Delta 档案）；name 缺省=列出全部可用包，name 支持目录名或中文名（如 鲁迅 / luxun）",
             "inputSchema": _schema({"name": {"type": "string"}})},
            {"name": "fp.check",
             "description": "风格指纹验收：按文本文体自动选层（分层包），逐指标阈值 + 层内真迹留一 Delta 及格线；genre 可指定 auto/narrative/essay/all，delta_max 显式覆盖及格线",
             "inputSchema": _schema({"pack": {"type": "string"},
                                     "text_path": {"type": "string"},
                                     "genre": {"type": "string", "enum": ["auto", "narrative", "essay", "all"]},
                                     "delta_max": {"type": "number"}},
                                    ["pack", "text_path"])},
        ]

    def call_tool(self, name: str, args: dict) -> dict:
        self._chars = 0
        handlers = {
            "story.sync": self.t_sync,
            "story.search": self.t_search,
            "story.character": self.t_character,
            "story.recap": self.t_recap,
            "story.foreshadow": self.t_foreshadow,
            "story.propose_delta": self.t_propose_delta,
            "story.merge_delta": self.t_merge_delta,
            "story.cost_forecast": self.t_cost_forecast,
            "stylepack.info": self.t_stylepack_info,
            "fp.check": self.t_fp_check,
        }
        if name not in handlers:
            return {"error": f"未知工具：{name}"}
        try:
            result = handlers[name](args or {})
        except Exception as e:  # noqa: BLE001 —— 工具失败走 isError，不崩协议
            return {"error": f"{type(e).__name__}: {e}"}
        if self._chars:
            try:
                cost.log_entry(self.project, f"mcp:{name}", self._chars)
            except Exception:  # noqa: BLE001 —— 记账失败不影响主流程
                pass
        return fit(result)

    # ---- JSON-RPC 协议
    def handle(self, msg: dict) -> dict | None:
        """处理一条已解析的协议消息；通知返回 None，请求返回响应对象。"""
        method = msg.get("method", "")
        msg_id = msg.get("id")
        if method.startswith("notifications/"):
            return None
        try:
            if method == "initialize":
                result = {"protocolVersion": msg.get("params", {}).get(
                    "protocolVersion", PROTOCOL_VERSION),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                params = msg.get("params", {})
                out = self.call_tool(params.get("name", ""), params.get("arguments") or {})
                if "error" in out:
                    # 错误也带全载荷：available 等自救信息不许在协议层被丢弃
                    result = {"content": [{"type": "text",
                                           "text": json.dumps(out, ensure_ascii=False)}],
                              "isError": True}
                else:
                    result = {"content": [{"type": "text",
                                           "text": json.dumps(out, ensure_ascii=False)}],
                              "isError": False}
            else:
                return {"jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32601, "message": f"未知方法：{method}"}}
        except Exception as e:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        if size > 2 * RETURN_LIMIT:  # 协议层兜底（工具层已 fit 到 ≤2KB）
            result = {"content": [{"type": "text",
                                   "text": json.dumps({"truncated": True},
                                                      ensure_ascii=False)}],
                      "isError": True}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def run_stdio(self) -> None:
        splib.force_utf8_stdio()  # 协议字节必须是 UTF-8，不许本地代码页污染
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                self._send({"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32700, "message": f"解析失败：{e}"}})
                continue
            resp = self.handle(msg)
            if resp is not None:
                self._send(resp)

    @staticmethod
    def _send(obj: dict) -> None:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description="StylePack MCP server")
    ap.add_argument("--project", default=".", help="写作项目目录（默认当前目录）")
    args = ap.parse_args()
    server = MCPServer(Path(args.project))
    print(f"stylepack mcp ready: project={server.project}", file=sys.stderr)
    server.run_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
