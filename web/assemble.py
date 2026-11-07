# -*- coding: utf-8 -*-
"""assemble：装配预览——创作环的上下文组装与透明化（r4 §七 P2 吸收项）。

加载顺序照 style-apply 上下文加载协议（照搬不发明）：
  1 风格包档案（card/profile/thought/lexicon/limits/exemplars，整件装载不裁剪）
  3 bible 相关条目（按关键词命中；记忆注入最小版：命中优先、预算内装入）
  5 canon 层（canon/canon-terms.json 存在时：must/ban 术语表）
  4 章节锚定（上一章结尾 800 字）

纪律：
- 预览与生成走**同一个** assemble()——所见即所发；/generate 端点重跑组装并
  把装配快照写进 sessions/（可复判）。
- 每项带来源文件 + token 估算——红线 1（外发知情）的落地物。
- 预算裁剪只裁记忆与锚定，风格包档案不裁（盲测协议即整件装载）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import splib  # noqa: E402  (web/ 已把 scripts/ 加入 sys.path)

PACK_FILES = [("card.md", "包卡"), ("profile.md", "文风档案"),
              ("thought.md", "思想档案"), ("lexicon.md", "词汇表"),
              ("limits.md", "能力边界"), ("exemplars.md", "范例")]

TAIL_CHARS = 800
CHARS_PER_TOKEN = 0.75  # 中文粗估


def _est_tokens(text: str) -> int:
    return int(len(text) * CHARS_PER_TOKEN)


def _split_blocks(text: str) -> list[tuple[str, str]]:
    if "## " not in text:
        return [("", text.strip())]
    parts = text.split("\n## ")
    blocks: list[tuple[str, str]] = []
    head = parts[0].strip()
    if head:
        blocks.append((head.splitlines()[0].lstrip("# ").strip()[:30], head))
    for p in parts[1:]:
        title = p.splitlines()[0].lstrip("# ").strip()[:30]
        blocks.append((title, "## " + p.strip()))
    return blocks


def _matched_blocks(path: Path, keywords: list[str], kind: str,
                    resident_names: set[str] | None = None) -> list[dict]:
    """bible 块匹配（v0.9.2 World Info 化）：
    - 常驻：块内 `<!-- resident -->` 标记，或块标题命中 core 实体名（tier=core）
    - 直接命中：关键词出现在块内
    - 递归（深度 1）：直接命中块的文本再扫一轮关键词，带入关联条目（去重）
    prio：0=常驻 / 1=直接命中 / 2=递归——预算裁剪从 prio 高的开始裁。"""
    if not path.is_file():
        return []
    text = splib.read_text(path)[0]
    if not text.strip():
        return []
    blocks = _split_blocks(text)
    kw = [k for k in keywords if k]
    resident_names = resident_names or set()
    out: dict[str, dict] = {}

    def add(title: str, body: str, prio: int, tag: str) -> None:
        key = f"{path.name}#{title}"
        if key in out and out[key]["prio"] <= prio:
            return
        out[key] = {"kind": f"{kind}·{tag}", "source": f"bible/{key}",
                    "text": body, "prio": prio}

    for t, body in blocks:
        if "<!-- resident -->" in body or t in resident_names:
            add(t, body, 0, "常驻")
    direct: list[tuple[str, str]] = []
    if kw:
        direct = [b for b in blocks if any(k in b[1] for k in kw)]
    if not direct:
        direct = blocks[:1]  # 无命中只带首块防整卷灌入（prio 视作直接）
    for t, body in direct:
        add(t, body, 1, "命中")
    # 递归一轮（深度 1）：未命中块的实体名（块标题）出现在已命中块文本中
    # → 关联注入。例：关键词"韩天宇"命中人物块，人物块写"兜里只有铜币"→
    # "## 铜币"块即使不在关键词里也被带出。只扫一轮，不再递归。
    if direct:
        scan = "\n".join(b for _, b in direct)
        direct_keys = {t for t, _ in direct}
        for t, body in blocks:
            if t in direct_keys:
                continue
            if t and t in scan:
                add(t, body, 2, "关联")
    return list(out.values())


def _chapter_num(stem: str) -> int | None:
    m = re.match(r"(\d+)", stem)
    return int(m.group(1)) if m else None


_NUM_SEC = re.compile(r"^## 弧(\d+)《.+?》（第(\d+)-(\d+)章）", re.M)


def numbers_section(project_dir: Path, chapter_no: int) -> str:
    """硬数字表当前弧节（v0.11.1 B-2）：返回覆盖 chapter_no 的弧节原文；
    无表/无覆盖弧返回空串（轻量项目与未开弧状态零变化）。
    规范层附件——调用方不得裁剪（trimmable=False）。"""
    p = project_dir / "bible" / "硬数字表.md"
    if not p.is_file():
        return ""
    text = splib.read_text(p)[0]
    secs = list(_NUM_SEC.finditer(text))
    for i, m in enumerate(secs):
        if int(m.group(2)) <= chapter_no <= int(m.group(3)):
            end = secs[i + 1].start() if i + 1 < len(secs) else len(text)
            return text[m.start():end].strip()
    return ""


def ref_pack_items(ref_pack_dirs: list[Path], project_dir: Path) -> list[dict]:
    """参考池受限层（v0.13.13）：每个参考包一条 item——只取精华卡（card.md）
    + 词汇表（lexicon.md），坚决不取 exemplars（范例=格式特征载体，灾厄前线
    事故帮凶③）；文本带禁令头（取味不取形）；prio=3（预算紧张最先裁，
    高于递归的 2）。"""
    out = []
    for rd in ref_pack_dirs:
        try:
            meta = json.loads((rd / "pack.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        disp = str(meta.get("display_name") or rd.name)
        parts = [f"【参考包·{disp}｜只取语感：词汇/调度/情绪处理——禁止复制本参考包"
                 "的排版、句式格式、破折号习惯（取味不取形）】"]
        for fname in ("card.md", "lexicon.md"):
            f = rd / fname
            if f.is_file():
                parts.append(splib.read_text(f)[0])
        src = (str(rd.relative_to(project_dir))
               if rd.is_relative_to(project_dir) else f"stylepacks/{rd.name}")
        out.append({"kind": "包·参考", "source": src,
                    "text": "\n\n".join(parts), "trimmable": True, "prio": 3})
    return out


def assemble(project_dir: Path, pack_dir: Path, chapter_no: int,
             keywords: list[str] | None = None,
             budget_tokens: int = 24000,
             ref_pack_dirs: list[Path] | None = None) -> dict:
    keywords = keywords or []
    items: list[dict] = []  # 内部项：kind/source/text
    if ref_pack_dirs:
        items += ref_pack_items(ref_pack_dirs, project_dir)

    for fname, label in PACK_FILES:
        p = pack_dir / fname
        if p.is_file():
            text = splib.read_text(p)[0]
            src = (str(p.relative_to(project_dir))
                   if pack_dir.is_relative_to(project_dir)
                   else f"stylepacks/{'local/' if 'local' in pack_dir.parts else ''}{pack_dir.name}/{fname}")
            items.append({"kind": f"包·{label}", "source": src, "text": text,
                          "trimmable": False})

    # v0.9.2 常驻双通道（D4）：names.json tier=core 的实体块自动常驻
    core_names: set[str] = set()
    names_json = project_dir / "bible" / "names.json"
    if names_json.is_file():
        try:
            nj = json.loads(names_json.read_text(encoding="utf-8"))
            core_names = {str(x.get("name", "")).strip()
                          for x in nj.get("names", [])
                          if isinstance(x, dict) and x.get("tier") == "core"}
        except (json.JSONDecodeError, OSError):
            pass

    for fname, kind in (("characters.md", "记忆·人物"), ("world.md", "记忆·设定"),
                        ("foreshadowing.md", "记忆·伏笔")):
        items += _matched_blocks(project_dir / "bible" / fname, keywords, kind,
                                 core_names)

    terms = project_dir / "canon" / "canon-terms.json"
    if terms.is_file():
        try:
            t = json.loads(terms.read_text(encoding="utf-8"))
            must = [x.get("term") for x in t.get("must", []) if isinstance(x, dict)]
            ban = [x.get("term") for x in t.get("ban", []) if isinstance(x, dict)]
            text = (f"must（按阈值落实）：{'、'.join(must) or '无'}\n"
                    f"ban（绝对不出现）：{'、'.join(ban) or '无'}")
            items.append({"kind": "canon·术语", "source": "canon/canon-terms.json",
                          "text": text, "trimmable": False})
        except (json.JSONDecodeError, OSError):
            pass

    # 规范·硬数字表（v0.11.1 B-2）：当前弧节数字口径进装配——
    # 正文只准引用表内口径，不得自造（规范层附件，不参与预算裁剪）
    num_sec = numbers_section(project_dir, chapter_no)
    if num_sec:
        items.append({"kind": "规范·硬数字表", "source": "bible/硬数字表.md",
                      "text": num_sec + "\n（唯一口径：只准引用，不得自造）",
                      "trimmable": False})

    ms = project_dir / "manuscript"
    if ms.is_dir():
        prev = [f for f in ms.glob("*.md")
                if (n := _chapter_num(f.stem)) and n < chapter_no]
        if prev:
            latest = max(prev, key=lambda f: _chapter_num(f.stem) or 0)
            text = splib.read_text(latest)[0][-TAIL_CHARS:]
            items.append({"kind": "章节锚定·上一章结尾",
                          "source": f"manuscript/{latest.name}", "text": text,
                          "trimmable": True})

    # 大纲·卷内位置（v0.9.3）：outline.md 的卷主题 + 当前章概要 + 前后各一章
    outline = project_dir / "outline.md"
    if outline.is_file():
        otext = splib.read_text(outline)[0]
        cur_vol = cur_sec = prev_sec = next_sec = ""
        vol_title = ""
        sections: list[tuple[str, str]] = []  # (标题行, 概要)
        vol = ""
        for line in otext.splitlines():
            if line.startswith("## ") and not line.startswith("###"):
                vol = line.lstrip("# ").strip()
            elif line.startswith("###"):
                sections.append((vol, line.lstrip("# ").strip()))
        for i, (v, sec) in enumerate(sections):
            m = re.match(r"(?:第)?(\d+)", sec)
            if m and int(m.group(1)) == chapter_no:
                cur_vol, cur_sec = v, sec
                prev_sec = sections[i - 1][1] if i > 0 else ""
                next_sec = sections[i + 1][1] if i + 1 < len(sections) else ""
                break
        if cur_sec:
            lines = [f"卷：{cur_vol}" if cur_vol else "",
                     f"前一章：{prev_sec}" if prev_sec else "",
                     f"本章大纲：{cur_sec}",
                     f"后一章（走向，勿剧透提前）：{next_sec}" if next_sec else ""]
            items.append({"kind": "大纲·卷内位置", "source": "outline.md",
                          "text": "\n".join(x for x in lines if x)[:800],
                          "trimmable": True})

    # 记忆·前情提要（v0.9.0）：MCP 同源 Store 的 recap——最近章摘要+未回收伏笔。
    # 无 db / 空库（新项目、未走记忆登记）静默跳过，装配行为不变。
    pending_memory = 0  # v0.11.1 B-4：隔离区未合并计数（state drift 防线信号）
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from store import Store  # noqa: E402 —— 延迟导入，无 server/ 时跳过
        store = Store(project_dir)
        try:
            recap = store.recap(3)
        finally:
            store.close()
        pending_memory = int(recap.get("pending_count") or 0)
        if recap.get("recent") or recap.get("open_foreshadow"):
            lines = [f"第{r['chapter']}章摘要：{r['digest']}"
                     for r in recap["recent"]]
            if recap["open_foreshadow"]:
                lines.append("未回收伏笔：" + "；".join(
                    f"{r['title']}（第{r['planted_chapter']}章埋）"
                    for r in recap["open_foreshadow"]))
            items.append({"kind": "记忆·前情提要",
                          "source": "style/memory.db（recap）",
                          "text": "\n".join(lines)[:1200], "trimmable": True})
    except Exception:  # noqa: BLE001 —— 记忆是增强，绝不阻断装配
        pass

    # 记忆·单元卡（v0.13.14）：memory/units.md（L1，泰拉灾厄原生格式，会话
    # 互通）最后 2 张——跨单元边界的前情主粮。无文件静默跳过。
    try:
        import appstate  # noqa: E402 —— 延迟导入（web/ 已入 sys.path）
        cards = appstate.units_md_cards(project_dir)
        if cards:
            recent = cards[-2:]
            txt = "\n\n".join(f"{c['id']}《{c['title']}》：{c['body']}"
                              for c in recent)
            items.append({"kind": "记忆·单元卡", "source": "memory/units.md",
                          "text": txt[:900], "trimmable": True, "prio": 1})
    except Exception:  # noqa: BLE001
        pass

    # 预算裁剪：只裁 trimmable；v0.9.2 按 prio 从高到低裁
    # （先裁"关联"，再"命中"，常驻最后——重要记忆活到最后）
    def tok(x: dict) -> int:
        return _est_tokens(x["text"])

    total = sum(tok(i) for i in items)
    trimmables = sorted([i for i in items if i.get("trimmable")],
                        key=lambda i: -(i.get("prio", 0)))
    for item in trimmables:
        if total <= budget_tokens:
            break
        total -= tok(item)
        item["dropped"] = True

    preview = []
    for i in items:
        preview.append({"kind": i["kind"], "source": i["source"],
                        "chars": len(i["text"]), "est_tokens": tok(i),
                        "dropped": bool(i.get("dropped")),
                        "excerpt": i["text"][:160] + ("…" if len(i["text"]) > 160 else "")})
    kept_texts = [f"【{i['kind']}｜{i['source']}】\n{i['text']}"
                  for i in items if not i.get("dropped")]
    return {"items": preview, "kept_texts": kept_texts,
            "total_chars": sum(len(i["text"]) for i in items),
            "total_est_tokens": sum(tok(i) for i in items if not i.get("dropped")),
            "budget_tokens": budget_tokens,
            "within_budget": total <= budget_tokens,
            "pending_memory": pending_memory}
