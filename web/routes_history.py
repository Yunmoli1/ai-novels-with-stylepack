# -*- coding: utf-8 -*-
"""routes_history：历史章节与成本浏览（v0.9.5）。

sessions/ 是每章交付的完整可复判快照——此前只能翻 JSON 文件；
本模块把它变成网页：章节列表（门禁/成本概览）+ 详情（立意/拍子/报告）
+ cost.jsonl 的每章消耗条形图。纯读端点，CLI 等价 = 直接读文件。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import appstate
import routes_create as _rc

router = APIRouter(prefix="/app/api/history")


def _project(cfg: dict, name: str) -> Path:
    return _rc._project_dir(cfg, name)


@router.get("/sessions")
def sessions_list(project: str):
    cfg = appstate.load_config()
    sd = _project(cfg, project) / "sessions"
    out = []
    if sd.is_dir():
        for f in sorted(sd.glob("*.json"), reverse=True):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            checks = d.get("checks", {})
            fp_ok = (checks.get("fp_check") or {}).get("exit_code") == 0
            aic = checks.get("ai_cliche") or {}
            aic_ok = (aic.get("exit_code") == 0) if aic else None
            ending = checks.get("ending") or {}
            totals = d.get("session_totals") or {}
            out.append({
                "file": f.name, "ts": d.get("ts", ""),
                "chapter_no": d.get("chapter_no"), "title": d.get("title", ""),
                "chars": len(d.get("text", "")),
                "model": (d.get("usage") or {}).get("model", ""),
                "session_tokens": totals.get("tokens"),
                "session_calls": totals.get("calls"),
                "fp_ok": fp_ok, "aic_ok": aic_ok,
                "ending": (ending or {}).get("violation"),
                "pack": d.get("pack", "")})
    return {"sessions": out}


@router.get("/session_detail")
def session_detail(project: str, file: str):
    cfg = appstate.load_config()
    sd = _project(cfg, project) / "sessions"
    p = (sd / file).resolve()
    if not p.is_file() or p.parent != sd.resolve():
        raise HTTPException(404, "会话文件不存在")
    d = json.loads(p.read_text(encoding="utf-8"))
    text = d.get("text", "")
    d["text_preview"] = text[:1200] + ("…" if len(text) > 1200 else "")
    d.pop("text", None)  # 全文不搬（预览够判读；全文看 manuscript）
    d.pop("assembly", None)
    return d


@router.get("/costs")
def costs(project: str):
    """cost.jsonl 全量（date/skill/tokens/session_tokens/chars/note）——
    图表与累计口径的数据源。"""
    cfg = appstate.load_config()
    c = _project(cfg, project) / "style" / "cost.jsonl"
    rows = []
    if c.is_file():
        for line in c.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return {"rows": rows,
            "total_tokens": sum(int(r.get("session_tokens")
                                     or r.get("tokens") or 0) for r in rows)}


@router.get("/board")
def board(project: str):
    """长篇看板（v0.11.2 C-5）：弧聚合视图——弧预算占用进度条 + 每章拆账。
    数据源与 /costs 同源（sessions 记录 + budget.json），不另立账本。"""
    cfg = appstate.load_config()
    d = _project(cfg, project)
    if not _rc._is_longform(d):
        return {"longform": False}
    outline = d / "outline.md"
    arcs = _rc._parse_arcs(outline.read_text(encoding="utf-8")
                           if outline.is_file() else "")
    b = _rc._budget_of(d) or {}
    arc_budget = int(b.get("arc_budget") or 0)
    halt_mult = float(b.get("halt_multiplier") or 2.0)
    per: dict[int, dict] = {}
    sd = d / "sessions"
    if sd.is_dir():
        for f in sd.glob("*.json"):
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            n = int(r.get("chapter_no") or 0)
            if not n:
                continue
            t = int((r.get("session_totals") or {}).get("tokens") or 0)
            if not t:
                u = r.get("usage") or {}
                t = int(u.get("prompt_tokens", 0)) + int(u.get("completion_tokens", 0))
            cur = per.setdefault(n, {"tokens": 0, "title": r.get("title", "")})
            cur["tokens"] += t
    out = []
    for a in arcs:
        chs, spend = [], 0
        for n in range(a["start"], a["end"] + 1):
            if n in per:
                spend += per[n]["tokens"]
                chs.append({"chapter_no": n, **per[n]})
        state = "none"
        if arc_budget:
            state = ("halt" if spend >= int(arc_budget * halt_mult)
                     else "warning" if spend >= arc_budget else "normal")
        out.append({"no": a["no"], "title": a["title"], "start": a["start"],
                    "end": a["end"], "spend": spend, "arc_budget": arc_budget,
                    "state": state,
                    "chapters": sorted(chs, key=lambda c: c["chapter_no"])})
    return {"longform": True, "arcs": out,
            "chapter_budget": int(b.get("chapter_budget") or 0),
            "arc_budget": arc_budget}


class ChapterOpIn(BaseModel):
    project: str
    file: str
    new_title: str = ""


@router.post("/chapter_rename")
def chapter_rename(body: ChapterOpIn):
    """章节改名（manuscript/NNN-题.md 重命名，章号保留）。"""
    cfg = appstate.load_config()
    ms = _project(cfg, body.project) / "manuscript"
    p = (ms / body.file).resolve()
    if not p.is_file() or p.parent != ms.resolve():
        raise HTTPException(404, "章节文件不存在")
    m = re.match(r"(\d+)", p.stem)
    if not m:
        raise HTTPException(400, "文件名无章号前缀")
    title = (body.new_title or "").strip()
    for ch in '\/:*?"<>|':
        title = title.replace(ch, "_")
    title = title.strip(". ") or "未命名"
    target = ms / f"{int(m.group(1)):03d}-{title}.md"
    if target == p:
        return {"ok": True, "file": target.name}
    if target.exists():
        raise HTTPException(409, f"目标文件已存在：{target.name}")
    p.rename(target)
    return {"ok": True, "file": target.name}


@router.post("/chapter_delete")
def chapter_delete(body: ChapterOpIn):
    """删除章节（confirm 在前端；文件移入 manuscript/.trash/ 可恢复）。"""
    cfg = appstate.load_config()
    ms = _project(cfg, body.project) / "manuscript"
    p = (ms / body.file).resolve()
    if not p.is_file() or p.parent != ms.resolve():
        raise HTTPException(404, "章节文件不存在")
    trash = ms / ".trash"
    trash.mkdir(exist_ok=True)
    p.rename(trash / (time.strftime("%Y%m%d-%H%M%S-") + p.name))
    return {"ok": True}
