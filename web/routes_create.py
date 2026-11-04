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


def _pack_dir(pack: str) -> Path:
    d = (STYLEPACKS / pack).resolve()
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


def _record_usage(session_id: str, usage: dict) -> None:
    s = _sessions.setdefault(session_id, {"tokens": 0, "calls": 0})
    s["tokens"] += usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    s["calls"] += 1


def _session_totals(session_id: str) -> dict:
    """本章会话累计（所有调用含重试/门禁判官的真实消耗）。"""
    s = _sessions.get(session_id or "", {})
    return {"tokens": int(s.get("tokens", 0)), "calls": int(s.get("calls", 0))}


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
    cfg["providers"] = merged
    for p in cfg["providers"]:
        if not isinstance(p.get("models"), list):
            p["models"] = []
    cfg["routing"] = body.routing or {}
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
    result = assemble_mod.assemble(
        _project_dir(cfg, body.project), _pack_dir(body.pack),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000))
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
    pack_dir = _pack_dir(body.pack)
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


def _session_id(body) -> str:
    return body.session_id or uuid.uuid4().hex[:12]


def _do_model(cfg: dict, route: str, session_id: str, prompt: str,
              max_tokens: int, json_mode: bool):
    base, key, model = _resolve_model(cfg, route)
    _guard(cfg, session_id, int(max_tokens * 1.5))
    try:
        result = model_client.chat(base, key, model,
                                   [{"role": "system", "content": creation.SYSTEM},
                                    {"role": "user", "content": prompt}],
                                   temperature=cfg.get("temperature", 0.8),
                                   max_tokens=max_tokens)
    except ValueError as exc:  # 已 sanitize，可直接示人
        raise HTTPException(502, str(exc))
    _record_usage(session_id, result)
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
    assembly = assemble_mod.assemble(
        _project_dir(cfg, body.project), _pack_dir(body.pack),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000))
    prompt = creation.outline_prompt(body.chapter_no, body.title, body.keywords,
                                     assembly["kept_texts"], body.user_notes)
    result = _do_model(cfg, "write", sid, prompt, 2200, True)
    return {"session_id": sid, "options": result["json"].get("options", []),
            "recommended": result["json"].get("recommended", 0),
            "usage": result, "assembly": {k: v for k, v in assembly.items()
                                          if k != "kept_texts"}}


class BeatsIn(OutlineIn):
    chosen: dict = {}


@router.post("/beats")
def do_beats(body: BeatsIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    assembly = assemble_mod.assemble(
        _project_dir(cfg, body.project), _pack_dir(body.pack),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000))
    canon_note = ("二创项目：原作锚点必须落到 canon-terms.json 的 must 术语与人物"
                  if (_project_dir(cfg, body.project) / "canon" / "canon-terms.json").is_file()
                  else "")
    prompt = creation.beats_prompt(body.chapter_no, body.title, body.chosen,
                                   assembly["kept_texts"], canon_note,
                                   _clean_target_chars(body.target_chars))
    result = _do_model(cfg, "write", sid, prompt, 2400, True)
    return {"session_id": sid, **result["json"], "usage": result}


class RerollIn(BeatsIn):
    beats: list[dict] = []
    index: int = 1


@router.post("/reroll_beat")
def do_reroll(body: RerollIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    assembly = assemble_mod.assemble(
        _project_dir(cfg, body.project), _pack_dir(body.pack),
        body.chapter_no, body.keywords, cfg.get("context_budget_tokens", 24000))
    prompt = creation.reroll_beat_prompt(body.chapter_no, body.title, body.chosen,
                                         body.beats, body.index,
                                         assembly["kept_texts"],
                                         _clean_target_chars(body.target_chars))
    result = _do_model(cfg, "write", sid, prompt, 600, True)
    return {"session_id": sid, "beat": result["json"], "usage": result}


class GenerateIn(BeatsIn):
    beats: list[dict] = []
    tone_note: str = "不指定"
    canon_anchor: str = "无"
    n_drafts: int = 1
    session_id: str = ""


def _prep_generate(cfg: dict, body: GenerateIn) -> dict:
    """装配 + 提示词 + 预算：/generate 与 /generate_stream 共用（所见即所发）。"""
    project_dir = _project_dir(cfg, body.project)
    pack_dir = _pack_dir(body.pack)
    assembly = assemble_mod.assemble(
        project_dir, pack_dir, body.chapter_no, body.keywords,
        cfg.get("context_budget_tokens", 24000))
    target = _clean_target_chars(body.target_chars)
    prompt = creation.prose_prompt(body.chapter_no, body.title, body.chosen,
                                   body.beats, body.tone_note, body.canon_anchor,
                                   assembly["kept_texts"],
                                   target or cfg.get("prose_max_tokens", 3500) * 2 // 3)
    return {"pack_dir": pack_dir, "assembly": assembly, "prompt": prompt,
            "budget": _prose_budget(cfg, target), "target": target}


@router.post("/generate")
def do_generate(body: GenerateIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    prep = _prep_generate(cfg, body)
    pack_dir, assembly, prompt, budget = (prep["pack_dir"], prep["assembly"],
                                          prep["prompt"], prep["budget"])
    drafts = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(max(1, min(3, body.n_drafts))):
            result = _do_model(cfg, "write", sid, prompt, budget, False)
            draft_path = Path(td) / f"d{i}.txt"
            draft_path.write_text(result["text"], encoding="utf-8", newline="\n")
            fp = _run_gate("fp_check.py", [str(pack_dir), str(draft_path)])
            borrow = _run_gate("borrow_check.py", [str(draft_path),
                                                   "--pack", str(pack_dir)])
            aic = _run_gate("ai_cliche_check.py", [str(draft_path),
                                                   "--pack", str(pack_dir)])
            drafts.append({"text": result["text"], "usage": result,
                           "fp_check": fp, "borrow_check": borrow,
                           "ai_cliche": aic})
    return {"session_id": sid, "drafts": drafts,
            "assembly_preview": assembly["items"],
            "assembly_tokens": assembly["total_est_tokens"]}


# ---- 流式生成（v0.6.4）：SSE 事件流，生成现场侧栏逐字渲染 ----

def _sse(type_: str, **fields) -> str:
    return ("event: " + type_ + "\ndata: "
            + json.dumps({"type": type_, **fields}, ensure_ascii=False) + "\n\n")


def _stream_one_draft(cfg: dict, sid: str, prompt: str, budget: int,
                      pack_dir: Path, index: int, done_event: str = "draft_done",
                      extra: dict | None = None):
    """产出一个稿的事件序列：流式优先；空稿/流式不可用回退非流加倍链（v0.6.2）。
    结尾必发 done_event（成功）或 error（失败）——前端按此收口。"""
    base, key, model = _resolve_model(cfg, "write")
    messages = [{"role": "system", "content": creation.SYSTEM},
                {"role": "user", "content": prompt}]
    _guard(cfg, sid, int(budget * 1.5))
    parts: list[str] = []
    usage: dict = {}
    finish: str | None = None
    try:
        for ev in model_client.chat_stream(base, key, model, messages,
                                           temperature=cfg.get("temperature", 0.8),
                                           max_tokens=budget):
            if ev["type"] == "delta":
                parts.append(ev["text"])
                yield _sse("delta", index=index, text=ev["text"],
                           chars=sum(len(p) for p in parts))
            elif ev["type"] == "reasoning":
                yield _sse("reasoning", index=index)
            else:
                usage = ev["usage"]
                finish = ev.get("finish_reason")
    except ValueError as exc:
        yield _sse("status", message=f"流式不可用（{_short(exc)}），回退整段生成……")
    text = "".join(parts)
    if not text.strip() or finish == "length":  # 空稿或截断 → 加倍回退（v0.6.5）
        why = "输出被截断（finish=length）" if text.strip() else "流式返回空正文"
        yield _sse("status", message=f"{why}——加倍预算回退重试……")
        try:
            result = _do_model(cfg, "write", sid, prompt, budget * 2, False)
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
    _record_usage(sid, usage)
    yield _sse("status", index=index, message="门禁运行中（fp_check/borrow_check）……")
    with tempfile.TemporaryDirectory() as td:
        draft_path = Path(td) / f"stream{index}.txt"
        draft_path.write_text(text, encoding="utf-8", newline="\n")
        fp = _run_gate("fp_check.py", [str(pack_dir), str(draft_path)])
        borrow = _run_gate("borrow_check.py", [str(draft_path),
                                               "--pack", str(pack_dir)])
        aic = _run_gate("ai_cliche_check.py", [str(draft_path),
                                               "--pack", str(pack_dir)])
    yield _sse(done_event, index=index, text=text, usage=usage,
               fp_check=fp, borrow_check=borrow, ai_cliche=aic,
               **(extra or {}))


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
                   assembly_tokens=prep["assembly"]["total_est_tokens"])
        for i in range(max(1, min(3, body.n_drafts))):
            yield _sse("draft_start", index=i)
            yield from _stream_one_draft(cfg, sid, prep["prompt"], prep["budget"],
                                         prep["pack_dir"], i)
        yield _sse("all_done", assembly_tokens=prep["assembly"]["total_est_tokens"])

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


class ReviseIn(BaseModel):
    project: str
    pack: str
    chapter_no: int
    title: str
    keywords: list[str] = []
    chosen: dict = {}
    beats: list[dict] = []
    text: str
    reports: dict = {}   # {fp_check/borrow_check: {exit_code, report}, ending: {...}}
    revision: int = 0
    target_chars: int = 0
    session_id: str = ""


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
    pack_dir = _pack_dir(body.pack)
    assembly = assemble_mod.assemble(
        project_dir, pack_dir, body.chapter_no, body.keywords,
        cfg.get("context_budget_tokens", 24000))
    target = _clean_target_chars(body.target_chars) or len(body.text or "")
    prompt = creation.revise_prompt(body.chapter_no, body.title, body.beats,
                                    assembly["kept_texts"], body.text,
                                    _gate_reports_text(body.reports), target)
    return {"pack_dir": pack_dir, "prompt": prompt,
            # ×2：修订要整篇重写（输出≈原文），思考型模型的推理也吃同一预算——
            # 2500 字章在 ×1 下实测推理+正文 >14000 tokens 被截成 1099 字
            "budget": _prose_budget(cfg, target) * 2}


@router.post("/revise")
def do_revise(body: ReviseIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    prep = _prep_revise(cfg, body)
    result = _do_model(cfg, "write", sid, prep["prompt"], prep["budget"], False)
    with tempfile.TemporaryDirectory() as td:
        draft_path = Path(td) / "revised.txt"
        draft_path.write_text(result["text"], encoding="utf-8", newline="\n")
        fp = _run_gate("fp_check.py", [str(prep["pack_dir"]), str(draft_path)])
        borrow = _run_gate("borrow_check.py", [str(draft_path),
                                               "--pack", str(prep["pack_dir"])])
        aic = _run_gate("ai_cliche_check.py", [str(draft_path),
                                               "--pack", str(prep["pack_dir"])])
    return {"session_id": sid, "text": result["text"], "usage": result,
            "fp_check": fp, "borrow_check": borrow, "ai_cliche": aic,
            "revision": int(body.revision) + 1}


@router.post("/revise_stream")
def do_revise_stream(body: ReviseIn):
    cfg = appstate.load_config()
    sid = _session_id(body)
    prep = _prep_revise(cfg, body)

    def gen():
        yield _sse("session", session_id=sid)
        yield _sse("status", message="按报告修订生成中……")
        yield from _stream_one_draft(cfg, sid, prep["prompt"], prep["budget"],
                                     prep["pack_dir"], 0, done_event="revised_done",
                                     extra={"revision": int(body.revision) + 1})

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
                           cfg, len(body.text) or 2500) * 2), False)
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
            "fp_check": fp, "borrow_check": borrow, "ai_cliche": aic}


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
    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "tool": "web-create v0.11.0", "session_id": body.session_id,
        "project": body.project, "pack": body.pack,
        "chapter_no": body.chapter_no, "title": title,
        "keywords": body.keywords,
        "target_chars": _clean_target_chars(body.target_chars),
        "chosen": body.chosen, "beats": body.beats,
        "tone_note": body.tone_note, "canon_anchor": body.canon_anchor,
        "checks": body.checks, "usage": body.usage,
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
                         note=f"第{body.chapter_no}章《{title}》")
    return {"ok": True, "manuscript": str(target), "sessions_dir": str(sessions),
            "session_totals": totals}


# ---- 新建项目（v0.10.0：不开 agent 的用户从这里开始第一本书）----

class ProjectCreateIn(BaseModel):
    name: str
    mode: str = "light"            # light=现状 | longform=长篇连载（v0.11 骨架）
    pack: str | None = None        # 可选：风格包钉扎（export → style/pinned-pack.md）
    canon_pack: str | None = None  # 可选：canon 包钉扎（terms 快照 → canon/）


BIBLE_TEMPLATES = {
    "characters.md": "# 人物\n\n## 主角名\n一句话身份。性格：\n口头禅/说话习惯：\n与谁什么关系：\n",
    "world.md": "# 世界设定\n\n## 基本规则\n（力量体系/经济/地理，一段一条）\n",
    "names.json": '{"names": []}\n'
                  '# 每个人名：{"name": "主角名", "tier": "core", "aliases": []}\n'
                  "# tier=core 的实体块自动常驻装配（World Info）\n",
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
            pack_dir = _pack_dir(body.pack)
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


def _longform_skeleton(d: Path) -> list[str]:
    notes = []
    for path_obj, tpl in ((d / LONGFORM_MARKER, TPL_DEFENSE),
                          (d / "00_项目宪法.md", TPL_CONSTITUTION),
                          (d / "bible" / "硬数字表.md", TPL_NUMBERS),
                          (d / "outline.md", TPL_OUTLINE_LONGFORM)):
        path_obj.write_text(tpl, encoding="utf-8", newline="\n")
    notes.append("长篇骨架：00_写作防线.md（G0-G4 闸门模板）+ 00_项目宪法.md（条款待填）"
                 " + bible/硬数字表.md + 结构化卷纲")
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
