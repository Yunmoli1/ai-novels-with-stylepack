# -*- coding: utf-8 -*-
"""appstate：工作台配置与工作区数据层（v0.6.0，r4 红线 2 的双层数据落点）。

- 模型配置（含 API key）只存 web/config.local.json（gitignore，服务端本地），
  永不入 git/日志/浏览器 DOM——对外接口一律脱敏（GET 不回 key）。
- 工作区数据 = 文件（pinned/cost/sessions/manuscript），不用 SQL；
  读现有协议（style/pinned-pack.md 存在则作为默认包提示），写只落工作区。
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "web" / "config.local.json"


def workbench_version() -> str:
    """当前工作台版本 = CHANGELOG 最新条目（页脚/启动横幅显示——
    防"旧实例跑旧代码"事故重演，用户一眼可核）。"""
    try:
        head = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")[:400]
        if m := re.search(r"^## \[([\d.]+)\]", head, re.M):
            return m.group(1)
    except OSError:
        pass
    return "?"

DEFAULT_CONFIG = {
    "rev": 0,                  # 乐观锁版本号：每次保存 +1（防陈旧页面静默覆盖）
    "providers": [],           # [{name, base_url, api_key, models: [id,...]}]
    "routing": {"write": None, "judge": None, "critique": None},
    # routing 条目 = {"provider": <name>, "model": <id>}
    "workspace_root": str(ROOT.parent),   # 默认 = 仓库上一级（既有项目所在根，r4 §四）
    "context_budget_tokens": 24000,
    "session_cost_limit_usd": None,       # 花费护栏：单会话上限（None=不设）
    "prose_max_tokens": 3500,
    "temperature": 0.8,
}


def load_config(path: Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy defaults
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for k, v in data.items():
            if k in cfg and isinstance(cfg[k], dict) and isinstance(v, dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    cfg["_path"] = str(p)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    p = Path(path) if path else Path(cfg.get("_path") or DEFAULT_CONFIG_PATH)
    out = {k: v for k, v in cfg.items() if not k.startswith("_")}
    p.parent.mkdir(parents=True, exist_ok=True)
    # 写前备份上一版（含 key 的本地文件损坏/误删时有救；.bak 同样被 gitignore 覆盖）
    if p.is_file():
        try:
            bak = p.read_bytes()
            p.with_suffix(".json.bak").write_bytes(bak)
        except OSError:
            pass
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")


def resolve_route(cfg: dict, route: str) -> tuple[dict | None, str | None]:
    """routing 条目 → (provider, model)。未配置返回 (None, None)。"""
    entry = (cfg.get("routing") or {}).get(route)
    if not entry:
        return None, None
    for prov in cfg.get("providers", []):
        if prov.get("name") == entry.get("provider"):
            return prov, entry.get("model")
    return None, None


# ---- 思考档（v0.13.8）：路由条目可选 thinking=off/low/medium/high + thinking_json。
# L1 主机映射：认得出的家按自家参数形态发；认不出的主机（中转站常态）走
# OpenAI reasoning_effort 形态——由 L2 探针验真伪，L3 运行时 400 自动去参兜底。
# 不选档=零额外参数（错误参数根本不出手）。
_THINKING_EFFORT = {"off": "minimal", "low": "low", "medium": "medium",
                    "high": "high"}


def thinking_extra(base_url: str, level: str | None,
                   custom: dict | None = None) -> dict | None:
    """思考档 → 请求体附加参数。custom（自定义 JSON）显式优先；
    GLM=thinking.type（无档位只有开关）/ Qwen=enable_thinking /
    OpenRouter=reasoning.effort / 其余（openai 官方+未识别主机）=reasoning_effort。"""
    if isinstance(custom, dict) and custom:
        return dict(custom)
    if level not in _THINKING_EFFORT:
        return None
    host = (base_url or "").lower()
    if "zhipu" in host or "bigmodel" in host:
        return {"thinking": {"type": "disabled" if level == "off" else "enabled"}}
    if "dashscope" in host or "aliyuncs" in host:
        return {"enable_thinking": level != "off"}
    if "openrouter" in host:
        if level == "off":
            return {"reasoning": {"enabled": False, "exclude": True}}
        return {"reasoning": {"effort": level}}
    return {"reasoning_effort": _THINKING_EFFORT[level]}


def route_thinking(cfg: dict, route: str) -> dict | None:
    """routing 条目（thinking/thinking_json）→ 该路由的请求体附加参数。
    探针/运行时记档为拒绝（thinking_support[model]=False）→ 不再发参，
    直到用户在配置页重新探针或改档——显式恢复，不静默重试。"""
    entry = (cfg.get("routing") or {}).get(route)
    if not isinstance(entry, dict) or not (entry.get("thinking")
                                           or entry.get("thinking_json")):
        return None
    for prov in cfg.get("providers", []):
        if prov.get("name") == entry.get("provider"):
            support = prov.get("thinking_support") or {}
            if support.get(entry.get("model")) is False:
                return None
            return thinking_extra(prov.get("base_url", ""),
                                  entry.get("thinking"), entry.get("thinking_json"))
    return None


def mark_thinking_support(path: Path | None, provider: str, model: str,
                          ok: bool) -> None:
    """探针/运行时降级结果记档（providers[i].thinking_support[model]）。
    独立 load→改→save（不复用请求期 cfg，防陈旧页覆盖）；值未变不落盘。"""
    cfg = load_config(path)
    for prov in cfg.get("providers", []):
        if prov.get("name") == provider:
            support = prov.setdefault("thinking_support", {})
            if support.get(model) == ok:
                return
            support[model] = ok
            save_config(cfg, path)
            return


def sanitize_config(cfg: dict) -> dict:
    """对外暴露的配置视图：key 永不出服务端（r4 红线 5）。"""
    out = json.loads(json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")}))
    for prov in out.get("providers", []):
        prov["has_key"] = bool(prov.get("api_key"))
        prov.pop("api_key", None)
    return out


PinHeader = re.compile(r"钉扎\s*[:：]\s*(\S+)\s+v(\S+)")


def read_pinned_pack(project_dir: Path) -> dict | None:
    """读现有钉扎协议 style/pinned-pack.md（版本注头）；没有/非包引用返回 None。"""
    p = project_dir / "style" / "pinned-pack.md"
    if not p.is_file():
        return None
    head = p.read_text(encoding="utf-8", errors="ignore")[:400]
    m = PinHeader.search(head)
    if not m:
        return None
    return {"pack": m.group(1), "version": m.group(2)}


def discover_projects(workspace_root: Path) -> list[dict]:
    """工作区项目发现：含 manuscript/ 或 bible/ 或 style/ 或 canon/ 的直接子目录。"""
    out = []
    if not workspace_root.is_dir():
        return out
    for d in sorted(workspace_root.iterdir()):
        if not d.is_dir():
            continue
        markers = [m for m in ("manuscript", "bible", "style", "canon")
                   if (d / m).is_dir()]
        if markers:
            out.append({"name": d.name, "path": str(d), "markers": markers,
                        "pinned": read_pinned_pack(d)})
    return out


def list_chapters(project_dir: Path) -> list[dict]:
    ms = project_dir / "manuscript"
    if not ms.is_dir():
        return []
    out = []
    for f in sorted(ms.glob("*.md")):
        num = re.match(r"(\d+)", f.stem)
        out.append({"file": f.name, "stem": f.stem,
                    "no": int(num.group(1)) if num else None,
                    "chars": len(f.read_text(encoding="utf-8", errors="ignore"))})
    return out


def append_cost(project_dir: Path, skill: str, chars: int,
                model: str = "", tokens: int = 0, note: str = "",
                session_tokens: int = 0, session_calls: int = 0,
                session_id: str = "") -> dict:
    """与 cost.py 同账本同文件（style/cost.jsonl）；模型调用加 model/tokens
    附加字段；session_tokens/session_calls = 本章会话真实总消耗/调用次数
    （tokens 只记交付稿最后一次调用——v0.6.8 起总账单独成字段，不再低估）。
    session（v0.12）：会话标识入账——预算 spend 排除本会话行防双算。"""
    entry = {
        "date": datetime.date.today().isoformat(),
        "skill": skill, "chars": int(chars), "files": 1,
        "model": model, "tokens": int(tokens),
        "note": note or "web 工作台模型调用",
    }
    if session_tokens:
        entry["session_tokens"] = int(session_tokens)
        entry["session_calls"] = int(session_calls)
    if session_id:
        entry["session"] = session_id
    if "tokens" in entry and entry["tokens"]:
        entry["chars"] = entry["chars"] or int(entry["tokens"] * 2)  # 折算口径：2 字/token（中文）
    cost = project_dir / "style" / "cost.jsonl"
    cost.parent.mkdir(parents=True, exist_ok=True)
    with cost.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
