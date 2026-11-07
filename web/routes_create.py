# -*- coding: utf-8 -*-
"""routes_create：创作环与配置的 API（v0.6.8：方案槽 + 会话总账）。

红线落实：
- GET /app/api/config 永不返回 api_key（sanitize）；
- 装配预览与生成共用 assemble()（所见即所发）；
- fp_check/borrow_check 为 advisory 报告，UI 不得渲染成通过/失败门，
  交付动作必须显式点"确认交付"（阶段门的显式覆盖出口）；
- 每次模型调用前检查会话 token 护栏，调用后记账 cost.jsonl。
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import appstate
import assemble as assemble_mod
import creation
import model_client
import splib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STYLEPACKS = ROOT / "stylepacks"

router = APIRouter(prefix="/app/api")

# 会话 token 护栏的内存账（本地单用户，进程内存即可）
# v0.11.2 C-3：分桶拆账 gen/rev/other——halt 诊断面板"哪一环节烧的"的数据源
_sessions: dict[str, dict] = {}


def _ws_root(cfg: dict) -> Path:
    return Path(cfg.get("workspace_root") or appstate.ROOT.parent)


def _project_dir(cfg: dict, name: str) -> Path:
    d = (_ws_root(cfg) / name).resolve()
    root = _ws_root(cfg).resolve()
    if root not in d.parents and d != root:
        raise HTTPException(400, "项目名非法")
    if not d.is_dir():
        raise HTTPException(404, f"项目不存在：{name}")
    return d


def _pack_dir(pack: str, project_dir: Path | None = None) -> Path:
    """包名 → 包目录。v0.13.12：支持 `project:<style/下的目录名>` 前缀——
    项目本地包（style/pack-*，防线定义的主包所在地）入册；traversal 守卫
    + pack.json 存在 + 草稿拦截与全局包同规。"""
    if pack.startswith("project:"):
        if project_dir is None:
            raise HTTPException(400, "project: 前缀包需要项目上下文")
        name = pack[len("project:"):].strip("/")
        d = (project_dir / "style" / name).resolve()
        dr = project_dir.resolve()
        if d != dr and dr not in d.parents:
            raise HTTPException(400, "路径越界（traversal 已拦截）")
        return _pack_dir_checked(d, pack)
    d = (STYLEPACKS / pack).resolve()
    return _pack_dir_checked(d, pack)


def _pack_dir_checked(d: Path, pack: str) -> Path:
    if not (d / "pack.json").is_file():
        raise HTTPException(404, f"风格包不存在或无 pack.json：{pack}")
    meta = {}
    try:
        meta = json.loads((d / "pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if meta.get("status") == "draft":  # v0.7.0：蒸馏台草稿包不得用于创作
        raise HTTPException(400, f"包 {pack} 仍是草稿（蒸馏台未定稿）——不能用于创作")
    return d


def _ref_pack_dirs(cfg: dict, project: str,
                   ref_packs: list[str]) -> list[Path]:
    """参考池名列表 → 目录（v0.13.13；上限 3——棘轮风险与参考数正相关）。"""
    if not ref_packs:
        return []
    if len(ref_packs) > 3:
        raise HTTPException(400, "参考池上限 3 个——参考越多棘轮风险越高")
    pdir = _project_dir(cfg, project)
    return [_pack_dir(rp, pdir) for rp in ref_packs]


def _run_ref_borrow(draft_path: Path, ref_dirs: list[Path]) -> list[dict]:
    """参考池搬运检查：正文 vs 每个参考包语料各跑一遍 borrow_check
    （零 token，advisory）——把防线"只准化用不准搬运"机械化。"""
    out = []
    for rd in ref_dirs:
        r = _run_gate("borrow_check.py", [str(draft_path), "--pack", str(rd)])
        r["ref_pack"] = rd.name
        out.append(r)
    return out


def _resolve_model(cfg: dict, route: str) -> tuple[str, str, str]:
    prov, model = appstate.resolve_route(cfg, route)
    if not prov or not model:
        raise HTTPException(400, f"未配置 {route} 模型路由——请先到「模型配置」页设置")
    return prov["base_url"], prov.get("api_key"), model


def _clean_target_chars(n) -> int:
    """字数挡位消毒：0=未指定；越界/非法一律归 0（不猜测）。"""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return 0
    return n if 300 <= n <= 20000 else 0


def _prose_budget(cfg: dict, target_chars: int) -> int:
    """正文生成 max_tokens：显式字数挡位按 1 字≈0.75 token 换算（与 assemble
    同口径）加 600 余量；只增不减地覆盖 prose_max_tokens 配置兜底。"""
    base = cfg.get("prose_max_tokens", 3500)
    if not target_chars:
        return base
    return max(base, int(target_chars * assemble_mod.CHARS_PER_TOKEN) + 600)


def _guard(cfg: dict, session_id: str, est_tokens: int) -> None:
    limit = cfg.get("session_max_tokens")
    if not limit:
        return
    used = _sessions.get(session_id, {}).get("tokens", 0)
    if used + est_tokens > int(limit):
        raise HTTPException(429, f"会话 token 护栏：已用 {used} + 本次 {est_tokens} "
                                 f"> 上限 {limit}（可在模型配置页调整）")


def _record_usage(session_id: str, usage: dict, kind: str = "other") -> None:
    s = _sessions.setdefault(session_id, {"tokens": 0, "calls": 0,
                                          "gen": 0, "rev": 0, "other": 0})
    t = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    s["tokens"] += t
    s["calls"] += 1
    s[kind] = s.get(kind, 0) + t


def _session_totals(session_id: str) -> dict:
    """本章会话累计（所有调用含重试/门禁判官的真实消耗）+ 分桶拆账。"""
    s = _sessions.get(session_id or "", {})
    return {"tokens": int(s.get("tokens", 0)), "calls": int(s.get("calls", 0)),
            "gen": int(s.get("gen", 0)), "rev": int(s.get("rev", 0)),
            "other": int(s.get("other", 0))}


def _run_gate(script: str, args: list[str]) -> dict:
    """advisory 门禁：跑 CLI 脚本，返回报告（不作为通过/失败判定）。"""
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                           capture_output=True, encoding="utf-8", errors="replace",
                           timeout=120)
        return {"script": script, "exit_code": r.returncode,
                "report": (r.stdout or "") + (r.stderr or "")}
    except subprocess.TimeoutExpired:
        return {"script": script, "exit_code": -1, "report": "超时"}


# ---- 配置 ----

class ConfigIn(BaseModel):
    providers: list[dict] = []
    routing: dict = {}
    workspace_root: str | None = None
    context_budget_tokens: int = 24000
    session_max_tokens: int | None = 200000
    prose_max_tokens: int = 3500
    temperature: float = 0.8
    rev: int | None = None  # 乐观锁：陈旧页面提交旧 rev → 409（防静默覆盖）


@router.get("/config")
def get_config():
    cfg = appstate.load_config()
    view = appstate.sanitize_config(cfg)
    view["workspace_projects"] = appstate.discover_projects(_ws_root(cfg))
    return view


@router.post("/config")
def set_config(body: ConfigIn):
    cfg = appstate.load_config()
    cur_rev = int(cfg.get("rev", 0))
    if body.rev is None:
        return JSONResponse(status_code=400, content={
            "detail": "缺少 rev（配置版本号）——请刷新页面后重试；"
                      "不带 rev 的写入已禁止（防陈旧页面静默覆盖配置）"})
    if body.rev != cur_rev:
        return JSONResponse(status_code=409, content={
            "detail": f"配置已被其他窗口/操作更新（本页 rev={body.rev}，最新 rev={cur_rev}）",
            "config": appstate.sanitize_config(cfg), "rev": cur_rev})
    old_by_name = {p.get("name"): p for p in cfg.get("providers", [])
                   if isinstance(p, dict)}
    merged = []
    for p in body.providers:
        if not (p.get("name") and p.get("base_url")):
            continue
        key = (p.get("api_key") or "").strip()
        if not key and p["name"] in old_by_name:
            key = (old_by_name[p["name"]].get("api_key") or "").strip()
        merged.append({"name": p["name"], "base_url": p["base_url"],
                       "api_key": key,
                       "models": p.get("models") if isinstance(p.get("models"), list) else []})
        # 思考档支持度记档跟随供应商保留（探针/运行时降级结果，v0.13.8）
        old_sup = old_by_name[p["name"]].get("thinking_support")
        if isinstance(old_sup, dict):
            merged[-1]["thinking_support"] = old_sup
    cfg["providers"] = merged
    for p in cfg["providers"]:
        if not isinstance(p.get("models"), list):
            p["models"] = []
    clean_routing: dict = {}
    for k, v in (body.routing or {}).items():
        if isinstance(v, dict):
            v = dict(v)
            if v.get("thinking") not in ("off", "low", "medium", "high"):
                v.pop("thinking", None)
            if not isinstance(v.get("thinking_json"), dict):
                v.pop("thinking_json", None)
        clean_routing[k] = v
    cfg["routing"] = clean_routing
    if body.workspace_root:
        cfg["workspace_root"] = body.workspace_root
    cfg["context_budget_tokens"] = body.context_budget_tokens
    cfg["session_max_tokens"] = body.session_max_tokens
    cfg["prose_max_tokens"] = body.prose_max_tokens
    cfg["temperature"] = body.temperature
    cfg["rev"] = cur_rev + 1
    appstate.save_config(cfg)
    return {"ok": True, "config": appstate.sanitize_config(appstate.load_config())}


class TestIn(BaseModel):
    name: str


@router.post("/config/test")
def test_connection(body: TestIn):
    cfg = appstate.load_config()
    for prov in cfg.get("providers", []):
        if prov.get("name") == body.name:
            try:
                ids = model_client.list_models(prov["base_url"], prov.get("api_key"))
                return {"ok": True, "models": ids}
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
    raise HTTPException(404, f"未找到 provider：{body.name}")


class ThinkProbeIn(BaseModel):
    provider: str
    model: str
    level: str = ""            # off/low/medium/high；空 + custom = 自定义 JSON 探针
    custom: dict | None = None


@router.post("/config/thinking-probe")
def thinking_probe(body: ThinkProbeIn):
    """L2 思考参数探针（v0.13.8）：单发最小请求验供应商收不收这组参数。
    True/False 记档进 providers.thinking_support（False 后该路由不再发参，
    显式重新探针才恢复）；None=网络/其他错，不记档不冤枉。"""
    cfg = appstate.load_config()
    prov = next((p for p in cfg.get("providers", [])
                 if p.get("name") == body.provider), None)
    if not prov:
        raise HTTPException(404, f"未找到 provider：{body.provider}")
    if not body.level and not body.custom:
        raise HTTPException(400, "level 与 custom 皆为空——无参数可探")
    extra = appstate.thinking_extra(prov.get("base_url", ""),
                                    body.level or None, body.custom)
    if not extra:
        raise HTTPException(400, "无效思考档——off/low/medium/high 或自定义 JSON")
    r = model_client.probe_extra(prov["base_url"], prov.get("api_key"),
                                 body.model, extra)
    if r["supported"] is not None:
        appstate.mark_thinking_support(None, body.provider, body.model,
                                       bool(r["supported"]))
    return {"ok": r["supported"], "detail": r["detail"], "extra": extra}


# ---- 项目/包 ----

@router.get("/projects")
def projects():
    cfg = appstate.load_config()

    def _pack_entry(name: str, d: Path) -> dict | None:
        try:
            meta = json.loads((d / "pack.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if meta.get("status") == "draft":  # v0.7.0：草稿包不进创作页下拉
            return None
        return {"name": name, "version": _pack_version(d)}

    packs = [e for e in (_pack_entry(d.name, d) for d in sorted(STYLEPACKS.iterdir())
                         if d.is_dir() and (d / "pack.json").is_file()
                         and d.name != "local") if e]
    local = STYLEPACKS / "local"
    if local.is_dir():
        packs += [e for e in (_pack_entry(f"local/{d.name}", d)
                              for d in sorted(local.iterdir())
                              if d.is_dir() and (d / "pack.json").is_file()) if e]
    projects = appstate.discover_projects(_ws_root(cfg))
    for pr in projects:
        pr["longform"] = _is_longform(_ws_root(cfg) / pr["name"])
    return {"workspace_root": str(_ws_root(cfg)),
            "projects": projects,
            "packs": packs}


@router.get("/next_chapter")
def next_chapter(project: str):
    """推荐下一章号：扫 manuscript/NNN-*.md 取最大 +1（空则 1）——
    章节号错乱会让"上一章结尾"锚定失效，这是防呆不是强约束。"""
    cfg = appstate.load_config()
    ms = _project_dir(cfg, project) / "manuscript"
    best = 0
    if ms.is_dir():
        for f in ms.glob("*.md"):
            if m := re.match(r"(\d+)", f.stem):
                best = max(best, int(m.group(1)))
    hint = ""
    outline = _project_dir(cfg, project) / "outline.md"
    if outline.is_file() and (m := re.search(
            rf"^###+\s*(?:第)?{best + 1}(?:章|[-.：: ])",
            outline.read_text(encoding="utf-8"), re.M)):
        hint = f"outline.md 已有第 {best + 1} 章概要（{m.group(0).strip()[:40]}）"
    return {"next": best + 1, "found": best, "outline_hint": hint}


class AssembleIn(BaseModel):
    project: str
    pack: str
    chapter_no: int
    keywords: list[str] = []
    ref_packs: list[str] = []     # v0.13.13 参考池（cap 3，取味不取形）
    allow_unbilled: bool = False  # C-2 拆账强制：显式确认越过


@router.get("/presets")
def presets(project: str = "", pack: str = ""):
    """调子/锚点初始选项（datalist 建议，不强制）：调子取包 registers.md 分区名
    （无则通用建议集）；锚点取项目 sessions 实际用过的 canon_anchor（新→旧）。"""
    tones = ["不指定"]
    tone_source = "generic"
    reg = None
    if pack:
        try:
            reg = _pack_dir(pack) / "registers.md"
        except HTTPException:
            reg = None
    if reg and reg.is_file():
        for line in reg.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith("#### ") and s[5:].strip() not in tones:
                tones.append(s[5:].strip())
        if len(tones) > 1:
            tone_source = "registers"
    if tone_source == "generic":
        tones += ["轻快日常", "紧张压迫", "温情", "荒诞喜剧", "沉郁压抑"]
    anchors = ["无"]
    if project:
        cfg = appstate.load_config()
        try:
            pdir = _project_dir(cfg, project)
        except HTTPException:
            pdir = None
        if pdir:
            for j in sorted((pdir / "sessions").glob("*.json"), reverse=True):
                try:
                    a = json.loads(j.read_text(encoding="utf-8")).get("canon_anchor")
                except (OSError, ValueError):
                    continue
                if a and a != "无" and a.strip() not in anchors:
                    anchors.append(a.strip())
    return {"tones": tones[:12], "tone_source": tone_source,
            "anchors": anchors[:10]}


@router.post("/assemble")
def do_assemble(body: AssembleIn):
    cfg = appstate.load_config()
    pdir = _project_dir(cfg, body.project)
    _ledger_gate(pdir, body.chapter_no, body.allow_unbilled)
    result = assemble_mod.assemble(
        pdir, _pack_dir(body.pack, pdir),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000),
        ref_pack_dirs=_ref_pack_dirs(cfg, body.project, body.ref_packs))
    result.pop("kept_texts", None)  # 预览不外带全文
    return result


# ---- 方案槽（v0.6.6）：装配输入可重放，5 槽环形，锁定不被挤掉 ----

def _slots_dir(project_dir: Path) -> Path:
    d = project_dir / "slots"
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.is_file():  # 方案含创作配置，防误提交（与 sessions 同款）
        gi.write_text("*\n!.gitignore\n", encoding="utf-8", newline="\n")
    return d


def _pack_version(pack_dir: Path) -> str:
    try:
        return str(json.loads((pack_dir / "pack.json").read_text(encoding="utf-8")
                              ).get("version") or "")
    except (OSError, ValueError):
        return ""


def _slot_path(project_dir: Path, slot_id: int) -> Path:
    sid = int(slot_id)
    if not 1 <= sid <= 5:
        raise HTTPException(400, "槽位号须在 1–5")
    return _slots_dir(project_dir) / f"slot-{sid}.json"


def _read_slot(p: Path) -> dict | None:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_slot(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")


@router.get("/slots")
def slots_list(project: str):
    cfg = appstate.load_config()
    pdir = _project_dir(cfg, project)
    sd = pdir / "slots"
    return {"slots": [(_read_slot(sd / f"slot-{i}.json")
                       if sd.is_dir() else None) for i in range(1, 6)]}


class SlotCaptureIn(BaseModel):
    project: str
    pack: str
    chapter_no: int
    keywords: list[str] = []
    target_chars: int = 0
    title: str = ""


@router.post("/slots/capture")
def slot_capture(body: SlotCaptureIn):
    """装配预览成功后自动入槽：同指纹（项目|包|章|关键词|挡位）更新原槽，
    否则空槽优先、其次挤掉最旧未锁定槽；全锁且无空 → 409 请解锁。"""
    cfg = appstate.load_config()
    pdir = _project_dir(cfg, body.project)
    pack_dir = _pack_dir(body.pack, pdir)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    fp = "|".join([body.project, body.pack, str(body.chapter_no),
                   ",".join(sorted(body.keywords)),
                   str(_clean_target_chars(body.target_chars))])
    sd = _slots_dir(pdir)
    slots = [(_read_slot(sd / f"slot-{i}.json"), i) for i in range(1, 6)]
    for s, i in slots:
        if s and s.get("fingerprint") == fp:
            s["title"], s["ts"] = body.title, now
            _write_slot(sd / f"slot-{i}.json", s)
            return {"slot": s, "reused": True}
    empty = [i for s, i in slots if s is None]
    if empty:
        sid = empty[0]
    else:
        unlocked = sorted((s.get("ts") or "", i) for s, i in slots
                          if s and not s.get("locked"))
        if not unlocked:
            raise HTTPException(409, "5 个方案槽已满且全部锁定——"
                                     "请解锁或清空一个方案后再装配")
        sid = unlocked[0][1]
    slot = {"id": sid, "fingerprint": fp, "locked": False, "name": "",
            "ts": now, "project": body.project, "pack": body.pack,
            "pack_version": _pack_version(pack_dir),
            "chapter_no": body.chapter_no, "title": body.title,
            "keywords": body.keywords,
            "target_chars": _clean_target_chars(body.target_chars),
            "chosen": None, "beats": [], "tone_note": "", "canon_anchor": "",
            "latest_draft": None, "drafts": []}
    _write_slot(sd / f"slot-{sid}.json", slot)
    return {"slot": slot, "reused": False}


class SlotUpdateIn(BaseModel):
    project: str
    slot_id: int
    chosen: dict | None = None
    beats: list[dict] | None = None
    tone_note: str | None = None
    canon_anchor: str | None = None
    latest_draft: dict | None = None
    drafts: list[dict] | None = None  # 批次落盘（v0.7.3）：最近批次全量，刷新可恢复
    name: str | None = None
    locked: bool | None = None


@router.post("/slots/update")
def slot_update(body: SlotUpdateIn):
    cfg = appstate.load_config()
    p = _slot_path(_project_dir(cfg, body.project), body.slot_id)
    s = _read_slot(p)
    if not s:
        raise HTTPException(404, f"槽位 {body.slot_id} 为空——先装配预览入槽")
    for k in ("chosen", "beats", "tone_note", "canon_anchor",
              "latest_draft", "drafts", "name", "locked"):
        v = getattr(body, k)
        if v is not None:
            s[k] = v
    if s.get("chosen") and not s.get("name"):  # 槽名自动取立意方向
        s["name"] = str(s["chosen"].get("title") or "")[:24]
    s["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    _write_slot(p, s)
    return {"slot": s}


class SlotClearIn(BaseModel):
    project: str
    slot_id: int


@router.post("/slots/clear")
def slot_clear(body: SlotClearIn):
    cfg = appstate.load_config()
    p = _slot_path(_project_dir(cfg, body.project), body.slot_id)
    if p.is_file():
        p.unlink()
    return {"ok": True}


# ---- 共创与生成 ----

class OutlineIn(BaseModel):
    project: str
    pack: str
    chapter_no: int
    title: str
    keywords: list[str] = []
    user_notes: str = ""
    target_chars: int = 0  # 字数挡位（v0.6.3）：0=未指定
    session_id: str | None = None
    g0: dict = {}  # G0 七字段简报（v0.11.1 B-1；跳过时 {"skipped": true} 留痕）
    allow_unbilled: bool = False     # C-2 拆账强制：显式确认越过
    allow_over_budget: bool = False  # C-3 止损闸：显式确认越过（G4 最高指令权）


def _session_id(body) -> str:
    return body.session_id or uuid.uuid4().hex[:12]


def _thinking_aftermath(cfg: dict, route: str, model: str, sid: str,
                        result: dict) -> None:
    """思考档善后（v0.13.8）：L3 运行时降级记档 + 警告入会话（绝不静默——
    用户选关思考是为省成本，静默回退=成本悄悄爆炸）；usage 交叉验证参数真伪。
    警告存 _sessions[sid]["warnings"]，经预算状态/draft_done/save 浮现。"""
    entry = (cfg.get("routing") or {}).get(route) or {}
    level = entry.get("thinking")
    warns: list[str] = []
    dropped = result.get("thinking_fallback") or []
    if dropped:
        appstate.mark_thinking_support(None, entry.get("provider", ""), model, False)
        warns.append(f"思考参数被供应商拒绝（{','.join(dropped)}）——本次已自动"
                     "去参出稿并记档：该模型不支持此思考档，请到模型配置页调整")
    rt = result.get("reasoning_tokens")
    if rt is not None and level:
        if level == "off" and rt > 0:
            warns.append(f"思考档=关但 reasoning_tokens={rt}——参数疑似未生效"
                         "（供应商可能静默忽略），成本仍按思考计")
        elif level in ("low", "medium", "high") and rt == 0:
            warns.append(f"思考档={level}但 reasoning_tokens=0——参数疑似未生效")
    if warns:
        s = _sessions.setdefault(sid, {"tokens": 0, "calls": 0,
                                       "gen": 0, "rev": 0, "other": 0})
        s.setdefault("warnings", []).extend(warns)


def _session_warnings(sid: str) -> list[str]:
    return list(_sessions.get(sid, {}).get("warnings") or [])


def _do_model(cfg: dict, route: str, session_id: str, prompt: str,
              max_tokens: int, json_mode: bool, kind: str = "other"):
    base, key, model = _resolve_model(cfg, route)
    extra = appstate.route_thinking(cfg, route)
    _guard(cfg, session_id, int(max_tokens * 1.5))
    try:
        result = model_client.chat(base, key, model,
                                   [{"role": "system", "content": creation.SYSTEM},
                                    {"role": "user", "content": prompt}],
                                   temperature=cfg.get("temperature", 0.8),
                                   max_tokens=max_tokens, extra=extra)
    except ValueError as exc:  # 已 sanitize，可直接示人
        raise HTTPException(502, str(exc))
    _thinking_aftermath(cfg, route, model, session_id, result)
    _record_usage(session_id, result, kind)
    if not result["text"].strip():  # 双保险：chat() 已拦，此处兜底
        raise HTTPException(502, "模型返回空正文（上游未拦住）——请重试或检查模型配置")
    if json_mode:
        try:
            result["json"] = creation.extract_json(result["text"])
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(502, f"模型未返回可解析 JSON：{exc}｜原文头 300 字："
                                     f"{result['text'][:300]}")
    return result


@router.post("/outline")
def do_outline(body: OutlineIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    pdir = _project_dir(cfg, body.project)
    _ledger_gate(pdir, body.chapter_no, body.allow_unbilled)
    bs = _budget_gate(pdir, body.chapter_no, sid, body.allow_over_budget)
    assembly = assemble_mod.assemble(
        pdir, _pack_dir(body.pack, pdir),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000))
    prompt = creation.outline_prompt(body.chapter_no, body.title, body.keywords,
                                     assembly["kept_texts"], body.user_notes)
    g0t = _g0_text(body.g0)
    if g0t:
        prompt += chr(10) * 2 + g0t
    result = _do_model(cfg, _write_route(cfg, pdir, body), sid, prompt, 2200,
                       True, kind="gen")
    return {"session_id": sid, "options": result["json"].get("options", []),
            "recommended": result["json"].get("recommended", 0),
            "usage": result, "budget": _budget_state(pdir, body.chapter_no, sid),
            "assembly": {k: v for k, v in assembly.items()
                         if k != "kept_texts"}}


class BeatsIn(OutlineIn):
    chosen: dict = {}


@router.post("/beats")
def do_beats(body: BeatsIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    pdir = _project_dir(cfg, body.project)
    _ledger_gate(pdir, body.chapter_no, body.allow_unbilled)
    bs = _budget_gate(pdir, body.chapter_no, sid, body.allow_over_budget)
    assembly = assemble_mod.assemble(
        pdir, _pack_dir(body.pack, pdir),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000))
    canon_note = ("二创项目：原作锚点必须落到 canon-terms.json 的 must 术语与人物"
                  if (pdir / "canon" / "canon-terms.json").is_file() else "")
    prompt = creation.beats_prompt(body.chapter_no, body.title, body.chosen,
                                   assembly["kept_texts"], canon_note,
                                   _clean_target_chars(body.target_chars))
    g0t = _g0_text(body.g0)
    if g0t:
        prompt += chr(10) * 2 + g0t
    result = _do_model(cfg, _write_route(cfg, pdir, body), sid, prompt, 2400,
                       True, kind="gen")
    return {"session_id": sid, **result["json"], "usage": result,
            "budget": _budget_state(pdir, body.chapter_no, sid)}


class RerollIn(BeatsIn):
    beats: list[dict] = []
    index: int = 1


@router.post("/reroll_beat")
def do_reroll(body: RerollIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    pdir = _project_dir(cfg, body.project)
    bs = _budget_gate(pdir, body.chapter_no, sid, body.allow_over_budget)
    assembly = assemble_mod.assemble(
        pdir, _pack_dir(body.pack, pdir),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000))
    prompt = creation.reroll_beat_prompt(body.chapter_no, body.title, body.chosen,
                                         body.beats, body.index,
                                         assembly["kept_texts"],
                                         _clean_target_chars(body.target_chars))
    g0t = _g0_text(body.g0)
    if g0t:
        prompt += chr(10) * 2 + g0t
    result = _do_model(cfg, _write_route(cfg, pdir, body), sid, prompt, 600,
                       True, kind="gen")
    return {"session_id": sid, "beat": result["json"], "usage": result,
            "budget": _budget_state(pdir, body.chapter_no, sid)}


class GenerateIn(BeatsIn):
    ref_packs: list[str] = []     # v0.13.13 参考池
    beats: list[dict] = []
    tone_note: str = "不指定"
    canon_anchor: str = "无"
    n_drafts: int = 1
    session_id: str = ""


def _prep_generate(cfg: dict, body: GenerateIn) -> dict:
    """装配 + 提示词 + 预算：/generate 与 /generate_stream 共用（所见即所发）。"""
    project_dir = _project_dir(cfg, body.project)
    pack_dir = _pack_dir(body.pack, project_dir)
    ref_dirs = _ref_pack_dirs(cfg, body.project, body.ref_packs)
    sid = _session_id(body)
    _ledger_gate(project_dir, body.chapter_no, body.allow_unbilled)
    bstate = _budget_gate(project_dir, body.chapter_no, sid,
                          body.allow_over_budget)
    assembly = assemble_mod.assemble(
        project_dir, pack_dir, body.chapter_no, body.keywords,
        cfg.get("context_budget_tokens", 24000), ref_pack_dirs=ref_dirs)
    target = _clean_target_chars(body.target_chars)
    prompt = creation.prose_prompt(body.chapter_no, body.title, body.chosen,
                                   body.beats, body.tone_note, body.canon_anchor,
                                   assembly["kept_texts"],
                                   target or cfg.get("prose_max_tokens", 3500) * 2 // 3)
    g0t = _g0_text(getattr(body, "g0", None))
    if g0t:
        prompt = prompt + chr(10) * 2 + g0t
    return {"pack_dir": pack_dir, "project_dir": project_dir,
            "ref_dirs": ref_dirs,
            "assembly": assembly, "prompt": prompt, "route":
                _write_route(cfg, project_dir, body), "bstate": bstate,
            "budget": _prose_budget(cfg, target), "target": target}


@router.post("/generate")
def do_generate(body: GenerateIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    prep = _prep_generate(cfg, body)
    pack_dir, assembly, prompt, budget = (prep["pack_dir"], prep["assembly"],
                                          prep["prompt"], prep["budget"])
    project_dir = prep["project_dir"]
    ledger = str(project_dir / "bible" / "硬数字表.md")
    longform = _is_longform(project_dir)
    route = prep["route"]
    drafts = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(max(1, min(3, body.n_drafts))):
            result = _do_model(cfg, route, sid, prompt, budget, False, kind="gen")
            draft_path = Path(td) / f"d{i}.txt"
            draft_path.write_text(result["text"], encoding="utf-8", newline="\n")
            fp = _run_gate("fp_check.py", [str(pack_dir), str(draft_path)])
            borrow = _run_gate("borrow_check.py", [str(draft_path),
                                                   "--pack", str(pack_dir)])
            aic = _run_gate("ai_cliche_check.py", [str(draft_path),
                                                   "--pack", str(pack_dir)])
            nums = (_run_gate("numbers_check.py", [str(draft_path), "--ledger",
                                                   ledger, "--chapter",
                                                   str(body.chapter_no)])
                    if longform else None)
            nms = (_run_gate("names_check.py", [str(draft_path), "--variants",
                                                str(project_dir / "bible"
                                                     / "专名表.tsv"),
                                                "--characters",
                                                str(project_dir / "bible"
                                                    / "characters.md")])
                   if longform else None)
            ref_b = (_run_ref_borrow(draft_path, prep["ref_dirs"])
                     if prep.get("ref_dirs") else None)
            drafts.append({"text": result["text"], "usage": result,
                           "fp_check": fp, "borrow_check": borrow,
                           "ai_cliche": aic, "numbers_check": nums,
                           "names_check": nms, "ref_borrow": ref_b})
    return {"session_id": sid, "drafts": drafts,
            "warnings": _session_warnings(sid),
            "assembly_preview": assembly["items"],
            "assembly_tokens": assembly["total_est_tokens"],
            "budget": _budget_state(project_dir, body.chapter_no, sid)}


# ---- 流式生成（v0.6.4）：SSE 事件流，生成现场侧栏逐字渲染 ----

def _sse(type_: str, **fields) -> str:
    return ("event: " + type_ + "\ndata: "
            + json.dumps({"type": type_, **fields}, ensure_ascii=False) + "\n\n")


def _stream_one_draft(cfg: dict, sid: str, prompt: str, budget: int,
                      pack_dir: Path, index: int, done_event: str = "draft_done",
                      extra: dict | None = None,
                      numbers_ctx: dict | None = None, route: str = "write",
                      ref_dirs: list[Path] | None = None):
    """产出一个稿的事件序列：流式优先；空稿/流式不可用回退非流加倍链（v0.6.2）。
    结尾必发 done_event（成功）或 error（失败）——前端按此收口。
    numbers_ctx（v0.11.1 B-3）：{"ledger": 路径, "chapter": 章号}——长篇项目
    交付前数字对照（advisory 报不拦），None=轻量项目跳过。
    route（v0.11.2 C-4）：量产章走 write_mass（路由解析在 _prep_generate）。"""
    base, key, model = _resolve_model(cfg, route)
    think = appstate.route_thinking(cfg, route)
    messages = [{"role": "system", "content": creation.SYSTEM},
                {"role": "user", "content": prompt}]
    _guard(cfg, sid, int(budget * 1.5))
    parts: list[str] = []
    usage: dict = {}
    finish: str | None = None
    try:
        for ev in model_client.chat_stream(base, key, model, messages,
                                           temperature=cfg.get("temperature", 0.8),
                                           max_tokens=budget, extra=think):
            if ev["type"] == "delta":
                parts.append(ev["text"])
                yield _sse("delta", index=index, text=ev["text"],
                           chars=sum(len(p) for p in parts))
            elif ev["type"] == "reasoning":
                yield _sse("reasoning", index=index)
            else:
                _thinking_aftermath(cfg, route, model, sid,
                                    {"thinking_fallback": ev.get("thinking_fallback"),
                                     "reasoning_tokens":
                                         (ev.get("usage") or {}).get("reasoning_tokens")})
                usage = ev["usage"]
                finish = ev.get("finish_reason")
    except ValueError as exc:
        yield _sse("status", message=f"流式不可用（{_short(exc)}），回退整段生成……")
    text = "".join(parts)
    if not text.strip() or finish == "length":  # 空稿或截断 → 加倍回退（v0.6.5）
        why = "输出被截断（finish=length）" if text.strip() else "流式返回空正文"
        yield _sse("status", message=f"{why}——加倍预算回退重试……")
        try:
            result = _do_model(cfg, route, sid, prompt, budget * 2, False,
                               kind="gen")
        except HTTPException as exc:
            if text.strip():  # 保留截断部分，前端按徽标警告
                yield _sse("status", message=f"回退失败：{_short(exc)}；"
                                             "保留流式部分稿（截断，建议再修订）")
            else:
                yield _sse("error", message=str(exc.detail))
                return
        else:
            if len(result["text"]) > len(text):
                text, usage = result["text"], result
                yield _sse("replace", index=index, text=text, chars=len(text))
    if not text.strip():
        yield _sse("error", message="模型返回空正文（含回退重试）——"
                                    "请按报错对策更换模型或关闭思考模式")
        return
    usage = {**usage, "model": usage.get("model") or model}
    usage.setdefault("finish_reason", finish)  # 截断时前端据此警告
    _record_usage(sid, usage, "gen")
    yield _sse("status", index=index, message="门禁运行中（fp_check/borrow_check）……")
    with tempfile.TemporaryDirectory() as td:
        draft_path = Path(td) / f"stream{index}.txt"
        draft_path.write_text(text, encoding="utf-8", newline="\n")
        fp = _run_gate("fp_check.py", [str(pack_dir), str(draft_path)])
        borrow = _run_gate("borrow_check.py", [str(draft_path),
                                               "--pack", str(pack_dir)])
        aic = _run_gate("ai_cliche_check.py", [str(draft_path),
                                               "--pack", str(pack_dir)])
        nums = (_run_gate("numbers_check.py", [str(draft_path), "--ledger",
                                               numbers_ctx["ledger"],
                                               "--chapter",
                                               str(numbers_ctx["chapter"])])
                if numbers_ctx else None)
        nms = (_run_gate("names_check.py", [str(draft_path), "--variants",
                                            numbers_ctx["variants"],
                                            "--characters",
                                            numbers_ctx["characters"]])
                if numbers_ctx else None)
    ref_b = (_run_ref_borrow(draft_path, ref_dirs) if ref_dirs else None)
    yield _sse(done_event, index=index, text=text, usage=usage,
               fp_check=fp, borrow_check=borrow, ai_cliche=aic,
               numbers_check=nums, names_check=nms, ref_borrow=ref_b,
               warnings=_session_warnings(sid), **(extra or {}))


def _short(exc: Exception, n: int = 120) -> str:
    return str(exc)[:n]


@router.post("/generate_stream")
def do_generate_stream(body: GenerateIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    prep = _prep_generate(cfg, body)
    prov, model = appstate.resolve_route(cfg, "write")
    model_label = f'{prov["name"]}/{model}' if prov else model

    def gen():
        yield _sse("session", session_id=sid, model=model_label,
                   target_chars=prep["target"],
                   assembly_tokens=prep["assembly"]["total_est_tokens"],
                   budget=prep["bstate"])
        for i in range(max(1, min(3, body.n_drafts))):
            yield _sse("draft_start", index=i)
            nctx = None
            if (prep["project_dir"] / LONGFORM_MARKER).is_file():
                nctx = {"ledger": str(prep["project_dir"]
                                      / "bible" / "硬数字表.md"),
                        "chapter": body.chapter_no,
                        "variants": str(prep["project_dir"]
                                        / "bible" / "专名表.tsv"),
                        "characters": str(prep["project_dir"]
                                          / "bible" / "characters.md")}
            yield from _stream_one_draft(cfg, sid, prep["prompt"], prep["budget"],
                                         prep["pack_dir"], i, numbers_ctx=nctx,
                                         route=prep["route"],
                                         ref_dirs=prep.get("ref_dirs"))
        yield _sse("all_done", assembly_tokens=prep["assembly"]["total_est_tokens"],
                   budget=_budget_state(prep["project_dir"], body.chapter_no, sid),
                   warnings=_session_warnings(sid))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


class ReviseIn(BaseModel):
    project: str
    pack: str
    chapter_no: int
    title: str
    ref_packs: list[str] = []     # v0.13.13 参考池
    keywords: list[str] = []
    chosen: dict = {}
    beats: list[dict] = []
    text: str
    reports: dict = {}   # {fp_check/borrow_check: {exit_code, report}, ending: {...}}
    revision: int = 0
    target_chars: int = 0
    session_id: str = ""
    allow_over_budget: bool = False  # C-3 止损闸显式确认


def _gate_reports_text(reports: dict) -> str:
    parts = []
    for name in ("fp_check", "borrow_check"):
        rep = reports.get(name) or {}
        if rep.get("report"):
            parts.append(f"[{name}] exit={rep.get('exit_code')}" + chr(10)
                         + rep["report"])
    ending = reports.get("ending")
    if ending:
        parts.append(f"[ending_check] violation={ending.get('violation')}：{ending.get('reason')}")
    return (chr(10) * 2).join(parts) or "（无报告正文——按风格上下文的句长纪律自查）"


def _prep_revise(cfg: dict, body: ReviseIn) -> dict:
    project_dir = _project_dir(cfg, body.project)
    pack_dir = _pack_dir(body.pack, project_dir)
    ref_dirs = _ref_pack_dirs(cfg, body.project, body.ref_packs)
    bstate = _budget_gate(project_dir, body.chapter_no, _session_id(body),
                          body.allow_over_budget)
    assembly = assemble_mod.assemble(
        project_dir, pack_dir, body.chapter_no, body.keywords,
        cfg.get("context_budget_tokens", 24000), ref_pack_dirs=ref_dirs)
    target = _clean_target_chars(body.target_chars) or len(body.text or "")
    prompt = creation.revise_prompt(body.chapter_no, body.title, body.beats,
                                    assembly["kept_texts"], body.text,
                                    _gate_reports_text(body.reports), target)
    return {"pack_dir": pack_dir, "ref_dirs": ref_dirs, "prompt": prompt,
            "bstate": bstate,
            # ×2：修订要整篇重写（输出≈原文），思考型模型的推理也吃同一预算——
            # 2500 字章在 ×1 下实测推理+正文 >14000 tokens 被截成 1099 字
            "budget": _prose_budget(cfg, target) * 2}


@router.post("/revise")
def do_revise(body: ReviseIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    project_dir = _project_dir(cfg, body.project)
    prep = _prep_revise(cfg, body)
    result = _do_model(cfg, "write", sid, prep["prompt"], prep["budget"], False,
                       kind="rev")
    with tempfile.TemporaryDirectory() as td:
        draft_path = Path(td) / "revised.txt"
        draft_path.write_text(result["text"], encoding="utf-8", newline="\n")
        fp = _run_gate("fp_check.py", [str(prep["pack_dir"]), str(draft_path)])
        borrow = _run_gate("borrow_check.py", [str(draft_path),
                                               "--pack", str(prep["pack_dir"])])
        aic = _run_gate("ai_cliche_check.py", [str(draft_path),
                                               "--pack", str(prep["pack_dir"])])
        ref_b = (_run_ref_borrow(draft_path, prep.get("ref_dirs") or [])
                 if prep.get("ref_dirs") else None)
    return {"session_id": sid, "text": result["text"], "usage": result,
            "fp_check": fp, "borrow_check": borrow, "ai_cliche": aic,
            "ref_borrow": ref_b,
            "budget": _budget_state(project_dir, body.chapter_no, sid),
            "revision": int(body.revision) + 1}


@router.post("/revise_stream")
def do_revise_stream(body: ReviseIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    prep = _prep_revise(cfg, body)

    def gen():
        yield _sse("session", session_id=sid, budget=prep["bstate"])
        yield _sse("status", message="按报告修订生成中……")
        yield from _stream_one_draft(cfg, sid, prep["prompt"], prep["budget"],
                                     prep["pack_dir"], 0, done_event="revised_done",
                                     extra={"revision": int(body.revision) + 1},
                                     ref_dirs=prep.get("ref_dirs"))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


class RewriteIn(GenerateIn):
    text: str
    fragment: str
    instruction: str


@router.post("/rewrite")
def do_rewrite(body: RewriteIn):
    """局部改写（v0.9.3）：只动片段、其余逐字保留，输出整章 + 三道 advisory 门。"""
    if not body.fragment.strip():
        raise HTTPException(400, "改写片段为空")
    if body.fragment not in body.text:
        raise HTTPException(400, "片段不在正文中（请从当前稿原样粘贴）")
    if not (body.instruction or "").strip():
        raise HTTPException(400, "改写指令为空")
    cfg = appstate.load_config()
    sid = _session_id(body)
    prep = _prep_generate(cfg, body)
    prompt = creation.rewrite_prompt(body.chapter_no, body.title, body.beats,
                                     prep["assembly"]["kept_texts"], body.text,
                                     body.fragment, body.instruction)
    result = _do_model(cfg, "write", sid, prompt,
                       max(prep["budget"], _prose_budget(
                           cfg, len(body.text) or 2500) * 2), False, kind="gen")
    text = result["text"]
    # 改写守护：其余部分应基本保留（差异段落数 >1/3 视为跑偏，退回原稿提示）
    import difflib
    kept_ratio = difflib.SequenceMatcher(
        None, body.text, text).quick_ratio()
    with tempfile.TemporaryDirectory() as td:
        draft_path = Path(td) / "rewritten.txt"
        draft_path.write_text(text, encoding="utf-8", newline="\n")
        fp = _run_gate("fp_check.py", [str(prep["pack_dir"]), str(draft_path)])
        borrow = _run_gate("borrow_check.py", [str(draft_path),
                                               "--pack", str(prep["pack_dir"])])
        aic = _run_gate("ai_cliche_check.py", [str(draft_path),
                                               "--pack", str(prep["pack_dir"])])
    return {"session_id": sid, "text": text, "usage": result,
            "kept_ratio": round(kept_ratio, 3),
            "kept_warning": kept_ratio < 0.6,
            "fp_check": fp, "borrow_check": borrow, "ai_cliche": aic,
            "budget": _budget_state(prep["project_dir"], body.chapter_no, sid),
            "warnings": _session_warnings(sid)}


class ExportIn(BaseModel):
    project: str
    chapter_from: int
    chapter_to: int


@router.post("/export")
def do_export(body: ExportIn):
    """导出合并（v0.9.3）：manuscript 按章号区间合并为单个 txt 下载（内存不落盘）。"""
    cfg = appstate.load_config()
    ms = _project_dir(cfg, body.project) / "manuscript"
    picked = []
    for f in sorted(ms.glob("*.md")) if ms.is_dir() else []:
        if (n := _chapter_num_local(f.stem)) and body.chapter_from <= n <= body.chapter_to:
            picked.append((n, f))
    if not picked:
        raise HTTPException(404, f"区间 {body.chapter_from}–{body.chapter_to} 内没有章节")
    parts = []
    for n, f in picked:
        parts.append(splib.read_text(f)[0].strip())
    blob = "\n\n\n".join(parts) + "\n"
    from fastapi.responses import Response
    fname = f"{body.project}-{body.chapter_from:03d}-{picked[-1][0]:03d}.txt"
    return Response(content=blob.encode("utf-8"), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition":
                             f"attachment; filename*=UTF-8''{__import__('urllib.parse', fromlist=['quote']).quote(fname)}"})


def _chapter_num_local(stem: str) -> int | None:
    m = re.match(r"(\d+)", stem)
    return int(m.group(1)) if m else None


class EndingIn(BaseModel):
    project: str
    title: str
    text: str
    session_id: str = ""


@router.post("/ending_check")
def do_ending(body: EndingIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    tail = body.text[-800:]
    prompt = creation.ending_check_prompt(body.title, tail)
    result = _do_model(cfg, "judge", sid, prompt, 500, True)
    return {"session_id": sid, "ending_check": result["json"], "usage": result}


class SaveIn(BaseModel):
    project: str
    pack: str
    chapter_no: int
    title: str
    text: str
    keywords: list[str] = []  # v0.6.6：入记录，历史会话可精确重放装配
    chosen: dict = {}
    beats: list[dict] = []
    tone_note: str = "不指定"
    canon_anchor: str = "无"
    checks: dict = {}
    usage: dict = {}
    target_chars: int = 0
    session_id: str = ""
    assembly_preview: list[dict] = []
    g0: dict = {}  # v0.11.1 B-1：七字段简报留痕（跳过时 {"skipped": true}）


@router.post("/save")
def do_save(body: SaveIn):
    if not (body.text or "").strip():
        raise HTTPException(400, "草稿为空，拒绝交付——请回到创作环重新生成或修订")
    title = (body.title or "").strip()
    for ch in '\\/:*?"<>|':  # Windows 文件名非法字符
        title = title.replace(ch, "_")
    title = title.strip(". ") or "未命名"  # 结尾点/空格在 Windows 非法；纯符号回退

    cfg = appstate.load_config()
    project_dir = _project_dir(cfg, body.project)
    ms = project_dir / "manuscript"
    ms.mkdir(parents=True, exist_ok=True)
    target = ms / f"{body.chapter_no:03d}-{title}.md"
    if target.exists():
        stamp = time.strftime("%H%M%S")
        target = ms / f"{body.chapter_no:03d}-{title}-{stamp}.md"
    target.write_text(body.text, encoding="utf-8", newline="\n")

    sessions = project_dir / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    gitignore = sessions / ".gitignore"
    if not gitignore.is_file():  # 会话记录含创作内容，防误提交
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8", newline="\n")
    # v0.11.1 B-1/B-3：G0 留痕 + 交付即数字对照（长篇项目，报不拦）
    checks = dict(body.checks)
    nums = nms = None
    if _is_longform(project_dir):
        nums = _run_gate("numbers_check.py",
                         [str(target), "--ledger",
                          str(project_dir / "bible" / "硬数字表.md"),
                          "--chapter", str(body.chapter_no)])
        checks["numbers_check"] = nums
        nms = _run_gate("names_check.py",
                        [str(target), "--variants",
                         str(project_dir / "bible" / "专名表.tsv"),
                         "--characters",
                         str(project_dir / "bible" / "characters.md")])
        checks["names_check"] = nms
    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "tool": "web-create v0.12.0", "session_id": body.session_id,
        "project": body.project, "pack": body.pack,
        "chapter_no": body.chapter_no, "title": title,
        "keywords": body.keywords,
        "target_chars": _clean_target_chars(body.target_chars),
        "chosen": body.chosen, "beats": body.beats,
        "tone_note": body.tone_note, "canon_anchor": body.canon_anchor,
        "g0": body.g0,
        "checks": checks, "usage": body.usage,
        "assembly": body.assembly_preview,
        "session_totals": _session_totals(body.session_id),
        "output_file": target.name, "text": body.text,
    }
    (sessions / f"{time.strftime('%Y%m%d-%H%M%S')}-{body.chapter_no:03d}.json"
     ).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8", newline="\n")
    totals = _session_totals(body.session_id)
    appstate.append_cost(project_dir, "web-create",
                         chars=len(body.text), model=str(body.usage.get("model", "")),
                         tokens=(body.usage.get("prompt_tokens", 0)
                                 + body.usage.get("completion_tokens", 0)),
                         session_tokens=totals["tokens"],
                         session_calls=totals["calls"],
                         session_id=body.session_id,
                         note=f"第{body.chapter_no}章《{title}》")
    return {"ok": True, "manuscript": str(target), "sessions_dir": str(sessions),
            "session_totals": totals, "numbers_check": nums,
            "names_check": nms,
            "budget": _budget_state(project_dir, body.chapter_no,
                                    body.session_id)}


# ---- 新建项目（v0.10.0：不开 agent 的用户从这里开始第一本书）----

class ProjectCreateIn(BaseModel):
    name: str
    mode: str = "light"            # light=现状 | longform=长篇连载（v0.11 骨架）
    pack: str | None = None        # 可选：风格包钉扎（export → style/pinned-pack.md）
    canon_pack: str | None = None  # 可选：canon 包钉扎（terms 快照 → canon/）


BIBLE_TEMPLATES = {
    "characters.md": "# 人物\n\n## 主角名\n一句话身份。性格：\n口头禅/说话习惯：\n与谁什么关系：\n状态：在场（死亡/离场改：死亡（第N章）/离场（第N章）——names_check 状态门用）\n",
    "world.md": "# 世界设定\n\n## 基本规则\n（力量体系/经济/地理，一段一条）\n",
    "names.json": '{"names": []}\n'
                  '# 每个人名：{"name": "主角名", "tier": "core", "aliases": []}\n'
                  "# tier=core 的实体块自动常驻装配（World Info）\n",
    "专名表.tsv": "# 专名总账（names_check --variants 用）\n# 正名<TAB>禁用变体1|变体2（形近/音近错写由作者养表；# 开头为注释）\n# 例：陈曦\t陈熙|陈稀\n",
    "../outline.md": "# 卷纲\n\n## 卷一 卷名\n\n### 1 第一章题\n概要一两句。\n\n### 2 第二章题\n概要。\n",
}


@router.post("/projects/create")
def project_create(body: ProjectCreateIn):
    cfg = appstate.load_config()
    name = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", body.name.strip()).strip("-")
    if not name:
        raise HTTPException(400, "项目名非法（中英文/数字/连字符，40 字内）")
    d = (_ws_root(cfg) / name[:40])
    if d.exists():
        raise HTTPException(409, f"项目已存在：{d.name}")
    for sub in ("manuscript", "bible", "style", "sessions"):
        (d / sub).mkdir(parents=True)
    (d / "sessions" / ".gitignore").write_text("*\n!.gitignore\n",
                                               encoding="utf-8", newline="\n")
    for fname, tpl in BIBLE_TEMPLATES.items():
        (d / "bible" / fname if not fname.startswith("../")
         else d / fname[3:]).write_text(tpl, encoding="utf-8", newline="\n")
    notes = ["骨架：manuscript/ bible/ style/ sessions/（gitignore）"]
    # 可选风格包钉扎（export 单文件 + 版本注头，复用 read_pinned_pack 协议）
    if body.pack:
        try:
            pack_dir = _pack_dir(body.pack, d)
        except HTTPException:
            raise HTTPException(400, f"风格包不存在：{body.pack}")
        out = d / "style" / "pinned-pack.md"
        r = _run_gate("export_pack.py", [str(pack_dir), "--out", str(out)])
        if r["exit_code"] != 0:
            raise HTTPException(502, f"钉扎导出失败：{r['report'][-300:]}")
        ver = _pack_version(pack_dir)
        head = f"<!-- 钉扎：{body.pack} v{ver} at {datetime.date.today()} -->\n"
        out.write_text(head + out.read_text(encoding="utf-8"), encoding="utf-8")
        notes.append(f"已钉扎 {body.pack} v{ver}（style/pinned-pack.md）")
    # 可选 canon 包钉扎（terms 快照 + card）
    if body.canon_pack:
        notes.append(_pin_canon(d, body.canon_pack))
    # 长篇模式骨架（v0.11 阶段 A）：防线/宪法/硬数字表/结构化卷纲
    if body.mode == "longform":
        notes += _longform_skeleton(d)
    return {"ok": True, "name": d.name, "notes": notes,
            "cli": "网页建项目 = 手工建 manuscript/bible/style 目录；"
                   "钉扎 = python scripts/export_pack.py <包> --out <项目>/style/pinned-pack.md"}


# ---- 长篇模式（v0.11 阶段 A）：骨架模板与弧管理 ----
# 治理框架来源：灾厄前线实战验证（写作防线 G0-G4 / 硬数字表 / 弧结构）。
# 公理：①成本=轮数×上下文重发；②规范层必须对描述层有执法权。

LONGFORM_MARKER = "00_写作防线.md"  # 项目根存在此文件 = 长篇模式

TPL_DEFENSE = """# 写作防线

> 长篇模式治理框架（StylePack v0.11 内置模板，源自长篇连载实战验证）。
> 本文件是项目的**执法手册**：所有写作循环受以下闸门约束。

## 闸门

| 闸门 | 时机 | 手段 | 拦截动作 |
|---|---|---|---|
| G0 写前 | 每章生成前 | 七字段简报（锚点/主角状态/弧线位置/伏笔动作/出场口癖/结尾钩子/衔接） | 缺字段不生成（工作台表单强制） |
| G1 写后 | 每章落盘后 | 门控检查（字数/标点/锚点在场/主角在场/专名正字） | FAIL 不修复不进下一章 |
| G2 轮末 | 每 10 章 | 结构检查 + 拆账留痕（历史页） | 违规项当轮修复 |
| G3 漂移网 | 每弧末 | 独立对照审查（对照大纲/硬数字表/人物档案） | 必修项未清不开新弧 |
| G4 验收 | 每弧末 | 作者抽读 | 否决=最高指令 |

## 预算纪律

- 单章修稿预算：＿＿万 tokens；单弧预算：＿＿万
- 超预警：停止并诊断（成本=轮数×上下文重发，不是产出×单价）
- 禁止整章重写式返修；修稿一律 diff 级

## 规范层/描述层等级制

- 规范层（不可被正文无声覆盖）：00_项目宪法.md、outline.md 铁律、bible/硬数字表.md、本文件
- 正文与规范层冲突时：**停写上报**，不许圆稿
"""

TPL_CONSTITUTION = """# 项目宪法（规范层·最高约束）

> 本文件是项目的规范层：正文与本文冲突时，停写上报，不得圆稿。
> 条款由作者填写——填下的每一条都对写作流程有执法权。

## 底线（不可违背）
1. 
2. 

## 每章必含
- 

## 禁区
- 
"""

TPL_NUMBERS = """# 硬数字表

> 规范层附件：正文会出现的硬数字（频率/时间/人数/金额/计数）**唯一口径**。
> 写作只准引用本表数字，不得自造；弧末审查以本表为对照基准。
> 每开新弧追加一节；改数须留痕（旧值→新值+理由）。
"""

TPL_OUTLINE_LONGFORM = """# 卷纲

## 卷一 卷名
铁律：（本卷不可违背的约束，逐条列出）
"""

# C-1 预算层默认值（C1 已追认 2026-11-05：单章 15 万/弧 150 万/止损 ×2；
# 依据 $high 实测 12-15万/万字；medium 档落地后仅校准量产路由，预算线不动）
TPL_BUDGET = {
    "chapter_budget": 150000,
    "arc_budget": 1500000,
    "halt_multiplier": 2.0,
    "note": "已按 $high 实测 12-15万/万字 追认（2026-11-05）；"
            "medium 档落地后量产路由可再降档；单位=tokens",
    "rev": 1,
}


def _longform_skeleton(d: Path) -> list[str]:
    notes = []
    for path_obj, tpl in ((d / LONGFORM_MARKER, TPL_DEFENSE),
                          (d / "00_项目宪法.md", TPL_CONSTITUTION),
                          (d / "bible" / "硬数字表.md", TPL_NUMBERS),
                          (d / "outline.md", TPL_OUTLINE_LONGFORM)):
        path_obj.write_text(tpl, encoding="utf-8", newline="\n")
    budget = d / "style" / "budget.json"
    budget.write_text(json.dumps(TPL_BUDGET, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    notes.append("长篇骨架：00_写作防线.md（G0-G4 闸门模板）+ 00_项目宪法.md（条款待填）"
                 " + bible/硬数字表.md + 结构化卷纲")
    notes.append("预算层：style/budget.json（单章 15 万 / 弧 150 万 / 止损 ×2——"
                 "默认值待标定，C1/D7）")
    return notes


def _is_longform(d: Path) -> bool:
    return (d / LONGFORM_MARKER).is_file()


def _parse_arcs(outline_text: str) -> list[dict]:
    """解析 outline.md 的弧块：### 【弧N·弧名】（第X-Y章）+ 四字段列表。"""
    import re as _re
    arcs = []
    pat = ("^###" + chr(92) + "s*【弧(" + chr(92) + "d+)·(.+?)】（第("
           + chr(92) + "d+)-(" + chr(92) + "d+)章）" + chr(10)
           + "- 原作锚点：(.*)" + chr(10)
           + "- 张力设计：(.*)" + chr(10)
           + "- 勾稽点：(.*)" + chr(10)
           + "- 章数字数：(.*)$")
    for m in _re.finditer(pat, outline_text, _re.M):
        arcs.append({"no": int(m.group(1)), "title": m.group(2),
                     "start": int(m.group(3)), "end": int(m.group(4)),
                     "anchors": m.group(5).strip(), "tension": m.group(6).strip(),
                     "hooks": m.group(7).strip(), "size": m.group(8).strip()})
    return arcs


# ---- G0 写前简报（v0.11.1 阶段 B）：七字段表单 + 弧简报卡 + 探针章 ----
# 治理来源：灾厄前线 G0"缺一不派发"；图纸门 §5.3（v0.12 设想）：
# 灾厄前线 25 万字事故=大纲细微误差被逐章忠实执行——弧前图纸审+探针章
# 把结构性误差的修正成本压到 1-2 章。

G0_LABELS = (("anchor", "原作锚点"), ("hero_state", "主角状态"),
             ("arc_pos", "弧线位置"), ("foreshadow", "伏笔动作"),
             ("quirks", "出场口癖"), ("ending_hook", "结尾钩子"),
             ("bridge", "衔接上一章"))


def _g0_text(g0: dict | None) -> str:
    """G0 简报 → 提示词附件（空/跳过返回空串）。缺字段执法在前端
    （置灰+跳过链接，D4 决策），服务端只透传与留痕。"""
    if not isinstance(g0, dict) or g0.get("skipped"):
        return ""
    lines = []
    for k, label in G0_LABELS:
        v = str(g0.get(k, "") or "").strip()
        if v:
            lines.append(f"- {label}：{v}")
    if not lines:
        return ""
    return ("【写前简报 G0（七字段，本章写作必须落实）】" + chr(10)
            + chr(10).join(lines))


def _prev_ending_hook(d: Path, chapter_no: int) -> str:
    """衔接默认值：此前交付章节 G0 登记的结尾钩子（sessions 记录，取最近章）。"""
    best, hook = -1, ""
    for j in (d / "sessions").glob("*.json"):
        try:
            rec = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        n = int(rec.get("chapter_no") or 0)
        h = str((rec.get("g0") or {}).get("ending_hook", "") or "").strip()
        if 0 < n < chapter_no and n >= best and h:
            best, hook = n, h
    return hook[:200]


def _arc_confirmed(outline_text: str, arc: dict) -> bool:
    """图纸确认（G-0.5）：弧块内含「- 图纸确认：」行即已过目。"""
    i = outline_text.find(f"【弧{arc['no']}·{arc['title']}】")
    if i < 0:
        return False
    j = outline_text.find("### 【", i + 1)
    return "图纸确认" in outline_text[i:(j if j > 0 else len(outline_text))]


@router.get("/longform/status")
def longform_status(project: str):
    cfg = appstate.load_config()
    d = _project_dir(cfg, project)
    if not _is_longform(d):
        return {"longform": False, "arcs": []}
    outline = d / "outline.md"
    arcs = _parse_arcs(outline.read_text(encoding="utf-8")) if outline.is_file() else []
    ms = d / "manuscript"
    max_ch = 0
    if ms.is_dir():
        for f in ms.glob("*.md"):
            mm = re.match(r"(\d+)", f.stem)
            if mm:
                max_ch = max(max_ch, int(mm.group(1)))
    return {"longform": True, "arcs": arcs, "max_chapter": max_ch,
            "next_arc_no": (arcs[-1]["no"] + 1) if arcs else 1,
            "next_start": max(max_ch + 1, (arcs[-1]["end"] + 1) if arcs else 1)}


@router.get("/longform/g0")
def longform_g0(project: str, chapter_no: int):
    """G0 写前简报（v0.11.1 B-1）：当前弧定位 + 七字段自动预填（可改）+
    探针章标记（每弧前 2 章，J9）+ 图纸确认状态 + 硬数字表当前弧节。
    轻量项目返回 longform=False（前端不出现 G0 表单——回归零变化）。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, project)
    if not _is_longform(d):
        return {"longform": False}
    outline = d / "outline.md"
    otext = outline.read_text(encoding="utf-8") if outline.is_file() else ""
    arcs = _parse_arcs(otext)
    arc = next((a for a in arcs if a["start"] <= chapter_no <= a["end"]), None)
    brief = {k: "" for k, _ in G0_LABELS}
    probe = False
    if arc:
        off = chapter_no - arc["start"] + 1
        total = arc["end"] - arc["start"] + 1
        brief["anchor"] = arc["anchors"]
        brief["arc_pos"] = (f"弧{arc['no']}《{arc['title']}》第 {off}/{total} 章"
                            f"（全弧第 {arc['start']}-{arc['end']} 章）")
        probe = (chapter_no - arc["start"]) < 2  # J9：每弧前 2 章为探针
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from store import Store  # noqa: E402
        store = Store(d)
        try:
            recap = store.recap(3)
        finally:
            store.close()
        recent = recap.get("recent") or []
        if recent:
            latest = max(recent, key=lambda r: int(r.get("chapter") or 0))
            brief["hero_state"] = str(latest.get("digest", ""))[:200]
        ff = recap.get("open_foreshadow") or []
        if ff:
            brief["foreshadow"] = "；".join(
                f"{r['title']}（第{r['planted_chapter']}章埋，待回收）"
                for r in ff)[:300]
    except Exception:  # noqa: BLE001 —— 记忆是增强，绝不阻断
        pass
    prev = _prev_ending_hook(d, chapter_no)
    if prev:
        brief["bridge"] = prev
    return {"longform": True, "arc": arc, "probe": probe,
            "arc_confirmed": bool(arc and _arc_confirmed(otext, arc)),
            "brief": brief, "budget": _budget_of(d),
            "blueprint_changed": _blueprint_changed(d),
            "numbers_section": assemble_mod.numbers_section(d, chapter_no)}


class ArcConfirmIn(BaseModel):
    project: str
    arc_no: int


@router.post("/longform/arc_confirm")
def longform_arc_confirm(body: ArcConfirmIn):
    """弧简报卡确认（G-0.5 图纸门，§5.3）：人对照原作过目本弧图纸后落痕——
    确认行写进弧块；未确认的弧，前端置灰生成（G0 门的一环）。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    outline = d / "outline.md"
    if not outline.is_file():
        raise HTTPException(404, "outline.md 不存在")
    text = outline.read_text(encoding="utf-8")
    arc = next((a for a in _parse_arcs(text) if a["no"] == body.arc_no), None)
    if not arc:
        raise HTTPException(404, f"弧{body.arc_no} 不存在")
    if _arc_confirmed(text, arc):
        return {"ok": True, "already": True}
    i = text.find(f"### 【弧{arc['no']}·{arc['title']}】")
    if i < 0:
        raise HTTPException(500, "弧块定位失败（格式漂移？请手查 outline.md）")
    j = text.find("- 章数字数：", i)
    if j < 0:
        raise HTTPException(500, "弧块缺章数字数行——格式漂移，请手查 outline.md")
    eol = text.find(chr(10), j)
    stamp = datetime.date.today().isoformat()
    line = f"{chr(10)}- 图纸确认：{stamp}（弧简报卡已过目，G-0.5）"
    outline.write_text(text[:eol] + line + text[eol:] if eol >= 0 else text + line,
                       encoding="utf-8", newline=chr(10))
    _blueprint_baseline(d, refresh=True)  # 图纸确认=基线时刻（§5.3）
    return {"ok": True, "confirmed": stamp,
            "cli": "网页确认 = outline.md 弧块追加「- 图纸确认：日期」"}


# ---- 成本框架（v0.11.2 阶段 C）：预算层 + 拆账强制 + 三态执法 + 量产路由 ----
# 设计：工作台v0.11-C成本控制-设计设想.md §四（三层钱包+两道闸）。
# 定律：agent 成本 = 轮数 × 上下文重发——工作台是单发架构，执法对象是
# "单章累计"（会话分桶 + 账本本章历史行）。C4：预算存 style/budget.json
# （文件协议随项目走）；C5：usage 缺失时估算值已入账（v0.6.4），判定不区分。

def _budget_of(project_dir: Path) -> dict | None:
    """style/budget.json（C4）；文件缺失的长篇项目（0.11.0 老项目）用默认值
    执法（rev=0 表示尚未落盘）；轻量项目 None=预算层不存在。"""
    if not _is_longform(project_dir):
        return None
    p = project_dir / "style" / "budget.json"
    if p.is_file():
        try:
            b = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(b, dict) and b.get("chapter_budget"):
                return b
        except (OSError, ValueError):
            pass
    return dict(TPL_BUDGET, rev=0)


def _chapter_ledger_tokens(project_dir: Path, chapter_no: int,
                           exclude_sid: str = "") -> int:
    """本章在账本里的历史拆账（弃稿重开：上一轮对同章号的交付消耗）。
    exclude_sid：排除当前会话自己的行（v0.12 起账本行带 session 字段——
    否则交付后 spend 双算，会提前误触闸）。"""
    cost = project_dir / "style" / "cost.jsonl"
    total, tag = 0, f"第{chapter_no}章"
    if cost.is_file():
        for line in cost.read_text(encoding="utf-8").splitlines():
            if tag not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if exclude_sid and row.get("session") == exclude_sid:
                continue
            total += int(row.get("session_tokens") or row.get("tokens") or 0)
    return total


def _budget_state(project_dir: Path, chapter_no: int, sid: str) -> dict | None:
    """预算三态（C-3）：normal / warning(≥单章预算) / halt(≥预算×止损倍数)。
    spend = 本章会话已烧（含重试/修订分桶）+ 账本本章历史行（排除本会话行）。"""
    b = _budget_of(project_dir)
    if not b:
        return None
    s = _sessions.get(sid or "", {})
    session_t = int(s.get("tokens", 0))
    ledger_t = _chapter_ledger_tokens(project_dir, chapter_no, exclude_sid=sid)
    spend = session_t + ledger_t
    line = int(b.get("chapter_budget") or 0)
    halt = int(line * float(b.get("halt_multiplier") or 2.0))
    state = "normal"
    if line and spend >= halt:
        state = "halt"
    elif line and spend >= line:
        state = "warning"
    return {"state": state, "spend": spend, "chapter_budget": line,
            "halt_line": halt, "session_tokens": session_t,
            "ledger_tokens": ledger_t,
            "breakdown": {"gen": int(s.get("gen", 0)),
                          "rev": int(s.get("rev", 0)),
                          "other": int(s.get("other", 0))},
            "arc_budget": int(b.get("arc_budget") or 0),
            "warnings": _session_warnings(sid)}


def _budget_gate(project_dir: Path, chapter_no: int, sid: str,
                 allow_over: bool) -> dict | None:
    """止损闸：halt 且未显式确认 → 429（C2：禁按钮的服务端牙齿；
    显式确认 allow_over=True 可越——G4 最高指令权，永不真锁死）。"""
    bs = _budget_state(project_dir, chapter_no, sid)
    if bs and bs["state"] == "halt" and not allow_over:
        raise HTTPException(
            429, f"止损闸：本章已烧 {bs['spend']} / 止损线 {bs['halt_line']}"
                 f" tokens（单章预算 {bs['chapter_budget']}×止损倍数）——"
                 "出路：换模型（配置页）/ 调高预算（显式确认）/ 放弃本章")
    return bs


def _ledger_gate(project_dir: Path, chapter_no: int, allow_unbilled: bool) -> None:
    """拆账强制（C 阶段执法）：开"最新章+1"前，上一章必须有交付拆账记录
    （web 交付天然落账；CLI/agent 混合工作流会被拦——显式确认可越过，
    把账本从"可选看"变"必经之路"）。改写旧章不受限。"""
    if not _is_longform(project_dir):
        return
    ms = project_dir / "manuscript"
    best = 0
    if ms.is_dir():
        for f in ms.glob("*.md"):
            if m := re.match(r"(\d+)", f.stem):
                best = max(best, int(m.group(1)))
    if chapter_no != best + 1 or best < 1 or allow_unbilled:
        return
    cost = project_dir / "style" / "cost.jsonl"
    tag = f"第{best}章"
    if cost.is_file() and tag in cost.read_text(encoding="utf-8"):
        return
    raise HTTPException(
        409, f"拆账强制：第{best}章没有交付拆账记录（style/cost.jsonl 无本章行）"
             "——先在网页对上一章走一次交付，或显式确认越过（防线：无拆账不开工）")


def _write_route(cfg: dict, project_dir: Path, body) -> str:
    """C-4/C3 量产路由：长篇 + G0 章类型=量产（默认）+ 已配置 write_mass
    → 量产档；关键章（chapter_type=key）与未配置时回退 write。"""
    if _is_longform(project_dir):
        g0 = getattr(body, "g0", None) or {}
        if g0.get("chapter_type", "mass") != "key" \
                and cfg.get("routing", {}).get("write_mass"):
            return "write_mass"
    return "write"


class BudgetIn(BaseModel):
    project: str
    chapter_budget: int
    arc_budget: int
    halt_multiplier: float
    rev: int  # 乐观锁（死规矩 #10：预算可被网页与手改两个写入方触达）


@router.get("/longform/budget")
def longform_budget_get(project: str):
    cfg = appstate.load_config()
    b = _budget_of(_project_dir(cfg, project))
    if b is None:
        raise HTTPException(400, "轻量项目无预算层")
    return b


@router.post("/longform/budget")
def longform_budget_set(body: BudgetIn):
    """调高/调整预算（halt 三出路之一，显式确认由前端对话框承担）：
    rev 乐观锁先行（死规矩 #10，与 /config 同序），旧 rev 409 强制刷新。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    cur = _budget_of(d) or {}
    if body.rev != int(cur.get("rev") or 0):
        return JSONResponse(status_code=409, content={
            "detail": f"预算已被他处修改（本页 rev={body.rev}，"
                      f"最新 rev={cur.get('rev')}）——刷新后重试",
            "budget": cur})
    if body.chapter_budget < 1:
        raise HTTPException(400, "单章预算须 ≥1 token")
    if body.arc_budget < body.chapter_budget:
        raise HTTPException(400, "弧预算须 ≥ 单章预算")
    if body.halt_multiplier < 1.0:
        raise HTTPException(400, "止损倍数须 ≥1.0")
    data = {"chapter_budget": int(body.chapter_budget),
            "arc_budget": int(body.arc_budget),
            "halt_multiplier": float(body.halt_multiplier),
            "note": str(cur.get("note", "")) or TPL_BUDGET["note"],
            "rev": int(cur.get("rev") or 0) + 1}
    (d / "style").mkdir(exist_ok=True)
    (d / "style" / "budget.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    return {"ok": True, **data,
            "cli": "网页改预算 = 编辑 style/budget.json（rev+1）"}


# ---- 弧末治理（v0.11.3 阶段 D）：漂移网 + 交接汇总 + 图纸变更检测 ----
# 来源：灾厄前线工单一（G3 清单模式：只验硬数字逐条+伏笔动作+节拍落位）、
# 两次实战交接汇总、图纸门 §5.3 防线4（hash 检测外部改动→受影响回扫）。

def _file_sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else ""


def _blueprint_files(d: Path) -> dict:
    """图纸文件集：outline.md + bible 全部 md/json（人物卡/世界观/数字表在列）。"""
    out = {}
    o = d / "outline.md"
    if o.is_file():
        out["outline.md"] = _file_sha(o)
    bible = d / "bible"
    if bible.is_dir():
        for f in sorted(bible.iterdir()):
            if f.suffix in (".md", ".json"):
                out[f"bible/{f.name}"] = _file_sha(f)
    return out


def _blueprint_baseline(d: Path, refresh: bool = False) -> dict:
    """图纸基线（style/blueprint.json）。首读自动建（缓存性质）；refresh=True
    在人工确认点（开弧/图纸确认/再确认）重置。"""
    p = d / "style" / "blueprint.json"
    if not refresh and p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    base = {"files": _blueprint_files(d),
            "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")
    return base


def _blueprint_changed(d: Path) -> list[str]:
    base = _blueprint_baseline(d)
    cur = _blueprint_files(d)
    return [k for k in sorted(set(base["files"]) | set(cur))
            if base["files"].get(k) != cur.get(k)]


class ProjectIn(BaseModel):
    project: str


@router.post("/longform/blueprint_confirm")
def longform_blueprint_confirm(body: ProjectIn):
    """图纸再确认（§5.3 防线4 出口）：人核对变更（含回扫结果）后重置基线。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    base = _blueprint_baseline(d, refresh=True)
    return {"ok": True, "files": len(base["files"]),
            "ts": base["ts"],
            "cli": "网页再确认 = 重写 style/blueprint.json 基线"}


@router.post("/longform/retroscan")
def longform_retroscan(body: ProjectIn):
    """账本回扫（retroscan，§12.3②）：numbers_check --all 全量对照历史章——
    新账落定后揪"后立口径与前文冲突"的旧错。advisory 报不拦。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    r = _run_gate("numbers_check.py",
                  [str(d), "--ledger", str(d / "bible" / "硬数字表.md"),
                   "--all"])
    return {"exit_code": r["exit_code"], "report": r["report"]}


@router.get("/longform/arcanet")
def longform_arcanet(project: str, arc_no: int):
    """弧末漂移网指令包（D/G3 清单模式）：复制到**独立会话/子代理**执行——
    只验硬数字表逐条 + 伏笔动作 + 弧节拍落位，不做五维全量（省百万级 tokens）。
    数字类错误须标来源（表外自造/表内执行错/表本身错——工单三分诊断）。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    outline = d / "outline.md"
    arcs = _parse_arcs(outline.read_text(encoding="utf-8")
                       if outline.is_file() else "")
    arc = next((a for a in arcs if a["no"] == arc_no), None)
    if not arc:
        raise HTTPException(404, f"弧{arc_no} 不存在")
    nums = assemble_mod.numbers_section(d, arc["end"])
    ff: list[str] = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from store import Store  # noqa: E402
        store = Store(d)
        try:
            recap = store.recap(1)
        finally:
            store.close()
        ff = [f"{r['title']}（第{r['planted_chapter']}章埋）"
              for r in (recap.get("open_foreshadow") or [])]
    except Exception:  # noqa: BLE001
        pass
    NL = chr(10)
    lines = [
        f"# 弧{arc['no']}《{arc['title']}》漂移网复检（清单模式·独立审查）",
        "",
        f"你是独立审查员，未参与本弧写作。审查对象：第 {arc['start']}-"
        f"{arc['end']} 章正文（manuscript/）。只做以下三类清单核对，"
        "不做全量五维审查：",
        "",
        "## 一、硬数字表逐条对照（数字唯一口径，只准引用）",
        "对下表每条口径，在对应章节找出正文落点；找不出/写错即 FAIL。",
    ]
    if nums:
        lines += ["```", nums, "```",
                  "数字类错误标注来源（三分诊断）：①表外自造（写手造了表外数字）/"
                  "②表内执行错（表对写错）/③表本身错（回填笔误）。"]
    else:
        lines.append("（本弧硬数字表为空——正文出现关键数字时逐条列出待回填）")
    lines += ["", "## 二、伏笔动作核对（每章应有动作或明确回收）"]
    lines += [f"- {x}" for x in ff] or ["- （账本无未回收伏笔）"]
    lines += [
        "",
        "## 三、弧节拍落位",
        f"- 原作锚点：{arc['anchors']}",
        f"- 张力设计：{arc['tension']}",
        f"- 勾稽点：{arc['hooks']}",
        "",
        "## 输出格式",
        "每条：PASS / FAIL + 章节定位 + 原文证据（≤50 字引用）。",
        "末尾给三行：必修项数 / 建议项数 / 结论（通过 / 修复后复检）。",
        "",
        "## 纪律",
        "- 只审不改；发现矛盾**停写上报**，禁止圆稿；",
        "- 你与写作不在同一会话——不许参考写作过程，只看文本与以上清单。",
    ]
    return {"arc": arc, "prompt": NL.join(lines),
            "chapters": [arc["start"], arc["end"]]}


class ArcnetArchiveIn(BaseModel):
    project: str
    arc_no: int
    report: str


@router.post("/longform/arcanet/archive")
def arcanet_archive(body: ArcnetArchiveIn):
    """漂移网结果归档：整合/一致性报告/弧N-漂移网-*.md（永不覆盖，撞名加序号）。"""
    if not (body.report or "").strip():
        raise HTTPException(400, "报告为空，拒绝归档")
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    out_dir = d / "整合" / "一致性报告"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    f, k = out_dir / f"弧{body.arc_no}-漂移网-{stamp}.md", 2
    while f.exists():
        f = out_dir / f"弧{body.arc_no}-漂移网-{stamp}-{k}.md"
        k += 1
    head = (f"<!-- 弧{body.arc_no} 漂移网复检归档 {stamp}｜清单模式 "
            f"numbers 纪律 v0.11.3 -->" + chr(10))
    f.write_text(head + body.report.strip() + chr(10),
                 encoding="utf-8", newline=chr(10))
    return {"ok": True, "file": str(f.relative_to(d)),
            "cli": "网页归档 = 报告存 整合/一致性报告/弧N-漂移网-*.md"}


def _arcnet_archived(d: Path, arc_no: int) -> bool:
    rep = d / "整合" / "一致性报告"
    return rep.is_dir() and any(rep.glob(f"弧{arc_no}-漂移网-*.md"))


@router.get("/longform/handover")
def longform_handover(project: str):
    """一键交接汇总草稿（D）：进度/成本/伏笔/断点全从文件与账本现算——
    压缩或换会话时复制即用。宪法来源：灾厄前线两次实战交接汇总。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    outline = d / "outline.md"
    arcs = _parse_arcs(outline.read_text(encoding="utf-8")
                       if outline.is_file() else "")
    ms, max_ch, words = d / "manuscript", 0, 0
    if ms.is_dir():
        for f in ms.glob("*.md"):
            if m := re.match(r"(\d+)", f.stem):
                max_ch = max(max_ch, int(m.group(1)))
            try:
                words += len(splib.read_text(f)[0])
            except OSError:
                pass
    cost = d / "style" / "cost.jsonl"
    total_tok, rows = 0, 0
    if cost.is_file():
        for line in cost.read_text(encoding="utf-8").splitlines():
            if "web-create" not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rows += 1
            total_tok += int(row.get("session_tokens")
                             or row.get("tokens") or 0)
    digest, hook = "", ""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from store import Store  # noqa: E402
        store = Store(d)
        try:
            recap = store.recap(1)
        finally:
            store.close()
        recent = recap.get("recent") or []
        if recent:
            latest = max(recent, key=lambda r: int(r.get("chapter") or 0))
            digest = f"第{latest['chapter']}章：{latest['digest']}"
        ff = recap.get("open_foreshadow") or []
    except Exception:  # noqa: BLE001
        ff = []
    hook = _prev_ending_hook(d, max_ch + 1) if max_ch else ""
    NL = chr(10)
    lines = [
        f"# 交接汇总（草稿·自动生成 {datetime.date.today().isoformat()}）",
        "",
        "## 一、进度",
        f"- 现役：第 {max_ch} 章｜{words} 字｜交付记录 {rows} 条",
        "- 弧状态：" + ("；".join(
            f"弧{a['no']}《{a['title']}》（{a['start']}-{a['end']}章，"
            f"{'图纸已确认' if _arc_confirmed(outline.read_text(encoding='utf-8') if outline.is_file() else '', a) else '图纸未确认'}"
            f"{'，漂移网已归档' if _arcnet_archived(d, a['no']) else '，漂移网待跑'}）"
            for a in arcs) or "（未开弧）"),
        "",
        "## 二、成本（web-create 交付口径）",
        f"- 累计 {total_tok} tokens（看板页有逐弧/逐章拆账）",
        "",
        "## 三、断点（下一章从这里接）",
    ]
    if digest:
        lines.append(f"- 最近摘要：{digest}")
    if hook:
        lines.append(f"- 上章结尾钩子：{hook}")
    if not digest and not hook:
        lines.append("- （暂无交付记录——新项目从开弧开始）")
    lines += ["", "## 四、未回收伏笔"]
    lines += [f"- {r['title']}（第{r['planted_chapter']}章埋）"
              for r in ff] or ["- （账本无未回收伏笔）"]
    changed = _blueprint_changed(d)
    lines += ["", "## 五、待办提醒"]
    if changed:
        lines.append(f"- ⚠ 图纸变更未确认：{'、'.join(changed)}"
                     "（建议回扫+再确认）")
    for a in arcs:
        if not _arcnet_archived(d, a["no"]) and max_ch >= a["end"]:
            lines.append(f"- 弧{a['no']}《{a['title']}》已写完但漂移网未归档"
                         "（弧末治理未闭环）")
    if lines[-1] == "## 五、待办提醒":
        lines.append("- （无——弧弧有网，图纸无变更）")
    return {"markdown": NL.join(lines) + NL}


class HandoverSaveIn(BaseModel):
    project: str
    markdown: str


@router.post("/longform/handover/save")
def handover_save(body: HandoverSaveIn):
    """交接草稿落盘项目根：00_交接汇总-草稿-*.md（永不覆盖，撞名加序号）——
    用户手改的 00_交接汇总.md 永远不被机器碰。"""
    if not (body.markdown or "").strip():
        raise HTTPException(400, "草稿为空，拒绝落盘")
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    f, k = d / f"00_交接汇总-草稿-{stamp}.md", 2
    while f.exists():
        f = d / f"00_交接汇总-草稿-{stamp}-{k}.md"
        k += 1
    f.write_text(body.markdown.strip() + chr(10),
                 encoding="utf-8", newline=chr(10))
    return {"ok": True, "file": f.name,
            "cli": "网页落盘 = 草稿存项目根 00_交接汇总-草稿-*.md（不覆盖手写版）"}


# ---- 量产连跑（v0.12）：章计划表规划器（0 token）——循环在前端（J1）----
# 设计：工作台v0.12-量产连跑-设计设想.md §二-§六。每站复用既有执法：
# 简报冻结→单发链（outline/beats/generate）→门禁→交付→digest 校验→
# 低风险合并→预算三态。红即停（§五），无自动修订，批量不跨弧末。

@router.get("/longform/batch/plan")
def longform_batch_plan(project: str, start: int, count: int = 5):
    """章计划表（§三 简报规划器）：M 份 G0 简报自动产出（钩子链/关键词派生
    J6/关键章自动标记 J4）+ 预检数据（成本预估/路由检查/弧边界）。规划 0 token；
    审批=冻结简报，前端循环照表执行（J1），探针章与关键章自动摘出。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    if not (1 <= count <= 10):
        raise HTTPException(400, "批量 1–10 章（J2 硬顶：漂移以章为单位累积）")
    outline = d / "outline.md"
    otext = outline.read_text(encoding="utf-8") if outline.is_file() else ""
    arcs = _parse_arcs(otext)
    arc = next((a for a in arcs if a["start"] <= start <= a["end"]), None)
    if not arc:
        raise HTTPException(400, f"第 {start} 章不在任何弧内——先开弧（批量不跨弧末）")
    ms = d / "manuscript"
    max_ch = 0
    if ms.is_dir():
        for f in ms.glob("*.md"):
            if m := re.match(r"(\d+)", f.stem):
                max_ch = max(max_ch, int(m.group(1)))
    if start <= max_ch:
        raise HTTPException(400, f"起始章 {start} 已交付或已存在（现役 {max_ch}）"
                                 "——连跑只吃未写的新章")
    end = min(start + count - 1, arc["end"])
    effective = end - start + 1
    hero_state, ff_text, ff_titles = "", "", []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from store import Store  # noqa: E402
        store = Store(d)
        try:
            recap = store.recap(3)
        finally:
            store.close()
        recent = recap.get("recent") or []
        if recent:
            latest = max(recent, key=lambda r: int(r.get("chapter") or 0))
            hero_state = str(latest.get("digest", ""))[:200]
        ff = recap.get("open_foreshadow") or []
        ff_titles = [r["title"] for r in ff]
        ff_text = "；".join(f"{r['title']}（第{r['planted_chapter']}章埋，待回收）"
                            for r in ff)[:300]
    except Exception:  # noqa: BLE001
        pass
    core_names = []
    nj = d / "bible" / "names.json"
    if nj.is_file():
        try:
            core_names = [str(x.get("name", "")).strip()
                          for x in json.loads(nj.read_text(encoding="utf-8")
                                              ).get("names", [])
                          if isinstance(x, dict) and str(x.get("name", "")).strip()]
        except (OSError, ValueError):
            pass
    anchor_terms = [t.strip() for t in re.split("[、，,]", arc["anchors"])
                    if t.strip()]
    rows, prev_hook = [], _prev_ending_hook(d, start)
    for i, n in enumerate(range(start, end + 1)):
        off = n - arc["start"] + 1
        total = arc["end"] - arc["start"] + 1
        brief = {"anchor": arc["anchors"], "hero_state": hero_state,
                 "arc_pos": (f"弧{arc['no']}《{arc['title']}》第 {off}/{total} 章"
                             f"（全弧第 {arc['start']}-{arc['end']} 章）"),
                 "foreshadow": ff_text, "quirks": "", "ending_hook": "",
                 "bridge": prev_hook if i == 0 else "",
                 "chapter_type": "mass"}
        key_reason = ""
        if n == arc["end"]:
            brief["chapter_type"], key_reason = "key", "弧末章"
        elif ff_titles:
            brief["chapter_type"], key_reason = "key", "有未回收伏笔"
        rows.append({"chapter_no": n, "brief": brief,
                     "title": f"第{n}章",
                     "keywords": (core_names[:6] + anchor_terms[:4]),
                     "key_reason": key_reason,
                     "probe": (n - arc["start"]) < 2})
    costs = []
    costf = d / "style" / "cost.jsonl"
    if costf.is_file():
        for line in costf.read_text(encoding="utf-8").splitlines():
            if "web-create" not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = int(r.get("session_tokens") or r.get("tokens") or 0)
            if t:
                costs.append(t)
    median = sorted(costs)[len(costs) // 2] if costs else 0
    return {"arc": arc, "start": start, "end": end,
            "clamped": effective < count, "rows": rows,
            "estimate_tokens": median * effective, "samples": len(costs),
            "write_mass": bool(cfg.get("routing", {}).get("write_mass")),
            "probe_rows": sum(1 for r in rows if r["probe"]),
            "max_ch": max_ch}


class BatchReportIn(BaseModel):
    project: str
    pack: str
    start: int
    end: int


@router.post("/longform/batch/report")
def longform_batch_report(body: BatchReportIn):
    """批后趋势报告（设想 §七 批后治理）：fp_check --per-file 对本批各章跑
    指纹偏差曲线，报告归档 整合/趋势报告/（永不覆盖，撞名加序号）。advisory。"""
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    ms = d / "manuscript"
    files = [str(f) for f in sorted(ms.glob("*.md"))
             if (n := _chapter_num_local(f.stem))
             and body.start <= n <= body.end] if ms.is_dir() else []
    if not files:
        raise HTTPException(404, f"区间 {body.start}-{body.end} 无章节文件")
    r = _run_gate("fp_check.py", [str(_pack_dir(body.pack, d)), *files,
                                  "--per-file"])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = d / "整合" / "趋势报告"
    out_dir.mkdir(parents=True, exist_ok=True)
    f, k = out_dir / f"连跑趋势-{body.start:03d}-{body.end:03d}-{stamp}.md", 2
    while f.exists():
        f = out_dir / f"连跑趋势-{body.start:03d}-{body.end:03d}-{stamp}-{k}.md"
        k += 1
    head = (f"<!-- 批后趋势 第{body.start}-{body.end}章｜fp_check --per-file｜"
            f"exit={r['exit_code']}｜{stamp} -->" + chr(10))
    f.write_text(head + (r["report"] or "").strip() + chr(10),
                 encoding="utf-8", newline=chr(10))
    return {"exit_code": r["exit_code"], "report": r["report"],
            "file": str(f.relative_to(d)),
            "cli": "网页趋势 = fp_check.py <包> <各章.md> --per-file"}


class ArcCreateIn(BaseModel):
    project: str
    title: str
    start: int
    end: int
    anchors: str
    tension: str
    hooks: str
    per_chapter: int = 3500
    numbers: list[dict] = []  # [{name, value}]——开弧即定账


@router.post("/longform/arc_create")
def longform_arc_create(body: ArcCreateIn):
    """开新弧：弧块追加进 outline.md（卷纲），硬数字表追加对应节。
    四字段+数字账一次定齐——这是硬数字表防再犯机制的入口。"""
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "弧名不能为空")
    if not (1 <= body.start <= body.end):
        raise HTTPException(400, "章号区间非法（需 1 ≤ 起 ≤ 止）")
    if body.end - body.start + 1 > 60:
        raise HTTPException(400, "单弧超过 60 章——请拆弧（防线：弧是审查与预算单位）")
    if not (body.anchors or "").strip() or not (body.tension or "").strip()             or not (body.hooks or "").strip():
        raise HTTPException(400, "四字段缺一不可（原作锚点/张力设计/勾稽点）")
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    if not _is_longform(d):
        raise HTTPException(400, "该项目不是长篇模式")
    outline = d / "outline.md"
    text = outline.read_text(encoding="utf-8") if outline.is_file()         else TPL_OUTLINE_LONGFORM
    arcs = _parse_arcs(text)
    no = (arcs[-1]["no"] + 1) if arcs else 1
    NL = chr(10)
    block = (f"{NL}### 【弧{no}·{title}】（第{body.start}-{body.end}章）{NL}"
             f"- 原作锚点：{body.anchors.strip()}{NL}"
             f"- 张力设计：{body.tension.strip()}{NL}"
             f"- 勾稽点：{body.hooks.strip()}{NL}"
             f"- 章数字数：{body.end - body.start + 1} 章 × 约 {body.per_chapter} 字{NL}")
    outline.write_text(text.rstrip() + NL + block,
                       encoding="utf-8", newline=NL)
    # 硬数字表追加节
    nums = d / "bible" / "硬数字表.md"
    sec = [f"{NL}## 弧{no}《{title}》（第{body.start}-{body.end}章）{NL}",
           "| 账目 | 口径 |", "|---|---|"]
    for item in body.numbers:
        name = str(item.get("name", "")).strip()[:40]
        value = str(item.get("value", "")).strip()[:120]
        if name:
            sec.append(f"| {name} | {value} |")
    if len(sec) == 3:
        sec.append("| （本弧无预设硬数字——正文出现关键数字时回填本表） | — |")
    with nums.open("a", encoding="utf-8", newline=NL) as f:
        f.write(NL.join(sec) + NL)
    _blueprint_baseline(d, refresh=True)  # 开弧=人工图纸动作：基线同步
    return {"ok": True, "arc_no": no, "outline_block": block.strip(),
            "numbers_rows": len(sec) - 3,
            "cli": "网页开弧 = 在 outline.md 追加弧块 + bible/硬数字表.md 追加节"}


CANONPACKS = ROOT / "canonpacks"


def _pin_canon(project_dir: Path, canon_pack: str) -> str:
    """canon 包钉扎进项目（terms 快照 + card）——create 与档案页共用。"""
    csrc = CANONPACKS / canon_pack
    if not (csrc / "pack.json").is_file():
        raise HTTPException(400, f"canon 包不存在：{canon_pack}")
    cdst = project_dir / "canon"
    cdst.mkdir(exist_ok=True)
    terms = json.loads((csrc / "terms.json").read_text(encoding="utf-8"))
    terms["_pinned_from"] = canon_pack
    (cdst / "canon-terms.json").write_text(
        json.dumps(terms, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    if (csrc / "card.md").is_file():
        (cdst / "pinned-canon.md").write_text(
            (csrc / "card.md").read_text(encoding="utf-8"),
            encoding="utf-8", newline="\n")
    return f"已钉扎 canon：{canon_pack}（canon/canon-terms.json）"


@router.get("/canon_packs")
def canon_packs():
    out = []
    if CANONPACKS.is_dir():
        for d in sorted(CANONPACKS.iterdir()):
            if d.is_dir() and (d / "pack.json").is_file():
                out.append(d.name)
    return {"packs": out}


class PinCanonIn(BaseModel):
    project: str
    canon_pack: str


@router.post("/pin_canon")
def pin_canon(body: PinCanonIn):
    cfg = appstate.load_config()
    d = _project_dir(cfg, body.project)
    return {"ok": True, "note": _pin_canon(d, body.canon_pack)}
