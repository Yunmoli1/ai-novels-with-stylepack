# -*- coding: utf-8 -*-
"""routes_serial：连载管理台的文件树与系统级动作（v0.13.0 阶段 D 落地）。

红线（设想 §五）：树只读 + 复用既有执法动作（改名/删除走 routes_history）
+ 系统级逃生门（资源管理器）；E 档不做清单（任意写/树内编辑/删账本）。
所有 path 参数强制 traversal guard（resolve + parent 校验，同 session_detail）。
"""
from __future__ import annotations

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
