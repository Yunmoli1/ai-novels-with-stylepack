# -*- coding: utf-8 -*-
"""routes_distill：蒸馏工作台 API（v0.7.1：阶段 A 入库/指纹/体检 + 阶段 B 采样精读）。

红线落实：
- 每个写操作响应带 cli 字段 = 等价 CLI 命令（插件属性：网页流程必有 CLI 等价）；
- 语料只允许 workspace downloads/corpus 之内（穿越防护）；
- status:"draft" 的包不进入任何消费枚举（创作/站点/项目包下拉），
  只能在本工作台与 /pack 预览，validate 通过并定稿后才对外可见；
- 成本纪律：精读前必走 plan_sampling 预告（N 篇/X 字/预计调用），
  >100k 字自动 map-reduce；账本入 <包>/cost.jsonl（gitignore）。
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

import appstate
import creation
import distillation
import model_client
import routes_create as _rc
import splib  # noqa: E402  # server.py 已把 scripts/ 加入 sys.path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STYLEPACKS = ROOT / "stylepacks"

router = APIRouter(prefix="/app/api/distill")


def _ws(cfg: dict) -> Path:
    return Path(cfg.get("workspace_root") or appstate.ROOT.parent)


def _corpus_root(cfg: dict) -> Path:
    return _ws(cfg) / "downloads" / "corpus"


def _safe_name(name: str, field: str = "名称") -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", (name or "").strip()).strip("-")
    if not s:
        raise HTTPException(400, f"{field}非法（仅限中英文/数字/连字符）")
    return s[:40]


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _corpus_dir(cfg: dict, rel: str) -> Path:
    root = _corpus_root(cfg)
    d = (root / rel).resolve()
    if not _under(d, root) or not d.is_dir():
        raise HTTPException(400, f"语料目录非法或不存在：{rel}")
    return d


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _pack_dir_checked(pack: str) -> Path:
    p = (pack or "").strip()
    if p.startswith("local/"):
        d = STYLEPACKS / "local" / _safe_name(p[len("local/"):], "包名")
    else:
        d = STYLEPACKS / _safe_name(p, "包名")
    if not (d / "pack.json").is_file():
        raise HTTPException(404, f"包不存在或无 pack.json：{pack}")
    return d


def _pack_rel(d: Path) -> str:
    return "stylepacks/" + d.resolve().relative_to(STYLEPACKS.resolve()).as_posix()


def _run_script(script: str, args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


# ---- 语料浏览 ----

@router.get("/corpus")
def corpus_browse():
    """downloads/corpus 下的作者与作品（长篇 chapters/ 布局 + 短篇平铺布局）。"""
    cfg = appstate.load_config()
    root = _corpus_root(cfg)
    if not root.is_dir():
        return {"root": str(root), "authors": []}
    authors = []
    for ad in sorted(root.iterdir()):
        if not ad.is_dir() or ad.name.startswith("_") or ad.name == "legacy-root-corpus":
            continue
        works = []
        for w in sorted(ad.iterdir()):
            if w.is_dir() and (w / "chapters").is_dir():
                works.append({"name": w.name, "layout": "novel", "dir": _rel(w, root),
                              "samples": len(list((w / "chapters").glob("*.md"))),
                              "has_stats": (w / "stats.json").is_file()})
        flat = [f for f in ad.iterdir()
                if f.is_file() and f.suffix.lower() in (".txt", ".md")]
        if flat:
            works.append({"name": "（平铺语料）", "layout": "flat", "dir": _rel(ad, root),
                          "samples": len(flat), "has_stats": False})
        if works:
            authors.append({"name": ad.name, "works": works})
    return {"root": str(root), "authors": authors}


@router.get("/samples")
def samples(dir: str):
    """语料集逐样本指标 + 离群标记（z≥2）：有 stats.json 读缓存，否则现场计算。"""
    cfg = appstate.load_config()
    d = _corpus_dir(cfg, dir)
    rows = []
    stats_path = d / "stats.json"
    if stats_path.is_file():
        stats = splib.load_json(stats_path)
        for ch in stats.get("chapters", []):
            m = ch.get("metrics", {})
            rows.append({
                "file": ch.get("file") or ch.get("title"), "chars": ch.get("chars"),
                "sent_p50": (m.get("sentence_length") or {}).get("p50"),
                "dialogue": (m.get("paragraph") or {}).get("dialogue_para_ratio")})
    else:
        for f in splib.collect_text_files([str(d)]):
            text, _ = splib.read_text(f)
            m = splib.compute_metrics(text)
            rows.append({"file": f.name, "chars": m["chars_total"],
                         "sent_p50": m["sentence_length"]["p50"],
                         "dialogue": m["paragraph"]["dialogue_para_ratio"]})
    for key in ("sent_p50", "dialogue"):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        if len(vals) >= 4:
            mean = sum(vals) / len(vals)
            std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            if std > 0:
                for r in rows:
                    if isinstance(r.get(key), (int, float)):
                        r[f"{key}_z"] = round((r[key] - mean) / std, 2)
    for r in rows:
        r["outlier"] = any(abs(r.get(k, 0)) >= 2
                           for k in ("sent_p50_z", "dialogue_z"))
    return {"dir": dir, "rows": rows,
            "outliers": sum(1 for r in rows if r["outlier"])}


# ---- 入库（raw body 上传，零新依赖）----

@router.post("/ingest")
async def ingest(author: str = Query(...), work: str = Query(""),
                 source_url: str = Query(""), source_date: str = Query(""),
                 notes: str = Query(""), no_strip_ads: bool = Query(False),
                 unwrap: bool = Query(False),
                 filename: str = Query("upload.txt"),
                 body: bytes = Body(b"")):
    """单文件上传入库（前端多文件逐个调用）。body = 原始 txt 字节。"""
    if not body:
        raise HTTPException(400, "空的上传内容")
    if len(body) > 50 * 1024 * 1024:
        raise HTTPException(400, "单文件超 50MB——请拆分后入库")
    if not filename.lower().endswith((".txt", ".md")):
        raise HTTPException(400, "仅支持 .txt/.md")
    cfg = appstate.load_config()
    a = _safe_name(author, "作者名")
    adir = _corpus_root(cfg) / a
    w = _safe_name(work or Path(filename).stem, "作品名")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        inpath = Path(td) / "input.txt"
        inpath.write_bytes(body)
        cmd = [sys.executable, str(SCRIPTS / "ingest.py"), "--input", str(inpath),
               "--out", str(adir), "--work", w]
        if source_url:
            cmd += ["--source-url", source_url]
        if source_date:
            cmd += ["--source-date", source_date]
        if notes:
            cmd += ["--notes", notes]
        if no_strip_ads:
            cmd.append("--no-strip-ads")
        if unwrap:
            cmd.append("--unwrap")
        r = _run_script("ingest.py", cmd[2:], timeout=300)
        if r.returncode != 0:
            raise HTTPException(502, f"ingest 失败：{(r.stderr or r.stdout)[-400:]}")
    prov = splib.load_json(adir / w / "provenance.json")
    rel = _rel(adir / w, _corpus_root(cfg))
    cli = (f'python scripts/ingest.py --input <文件> --out downloads/corpus/{a} '
           f'--work {w}'
           + (f' --source-url {source_url}' if source_url else '')
           + (' --no-strip-ads' if no_strip_ads else '')
           + (' --unwrap' if unwrap else ''))
    return {"ok": True, "work": w, "dir": rel,
            "chapters": prov.get("chapter_count"), "chars": prov.get("total_chars"),
            "encoding": prov.get("original_encoding"),
            "ads_removed": prov.get("ads_removed_lines"), "cli": cli}


# ---- 草稿包 ----

@router.get("/packs")
def packs_list():
    """蒸馏台侧栏的包列表（含草稿——只有创作页/站点/装配枚举才过滤）。"""
    out = []
    if STYLEPACKS.is_dir():
        for d in sorted(STYLEPACKS.iterdir()):
            if d.is_dir() and (d / "pack.json").is_file() and d.name != "local":
                out.append(d.name)
        local = STYLEPACKS / "local"
        if local.is_dir():
            out += [f"local/{x.name}" for x in sorted(local.iterdir())
                    if x.is_dir() and (x / "pack.json").is_file()]
    return {"packs": out}

class PackIn(BaseModel):
    name: str
    display_name: str = ""
    corpus_dir: str = ""  # 语料集相对路径（记入 provenance）


@router.post("/pack")
def pack_create(body: PackIn):
    """创建草稿包（status: draft）——已存在草稿则复用；已存在正式包则 409。"""
    name = _safe_name(body.name, "包名")
    target = STYLEPACKS / name
    pj = target / "pack.json"
    if pj.is_file():
        meta = splib.load_json(pj)
        if meta.get("status") == "draft":
            return {"ok": True, "reused": True, "name": name}
        raise HTTPException(409, f"包 {name} 已存在且已定稿——请换名")
    target.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    scaffold = {
        "format_version": "0.2", "name": name,
        "display_name": body.display_name or name, "language": "zh",
        "genres": [], "registers": False, "version": "0.1.0",
        "created": today, "updated": today, "status": "draft",
        "corpus": {"works": [], "total_chars": 0,
                   "sampling": f"待定（蒸馏台草案，语料集：{body.corpus_dir or '未记录'}）",
                   "confidence": "未定稿（蒸馏台草稿）"},
        # provenance 须为数组、license_note/changelog 必备——validate 硬性字段
        "provenance": [], "license_note": "", "changelog": [],
    }
    pj.write_text(json.dumps(scaffold, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8", newline="\n")
    cli = "python scripts/validate_pack.py " + f"stylepacks/{name}"
    return {"ok": True, "reused": False, "name": name, "cli": cli}


@router.get("/pack")
def pack_preview(pack: str):
    d = _pack_dir_checked(pack)
    meta = splib.load_json(d / "pack.json")
    files = sorted(f.name for f in d.iterdir() if f.is_file())
    return {"name": d.name, "status": meta.get("status", "published"),
            "version": meta.get("version", ""), "files": files,
            "display_name": meta.get("display_name", ""),
            "corpus": meta.get("corpus", {}),
            "provenance": meta.get("provenance", {})}


class FingerprintIn(BaseModel):
    pack: str
    corpus_dir: str
    exclude: list[str] = []


@router.post("/fingerprint")
def fingerprint(body: FingerprintIn):
    """fp_extract（指标存档）+ build_delta --layered（写 fingerprint.json），
    支持 --exclude 离群剔除后重算。零模型调用。"""
    d = _pack_dir_checked(body.pack)
    cfg = appstate.load_config()
    cdir = _corpus_dir(cfg, body.corpus_dir)
    excl = [x for x in body.exclude if x.strip()]
    fp_json = d / "fp_extract.json"  # 工作数据（分析存档，非定稿物）
    r1 = _run_script("fp_extract.py", [str(cdir), "--json", str(fp_json), "--exclude", *excl])
    r2 = _run_script("build_delta.py", [str(cdir), "--pack", str(d), "--layered",
                                        "--exclude", *excl])
    if r2.returncode != 0:
        raise HTTPException(502, f"build_delta 失败：{(r2.stderr or r2.stdout)[-400:]}")
    fp = splib.load_json(d / "fingerprint.json")
    profile = fp.get("delta_profile") or {}
    layers = []
    for g, layer in sorted((fp.get("genres") or {}).items()):
        layers.append({"genre": g, "samples": layer.get("samples", []),
                       "n": len(layer.get("samples", []))})
    self_check = fp.get("self_check") or {}
    sc = [{"genre": g, "delta_max": v.get("delta_max"),
           "calibratable": v.get("delta_max") is not None}
          for g, v in sorted(self_check.items())]
    cli = (f'python scripts/fp_extract.py downloads/corpus/{body.corpus_dir} '
           f'--json stylepacks/{d.name}/fp_extract.json'
           + (" --exclude " + " ".join(excl) if excl else "")
           + f'\npython scripts/build_delta.py downloads/corpus/{body.corpus_dir} '
           + f'--pack stylepacks/{d.name} --layered'
           + (" --exclude " + " ".join(excl) if excl else ""))
    return {"ok": True, "n_samples": profile.get("n_samples", 0),
            "layers": layers, "self_check": sc,
            "excluded": excl, "fp_extract_report": (r1.stdout or "")[-1200:],
            "cli": cli}


class ValidateIn(BaseModel):
    pack: str


@router.post("/validate")
def validate_pack(body: ValidateIn):
    d = _pack_dir_checked(body.pack)
    r = _run_script("validate_pack.py", [str(d)], timeout=300)
    return {"exit_code": r.returncode, "report": (r.stdout or "") + (r.stderr or ""),
            "ok": r.returncode == 0,
            "cli": f"python scripts/validate_pack.py {_pack_rel(d)}"}


# ---- 阶段 B：采样精读（模型调用，D3=写作路由；纪律：先预告后烧）----

def _sample_rows(cfg: dict, rel: str, exclude: list[str] | None = None) -> list[dict]:
    d = _corpus_dir(cfg, rel)
    excl = set(exclude or [])
    rows = []
    stats_path = d / "stats.json"
    if stats_path.is_file():
        stats = splib.load_json(stats_path)
        for ch in stats.get("chapters", []):
            fname = ch.get("file") or ch.get("title")
            if fname in excl:
                continue
            m = ch.get("metrics", {})
            rows.append({"file": fname, "chars": ch.get("chars", 0),
                         "sent_p50": (m.get("sentence_length") or {}).get("p50"),
                         "dialogue": (m.get("paragraph") or {}).get("dialogue_para_ratio")})
    else:
        for f in splib.collect_text_files([str(d)]):
            if f.name in excl:
                continue
            text, _ = splib.read_text(f)
            m = splib.compute_metrics(text)
            rows.append({"file": f.name, "chars": m["chars_total"],
                         "sent_p50": m["sentence_length"]["p50"],
                         "dialogue": m["paragraph"]["dialogue_para_ratio"]})
    return rows


class SamplingIn(BaseModel):
    corpus_dir: str
    exclude: list[str] = []


@router.post("/plan_sampling")
def plan_sampling(body: SamplingIn):
    """自动选样（首/中/尾/对话密集/叙述密集，上限 8）+ 成本预告——
    烧模型前必走此步：N 篇/X 字/预计调用与 tokens（技能 2.1 纪律网页化）。"""
    cfg = appstate.load_config()
    rows = _sample_rows(cfg, body.corpus_dir, body.exclude)
    selection = distillation.plan_sampling(rows)
    total = sum(r["chars"] or 0 for r in selection)
    mode = "single" if total <= distillation.READ_SINGLE_MAX else "map"
    chunks = 1 if mode == "single" else max(
        1, -(-total // distillation.CHUNK_CHARS))
    est_tokens = int(total * 0.75) + distillation.READ_MAX_TOKENS * chunks
    return {"selection": selection, "total_chars": total, "mode": mode,
            "chunks": chunks, "est_calls": chunks, "est_tokens": est_tokens,
            "limits": {"single_max": distillation.READ_SINGLE_MAX,
                       "chunk_chars": distillation.CHUNK_CHARS}}


class ReadIn(BaseModel):
    pack: str
    corpus_dir: str
    files: list[str] = []


def _distill_call(cfg: dict, sid: str, prompt: str, max_tokens: int) -> dict:
    base, key, model = _rc._resolve_model(cfg, "write")  # D3：蒸馏用写作路由
    _rc._guard(cfg, sid, int(len(prompt) * 0.8) + max_tokens)
    try:
        result = model_client.chat(base, key, model,
                                   [{"role": "system",
                                     "content": distillation.SYSTEM_READ},
                                    {"role": "user", "content": prompt}],
                                   temperature=distillation.READ_TEMPERATURE,
                                   max_tokens=max_tokens)
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    _rc._record_usage(sid, result)
    return result


def _pack_cost(pack_dir: Path, usage: dict, note: str) -> None:
    """蒸馏账本：stylepacks/<包>/cost.jsonl（gitignore，不进仓库）。"""
    entry = {"date": datetime.date.today().isoformat(), "skill": "web-distill",
             "model": usage.get("model", ""),
             "tokens": (usage.get("prompt_tokens", 0)
                        + usage.get("completion_tokens", 0)),
             "note": note}
    with (pack_dir / "cost.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---- job 运行器（v0.7.3）：长任务后台线程 + 进度轮询；同步端点保留（CLI 等价）----

_jobs: dict[str, dict] = {}


_job_ctx = threading.local()


def _cur_job() -> dict | None:
    return getattr(_job_ctx, "v", None)


def _run_job(kind: str, fn, payload: dict) -> str:
    """启动后台 job（本地单用户；daemon 线程）。fn(payload, job) 内更新 job["step"]。"""
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "kind": kind, "status": "running", "step": "启动",
           "log": [], "result": None, "error": None}
    _jobs[jid] = job

    def wrapper():
        _job_ctx.v = job
        try:
            job["result"] = fn(payload, job)
            job["status"] = "done"
            job["step"] = "完成"
        except HTTPException as exc:
            job.update(status="error", error=str(exc.detail))
        except Exception as exc:  # noqa: BLE001
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")

    threading.Thread(target=wrapper, daemon=True).start()
    return jid


@router.get("/job/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job 不存在（或服务已重启——job 只在内存）")
    return job


def _read_job(payload: dict, job: dict) -> dict:
    return read_samples(ReadIn(**payload))


def _gen_draft_job(payload: dict, job: dict) -> dict:
    return gen_draft(GenDraftIn(**payload))


@router.post("/read_start")
def read_start(body: ReadIn):
    return {"job_id": _run_job("read", _read_job, body.model_dump())}


@router.post("/gen_draft_start")
def gen_draft_start(body: GenDraftIn):
    return {"job_id": _run_job("gen_draft", _gen_draft_job, body.model_dump())}


@router.post("/read")
def read_samples(body: ReadIn):
    """精读选样（≤100k 字单次；超出自动 map-reduce）→ analysis.json（工作数据，
    gitignore；不定稿入包）。提案是模型的，指纹/motif 数字仍是脚本的。"""
    if not body.files:
        raise HTTPException(400, "选样为空——先自动选样或勾选文件")
    cfg = appstate.load_config()
    cdir = _corpus_dir(cfg, body.corpus_dir)
    collected = {f.name: f for f in splib.collect_text_files([str(cdir)])}
    bad = [f for f in body.files if f not in collected]
    if bad:
        raise HTTPException(400, f"选样不在语料集内：{'、'.join(bad[:3])}")
    samples = [(name, splib.read_text(collected[name])[0]) for name in body.files]
    total = sum(len(t) for _, t in samples)
    pack_dir = _pack_dir_checked(body.pack)
    sid = f"distill-{uuid.uuid4().hex[:8]}"
    usage_total: dict = {}
    if total <= distillation.READ_SINGLE_MAX:
        if _cur_job():
            _cur_job()["step"] = "模型精读中（单次注入，思考型模型约 1–3 分钟）"
        result = _distill_call(cfg, sid, distillation.read_prompt(samples),
                               distillation.READ_MAX_TOKENS)
        analysis = creation.extract_json(result["text"])
        mode = "single"
        usage_total = result
    else:
        chunks = distillation.chunk_files(samples)
        obs = []
        for i, chunk in enumerate(chunks, 1):
            if _cur_job():
                _cur_job()["step"] = f"分块观察 {i}/{len(chunks)}（每块 ≤800 字摘要）"
            r = _distill_call(cfg, sid, distillation.chunk_prompt(chunk),
                              distillation.OBS_MAX_TOKENS)
            obs.append(creation.extract_json(r["text"]))
        if _cur_job():
            _cur_job()["step"] = "主汇总融合中"
        result = _distill_call(cfg, sid, distillation.reduce_prompt(obs),
                               distillation.READ_MAX_TOKENS)
        analysis = creation.extract_json(result["text"])
        mode = "map"
        usage_total = result
    record = {"pack": pack_dir.name,
              "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
              "mode": mode, "files": body.files, "total_chars": total,
              "usage": {"prompt_tokens": usage_total.get("prompt_tokens", 0),
                        "completion_tokens": usage_total.get("completion_tokens", 0),
                        "model": usage_total.get("model", "")},
              "analysis": analysis}
    (pack_dir / "analysis.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    _pack_cost(pack_dir, record["usage"],
               f"精读 {len(body.files)} 篇 {total} 字（{mode}）")
    return {"ok": True, "mode": mode, "analysis": analysis,
            "usage": record["usage"], "files": body.files,
            "cli": "技能路径：style-analyze（分层采样精读，六问题+思想四问；"
                   "网页端以写作路由完成同一流程）"}


class AnalysisIn(BaseModel):
    pack: str
    analysis: dict


@router.get("/analysis")
def analysis_get(pack: str):
    d = _pack_dir_checked(pack)
    p = d / "analysis.json"
    if not p.is_file():
        raise HTTPException(404, "该包还没有精读记录（analysis.json）")
    return splib.load_json(p)


@router.post("/analysis")
def analysis_save(body: AnalysisIn):
    """人工校订后的分析存档（工作数据，可编辑重跑；不定稿入包）。"""
    d = _pack_dir_checked(body.pack)
    record = (splib.load_json(d / "analysis.json")
              if (d / "analysis.json").is_file() else {})
    record["analysis"] = body.analysis
    record["edited_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    (d / "analysis.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    return {"ok": True}


# ---- 阶段 C：草案生成 + 逐节校订 + 定稿 ----

EDITABLE_FILES = {"card.md", "profile.md", "exemplars.md", "lexicon.md",
                  "limits.md", "thought.md", "tests/blind-prompts.md"}


class PackOnly(BaseModel):
    pack: str


@router.post("/preview_draft")
def preview_draft(body: PackOnly):
    """草案生成成本预告：N 次调用（范例/九章/三件套/思想可选）+ tokens 估算。"""
    d = _pack_dir_checked(body.pack)
    rec = (splib.load_json(d / "analysis.json")
           if (d / "analysis.json").is_file() else None)
    if not rec:
        raise HTTPException(404, "先跑阶段 B 精读（analysis.json 不存在）")
    total = int(rec.get("total_chars") or 0)
    calls = 4  # 范例 / 九章 profile / 三件套 / card 内含
    est = int(total * 0.75) + distillation.EXEMPLARS_MAX_TOKENS \
        + distillation.PROFILE_MAX_TOKENS + distillation.TRIO_MAX_TOKENS
    return {"est_calls": calls, "est_tokens": est, "mode_hint": "逐文件低温生成",
            "note": "另可选生成 thought.md（+1 次调用）；motif 验证是脚本不计费"}


class GenDraftIn(BaseModel):
    pack: str
    corpus_dir: str
    include_thought: bool = True


@router.post("/gen_draft")
def gen_draft(body: GenDraftIn):
    """草案生成：范例（引文逐字校验，伪造整条剔除）→ 九章 profile（引用范例
    序号）→ card/lexicon/limits 三件套 → thought（可选）→ motif_count --write
    → pack.json 补全（诚实 corpus/provenance）。提案是模型的，校验是脚本的。"""
    d = _pack_dir_checked(body.pack)
    rec_path = d / "analysis.json"
    if not rec_path.is_file():
        raise HTTPException(404, "先跑阶段 B 精读（analysis.json 不存在）")
    rec = splib.load_json(rec_path)
    analysis = rec.get("analysis") or {}
    files = rec.get("files") or []
    cfg = appstate.load_config()
    cdir = _corpus_dir(cfg, body.corpus_dir)
    collected = {f.name: f for f in splib.collect_text_files([str(cdir)])}
    samples = [(n, splib.read_text(collected[n])[0]) for n in files if n in collected]
    if not samples:
        raise HTTPException(400, "精读记录的选样文件已不在语料集——请重跑阶段 B")
    corpus_text = "\n".join(t for _, t in samples)
    sid = f"distill-{uuid.uuid4().hex[:8]}"
    spend = {"prompt_tokens": 0, "completion_tokens": 0}
    report: list[dict] = []

    def call(name: str, prompt: str, max_tokens: int) -> str:
        if _cur_job():
            _cur_job()["step"] = f"{name} 生成中（低温）"
        r = _distill_call(cfg, sid, prompt, max_tokens)
        spend["prompt_tokens"] += r.get("prompt_tokens", 0)
        spend["completion_tokens"] += r.get("completion_tokens", 0)
        report.append({"file": name, "completion_tokens": r.get("completion_tokens", 0)})
        return r["text"]

    # 1) 范例（引文逐字校验）
    ex_md = call("exemplars.md",
                 distillation.exemplars_prompt(analysis, samples),
                 distillation.EXEMPLARS_MAX_TOKENS)
    ex_md, dropped, labels = distillation.verify_exemplar_quotes(ex_md, corpus_text)
    (d / "exemplars.md").write_text(ex_md, encoding="utf-8", newline="\n")

    # 2) 九章 profile（引用范例序号）
    fp = splib.load_json(d / "fingerprint.json") if (d / "fingerprint.json").is_file() else {}
    sl = ((fp.get("genres") or {}).get("narrative", {}).get("metrics")
          or {}).get("sentence_length", {})
    metrics_note = (f"句长 P50={sl.get('p50', {}).get('target', '实测值')}、"
                    f"P25={sl.get('p25', {}).get('target', '—')}、"
                    f"P75={sl.get('p75', {}).get('target', '—')}（build_delta 实测）")
    (d / "profile.md").write_text(
        call("profile.md",
             distillation.profile_prompt(analysis, ex_md, metrics_note),
             distillation.PROFILE_MAX_TOKENS),
        encoding="utf-8", newline="\n")

    # 3) card/lexicon/limits 三件套（JSON 包装）
    top_chars: list[str] = []
    fp_ext = d / "fp_extract.json"
    if fp_ext.is_file():
        tc = splib.load_json(fp_ext).get("top_chars") or []
        # fp_extract 的 top_chars 是 [{char, per_1k}...] 列表（真语料实测形态）
        top_chars = ([x.get("char", "") for x in tc if isinstance(x, dict)]
                     if isinstance(tc, list) else list(tc.keys()))
    trio = creation.extract_json(call(
        "card+lexicon+limits",
        distillation.trio_prompt(analysis, top_chars, ex_md),
        distillation.TRIO_MAX_TOKENS))
    for key, fname in (("card_md", "card.md"), ("lexicon_md", "lexicon.md"),
                       ("limits_md", "limits.md")):
        (d / fname).write_text(str(trio.get(key) or ""), encoding="utf-8",
                               newline="\n")

    # 4) thought（可选）+ motif 脚本验证
    motif_report = ""
    if body.include_thought:
        (d / "thought.md").write_text(
            call("thought.md", distillation.thought_prompt(analysis),
                 distillation.THOUGHT_MAX_TOKENS),
            encoding="utf-8", newline="\n")
        if _cur_job():
            _cur_job()["step"] = "motif 词表脚本验证中"
        mc = _run_script("motif_count.py", [str(cdir), "--pack", str(d), "--write"],
                         timeout=300)
        motif_report = (mc.stdout or "") + (mc.stderr or "")
        if mc.returncode != 0:
            motif_report += "（motif 验证失败不阻塞草案——可修词表行后重跑）"

    # 5) pack.json 补全（诚实 corpus/provenance）
    meta = splib.load_json(d / "pack.json")
    works = []
    total_chars = 0
    for w in sorted(cdir.iterdir()):
        if w.is_dir() and (w / "provenance.json").is_file():
            prov = splib.load_json(w / "provenance.json")
            works.append(w.name)
            total_chars += int(prov.get("total_chars") or 0)
            meta.setdefault("provenance", []).append({
                "type": "ingest", "work": w.name,
                "url": prov.get("source_url", ""),
                "fetched_at": prov.get("fetched_at", ""),
                "notes": f"原编码 {prov.get('original_encoding', '?')}；"
                         f"去广告 {prov.get('ads_removed_lines', 0)} 行"})
    if not works:  # 平铺语料：作者目录即语料集
        works = [cdir.name]
        total_chars = sum(r["chars"] for r in
                          _sample_rows(cfg, body.corpus_dir))
        meta.setdefault("provenance", []).append({
            "type": "ingest", "work": cdir.name, "url": "", "fetched_at": "",
            "notes": "平铺语料（逐文件 provenance 见语料目录）"})
    meta["corpus"] = {"works": works, "total_chars": total_chars,
                      "sampling": f"分层采样精读 {len(files)} 篇（自动选样："
                                  f"首/中/尾/对话密集/叙述密集）",
                      "confidence": "低（新蒸馏草案，未盲测）"}
    meta["thought"] = bool(body.include_thought)
    splib.dump_json(meta, d / "pack.json")
    _pack_cost(d, spend, f"草案生成（thought={body.include_thought}）")
    return {"ok": True, "files": [r["file"] for r in report], "report": report,
            "quotes_dropped": dropped, "quotes_dropped_labels": labels,
            "motif_report": motif_report[-800:], "usage": spend,
            "cli": "技能路径：style-analyze 步 3（九章草案 → motif_count --write）"}


@router.get("/file")
def file_get(pack: str, name: str):
    if name not in EDITABLE_FILES:
        raise HTTPException(400, f"该文件不在可编辑清单：{name}")
    d = _pack_dir_checked(pack)
    p = d / name
    if not p.is_file():
        raise HTTPException(404, f"{name} 不存在（先草案生成）")
    return {"name": name, "content": p.read_text(encoding="utf-8")}


class FileIn(BaseModel):
    pack: str
    name: str
    content: str


@router.post("/file")
def file_save(body: FileIn):
    """逐节校订：人工编辑档案文件（白名单内；thought 需草案期勾选生成）。"""
    if body.name not in EDITABLE_FILES:
        raise HTTPException(400, f"该文件不在可编辑清单：{body.name}")
    d = _pack_dir_checked(body.pack)
    (d / body.name).write_text(body.content, encoding="utf-8", newline="\n")
    return {"ok": True}


class PublishIn(BaseModel):
    pack: str
    tier: str = "public"  # public | local
    license_note: str = ""
    confidence: str = "低（新蒸馏，未盲测）"


@router.post("/publish")
def publish(body: PublishIn):
    """定稿：validate 必须通过；按层落位（公版顶层 / 本地 local 层）并置
    status: published——此后创作页/站点/装配可见。"""
    d = _pack_dir_checked(body.pack)
    v = _run_script("validate_pack.py", [str(d)], timeout=300)
    if v.returncode != 0:
        raise HTTPException(400, "validate 未通过，定稿被拒绝：\n"
                                 + ((v.stdout or "") + (v.stderr or ""))[-900:])
    meta = splib.load_json(d / "pack.json")
    meta.pop("status", None)
    meta["corpus"]["confidence"] = body.confidence or "低（新蒸馏，未盲测）"
    if body.tier == "local":
        meta["license_note"] = (body.license_note
                                or "本地层：含受版权语料的分析，不得公开再分发")
    today = datetime.date.today().isoformat()
    meta.setdefault("changelog", []).append(
        {"version": meta.get("version", "0.1.0"), "date": today,
         "changes": "蒸馏台定稿（阶段 C）"})
    splib.dump_json(meta, d / "pack.json")
    if body.tier == "local":
        local = STYLEPACKS / "local"
        local.mkdir(exist_ok=True)
        target = local / d.name
        if target.exists():
            raise HTTPException(409, f"local 层已有同名包：{d.name}")
        d = d.rename(target)
    return {"ok": True, "path": _pack_rel(d),
            "visible": "创作页包下拉 / 包浏览站点 / 装配（钉扎即用）",
            "cli": f"python scripts/validate_pack.py {_pack_rel(d)}；"
                   f"手动定稿 = 编辑 pack.json 去 status 字段（local 层再移动目录）"}


# ---- 盲测验收 v2（v0.13.2）：多臂参数化（风格/canon/混合/裸）+ 轮数/题库
# 可选 + 胜率分轨（style/canon 独立测量——判定纪律：单维度结论不可终判）。
# 会话格式 v2：rounds[].segments=[{label, arm, text}]（arm 绝不进判读视图）；
# 旧格式（甲/乙+packed 键）按 legacy 路径判读，向后兼容。

BLIND_ROUNDS = 3
BLIND_ARMS = ("style", "canon", "both", "plain")
CANONPACKS = ROOT / "canonpacks"


def _blind_session_path(pack_dir: Path) -> Path:
    return pack_dir / "tests" / "blind-session.json"


def _pack_ctx(pack_dir: Path) -> str:
    """带包臂注入的档案上下文（card+profile+lexicon 禁用+limits，截 6k 字）。"""
    parts = []
    for name in ("card.md", "profile.md", "lexicon.md", "limits.md"):
        f = pack_dir / name
        if f.is_file():
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
    return ("\n\n".join(parts))[:6000]


def _canon_ctx(canon_dir: Path) -> str:
    """canon 臂注入的锚定上下文（card + must/ban 术语表，截 6k 字）。"""
    parts = []
    card = canon_dir / "card.md"
    if card.is_file():
        parts.append(card.read_text(encoding="utf-8", errors="replace"))
    terms = canon_dir / "terms.json"
    if terms.is_file():
        try:
            t = splib.load_json(terms)
            must = [x.get("term") for x in t.get("must", []) if isinstance(x, dict)]
            ban = [x.get("term") for x in t.get("ban", []) if isinstance(x, dict)]
            parts.append("must（按自然方式落实）：" + ("、".join(must) or "无")
                         + "\nban（绝对不出现）：" + ("、".join(ban) or "无"))
        except (OSError, ValueError):
            pass
    return ("\n\n".join(parts))[:6000]


def _parse_topics(md: str) -> list[dict]:
    """解析 blind-prompts.md：题号/标题/提示/期望特征。"""
    topics = []
    for block in re.split(r"^##\s+", md, flags=re.M)[1:]:
        lines = block.splitlines()
        title = lines[0].strip()
        prompt, checklist, mode = "", [], "head"
        for ln in lines[1:]:
            if ln.startswith("提示："):
                prompt = ln[len("提示："):].strip()
                mode = "chk"
            elif mode == "chk" and ln.strip().startswith("-"):
                checklist.append(ln.strip().lstrip("- [ ]").strip())
        topics.append({"title": title, "prompt": prompt, "checklist": checklist})
    return [t for t in topics if t["prompt"]]


def _blind_run(payload: dict, job: dict) -> dict:
    """盲测对局生成 v2：无题库先出题 → 每题按臂位各生成一段 → 段间打乱
    标甲乙丙丁 → blind-session.json（v2 格式：segments 带 arm，判读视图剥离）。"""
    pack_dir = _pack_dir_checked(payload["pack"])
    arms = payload.get("arms") or ["style", "plain"]
    arms = [a for a in arms if a in BLIND_ARMS]
    seen = list(dict.fromkeys(arms))
    if len(seen) < 2:
        raise HTTPException(400, "臂位至少 2 个（盲测需要对比）")
    canon_name = payload.get("canon_pack")
    if ("canon" in seen or "both" in seen) and not canon_name:
        raise HTTPException(400, "臂位含 canon/both 时必须选 canon 包")
    canon_dir = CANONPACKS / canon_name if canon_name else None
    if canon_dir is not None and not (canon_dir / "pack.json").is_file():
        raise HTTPException(400, f"canon 包不存在：{canon_name}")
    rounds_n = max(1, min(8, int(payload.get("rounds") or BLIND_ROUNDS)))
    topic_ids = [int(x) for x in (payload.get("topic_ids") or []) if int(x) >= 1]
    cfg = appstate.load_config()
    sid = f"blind-{uuid.uuid4().hex[:8]}"
    (pack_dir / "tests").mkdir(exist_ok=True)
    topics_md = pack_dir / "tests" / "blind-prompts.md"
    if not topics_md.is_file():
        if job:
            job["step"] = "出题中（按文风档案设计 3 道盲测题）"
        r = _distill_call(cfg, sid,
                          distillation.blind_topics_prompt(
                              _pack_ctx(pack_dir)),
                          distillation.BLIND_TOPIC_MAX_TOKENS)
        topics_md.write_text(r["text"], encoding="utf-8", newline="\n")
    topics = _parse_topics(topics_md.read_text(encoding="utf-8"))
    if topic_ids:
        topics = [t for i, t in enumerate(topics, 1) if i in topic_ids]
        if not topics:
            raise HTTPException(400, "题库勾选为空——至少勾一道题")
    topics = topics[:rounds_n]
    if not topics:
        raise HTTPException(400, "blind-prompts.md 无可解析题目（格式：## 题 N + 提示：）")
    pack_ctx = _pack_ctx(pack_dir)
    canon_ctx = _canon_ctx(canon_dir) if canon_dir else ""

    def _call(prompt: str) -> str:
        r = _distill_call(cfg, sid, prompt,
                          distillation.BLIND_GEN_MAX_TOKENS)
        spend["prompt_tokens"] += r.get("prompt_tokens", 0)
        spend["completion_tokens"] += r.get("completion_tokens", 0)
        return r["text"].strip()

    spend = {"prompt_tokens": 0, "completion_tokens": 0}
    import random
    rounds = []
    for i, t in enumerate(topics, 1):
        if job:
            job["step"] = f"第 {i}/{len(topics)} 轮对局生成（{len(seen)} 臂）"
        topic_prompt = f"提示：{t['prompt']}"
        segs = []
        for a in seen:
            if a == "style":
                prompt = distillation.blind_packed_prompt(topic_prompt, pack_ctx)
            elif a == "canon":
                prompt = distillation.blind_canon_prompt(topic_prompt, canon_ctx)
            elif a == "both":
                prompt = distillation.blind_both_prompt(topic_prompt,
                                                        pack_ctx, canon_ctx)
            else:
                prompt = distillation.blind_plain_prompt(topic_prompt)
            segs.append({"arm": a, "text": _call(prompt)})
        random.shuffle(segs)
        for lab, s in zip("甲乙丙丁", segs):
            s["label"] = lab
        rounds.append({"no": i, "title": t["title"], "prompt": t["prompt"],
                       "checklist": t["checklist"], "segments": segs,
                       "choice": None})
    session = {"pack": pack_dir.name, "canon_pack": canon_name,
               "arms": seen, "created": datetime.datetime.now().isoformat(
                   timespec="seconds"),
               "rounds": rounds, "results": None, "v": 2}
    _blind_session_path(pack_dir).write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    _pack_cost(pack_dir, spend, f"盲测对局 {len(rounds)} 轮×{len(seen)} 臂")
    return {"ok": True, "rounds": len(rounds), "arms": seen}


class BlindIn(BaseModel):
    pack: str
    canon_pack: str | None = None
    arms: list[str] = ["style", "plain"]
    rounds: int = 3
    topic_ids: list[int] = []  # 1-based 题 N 勾选；空=取前 N 题


@router.post("/blind/start")
def blind_start(body: BlindIn):
    return {"job_id": _run_job("blind", _blind_run, body.model_dump())}


def _view_round_v2(r: dict) -> dict:
    """判读视图剥臂（防泄漏）：只给 label+text。"""
    return {"no": r["no"], "title": r["title"], "prompt": r["prompt"],
            "checklist": r.get("checklist", []),
            "segments": [{"label": s["label"], "text": s["text"]}
                         for s in r["segments"]]}


@router.get("/blind/session")
def blind_session(pack: str):
    """判读视图：绝不含臂位标记（防泄漏）。legacy 会话走旧视图。"""
    d = _pack_dir_checked(pack)
    p = _blind_session_path(d)
    if not p.is_file():
        raise HTTPException(404, "还没有盲测对局——先生成")
    s = splib.load_json(p)
    view = {"pack": s["pack"], "done": s.get("results") is not None,
            "arms": s.get("arms") or ["style", "plain"]}
    if s.get("results"):
        view["results"] = s["results"]  # 已判完：揭示
    else:
        judged = sum(1 for r in s["rounds"] if r.get("choice") is not None)
        view["progress"] = f"{judged}/{len(s['rounds'])}"
    if s["rounds"] and "segments" in s["rounds"][0]:  # v2
        view["rounds"] = [_view_round_v2(r) for r in s["rounds"]
                          if r.get("choice") is None]
    else:  # legacy（v0.8.0 旧会话）
        view["legacy"] = True
        view["rounds"] = [{k: r[k] for k in ("no", "title", "prompt",
                                             "checklist", "甲", "乙")}
                          for r in s["rounds"] if r.get("choice") is None]
    return view


class BlindJudgeIn(BaseModel):
    pack: str
    round_no: int
    choice: str  # 甲/乙/丙/丁 | 都不像


@router.post("/blind/judge")
def blind_judge(body: BlindJudgeIn):
    d = _pack_dir_checked(body.pack)
    p = _blind_session_path(d)
    if not p.is_file():
        raise HTTPException(404, "还没有盲测对局")
    s = splib.load_json(p)
    if s.get("results"):
        raise HTTPException(409, "本轮盲测已判完（重新生成对局可再测）")
    r = next((x for x in s["rounds"] if x["no"] == body.round_no), None)
    if not r:
        raise HTTPException(404, f"没有第 {body.round_no} 轮")
    if r.get("choice"):
        raise HTTPException(409, f"第 {body.round_no} 轮已判定")
    labels = ([sg["label"] for sg in r["segments"]] if "segments" in r
              else ["甲", "乙"])
    if body.choice not in (*labels, "都不像"):
        raise HTTPException(400, f"choice 须为 {'/'.join(labels)}/都不像")
    r["choice"] = body.choice
    if all(x.get("choice") for x in s["rounds"]):
        if "segments" in r:  # v2 分轨计分
            tracks: dict = {}
            for x in s["rounds"]:
                for sg in x["segments"]:
                    tr = tracks.setdefault(sg["arm"], {"wins": 0, "n": 0})
                    tr["n"] += 1
                if x["choice"] != "都不像":
                    win = next(sg for sg in x["segments"]
                               if sg["label"] == x["choice"])
                    tracks[win["arm"]]["wins"] += 1
            for tr in tracks.values():
                tr["rate"] = round(tr["wins"] / tr["n"], 2) if tr["n"] else 0
            st = tracks.get("style", {})
            hits, total = st.get("wins", 0), st.get("n", 0)
            s["results"] = {
                "win_rate": round(hits / total, 2) if total else 0,
                "hits": hits, "total": total, "tracks": tracks,
                "per_round": [{"no": x["no"], "choice": x["choice"],
                               "winner": next((sg["arm"] for sg in x["segments"]
                                               if sg["label"] == x["choice"]),
                                              "都不像")}
                              for x in s["rounds"]]}
        else:  # legacy
            hits = sum(1 for x in s["rounds"] if x["choice"] == x["packed"])
            s["results"] = {
                "win_rate": round(hits / len(s["rounds"]), 2), "hits": hits,
                "total": len(s["rounds"]),
                "per_round": [{"no": x["no"], "packed": x["packed"],
                               "choice": x["choice"]} for x in s["rounds"]]}
        # 胜率入 calibration（evals/ 与判读台同账本）
        cal_path = ROOT / "evals" / "calibration.json"
        try:
            cal = splib.load_json(cal_path) if cal_path.is_file() else {}
            cal[f"web_blind_{d.name}_{datetime.date.today():%Y%m%d}"] = {
                "win_rate": s["results"]["win_rate"],
                "hits": s["results"]["hits"], "total": s["results"]["total"],
                "tracks": s["results"].get("tracks"),
                "via": "蒸馏台网页盲测"}
            splib.dump_json(cal, cal_path)
        except (OSError, ValueError):
            pass  # 账本写失败不影响判读结果
    _blind_session_path(d).write_text(
        json.dumps(s, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    return {"ok": True, "finished": s.get("results") is not None,
            "results": s.get("results")}
