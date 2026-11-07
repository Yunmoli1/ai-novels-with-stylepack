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
import tempfile
import uuid
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import appstate
import routes_create as _rc
import routes_distill as _rd
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


class DefaultPackIn(BaseModel):
    project: str
    pack: str = ""   # 空 = 清除默认


def _project_local_packs(d: Path) -> list[dict]:
    """项目本地包（style/pack-*，有 pack.json 且非草稿）——v0.13.12 入册。"""
    out = []
    sdir = d / "style"
    if not sdir.is_dir():
        return out
    for pdir in sorted(sdir.glob("pack-*")):
        if not (pdir / "pack.json").is_file():
            continue
        try:
            meta = json.loads((pdir / "pack.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if meta.get("status") == "draft":
            continue  # 草稿不进下拉（与全局包同规）
        out.append({"name": f"project:{pdir.name}",
                    "version": str(meta.get("version") or "?"),
                    "display_name": str(meta.get("display_name") or pdir.name)})
    return out


def _global_pack_names() -> list[str]:
    """全局/local 包名（local/ 根部无 pack.json——子目录才是包，先分支再过滤）。"""
    names = []
    if _rc.STYLEPACKS.is_dir():
        for pdir in sorted(_rc.STYLEPACKS.iterdir()):
            if not pdir.is_dir():
                continue
            if pdir.name == "local":
                for sub in sorted(pdir.iterdir()):
                    if sub.is_dir() and (sub / "pack.json").is_file():
                        names.append(f"local/{sub.name}")
            elif (pdir / "pack.json").is_file():
                names.append(pdir.name)
    return names


def _resolve_default_pack(d: Path, local_packs: list[dict]) -> tuple[str | None, str]:
    """默认包解析链（v0.13.12）：workbench.json 显式设置 > 钉扎头 >
    唯一项目本地包。返回 (默认包名或 None, 提示)。"""
    local_names = {p["name"] for p in local_packs}
    known = local_names | set(_global_pack_names())
    # ① 显式设置（style/workbench.json）
    wb = d / "style" / "workbench.json"
    if wb.is_file():
        try:
            wj = json.loads(wb.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            wj = {}
        dp = wj.get("default_pack")
        if dp and dp in known:
            return dp, "本项目默认（显式设置）"
    # ② 钉扎头（style-setup/pin 协议）
    pin = appstate.read_pinned_pack(d)
    if pin and pin.get("pack") and pin["pack"] in known:
        return pin["pack"], f"项目钉扎 v{pin.get('version', '?')}"
    # ③ 唯一项目本地包（多包无法判定主从，交还显式设置）
    if len(local_names) == 1:
        return next(iter(local_names)), "本项目唯一本地包"
    return None, ""


@router.get("/project_packs")
def project_packs_view(project: str):
    """项目本地包入册 + 默认包解析（v0.13.12）。前端据此重建包下拉
    （本项目分组）并应用默认链。"""
    cfg = appstate.load_config()
    d = _proj(cfg, project)
    packs = _project_local_packs(d)
    default, hint = _resolve_default_pack(d, packs)
    wj = {}
    wb = d / "style" / "workbench.json"
    if wb.is_file():
        try:
            wj = json.loads(wb.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            wj = {}
    return {"packs": packs, "default_pack": default, "hint": hint,
            "ref_packs": wj.get("ref_packs") or []}


@router.post("/default_pack")
def set_default_pack(body: DefaultPackIn):
    """设为/清除本项目默认包 → style/workbench.json（显式优于隐式）。
    pack 空 = 清除；全局/local/项目包均可设（存在性校验，草稿拦截）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    if body.pack:
        if body.pack.startswith("project:"):
            known = {p["name"] for p in _project_local_packs(d)}
        else:
            known = set(_global_pack_names())
        if body.pack not in known:
            raise HTTPException(400, f"包不存在或为草稿：{body.pack}")
    wbdir = d / "style"
    wbdir.mkdir(parents=True, exist_ok=True)
    wb = wbdir / "workbench.json"
    wj = {}
    if wb.is_file():
        try:
            wj = json.loads(wb.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            wj = {}
    wj["default_pack"] = body.pack or None
    wb.write_text(json.dumps(wj, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8", newline="\n")
    return {"ok": True, "default_pack": body.pack or None}


class RefPacksIn(BaseModel):
    project: str
    ref_packs: list[str] = []


@router.post("/ref_packs")
def set_ref_packs(body: RefPacksIn):
    """存项目参考池 → style/workbench.json（v0.13.13；cap 3，存在性校验，
    草稿拒收——参考池是防线语义的项目级配置）。"""
    if len(body.ref_packs) > 3:
        raise HTTPException(400, "参考池上限 3 个——参考越多棘轮风险越高")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    known_project = {p["name"] for p in _project_local_packs(d)}
    known = known_project | set(_global_pack_names())
    for rp in body.ref_packs:
        if rp not in known:
            raise HTTPException(400, f"参考包不存在或为草稿：{rp}")
    wbdir = d / "style"
    wbdir.mkdir(parents=True, exist_ok=True)
    wb = wbdir / "workbench.json"
    wj = {}
    if wb.is_file():
        try:
            wj = json.loads(wb.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            wj = {}
    wj["ref_packs"] = body.ref_packs
    wb.write_text(json.dumps(wj, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8", newline="\n")
    return {"ok": True, "ref_packs": body.ref_packs}


# ---- 单元卡（v0.13.14）：两级单位——故事卡（前置闸门）+封卡（L1 记忆）----


def _chapter_file(d: Path, no: int) -> Path | None:
    ms = d / "manuscript"
    if not ms.is_dir():
        return None
    hits = sorted(ms.glob(f"{no:03d}-*.md")) or sorted(ms.glob(f"{no}-*.md"))
    return hits[0] if hits else None


@router.get("/units")
def units_view(project: str):
    """单元注册表（workbench.json）+ 交付状态 + L1 记忆卡（units.md）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, project)
    units = appstate.read_units_registry(d)
    for u in units:
        u["chapters_status"] = [
            {"no": c, "delivered": _chapter_file(d, int(c)) is not None}
            for c in u.get("chapters", [])]
    cards = appstate.units_md_cards(d)
    return {"units": units, "memory_cards": cards[-10:],
            "next_id": _next_unit_id(units)}


def _next_unit_id(units: list[dict]) -> str:
    nums = []
    for u in units:
        m = re.match(r"U(\d+)", u.get("id") or "")
        if m:
            nums.append(int(m.group(1)))
    return f"U{(max(nums) + 1) if nums else 1:02d}"


class UnitCreateIn(BaseModel):
    project: str
    id: str
    title: str
    chapters: list[int] = []


@router.post("/units/create")
def unit_create(body: UnitCreateIn):
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    units = appstate.read_units_registry(d)
    if not re.match(r"^U\d+$", body.id):
        raise HTTPException(400, "单元 id 形如 U07")
    if any(u["id"] == body.id for u in units):
        raise HTTPException(400, f"单元 id 已存在：{body.id}")
    chs = sorted({int(c) for c in body.chapters})
    for u in units:
        if set(u.get("chapters", [])) & set(chs):
            raise HTTPException(400, f"章 {sorted(set(u['chapters']) & set(chs))} 已属于单元 {u['id']}")
    units.append({"id": body.id, "title": body.title.strip() or body.id,
                  "chapters": chs, "status": "draft",
                  "story": {}, "sealed_card": None})
    appstate.write_units_registry(d, units)
    return {"ok": True, "units": units}


class UnitUpdateIn(BaseModel):
    project: str
    id: str
    title: str | None = None
    chapters: list[int] | None = None
    story: dict | None = None
    status: str | None = None   # draft / approved


@router.post("/units/update")
def unit_update(body: UnitUpdateIn):
    """编辑故事卡/标题/章列表；批准=draft→approved（四行运动弧填全才可批）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    units = appstate.read_units_registry(d)
    u = next((x for x in units if x["id"] == body.id), None)
    if not u:
        raise HTTPException(404, f"单元不存在：{body.id}")
    if u.get("status") == "sealed":
        raise HTTPException(400, "已封卡单元不可编辑（L1 记忆已落 units.md）")
    if body.title is not None:
        u["title"] = body.title.strip() or u["title"]
    if body.chapters is not None:
        chs = sorted({int(c) for c in body.chapters})
        for x in units:
            if x["id"] != body.id and set(x.get("chapters", [])) & set(chs):
                raise HTTPException(400, f"章冲突：单元 {x['id']}")
        u["chapters"] = chs
    if body.story is not None:
        u["story"] = body.story
    if body.status == "approved":
        story = u.get("story") or {}
        if not all(story.get(k, "").strip() for k in ("kai", "tui", "zhe", "luo")):
            raise HTTPException(400, "故事卡四行运动弧（开端/推进/转折/落点）填全才能批准——故事卡不压缩")
        u["status"] = "approved"
    elif body.status == "draft":
        u["status"] = "draft"
    appstate.write_units_registry(d, units)
    return {"ok": True, "units": units}


class UnitDraftIn(BaseModel):
    project: str
    direction: str = ""


@router.post("/units/draft")
def unit_draft(body: UnitDraftIn):
    """🤖 故事卡草拟：大纲尾部+上一张 L1 卡+用户方向 → 四行运动弧候选
    （单发调用，不落盘——人审编辑后自己保存）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    outline = d / "outline.md"
    src = outline if outline.is_file() else d / "outline" / "总大纲.md"
    tail = ""
    if src.is_file():
        tail = src.read_text(encoding="utf-8", errors="ignore")[-3000:]
    cards = appstate.units_md_cards(d)
    last_card = cards[-1]["body"][:400] if cards else "（无——本单元是第一个）"
    prompt = ("你是网文单元故事卡起草助手。根据大纲尾部、上一张单元卡和创作方向，"
              "起草下一张单元故事卡。只输出 JSON："
              '{"kai":"开端（一行运动）","tui":"推进","zhe":"转折","luo":"落点",'
              '"hook":"单元末钩子","refs":"涉及术语/伏笔","band":"预期长度带如 2500-4500"}'
              "\n\n【大纲尾部】\n" + tail
              + "\n\n【上一张单元卡】\n" + last_card
              + "\n\n【创作方向】\n" + (body.direction.strip() or "（未填——按大纲走向）")
              + "\n\n纪律：运动弧写四行运动不压缩；钩子是下限不是终点；"
              "每个运动留呼吸点。")
    result = _rc._do_model(cfg, "write", f"unitdraft-{uuid.uuid4().hex[:8]}",
                           prompt, 900, True)
    try:
        cand = result["json"]
    except (KeyError, TypeError):
        raise HTTPException(502, "故事卡草拟未返回可解析 JSON")
    return {"candidate": cand}


class UnitSealDraftIn(BaseModel):
    project: str
    id: str


@router.post("/units/seal_draft")
def unit_seal_draft(body: UnitSealDraftIn):
    """🤖 封卡草拟：故事卡+单元内各章全文 → 150-250 字 L1 卡候选
    （单发调用，不落盘——人审编辑后自己确认）。"""
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    units = appstate.read_units_registry(d)
    u = next((x for x in units if x["id"] == body.id), None)
    if not u:
        raise HTTPException(404, f"单元不存在：{body.id}")
    texts = []
    for c in u.get("chapters", []):
        f = _chapter_file(d, int(c))
        if not f:
            raise HTTPException(400, f"第 {c} 章未交付——单元内全章交付后才能封卡")
        texts.append(f"【第{c}章 {f.stem}】\n"
                     + f.read_text(encoding="utf-8", errors="ignore")[:7000])
    story = u.get("story") or {}
    story_txt = "／".join(filter(None, [story.get(k, "")
                                        for k in ("kai", "tui", "zhe", "luo")]))
    prompt = ("你是网文单元卡收束助手。根据单元故事卡和单元内各章全文，写一张 "
              "L1 单元卡：150-250 字，覆盖——本单元事件链（含结果）、情绪终点、"
              "新伏笔/线头、出场人物。只输出 JSON："
              '{"card": "...", "current_hint": "覆盖式快照建议（故事内时间/'
              '资产变化/未决线头，80 字内）"}'
              "\n\n【故事卡】\n" + (story_txt or "（无）")
              + "\n\n【各章全文】\n" + "\n\n".join(texts))
    result = _rc._do_model(cfg, "write", f"unitseal-{uuid.uuid4().hex[:8]}",
                           prompt, 800, True)
    try:
        cand = result["json"]
    except (KeyError, TypeError):
        raise HTTPException(502, "封卡草拟未返回可解析 JSON")
    return {"candidate": cand}


class UnitSealConfirmIn(BaseModel):
    project: str
    id: str
    card: str
    checklist: dict = {}   # 四道过滤+跳读测试（人工勾选，仅记录不判定）


class UnitVerifyIn(BaseModel):
    project: str
    id: str
    pack: str


@router.post("/units/verify")
def unit_verify(body: UnitVerifyIn):
    """单元口径验收（v0.13.15）：单元内各章按序拼接临时文件，跑既有门禁
    （fp/borrow/ai_cliche 全项目；长篇加 numbers/names——脚本零改动，
    wrapper 拼）。advisory。"""
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    units = appstate.read_units_registry(d)
    u = next((x for x in units if x["id"] == body.id), None)
    if not u:
        raise HTTPException(404, f"单元不存在：{body.id}")
    texts = []
    for c in u.get("chapters", []):
        f = _chapter_file(d, int(c))
        if not f:
            raise HTTPException(400, f"第 {c} 章未交付——验收前全章交付")
        texts.append(f.read_text(encoding="utf-8", errors="ignore"))
    pack_dir = _rc._pack_dir(body.pack, d)
    longform = _rc._is_longform(d)
    reports = {}
    with tempfile.TemporaryDirectory() as td:
        draft_path = Path(td) / "unit.md"
        draft_path.write_text("\n\n".join(texts), encoding="utf-8",
                              newline="\n")
        reports["fp_check"] = _rc._run_gate("fp_check.py",
                                            [str(pack_dir), str(draft_path)])
        reports["borrow_check"] = _rc._run_gate(
            "borrow_check.py", [str(draft_path), "--pack", str(pack_dir)])
        reports["ai_cliche"] = _rc._run_gate(
            "ai_cliche_check.py", [str(draft_path), "--pack", str(pack_dir)])
        if longform:
            reports["numbers_check"] = _rc._run_gate(
                "numbers_check.py", [str(draft_path), "--ledger",
                                     str(d / "bible" / "硬数字表.md"),
                                     "--chapter", str(u.get("chapters", [0])[0])])
            reports["names_check"] = _rc._run_gate(
                "names_check.py", [str(draft_path), "--variants",
                                   str(d / "bible" / "专名表.tsv"),
                                   "--characters",
                                   str(d / "bible" / "characters.md")])
    return {"reports": reports, "chars": sum(len(x) for x in texts),
            "chapters": u.get("chapters", [])}


@router.post("/units/seal_confirm")
def unit_seal_confirm(body: UnitSealConfirmIn):
    """确认封卡：checklist 全勾才收（记录即约束——人工工序不判定但必须
    留痕）；卡追加 memory/units.md（L1，原生格式，会话互通）；注册表→sealed。"""
    required = ["跳读测试", "对话出声读", "人格锚点对照", "讲古打断", "情绪停留"]
    missing = [k for k in required if not body.checklist.get(k)]
    if missing:
        raise HTTPException(400, "封卡前未勾：" + "、".join(missing)
                            + "——人工工序不判定但必须留痕")
    if not body.card.strip():
        raise HTTPException(400, "卡文为空——先草拟或手写")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    units = appstate.read_units_registry(d)
    u = next((x for x in units if x["id"] == body.id), None)
    if not u:
        raise HTTPException(404, f"单元不存在：{body.id}")
    if u.get("status") == "sealed":
        raise HTTPException(400, "该单元已封卡")
    appstate.units_md_append(d, body.id, u.get("title") or body.id, body.card)
    u["status"] = "sealed"
    u["sealed_card"] = body.card.strip()
    u["checklist"] = body.checklist
    appstate.write_units_registry(d, units)
    return {"ok": True, "cards": len(appstate.units_md_cards(d))}


@router.get("/pipeline")
def pipeline_view(project: str, chapter: int = 0):
    """管线示波器（v0.13.9）：管线声明 + 交付会话记录摘要（泳道只读视图）。
    会话记录（sessions/*.json）是 run manifest 的既有载体（v0.6.x 起）——
    本端点只读摘要、剥正文（text 不出列表），人审/记忆两步当前未留痕，
    泳道标"未记录"。"""
    import pipeline
    cfg = appstate.load_config()
    d = _proj(cfg, project)
    runs: list[dict] = []
    sdir = d / "sessions"
    if sdir.is_dir():
        for f in sorted(sdir.glob("*.json"), reverse=True)[:40]:
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if chapter and rec.get("chapter_no") != chapter:
                continue
            usage = rec.get("usage") or {}
            checks = rec.get("checks") or {}
            preview = rec.get("assembly") or []
            kept = [i for i in preview if not i.get("dropped")]
            dropped = [i for i in preview if i.get("dropped")]
            runs.append({
                "file": f.name,
                "ts": rec.get("ts", ""),
                "chapter_no": rec.get("chapter_no"),
                "title": rec.get("title", ""),
                "chars": len(rec.get("text") or ""),
                "output_file": rec.get("output_file", ""),
                "model": usage.get("model", ""),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "retries": usage.get("retries", 0),
                "finish_reason": usage.get("finish_reason", ""),
                "checks": {k: {"exit_code": v.get("exit_code"),
                               "report_head": (v.get("report") or "")[:400]}
                           for k, v in checks.items() if isinstance(v, dict)},
                "assembly_kept": [{"kind": i.get("kind"), "source": i.get("source"),
                                   "est_tokens": i.get("est_tokens")}
                                  for i in kept],
                "assembly_dropped": [{"kind": i.get("kind"), "source": i.get("source"),
                                      "est_tokens": i.get("est_tokens")}
                                     for i in dropped],
                "g0_present": bool(rec.get("g0"))
                and not rec.get("g0", {}).get("skipped"),
            })
            if len(runs) >= 10:
                break
    return {"pipeline": pipeline.manifest(), "runs": runs, "chapter": chapter}


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


# ---- 设定工坊（v0.13.6）：世界观/人物/卷纲的块级生成流水线 ----
# 纪律：每步单发调用 + 产出候选（不落盘）+ 人审编辑 + 显式保存（块级合并，
# 永不整文件覆盖）。canon 锚定可选（同人模式）；落盘直进约束面板的数据源。
FORGE_JSON_NOTE = "只输出 JSON 本体（不要解释、不要 markdown 围栏）。"


def _canon_ctx_or_400(canon_name: str | None) -> str:
    if not canon_name:
        return ""
    canon_dir = _rd.CANONPACKS / canon_name
    if not (canon_dir / "pack.json").is_file():
        raise HTTPException(400, f"canon 包不存在：{canon_name}")
    return _rd._canon_ctx(canon_dir)


def _forge_material(material: str) -> str:
    return f"\n——参考资料（取材于此，不得照抄原文）——\n{material[:3000]}" \
        if (material or "").strip() else ""


class ForgeWorldIn(BaseModel):
    project: str
    brief: str          # 题材/一句话方向/要求
    canon_pack: str | None = None
    material: str = ""  # 粘贴的参考资料（同人原作资料/散稿）
    n: int = 4          # 生成块数 2-6


@router.post("/forge/world")
def forge_world(body: ForgeWorldIn):
    """世界观块候选生成：产出 {blocks:[{title,body}]}，不落盘——人审后走 /save。"""
    if not (body.brief or "").strip():
        raise HTTPException(400, "创作方向为空——至少给一句话")
    n = max(2, min(6, body.n))
    canon_ctx = _canon_ctx_or_400(body.canon_pack)
    canon_note = (f"必须贴合下方「世界观锚定」材料（术语/设定以材料为准，不自造）。\n"
                  f"——世界观锚定——\n{canon_ctx}\n" if canon_ctx else "")
    prompt = (f"设定工坊·世界观块候选（{FORGE_JSON_NOTE}）\n\n"
              f"按以下原料，为这本书生成 {n} 个世界观设定块候选。每块独立成条："
              f"标题即条目名（2-6 字），正文 2-4 行、一段一条、可执行"
              f"（力量体系/规则/地理/组织等，不做抒情描述）。\n"
              f"{canon_note}{_forge_material(body.material)}\n"
              f"——创作方向——\n{body.brief.strip()}\n\n"
              f'输出 JSON：{{"blocks": [{{"title": "条目名", "body": "正文"}}]}}')
    cfg = appstate.load_config()
    result = _rc._do_model(cfg, "write", f"forge-{uuid.uuid4().hex[:8]}",
                           prompt, 3000, True, kind="other")
    blocks = result["json"].get("blocks", [])
    if not blocks:
        raise HTTPException(502, "模型未返回世界观块——重试或换模型")
    return {"candidates": [{"title": str(b.get("title", "")).strip()[:40],
                            "body": str(b.get("body", "")).strip(),
                            "resident": False} for b in blocks
                           if str(b.get("title", "")).strip()],
            "usage": result}


class ForgeSaveWorldIn(BaseModel):
    project: str
    blocks: list[dict]  # [{title, body, resident}]


@router.post("/forge/world/save")
def forge_world_save(body: ForgeSaveWorldIn):
    """候选落盘：块级合并进 world.md（同名替换/新块追加，永不整文件覆盖）。"""
    if not body.blocks:
        raise HTTPException(400, "没有选中任何块")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    f = d / "bible" / "world.md"
    text = splib.read_text(f)[0] if f.is_file() else "# 世界设定\n"
    parts = text.split("\n## ")
    saved = 0
    for b in body.blocks:
        title = str(b.get("title", "")).strip()
        body_text = str(b.get("body", "")).strip()
        if not title or not body_text:
            continue
        new_block = f"## {title}\n{body_text}"
        if b.get("resident"):
            new_block += "\n" + RESIDENT_MARK
        hit = None
        for i, part in enumerate(parts):
            head = part if i == 0 else "## " + part
            if head.splitlines()[0].lstrip("# ").strip() == title:
                hit = i
                break
        if hit is not None:
            parts[hit] = new_block[3:] if hit else new_block
        else:
            parts.append(new_block)
        saved += 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n## ".join(parts), encoding="utf-8", newline="\n")
    return {"ok": True, "saved": saved}


class ForgeCharsIn(BaseModel):
    project: str
    brief: str
    canon_pack: str | None = None
    material: str = ""
    n: int = 3


@router.post("/forge/characters")
def forge_characters(body: ForgeCharsIn):
    """人物卡候选生成：产出 {people:[{name,identity,personality,quirk,taboo,
    aliases}]}，不落盘。"""
    if not (body.brief or "").strip():
        raise HTTPException(400, "创作方向为空——至少给一句话")
    n = max(1, min(5, body.n))
    canon_ctx = _canon_ctx_or_400(body.canon_pack)
    canon_note = (f"人物必须属于下方「世界观锚定」的世界（名字/身份/能力遵守"
                  f"材料，术语用 must 列表）。\n——世界观锚定——\n{canon_ctx}\n"
                  if canon_ctx else "")
    prompt = (f"设定工坊·人物卡候选（{FORGE_JSON_NOTE}）\n\n"
              f"按以下原料，为这本书生成 {n} 个主角/主要配角候选。名字须可入"
              f"专名表（2-3 字、不与常见词撞车）；taboo 是「从不说的话/词」"
              f"1-2 条（人设执法项）；quirk 是口头禅/说话习惯。\n"
              f"{canon_note}{_forge_material(body.material)}\n"
              f"——创作方向——\n{body.brief.strip()}\n\n"
              f'输出 JSON：{{"people": [{{"name": "名字", "identity": "一句话身份",'
              f' "personality": "性格", "quirk": "口头禅/说话习惯",'
              f' "taboo": ["从不说的话"], "aliases": []}}]}}')
    cfg = appstate.load_config()
    result = _rc._do_model(cfg, "write", f"forge-{uuid.uuid4().hex[:8]}",
                           prompt, 3000, True, kind="other")
    people = result["json"].get("people", [])
    if not people:
        raise HTTPException(502, "模型未返回人物候选——重试或换模型")
    out = []
    for p in people:
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        out.append({"name": name[:20],
                    "identity": str(p.get("identity", "")).strip()[:120],
                    "personality": str(p.get("personality", "")).strip()[:200],
                    "quirk": str(p.get("quirk", "")).strip()[:120],
                    "taboo": [str(t).strip()[:30] for t in (p.get("taboo") or [])
                              if str(t).strip()][:3],
                    "aliases": [str(a).strip()[:20] for a in (p.get("aliases") or [])
                                if str(a).strip()],
                    "tier": "minor", "resident": False})
    return {"candidates": out, "usage": result}


class ForgeSaveCharsIn(BaseModel):
    project: str
    people: list[dict]  # [{name, identity, personality, quirk, taboo, aliases, tier}]


@router.post("/forge/characters/save")
def forge_characters_save(body: ForgeSaveCharsIn):
    """人物候选落盘：characters.md 块级合并 + names.json 逐条 upsert。"""
    if not body.people:
        raise HTTPException(400, "没有选中任何人物")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    cf = d / "bible" / "characters.md"
    text = splib.read_text(cf)[0] if cf.is_file() else "# 人物\n"
    parts = text.split("\n## ")
    nf = d / "bible" / "names.json"
    people_list, _ = _load_names(d)
    saved = 0
    for p in body.people:
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        identity = str(p.get("identity", "")).strip()
        personality = str(p.get("personality", "")).strip()
        quirk = str(p.get("quirk", "")).strip()
        taboo = [str(t).strip() for t in (p.get("taboo") or []) if str(t).strip()]
        tier = str(p.get("tier") or "minor")
        card = f"## {name}\n{identity}。性格：{personality}\n" \
               f"口头禅/说话习惯：{quirk}\n状态：在场"
        if taboo:
            card += "\n禁语：" + "|".join(taboo)
        hit = None
        for i, part in enumerate(parts):
            head = part if i == 0 else "## " + part
            if head.splitlines()[0].lstrip("# ").strip() == name:
                hit = i
                break
        if hit is not None:
            parts[hit] = card[3:] if hit else card
        else:
            parts.append(card)
        entry = next((q for q in people_list
                      if str(q.get("name", "")).strip() == name), None)
        if entry:
            entry["tier"] = tier
            if p.get("aliases"):
                entry["aliases"] = p["aliases"]
        else:
            people_list.append({"name": name, "tier": tier,
                                "aliases": p.get("aliases") or []})
        saved += 1
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text("\n## ".join(parts), encoding="utf-8", newline="\n")
    _write_names(d, people_list)
    return {"ok": True, "saved": saved}


class ForgeOutlineIn(BaseModel):
    project: str
    brief: str
    canon_pack: str | None = None
    material: str = ""
    n_volumes: int = 1


@router.post("/forge/outline")
def forge_outline(body: ForgeOutlineIn):
    """卷纲骨架候选：卷名+铁律+弧草案（弧名/锚点/张力/勾稽点）——章号仍由
    开弧向导定（数字账开弧定，不自动）。"""
    if not (body.brief or "").strip():
        raise HTTPException(400, "创作方向为空——至少给一句话")
    n_vol = max(1, min(3, body.n_volumes))
    canon_ctx = _canon_ctx_or_400(body.canon_pack)
    canon_note = (f"卷纲必须落在下方「世界观锚定」的世界内。\n"
                  f"——世界观锚定——\n{canon_ctx}\n" if canon_ctx else "")
    prompt = (f"设定工坊·卷纲骨架候选（{FORGE_JSON_NOTE}）\n\n"
              f"按以下原料，为这本书生成 {n_vol} 卷的骨架。每卷：卷名、"
              f"铁律（本卷不可违背的约束 1-3 条，用；分隔）、弧草案 2-3 条"
              f"（弧名/原作锚点/张力设计/勾稽点——四字段是后续开弧向导的"
              f"原料，要可判定、不写抒情话）。\n"
              f"{canon_note}{_forge_material(body.material)}\n"
              f"——创作方向——\n{body.brief.strip()}\n\n"
              f'输出 JSON：{{"volumes": [{{"title": "卷一 卷名",'
              f' "rule": "铁律；铁律", "arcs": [{{"title": "弧名",'
              f' "anchor": "锚点", "tension": "张力", "hooks": "勾稽点"}}]}}]}}')
    cfg = appstate.load_config()
    result = _rc._do_model(cfg, "write", f"forge-{uuid.uuid4().hex[:8]}",
                           prompt, 3000, True, kind="other")
    volumes = result["json"].get("volumes", [])
    if not volumes:
        raise HTTPException(502, "模型未返回卷纲候选——重试或换模型")
    out = [{"title": str(v.get("title", "")).strip()[:40],
            "rule": str(v.get("rule", "")).strip()[:300],
            "arcs": [{"title": str(a.get("title", "")).strip()[:40],
                      "anchor": str(a.get("anchor", "")).strip()[:200],
                      "tension": str(a.get("tension", "")).strip()[:200],
                      "hooks": str(a.get("hooks", "")).strip()[:200]}
                     for a in (v.get("arcs") or [])
                     if str(a.get("title", "")).strip()]}
           for v in volumes if str(v.get("title", "")).strip()]
    return {"candidates": out, "usage": result}


class ForgeSaveOutlineIn(BaseModel):
    project: str
    volumes: list[dict]  # [{title, rule}]


@router.post("/forge/outline/save")
def forge_outline_save(body: ForgeSaveOutlineIn):
    """卷纲落盘：outline.md 追加/替换 ## 卷节（铁律行）——弧块仍走开弧向导。"""
    if not body.volumes:
        raise HTTPException(400, "没有选中任何卷")
    cfg = appstate.load_config()
    d = _proj(cfg, body.project)
    f = d / "outline.md"
    text = splib.read_text(f)[0] if f.is_file() else "# 卷纲\n"
    parts = text.split("\n## ")
    saved = 0
    for v in body.volumes:
        title = str(v.get("title", "")).strip()
        rule = str(v.get("rule", "")).strip()
        if not title:
            continue
        new_sec = f"## {title}\n铁律：{rule or '（待填）'}"
        hit = None
        for i, part in enumerate(parts):
            head = part if i == 0 else "## " + part
            if head.splitlines()[0].lstrip("# ").strip() == title:
                hit = i
                break
        if hit is not None:
            parts[hit] = new_sec[3:] if hit else new_sec
        else:
            parts.append(new_sec)
        saved += 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n## ".join(parts), encoding="utf-8", newline="\n")
    return {"ok": True, "saved": saved}
