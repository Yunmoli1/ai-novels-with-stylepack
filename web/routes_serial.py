# -*- coding: utf-8 -*-
"""routes_serial：连载管理台的文件树与系统级动作（v0.13.0 阶段 D 落地）。

红线（设想 §五）：树只读 + 复用既有执法动作（改名/删除走 routes_history）
+ 系统级逃生门（资源管理器）；E 档不做清单（任意写/树内编辑/删账本）。
所有 path 参数强制 traversal guard（resolve + parent 校验，同 session_detail）。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import appstate
import routes_create as _rc
import splib

router = APIRouter(prefix="/app/api/serial")

# 运行态产物（灰标注 + 来源说明）：文件协议可视化
SOURCE = {
    "manuscript": "交付落盘", "bible": "规范层档案", "style/cost.jsonl": "成本账本",
    "style/budget.json": "预算层", "style/blueprint.json": "图纸基线",
    "整合": "弧末归档", "sessions": "交付快照（不入库）",
    "slots": "方案槽（不入库）", "canon": "canon 钉扎",
    "00_写作防线.md": "执法手册", "00_项目宪法.md": "规范层",
    "outline.md": "卷纲/弧结构",
}
IGNORED = {"sessions", "slots", "__pycache__"}
PREVIEW_CHARS = 20000


def _proj(cfg: dict, project: str) -> Path:
    return _rc._project_dir(cfg, project)


def _safe(d: Path, sub: str) -> Path:
    """项目内路径守卫：resolve 后必须仍在项目内（防 ../ 逃逸）。"""
    p = (d / sub).resolve()
    if d.resolve() not in p.parents and p != d.resolve():
        raise HTTPException(400, "路径越界（traversal 已拦截）")
    return p


def _meta(p: Path, d: Path) -> dict:
    rel = p.relative_to(d).as_posix()
    kind = ""
    top = rel.split("/")[0]
    if rel in SOURCE:
        kind = SOURCE[rel]
    elif top in SOURCE:
        kind = SOURCE[top]
    ignored = top in IGNORED or p.name.startswith(".")
    try:
        stat = p.stat()
        size, mtime = stat.st_size, int(stat.st_mtime)
    except OSError:
        size, mtime = 0, 0
    return {"name": p.name, "rel": rel, "dir": p.is_dir(), "size": size,
            "mtime": mtime, "ignored": ignored, "source": kind}


@router.get("/tree")
def tree(project: str, sub: str = ""):
    """项目目录树（单层）：name/rel/size/mtime/灰标/来源标注。"""
    cfg = appstate.load_config()
    d = _proj(cfg, project)
    p = _safe(d, sub)
    if not p.is_dir():
        raise HTTPException(404, f"目录不存在：{sub}")
    entries = sorted((_meta(x, d) for x in p.iterdir()),
                     key=lambda x: (not x["dir"], x["name"].lower()))
    return {"root": str(d), "sub": sub, "entries": entries}


@router.get("/file")
def file_preview(project: str, path: str):
    """文件预览（只读，截断 20k 字符；全文走下载/资源管理器）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, project)
    p = _safe(d, path)
    if not p.is_file():
        raise HTTPException(404, f"文件不存在：{path}")
    raw = p.read_bytes()
    binary = b"\x00" in raw[:4096]
    text = "" if binary else splib.read_text(p)[0]
    return {"path": p.relative_to(d).as_posix(), "size": len(raw),
            "binary": binary, "chars": len(text),
            "truncated": len(text) > PREVIEW_CHARS,
            "text": text[:PREVIEW_CHARS],
            "source": _meta(p, d)["source"]}


@router.get("/download")
def file_download(project: str, path: str):
    """单文件下载（浏览器另存——只读动作的取出通道）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, project)
    p = _safe(d, path)
    if not p.is_file():
        raise HTTPException(404, f"文件不存在：{path}")
    import urllib.parse
    fname = urllib.parse.quote(p.name)
    return Response(content=p.read_bytes(),
                    media_type="application/octet-stream",
                    headers={"Content-Disposition":
                             f"attachment; filename*=UTF-8''{fname}"})


def _open_folder(path: Path) -> None:
    """系统级打开文件夹（平台分发；测试可 patch 本函数）。"""
    if sys.platform == "win32":
        os_startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def os_startfile(path: Path) -> None:
    import os
    os.startfile(str(path))  # noqa: S606 —— Windows 专属，仅本地工作台


class OpenIn(BaseModel):
    project: str


@router.post("/open_folder")
def open_folder(body: OpenIn):
    """资源管理器逃生门（§五 D 档）：浏览器负责看懂，OS 负责搬动。"""
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    _open_folder(d)
    return {"ok": True, "path": str(d)}


# ---- 约束面板（v0.13.5）：把散在四个文件里的硬标准摆成一张表 ----
# 人物 = names.json(供给级/别名) × characters.md(状态/禁语)；世界观/人物块 =
# resident 标记（常驻供给，预算裁剪都不裁）；术语 = canon must/ban；
# 硬数字 = 硬数字表弧节。所有开关 = 写回原文件（文件协议不变，CLI/agent 同源）。
RESIDENT_MARK = "<!-- resident -->"
STATUS_PAT = re.compile(r"状态[:：]\s*(死亡|离场)[（(]第(\d+)章[）)]")
TABOO_PAT = re.compile(r"禁语[:：]\s*(\S.*)")


def _bible(d: Path, name: str) -> str:
    f = d / "bible" / name
    return splib.read_text(f)[0] if f.is_file() else ""


def _blocks(text: str) -> list[tuple[str, str]]:
    """## 块切分 → [(标题, 块体)]（只列 ## 块，H1 前导不算——面板语义）。"""
    if "## " not in text:
        return []
    parts = text.split("\n## ")
    out = []
    first = parts[0].strip()
    if first.startswith("## "):
        out.append((first.splitlines()[0].lstrip("# ").strip(), first))
    for part in parts[1:]:
        body = "## " + part
        out.append((body.splitlines()[0].lstrip("# ").strip(), body))
    return out


def _load_names(d: Path) -> tuple[list[dict], bool]:
    """→ (people, ok)。names.json 含注释/坏 JSON = 模板态，只读不写。"""
    f = d / "bible" / "names.json"
    if not f.is_file():
        return [], True
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], False
    people = data.get("names", []) if isinstance(data, dict) else data
    return ([p for p in people if isinstance(p, dict)], True)


def _write_names(d: Path, people: list[dict]) -> None:
    f = d / "bible" / "names.json"
    f.write_text(json.dumps({"names": people}, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")


def _num_sections(d: Path) -> list[dict]:
    f = d / "bible" / "硬数字表.md"
    if not f.is_file():
        return []
    text = splib.read_text(f)[0]
    secs = list(re.finditer(r"^## 弧(\d+)《(.+?)》（第(\d+)-(\d+)章）", text, re.M))
    out = []
    for i, m in enumerate(secs):
        end = secs[i + 1].start() if i + 1 < len(secs) else len(text)
        rows = [ln for ln in text[m.end():end].splitlines()
                if ln.strip().startswith("|") and not ln.strip().startswith("|--")
                and "账目" not in ln]
        out.append({"no": int(m.group(1)), "title": m.group(2),
                    "start": int(m.group(3)), "end": int(m.group(4)),
                    "rows": len(rows)})
    return out


@router.get("/constraints")
def constraints_view(project: str):
    """约束面板数据：硬标准一览（人物供给级/状态/禁语、块常驻标记、术语、数字）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, project)
    people, ok = _load_names(d)
    chars_text = _bible(d, "characters.md")
    chars_blocks = _blocks(chars_text)
    status_of, taboo_of = {}, {}
    for title, body in chars_blocks:
        m = STATUS_PAT.search(body)
        if m:
            status_of[title] = {"state": m.group(1), "ch": int(m.group(2))}
        t = TABOO_PAT.search(body)
        if t:
            taboo_of[title] = [w.strip() for w in t.group(1).split("|") if w.strip()]
    people_view = []
    for p in people:
        nm = str(p.get("name", "")).strip()
        if nm:
            people_view.append({"name": nm, "aliases": p.get("aliases", []),
                                "tier": p.get("tier", "minor"),
                                "status": status_of.get(nm),
                                "taboo": taboo_of.get(nm, [])})
    registered = {p["name"] for p in people_view}
    ghost = [t for t, _ in chars_blocks if t not in registered]

    def block_view(text: str) -> list[dict]:
        return [{"title": t, "resident": RESIDENT_MARK in body,
                 "lines": len(body.splitlines())} for t, body in _blocks(text)]

    terms = None
    tf = d / "canon" / "canon-terms.json"
    if tf.is_file():
        try:
            t = splib.load_json(tf)
            terms = {"must": len(t.get("must", [])), "ban": len(t.get("ban", []))}
        except (OSError, ValueError):
            terms = None
    return {"names_ok": ok, "people": people_view, "ghost": ghost,
            "world_blocks": block_view(_bible(d, "world.md")),
            "char_blocks": block_view(chars_text),
            "terms": terms, "numbers": _num_sections(d)}


class TierIn(BaseModel):
    project: str
    name: str
    tier: str  # core=常驻（每章必进，预算裁剪都不裁）| minor=命中


@router.post("/constraints/tier")
def set_tier(body: TierIn):
    if body.tier not in ("core", "minor"):
        raise HTTPException(400, "tier 须为 core/minor")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    people, ok = _load_names(d)
    if not ok:
        raise HTTPException(400, "names.json 解析失败（含注释/坏 JSON）"
                                 "——请先在档案编辑器修正为纯 JSON")
    hit = next((p for p in people
                if str(p.get("name", "")).strip() == body.name), None)
    if hit:
        hit["tier"] = body.tier
    else:
        people.append({"name": body.name, "tier": body.tier, "aliases": []})
    _write_names(d, people)
    return {"ok": True, "name": body.name, "tier": body.tier}


class ResidentIn(BaseModel):
    project: str
    file: str  # world.md | characters.md
    title: str
    resident: bool


@router.post("/constraints/resident")
def set_resident(body: ResidentIn):
    if body.file not in ("world.md", "characters.md"):
        raise HTTPException(400, "file 须为 world.md/characters.md")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    f = d / "bible" / body.file
    if not f.is_file():
        raise HTTPException(404, f"{body.file} 不存在")
    text = splib.read_text(f)[0]
    parts = text.split("\n## ")
    hit = None
    for i, part in enumerate(parts):
        head = part if i == 0 else "## " + part
        if head.splitlines()[0].lstrip("# ").strip() == body.title:
            hit = i
            break
    if hit is None:
        raise HTTPException(404, f"块「{body.title}」不存在")
    body_text = parts[hit] if hit == 0 else "## " + parts[hit]
    if body.resident and RESIDENT_MARK not in body_text:
        body_text = body_text.replace("\n", f"\n{RESIDENT_MARK}\n", 1) \
            if "\n" in body_text else body_text + "\n" + RESIDENT_MARK
    elif not body.resident:
        body_text = body_text.replace(RESIDENT_MARK + "\n", "") \
            .replace(RESIDENT_MARK, "")
    parts[hit] = body_text[3:] if (hit and body_text.startswith("## ")) \
        else body_text
    f.write_text("\n## ".join(parts), encoding="utf-8", newline="\n")
    return {"ok": True, "file": body.file, "title": body.title,
            "resident": body.resident}


class StatusIn(BaseModel):
    project: str
    name: str
    state: str  # 在场 | 死亡 | 离场
    ch: int = 0


@router.post("/constraints/status")
def set_status(body: StatusIn):
    if body.state not in ("在场", "死亡", "离场"):
        raise HTTPException(400, "state 须为 在场/死亡/离场")
    if body.state != "在场" and body.ch < 1:
        raise HTTPException(400, "死亡/离场须给章号")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    f = d / "bible" / "characters.md"
    if not f.is_file():
        raise HTTPException(404, "characters.md 不存在")
    text = splib.read_text(f)[0]
    parts = text.split("\n## ")
    hit = None
    for i, part in enumerate(parts):
        head = part if i == 0 else "## " + part
        if head.splitlines()[0].lstrip("# ").strip() == body.name:
            hit = i
            break
    if hit is None:
        raise HTTPException(404, f"卡面「{body.name}」不存在")
    body_text = parts[hit] if hit == 0 else "## " + parts[hit]
    new_line = "状态：在场" if body.state == "在场" \
        else f"状态：{body.state}（第{body.ch}章）"
    lines = [ln for ln in body_text.splitlines()
             if not ln.strip().startswith("状态：")]
    title_i = next((k for k, ln in enumerate(lines) if ln.startswith("# ")), 0)
    lines.insert(title_i + 1, new_line)
    body_text = "\n".join(lines)
    parts[hit] = body_text[3:] if (hit and body_text.startswith("## ")) \
        else body_text
    f.write_text("\n## ".join(parts), encoding="utf-8", newline="\n")
    return {"ok": True, "name": body.name, "state": body.state, "ch": body.ch}
