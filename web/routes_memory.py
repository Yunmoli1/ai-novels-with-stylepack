# -*- coding: utf-8 -*-
"""routes_memory：记忆层接入创作环（v0.9.0 阶段 A）。

复用 server/store.py 的 Store（MCP 同一实现——网页与 agent 宿主共享记忆，
CLI 等价 = 现有 MCP 工具 story.propose_delta/merge_delta/recap/sync）。

风险纪律（隔离区协议，照搬 style-apply 技能）：
- 风险由脚本 _auto_risk 判定（core 实体=high，minor/new 视字段），不由模型自评；
- 中/高风险合并必须 force=true（用户显式确认），低风险直接合并留痕；
- 语义级矛盾由脚本校验与人工确认兜底。
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import appstate
import creation
import model_client
import routes_create as _rc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server") not in sys.path:
    sys.path.insert(0, str(ROOT / "server"))
from store import Store  # noqa: E402

router = APIRouter(prefix="/app/api/memory")


def _store(cfg: dict, project: str) -> Store:
    pdir = _rc._project_dir(cfg, project)
    return Store(pdir)


class DeltaIn(BaseModel):
    project: str
    chapter_no: int
    title: str
    text: str
    beats: list[dict] = []
    session_id: str = ""


@router.post("/delta")
def memory_delta(body: DeltaIn):
    """交付后登记：judge 路由从正文+拍子提取 digest/changes/foreshadow（一次
    ~2k tokens），经 Store.propose_delta 入隔离区。风险由脚本自动分级。"""
    cfg = appstate.load_config()
    store = _store(cfg, body.project)
    store.sync()  # bible → 索引保鲜（零成本，本地 SQLite）
    lang = _rc._project_language(cfg, body.project)  # 项目默认包语言（v0.13.17）
    prompt = creation.memory_digest_prompt(body.chapter_no, body.title,
                                           body.beats, body.text, lang=lang)
    sid = body.session_id or f"mem-{body.chapter_no:03d}"
    result = _rc._do_model(cfg, "judge", sid, prompt, 1400, True, lang=lang)
    data = result["json"]
    payload = {"chapter": f"{body.chapter_no:03d}",
               "digest": str(data.get("digest") or "")[:200]}
    changes = []
    for ch in data.get("changes") or []:
        if isinstance(ch, dict) and str(ch.get("entity", "")).strip():
            changes.append({"entity": str(ch["entity"]).strip()[:40],
                            "field": str(ch.get("field", "state"))[:30],
                            "value": str(ch.get("value", ""))[:200],
                            "note": str(ch.get("note", ""))[:120]})
    for f in data.get("foreshadow") or []:
        title = str(f if isinstance(f, str) else f.get("title", "")).strip()
        if title:
            changes.append({"entity": "伏笔", "field": "foreshadow",
                            "value": title[:120], "note": "本章埋设"})
    payload["changes"] = changes
    prop = store.propose_delta(payload)
    if not prop.get("ok"):
        raise HTTPException(502, f"隔离区写入失败：{prop.get('error')}")
    return {"ok": True, "proposed": prop["proposed"],
            "digest": payload["digest"], "usage": result,
            "hint": "低风险可直合并；中/高风险需逐条确认（force）"}


@router.get("/pending")
def memory_pending(project: str):
    """隔离区清单（按风险分组）；含 pending 老化提醒（recap.pending_aging 同源）。"""
    cfg = appstate.load_config()
    store = _store(cfg, project)
    c = store.conn()
    rows = [dict(r) for r in c.execute(
        "SELECT id, chapter, entity, field, value, risk, note, ts, status "
        "FROM pending_deltas WHERE status='pending' ORDER BY id").fetchall()]
    aging = store_pending_aging_safe(store)
    store.close()
    groups = {"high": [], "medium": [], "low": []}
    for r in rows:
        groups.setdefault(r["risk"], []).append(r)
    return {"groups": groups, "total": len(rows), "aging": aging}


def store_pending_aging_safe(store: Store) -> dict:
    try:
        return store.pending_aging()
    except Exception:  # noqa: BLE001 —— 老化提醒是 advisory，不挡接口
        return {}


class MergeIn(BaseModel):
    project: str
    ids: list[int] = []
    force: bool = False


@router.post("/merge")
def memory_merge(body: MergeIn):
    """合并隔离区：低风险直接；中/高风险必须 force=true（前端逐条/批量确认）。
    digest 合入 chapter_digests；field=foreshadow 入伏笔账本。"""
    cfg = appstate.load_config()
    store = _store(cfg, body.project)
    r = store.merge_delta(body.ids or None, body.force)
    store.close()
    return r


class SyncIn(BaseModel):
    project: str


@router.post("/sync")
def memory_sync(body: SyncIn):
    cfg = appstate.load_config()
    store = _store(cfg, body.project)
    r = store.sync()
    store.close()
    return r


@router.get("/recap")
def memory_recap(project: str, n: int = 3):
    """前情提要（最近 n 章摘要+未回收伏笔+pending 计数）——装配与面板共用。"""
    cfg = appstate.load_config()
    store = _store(cfg, project)
    try:
        data = store.recap(n)
    finally:
        store.close()
    return data
