# -*- coding: utf-8 -*-
"""routes_bible：项目档案编辑器（v0.10.0）。

纯工作台用户（不开 agent）维护设定的唯一入口：bible/（人物/世界/names/
伏笔）、canon/（术语表）、outline.md（卷纲）——文件协议与 agent 侧完全
同源，CLI 等价 = 直接编辑文件。白名单 + 穿越防护；names/canon-terms 的
JSON 合法性校验后才落盘。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import appstate
import routes_create as _rc

router = APIRouter(prefix="/app/api/bible")

# 允许编辑的相对路径（目录前缀 + 扩展名）
ALLOWED = [
    ("bible/", (".md", ".json")),
    ("canon/", (".md", ".json")),
]
ALLOWED_FILES = {"outline.md", "00_写作防线.md", "00_项目宪法.md"}


def _check_path(project_dir: Path, rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    p = (project_dir / rel).resolve()
    if not p.is_relative_to(project_dir.resolve()):
        raise HTTPException(400, "路径非法")
    ok = rel in ALLOWED_FILES or any(
        rel.startswith(pre) and p.suffix in exts for pre, exts in ALLOWED)
    if not ok:
        raise HTTPException(400, f"不在可编辑清单：{rel}（bible/·canon/·outline.md）")
    return p


def _project(cfg: dict, name: str) -> Path:
    return _rc._project_dir(cfg, name)


@router.get("/files")
def files(project: str):
    """项目档案清单：bible/ canon/ outline.md 现有文件。"""
    cfg = appstate.load_config()
    pd = _project(cfg, project)
    out = []
    for pre in ("bible/", "canon/"):
        d = pd / pre[:-1]
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix in (".md", ".json"):
                    out.append(pre + f.name)
    if (pd / "outline.md").is_file():
        out.append("outline.md")
    return {"files": out}


@router.get("/file")
def file_get(project: str, path: str):
    cfg = appstate.load_config()
    p = _check_path(_project(cfg, project), path)
    if not p.is_file():
        raise HTTPException(404, f"文件不存在：{path}（可从模板新建）")
    return {"path": path, "content": p.read_text(encoding="utf-8")}


class FileIn(BaseModel):
    project: str
    path: str
    content: str


@router.post("/file")
def file_save(body: FileIn):
    cfg = appstate.load_config()
    p = _check_path(_project(cfg, body.project), body.path)
    if p.suffix == ".json" and body.content.strip():
        try:
            json.loads(body.content)
        except ValueError as exc:
            raise HTTPException(400, f"JSON 不合法：{exc}（未保存）")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.content, encoding="utf-8", newline="\n")
    return {"ok": True, "path": body.path}


class TemplateIn(BaseModel):
    project: str
    kind: str  # characters | world | names | foreshadowing | outline | canon-terms


TEMPLATES = {
    "characters": ("bible/characters.md",
                   "# 人物\n\n## 主角名\n一句话身份。性格：\n口头禅/说话习惯：\n"),
    "world": ("bible/world.md",
              "# 世界设定\n\n## 基本规则\n（力量体系/经济/地理，一段一条）\n"),
    "names": ("bible/names.json",
              '{"names": [{"name": "主角名", "tier": "core", "aliases": []}]}\n'),
    "foreshadowing": ("bible/foreshadowing.md",
                      "# 伏笔\n\n## 标题\n状态：待回收。埋于第 N 章。\n"),
    "outline": ("outline.md",
                "# 卷纲\n\n## 卷一 卷名\n\n### 1 第一章题\n概要。\n"),
    "canon-terms": ("canon/canon-terms.json",
                    '{"work": "原作名", "must": [{"term": "术语", "wrong": [],'
                    ' "note": "说明"}], "allow": [], "ban": []}\n'),
}


@router.post("/template")
def make_template(body: TemplateIn):
    """从模板新建档案文件（已存在则 409 防覆盖）。"""
    if body.kind not in TEMPLATES:
        raise HTTPException(400, f"未知模板：{body.kind}")
    rel, content = TEMPLATES[body.kind]
    cfg = appstate.load_config()
    p = _check_path(_project(cfg, body.project), rel)
    if p.exists():
        raise HTTPException(409, f"已存在：{rel}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    return {"ok": True, "path": rel}
