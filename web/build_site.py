# -*- coding: utf-8 -*-
"""build_site：阶段 0 静态站点生成器（网页控制台 r4 · P0-1/2/3，零依赖）。

用法：
    python web/build_site.py [--out web/site]

产出（默认 web/site/，gitignore）：
    index.html               门户
    judging/index.html       盲测人工判读台（纯客户端：radio + localStorage + 导出 JSON）
    packs/index.html         包列表
    packs/<name>/index.html  包全档渲染 + 测量可视化（指标容差表 / LOO 留一线 / motif SVG）

红线落实（tests/test_web.py 锁定）：
    产物只读 stylepacks/ 与 evals/human_judging.json——语料全文与答案卷
    （human_judging_answers.json）从不进入构建输入，因此不会出现在产物里；
    引文 ≤200 字由包内 validate 既有保证。
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import splib  # noqa: E402

CSS = """:root{--bg:#14161a;--panel:#1d2127;--panel2:#232830;--text:#d8dce2;--muted:#8a919c;--accent:#6ea8fe;--accent-soft:rgba(110,168,254,.14);--border:#2a2f37;--good:#7bc47f;--bad:#e08585;--radius:10px;--speed:.15s}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.75 "Segoe UI","Microsoft YaHei",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
::selection{background:var(--accent-soft)}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:var(--panel2);border-radius:5px}::-webkit-scrollbar-thumb:hover{background:var(--border)}::-webkit-scrollbar-track{background:transparent}
.wrap{display:flex;min-height:100vh}
nav{width:210px;flex:0 0 210px;background:var(--panel);border-right:1px solid var(--border);padding:16px 12px;position:sticky;top:0;height:100vh;overflow:auto}
nav .brand{font-weight:700;margin:2px 6px 14px;letter-spacing:.5px;font-size:16px}
nav .brand .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--accent);margin-right:7px;vertical-align:1px}
nav .navsec{margin:14px 8px 4px;font-size:11.5px;color:var(--muted);letter-spacing:1.5px;text-transform:uppercase}
nav a{display:block;padding:6px 10px;border-radius:7px;color:var(--text);font-size:14px;transition:background var(--speed),color var(--speed)}
nav a:hover{background:var(--panel2);text-decoration:none}
nav a.active{background:var(--accent-soft);color:var(--accent);font-weight:600}
nav .sub{padding-left:16px;font-size:13px;color:var(--muted)}
main{flex:1;padding:26px 34px;max-width:980px}
h1{font-size:22px;margin:.2em 0 .6em}h2{font-size:18px;margin:1.4em 0 .5em;border-bottom:1px solid var(--border);padding-bottom:4px}h3{font-size:15.5px;margin:1.2em 0 .4em;color:var(--accent)}
p{margin:.5em 0}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;margin:10px 0}
.meta{color:var(--muted);font-size:13px}
table{border-collapse:collapse;margin:8px 0;width:100%}
th,td{border:1px solid var(--border);padding:4px 10px;text-align:left;font-size:13.5px}
th{background:var(--panel2)}
tr:hover td{background:rgba(110,168,254,.04)}
.passage{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin:10px 0;font:15.5px/2.0 "Noto Serif SC","Source Han Serif SC","SimSun",serif;white-space:pre-wrap}
blockquote{margin:.5em 0;padding:6px 14px;border-left:3px solid var(--accent);background:var(--panel2);border-radius:0 8px 8px 0}
code{background:var(--panel2);padding:1px 5px;border-radius:4px;font-size:13px}
.btn{display:inline-block;background:var(--accent);color:#10131a;border:0;border-radius:8px;padding:8px 18px;font-size:14px;font-weight:600;cursor:pointer;margin:6px 8px 6px 0;transition:filter var(--speed),transform var(--speed),background var(--speed)}
.btn:hover{filter:brightness(1.12)}
.btn:active{transform:translateY(1px)}
.btn:disabled{opacity:.45;cursor:not-allowed;filter:none;transform:none}
.btn.ghost{background:var(--panel2);color:var(--text);border:1px solid var(--border)}
.btn.ghost:hover{border-color:var(--accent);filter:none}
.btn:focus-visible,nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
input,textarea,select{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:6px 10px;font:inherit;transition:border-color var(--speed)}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.panel label{display:inline-flex;flex-direction:column;align-items:flex-start;gap:3px;margin:6px 12px 6px 0;font-size:12.5px;color:var(--muted)}
.verdict label,.panel label.inline{display:inline-flex;flex-direction:row;align-items:center;gap:6px;font-size:inherit;color:inherit;margin:0 14px 0 0}
.genrow{display:flex;flex-wrap:wrap;gap:6px;align-items:flex-end}
#toast{position:fixed;right:18px;bottom:18px;z-index:99;display:flex;flex-direction:column;gap:8px}
#toast .t{background:var(--panel2);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:10px 16px;font-size:14px;box-shadow:0 6px 24px rgba(0,0,0,.35);animation:tin .2s ease-out}
#toast .t.good{border-left-color:var(--good)}#toast .t.bad{border-left-color:var(--bad)}
@keyframes tin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.round{margin:26px 0}
.round .head{font-weight:700;margin-bottom:4px}
.verdict{margin-top:8px;padding:10px 14px;background:var(--panel2);border-radius:8px}
.verdict label{margin-right:14px}
textarea{width:100%}
select,button{font:inherit}
progress{width:180px;vertical-align:middle}
footer{color:var(--muted);font-size:12px;margin-top:30px;border-top:1px solid var(--border);padding-top:10px;display:flex;flex-wrap:wrap;gap:4px 18px}
footer .sep{color:var(--border)}
"""


def esc(t: str) -> str:
    return html.escape(t, quote=False)


def _inline(t: str) -> str:
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


import re  # noqa: E402  (推迟到 _inline 之后仅为可读性)


def md_to_html(md: str) -> str:
    """受控 md 子集 → HTML：标题/表格/引用/列表/段落/粗体/行内码。"""
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    para: list[str] = []
    def flush_para():
        if para:
            out.append(f"<p>{'<br>'.join(_inline(x) for x in para)}</p>")
            para.clear()
    while i < len(lines):
        s = lines[i].rstrip()
        if not s.strip():
            flush_para()
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            flush_para()
            lvl = min(len(m.group(1)) + 1, 5)  # 文件 h1 → 页面 h2，避免与页标题重复
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if s.lstrip().startswith("|"):
            flush_para()
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append(cells)
                i += 1
            if rows:
                head = "".join(f"<th>{_inline(c)}</th>" for c in rows[0])
                body = "".join(
                    "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                    for r in rows)
                out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue
        if s.startswith(">"):
            flush_para()
            quote: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{'<br>'.join(_inline(q) for q in quote if q)}</blockquote>")
            continue
        lm = re.match(r"^[-*]\s+(.*)$", s.strip())
        if lm and not s.startswith(" "):
            flush_para()
            items: list[str] = []
            while i < len(lines):
                m2 = re.match(r"^[-*]\s+(.*)$", lines[i].strip())
                if not m2:
                    break
                items.append(f"<li>{_inline(m2.group(1))}</li>")
                i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
            continue
        para.append(s.strip())
        i += 1
    flush_para()
    return "\n".join(out)


def layout(title: str, body: str, active: str, rel: str = "../") -> str:
    def navlink(href, label, key, cls=""):
        c = f' class="{cls} active"' if key == active else (f' class="{cls}"' if cls else "")
        return f'<a href="{href}"{c}>{label}</a>'
    import appstate as _appstate
    try:
        ver = _appstate.workbench_version()
    except Exception:  # noqa: BLE001
        ver = "?"
    nav = [
        '<div class="brand"><span class="dot"></span>StylePack</div>',
        '<div class="navsec">浏览</div>',
        navlink(f"{rel}index.html", "门户", "home"),
        navlink(f"{rel}packs/", "包浏览", "packs"),
        navlink(f"{rel}canon/", "canon 包", "canon"),
        navlink(f"{rel}judging/", "盲测判读台", "judging"),
        '<div class="navsec">工作台</div>',
        '<a href="/app/create">创作</a>',
        '<a href="/app/serial">连载台</a>',
        '<a href="/app/distill">蒸馏</a>',
        '<a href="/app/bible">项目档案</a>',
        '<a href="/app/history">历史与成本</a>',
        '<a href="/app/config">模型配置</a>',
    ]
    footer = (f'<footer><span>本地工作台 v{ver}</span><span class="sep">|</span>'
              '<span>全部数据与渲染均在本机</span><span class="sep">|</span>'
              '<span>引文 ≤200 字，全文不出库</span></footer>')
    favicon = ('<link rel="icon" href="data:image/svg+xml,'
               '%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E'
               '%3Crect width=%2732%27 height=%2732%27 rx=%277%27 fill=%27%2314161a%27/%3E'
               '%3Ctext x=%2716%27 y=%2723%27 font-size=%2718%27 text-anchor=%27middle%27%3E'
               '%E2%9C%92%3C/text%3E%3C/svg%3E">')
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · StylePack 工作台</title>
{favicon}
<link rel="stylesheet" href="{rel}style.css"></head>
<body><div class="wrap"><nav>
{chr(10).join(nav)}
</nav><main>{body}
{footer}
</main></div></body></html>"""


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def bars_svg(items: list[tuple[str, float]], unit: str = "") -> str:
    """motif 频率横条图（纯 SVG，零依赖）。"""
    if not items:
        return ""
    w, lh, left, maxv = 620, 30, 110, max(v for _, v in items)
    h = lh * len(items) + 8
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" role="img">']
    for i, (label, v) in enumerate(items):
        y = i * lh + 6
        bw = max(2, (w - left - 60) * v / maxv)
        parts.append(f'<text x="0" y="{y + 16}" fill="#d8dce2" font-size="14">{esc(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="20" rx="4" fill="#6ea8fe" opacity="0.85"/>')
        parts.append(f'<text x="{left + bw + 8:.1f}" y="{y + 16}" fill="#8a919c" font-size="12.5">{v:g}{unit}</text>')
    parts.append("</svg>")
    return "".join(parts)


MOTIF_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|")


def parse_motif_stats(thought_md: str) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    in_sec = False
    for line in thought_md.splitlines():
        if line.strip().startswith("## "):
            in_sec = "motif_stats" in line
            continue
        if in_sec:
            m = MOTIF_RE.match(line.strip())
            if m and m.group(1) != "motif":
                rows.append((m.group(1), float(m.group(2))))
    return rows


def render_metrics_table(metrics: dict) -> str:
    rows = []
    for group, sub in metrics.items():
        if isinstance(sub, dict) and "target" in sub:
            sub = {group: sub}
        for k, v in sub.items():
            if not isinstance(v, dict) or "target" not in v:
                continue
            rows.append(f"<tr><td>{esc(group)} · {esc(k)}</td>"
                        f"<td>{fmt(v['target'])}</td><td>±{fmt(v.get('tolerance_abs', 0))}</td></tr>")
    return (f"<table><thead><tr><th>指标</th><th>目标</th><th>容差</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def render_fingerprint(fp: dict) -> str:
    parts = []
    dp = fp.get("delta_profile", {})
    parts.append(f'<div class="panel">混合 Delta 档案：样本 <strong>{dp.get("n_samples", "?")}</strong> 篇 · '
                 f'高频字 <strong>{dp.get("top_n", "?")}</strong> 个'
                 f'<div class="meta">{esc(str(fp.get("notes", ""))[:220])}</div></div>')
    for g, layer in sorted(fp.get("genres", {}).items()):
        samples = layer.get("samples", [])
        sc = (fp.get("self_check", {}) or {}).get(g, {})
        loo = sc.get("delta_max")
        loo_txt = (f"留一及格线 delta_max=<strong>{fmt(loo)}</strong>（p50={fmt(sc.get('delta_p50'))}，n={sc.get('n')}）"
                   if loo is not None else f"不可标定（{esc(str(sc.get('note', 'n<3')))}）——该层 Delta 暂不进判定")
        parts.append(f"<h3>文体层：{esc(g)}（{len(samples)} 篇 · {fmt(layer.get('chars_total', 0))} 字）</h3>")
        parts.append(f'<div class="panel">{loo_txt}</div>')
        parts.append(render_metrics_table(layer.get("metrics", {})))
    return "\n".join(parts)


def render_pack_page(name: str, pack_dir: Path, is_local: bool = False) -> str:
    tier = ("<span style='color:var(--bad)'>[本地包·不得公开再分发]</span> "
            if is_local else "")
    rel = "../../../" if is_local else "../../"
    meta = splib.load_json(pack_dir / "pack.json")
    fp = splib.load_json(pack_dir / "fingerprint.json")
    body = [f"<h1>{tier}{esc(meta.get('display_name', name))} <span class='meta'>v{esc(meta.get('version', '?'))}"
            f" · format {esc(str(meta.get('format_version', '?')))} · 更新 {esc(meta.get('updated', '?'))}</span></h1>"]
    body.append("<h2>能力与语料</h2><div class='panel'>"
                f"genres：{esc('、'.join(meta.get('genres', [])))} ｜ 能力标记："
                f"thought={'✓' if meta.get('thought') else '✗'} ｜ "
                f"corpus：{len(meta.get('corpus', {}).get('works', []))} 篇 · "
                f"{fmt(meta.get('corpus', {}).get('total_chars', 0))} 字"
                f"<div class='meta'>{esc(str(meta.get('corpus', {}).get('confidence', '')))}</div></div>")
    for fname, label in (("card.md", "卡片"), ("profile.md", "文风档案 profile"),
                         ("thought.md", "思想档案 thought"), ("exemplars.md", "范例 exemplars"),
                         ("lexicon.md", "词汇 lexicon"), ("limits.md", "能力边界 limits")):
        p = pack_dir / fname
        if p.is_file():
            body.append(f"<h2>{label}</h2>")
            body.append(md_to_html(splib.read_text(p)[0]))
    body.append("<h2>测量可视化（fingerprint）</h2>")
    body.append(render_fingerprint(fp))
    thought = pack_dir / "thought.md"
    if thought.is_file():
        motifs = parse_motif_stats(splib.read_text(thought)[0])
        if motifs:
            body.append("<h3>motif 频率（advisory，永不进判定）</h3>")
            body.append(f'<div class="panel">{bars_svg(motifs, " /千字")}</div>')
    cl = meta.get("changelog", [])
    if cl:
        rows = "".join(f"<tr><td>{esc(c.get('version', ''))}</td><td>{esc(c.get('date', ''))}</td>"
                       f"<td>{esc(str(c.get('changes', '')))}</td></tr>" for c in cl[-3:])
        body.append(f"<h2>最近变更</h2><table><thead><tr><th>版本</th><th>日期</th><th>内容</th></tr></thead>"
                    f"<tbody>{rows}</tbody></table>")
    return layout(f"{meta.get('display_name', name)} 包", "\n".join(body), "packs", rel=rel)


def render_judging(data: dict, out_time: str) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    body = ["""<h1>盲测人工判读台</h1>
<p class="meta">同源模型判官已有 8 轮记录；你是同源偏差的最终解法。答案卷不在此页、不在此站点——判完导出结果，交给 <code>scripts/score_human_judging.py</code> 计分。</p>
<div class="panel">"""]
    for i, ins in enumerate(data.get("instruction", []), 1):
        body.append(f"<p>{i}. {esc(ins)}</p>")
    body.append("</div>")
    body.append(f'<p><progress id="prog" value="0" max="{len(data["rounds"])}"></progress> '
                f'<span id="progtext" class="meta">0 / {len(data["rounds"])} 已判</span>'
                '<button class="btn" id="export">导出判读结果</button>'
                '<button class="btn ghost" id="clear">清空本机暂存</button></p>')
    for r in data["rounds"]:
        body.append(f"""<div class="round panel" data-rid="{r['id']}">
<div class="head">回合 {r['id']}（{esc(r['author'])}）· 题：{esc(r['title'])}</div>
<div class="passage">【甲】{esc(r['甲'])}</div>
<div class="passage">【乙】{esc(r['乙'])}</div>
<div class="verdict">你的判读：
<label><input type="radio" name="c{r['id']}" value="甲">甲</label>
<label><input type="radio" name="c{r['id']}" value="乙">乙</label>
<label><input type="radio" name="c{r['id']}" value="都不像">都不像</label>
<label>置信度 <select name="f{r['id']}"><option value=""></option><option>高</option><option>中</option><option>低</option></select></label>
<br><textarea name="r{r['id']}" rows="2" placeholder="一两句理由（可选）"></textarea>
</div></div>""")
    body.append(f"""<script id="judging-data" type="application/json">{payload}</script>
<script>
const DATA = JSON.parse(document.getElementById('judging-data').textContent);
const KEY = 'stylepack_judging_v1';
const state = JSON.parse(localStorage.getItem(KEY) || '{{}}');
function save() {{
  localStorage.setItem(KEY, JSON.stringify(state));
  let n = 0;
  for (const r of DATA.rounds) if (state[r.id] && state[r.id].choice) n++;
  document.getElementById('prog').value = n;
  document.getElementById('progtext').textContent = n + ' / ' + DATA.rounds.length + ' 已判';
}}
function bind() {{
  for (const r of DATA.rounds) {{
    const box = document.querySelector('.round[data-rid="' + r.id + '"]');
    const pick = (k, v) => {{ (state[r.id] = state[r.id] || {{}})[k] = v; save(); }};
    box.addEventListener('change', e => {{
      if (e.target.name === 'c' + r.id) pick('choice', e.target.value);
      if (e.target.name === 'f' + r.id) pick('confidence', e.target.value);
    }});
    box.querySelector('textarea').addEventListener('input', e => pick('reason', e.target.value));
    const s = state[r.id] || {{}};
    if (s.choice) box.querySelector('input[value="' + s.choice + '"]').checked = true;
    if (s.confidence) box.querySelector('select').value = s.confidence;
    if (s.reason) box.querySelector('textarea').value = s.reason;
  }}
  save();
}}
document.getElementById('export').addEventListener('click', () => {{
  const rounds = DATA.rounds.map(r => ({{
    id: r.id, title: r.title,
    ...(state[r.id] || {{ choice: '', confidence: '', reason: '' }})
  }}));
  const blob = new Blob([JSON.stringify({{
    exported_at: new Date().toISOString(), protocol: DATA.protocol, rounds
  }}, null, 2)], {{ type: 'application/json' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'human_judging_results.json';
  a.click();
  alert('已导出。把文件交给：python scripts/score_human_judging.py human_judging_results.json');
}});
document.getElementById('clear').addEventListener('click', () => {{
  if (!confirm('清空本机暂存的判读进度？')) return;
  localStorage.removeItem(KEY);
  location.reload();
}});
bind();
</script>""")
    return layout("盲测判读台", "\n".join(body), "judging", rel="../")


def render_term_table(items: list) -> str:
    """术语条目通用表（must: term/wrong/note；ban: term/reason）；纯字符串列表兼容。"""
    if not items:
        return "<p class='meta'>（无）</p>"
    if not isinstance(items[0], dict):
        rows = "".join(f"<li>{esc(str(x))}</li>" for x in items)
        return f"<ul>{rows}</ul>"
    cols: list[str] = []
    for it in items:
        for k in it:
            if k not in cols:
                cols.append(k)
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    rows = []
    for it in items:
        cells = []
        for c in cols:
            v = it.get(c, "")
            if isinstance(v, list):
                v = "、".join(str(x) for x in v)
            cells.append(f"<td>{esc(str(v))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (f"<table><thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def render_canon_page(name: str, pack_dir: Path) -> str:
    meta = splib.load_json(pack_dir / "pack.json")
    body = [f"<h1>{esc(meta.get('display_name', name))} "
            f"<span class='meta'>v{esc(meta.get('version', '?'))} · "
            f"更新 {esc(meta.get('updated', '?'))}</span></h1>"]
    for fname, label in (("card.md", "卡片"), ("facts.md", "事实源 facts"),
                         ("conventions.md", "写作约定 conventions"),
                         ("sources.md", "来源 sources")):
        p = pack_dir / fname
        if p.is_file():
            body.append(f"<h2>{label}</h2>")
            body.append(md_to_html(splib.read_text(p)[0]))
    ch = pack_dir / "characters.json"
    if ch.is_file():
        c = splib.load_json(ch)
        roster = c.get("roster", [])
        body.append(f"<h2>角色名册（{len(roster)} 人）</h2>")
        rows = "".join(
            f"<tr><td>{esc(str(p.get('name', '')))}</td><td>{esc(str(p.get('tier', '')))}</td>"
            f"<td>{esc(str(p.get('role', '')))}</td><td>{esc(str(p.get('redline', '')))}</td></tr>"
            for p in roster)
        body.append("<table><thead><tr><th>角色</th><th>tier</th><th>定位</th><th>红线/要点</th>"
                    "</tr></thead><tbody>" + rows + "</tbody></table>")
    t = pack_dir / "terms.json"
    if t.is_file():
        terms = splib.load_json(t)
        body.append("<h2>术语判据（terms）</h2>")
        th = terms.get("thresholds") or {}
        if th:
            body.append("<p class='meta'>" +
                        esc("；".join(f"{k}={v}" for k, v in th.items())) + "</p>")
        for key, label in (("must", "must（必须正确使用的术语）"),
                           ("allow", "allow（允许用法）"),
                           ("ban", "ban（禁用/错写）")):
            items = terms.get(key) or []
            body.append(f"<h3>{label}（{len(items)}）</h3>")
            body.append(render_term_table(items))
        if terms.get("allow_note"):
            body.append(f"<p class='meta'>{esc(str(terms['allow_note']))}</p>")
    return layout(f"{meta.get('display_name', name)} canon 包",
                  "\n".join(body), "canon", rel="../../")


def iter_packs(repo: Path) -> list[tuple[Path, bool]]:
    """作者风格包唯一家园枚举：stylepacks/ 顶层 = 公版层；stylepacks/local/ = 本地层。
    死规矩（风格包统一管理-执行规划）：一切消费者只从这里枚举。
    status:"draft"（蒸馏台草稿）不进站点——公开面只见定稿包。"""
    packs_dir = repo / "stylepacks"

    def _published(d: Path) -> bool:
        try:
            return json.loads((d / "pack.json").read_text(encoding="utf-8")
                              ).get("status") != "draft"
        except (OSError, ValueError):
            return True  # 无 status 视为已发布（向后兼容旧包）

    out = [(d, False) for d in sorted(packs_dir.iterdir())
           if d.is_dir() and (d / "pack.json").is_file() and _published(d)]
    local = packs_dir / "local"
    if local.is_dir():
        out += [(d, True) for d in sorted(local.iterdir())
                if d.is_dir() and (d / "pack.json").is_file() and _published(d)]
    return out


def build(out_dir: Path, repo: Path = ROOT) -> Path:
    packs = iter_packs(repo)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "judging").mkdir(exist_ok=True)
    (out_dir / "packs").mkdir(exist_ok=True)
    (out_dir / "style.css").write_text(CSS, encoding="utf-8", newline="\n")

    # 判读数据 = 本机工作数据（含甲乙全文，2026-10-24 起不入库）——
    # 缺失时（CI/新 clone）降级：跳过判读台页，站点其余照建
    jp = repo / "evals" / "human_judging.json"
    if jp.is_file():
        judging_data = splib.load_json(jp)
    else:
        judging_data = None
        print("提示：evals/human_judging.json 不存在——跳过判读台页（本机判读数据，不入库）")
    stamp = datetime.date.today().isoformat()

    (out_dir / "index.html").write_text(layout("门户", f"""<h1>StylePack 本地工作台</h1>
<div class="panel">一台引擎，三张脸：CLI / MCP / <strong>Web</strong> 共用同一套脚本与包文件。
本站为阶段 0（判读 + 浏览），全部渲染在本机完成；判读进度只存本机浏览器（localStorage），
导出 JSON 后由 <code>scripts/score_human_judging.py</code> 对照本机答案卷计分。</div>
<h2>入口</h2>
<ul><li><a href="judging/">盲测人工判读台（8 回合）</a>——解锁同源偏差度量</li>
<li><a href="packs/">风格包浏览 + 测量可视化</a></li>
<li><a href="canon/">canon 包（二创约束）</a></li></ul>
<p class="meta">构建日期：{stamp} · 引文 ≤200 字；语料全文与判读答案永不进入本站点。</p>""", "home"),
                     encoding="utf-8", newline="\n")

    if judging_data is not None:  # 降级：无判读数据不建判读台（入口页链接仍指 /judging/ 由测试按存在性跳过）
        (out_dir / "judging" / "index.html").write_text(
            render_judging(judging_data, stamp), encoding="utf-8", newline="\n")

    cards = []
    for d, is_local in packs:
        meta = splib.load_json(d / "pack.json")
        tier = '<span style="color:var(--bad)">[本地·不得公开再分发]</span> ' if is_local else ""
        href = f"local/{d.name}/" if is_local else f"{d.name}/"
        cards.append(f"""<div class="panel">{tier}<strong><a href="{href}">{esc(meta.get('display_name', d.name))}</a></strong>
<span class="meta">v{esc(meta.get('version', '?'))} · 更新 {esc(meta.get('updated', '?'))} ·
{len(meta.get('corpus', {}).get('works', []))} 篇 {fmt(meta.get('corpus', {}).get('total_chars', 0))} 字
· thought={'✓' if meta.get('thought') else '✗'}</span>
<div class="meta">{esc(str(meta.get('corpus', {}).get('confidence', ''))[:120])}</div></div>""")
    (out_dir / "packs" / "index.html").write_text(
        layout("包浏览", "<h1>风格包</h1>" + "\n".join(cards), "packs", rel="../"),
        encoding="utf-8", newline="\n")

    for d, is_local in packs:
        page = render_pack_page(d.name, d, is_local)
        base = out_dir / "packs" / ("local" if is_local else "")
        (base / d.name).mkdir(parents=True, exist_ok=True)
        (base / d.name / "index.html").write_text(
            page, encoding="utf-8", newline="\n")

    # canon 包（v0.5.0 引入的 canonpacks 类型，v0.5.2 补渲染）
    canon_src = repo / "canonpacks"
    canonpacks = sorted(d for d in canon_src.iterdir()
                        if (d / "pack.json").is_file()) if canon_src.is_dir() else []
    (out_dir / "canon").mkdir(exist_ok=True)
    canon_cards = []
    for d in canonpacks:
        meta = splib.load_json(d / "pack.json")
        canon_cards.append(
            f"""<div class="panel"><strong><a href="{d.name}/">{esc(meta.get('display_name', d.name))}</a></strong>
<span class="meta">canon · v{esc(meta.get('version', '?'))} · 更新 {esc(meta.get('updated', '?'))}</span></div>""")
    if not canon_cards:
        canon_cards.append("<p class='meta'>（仓库内暂无 canonpacks/）</p>")
    (out_dir / "canon" / "index.html").write_text(
        layout("canon 包", "<h1>canon 包（二创约束引导）</h1>" + "\n".join(canon_cards),
               "canon", rel="../"),
        encoding="utf-8", newline="\n")
    for d in canonpacks:
        (out_dir / "canon" / d.name).mkdir(exist_ok=True)
        (out_dir / "canon" / d.name / "index.html").write_text(
            render_canon_page(d.name, d), encoding="utf-8", newline="\n")

    print(f"站点已生成：{out_dir}（{len(packs)} 个风格包 + {len(canonpacks)} 个 canon 包 + 判读台）")
    return out_dir


def main() -> int:
    splib.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="StylePack 阶段 0 静态站点生成器")
    ap.add_argument("--out", default=str(ROOT / "web" / "site"))
    args = ap.parse_args()
    build(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
