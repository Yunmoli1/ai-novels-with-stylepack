# -*- coding: utf-8 -*-
"""distillation：蒸馏台阶段 B——采样与精读的提示词与选样算法。

纪律（style-analyze 技能 2/2.1 节网页化）：
- 精读只回答问题，严禁全文复述；范例引文到草案阶段才定点取；
- 每个判断尽量溯源到具体篇目，不可溯源的条目在草案阶段删除；
- ≤100k 字单次注入；超出自动 map-reduce（块摘要 ≤800 字，主汇总只读摘要）。
- 提案是模型的，数字是脚本的（motif/指纹仍由脚本验证）。
"""
from __future__ import annotations

import json
import re

READ_SINGLE_MAX = 100_000  # 字：单次精读上限，超出走 map-reduce
CHUNK_CHARS = 60_000       # map 块的字数预算
READ_MAX_TOKENS = 2600     # 精读 JSON 输出上限
OBS_MAX_TOKENS = 1200      # 块观察输出上限
READ_TEMPERATURE = 0.3     # 分析任务低温

SYSTEM_READ = ("你是严谨的文风分析师。只依据给出的语料文本作答，每个判断尽量能"
               "指认到具体篇目；不做语料中无依据的断言。所有输出必须是可解析 JSON，"
               "不要寒暄、不要解释流程。")

_READ_SCHEMA = ('{{"视角": "", "节奏": "", "对话": "", "场景": "", "情绪": "", '
                '"手法": [{{"手法": "", "依据": ""}}], '
                '"选择": "", "立意动作": [{{"动作": "", "依据": ""}}], '
                '"细节": "", "意象族": ["词1"]}}')


def _body(samples: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"【{name}】\n{text}" for name, text in samples)


def read_prompt(samples: list[tuple[str, str]]) -> str:
    """单次精读（≤100k 字）：六问题（写法层）+ 思想四问（选择层）。"""
    return f"""请精读以下 {len(samples)} 篇语料（同一位作者），回答十个问题。

六问题（写法层）：
1. 叙事视角与人称
2. 句子如何制造节奏（长短/停顿/排比等具体手段）
3. 对话如何区分人物（措辞/句式/口癖）
4. 场景如何转换
5. 情绪如何外化（不直呼情绪时的载体）
6. 标志性手法清单（逐条给依据篇目）

思想四问（选择层）：
A. 作者选择写什么、拒绝写什么
B. 从题材到角度的招式（立意动作，逐条给动作名 + 依据篇目）
C. 作者的眼睛反复落在哪几类细节上
D. 反复出现的意象族（提案词表：文本中字面反复出现的词，10–30 个）

只输出 JSON：
{_READ_SCHEMA}

——语料——
{_body(samples)}"""


def chunk_prompt(samples: list[tuple[str, str]]) -> str:
    """map 块观察（≤800 字五项，只看自己那块）。"""
    return f"""以下是某作者语料中的一块（{len(samples)} 篇）。只依据文本输出不超过 800 字的观察 JSON：
{{"视角": "", "节奏": "", "对话": "", "场景": "", "手法": ["……"]}}

——文本——
{_body(samples)}"""


def reduce_prompt(observations: list[dict]) -> str:
    """reduce 主汇总：只读块摘要融合为最终答案；无据可提的思想四问置空，不得编造。"""
    obs = json.dumps(observations, ensure_ascii=False, indent=1)
    return f"""以下是对同一位作者语料分块精读后的 {len(observations)} 份观察摘要。
请融合为最终答案（思想四问若摘要无据可提，相应字段置空字符串/空数组，不得编造）。

只输出 JSON：
{_READ_SCHEMA}

——分块观察——
{obs}"""


def plan_sampling(rows: list[dict]) -> list[dict]:
    """自动选样：首/中/尾各 1–2 + 对话密集 1 + 叙述密集 1（去重，上限 8）。
    rows 须已按语料顺序排列，元素含 file/chars/dialogue。"""
    order = list(rows)
    n = len(order)
    if n == 0:
        return []
    picks: dict[str, list[str]] = {}

    def take(idx: int, reason: str) -> None:
        r = order[max(0, min(n - 1, idx))]
        if reason not in picks.setdefault(r["file"], []):
            picks[r["file"]].append(reason)

    take(0, "开头")
    if n > 1:
        take(1, "开头")
    if n > 6:
        take((n - 1) // 2, "中段")
        take((n - 1) // 2 + 1, "中段")
    elif n > 2:
        take(n // 2, "中段")
    take(n - 1, "结尾")
    if n > 2:
        take(n - 2, "结尾")
    with_d = [r for r in order if isinstance(r.get("dialogue"), (int, float))]
    if with_d:
        dense = max(with_d, key=lambda r: r["dialogue"])
        sparse = min(with_d, key=lambda r: r["dialogue"])
        take(order.index(dense), "对话密集")
        take(order.index(sparse), "叙述密集")
    out = [{**r, "reason": "、".join(picks[r["file"]])}
           for r in order if r["file"] in picks]
    return out[:8]


def chunk_files(samples: list[tuple[str, str]],
                chunk_chars: int = CHUNK_CHARS) -> list[list[tuple[str, str]]]:
    """按字数预算切 map 块（保篇完整，不切半篇）。"""
    chunks: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    cur_chars = 0
    for item in samples:
        cur.append(item)
        cur_chars += len(item[1])
        if cur_chars >= chunk_chars:
            chunks.append(cur)
            cur, cur_chars = [], 0
    if cur:
        chunks.append(cur)
    return chunks


# ---- 阶段 C：草案生成（提示词；引文校验是脚本的不是模型的）----

EXEMPLARS_MAX_TOKENS = 2600
PROFILE_MAX_TOKENS = 3200
TRIO_MAX_TOKENS = 2600
THOUGHT_MAX_TOKENS = 1800


def exemplars_prompt(analysis: dict, samples: list[tuple[str, str]]) -> str:
    return f"""基于以下风格分析与语料，写风格范例档案 exemplars.md。

要求：
- 6–10 条，每条格式（三行，缺一不可）：
### 特征标签
> 逐字引自下方语料的原文（≤200 字，一字不改）
批注：演示了什么手法、写作时应何时模仿
- 引文必须**逐字**取自语料——脚本会做逐字校验，伪造引文整条剔除
- 覆盖不同维度：叙事节奏 / 对话 / 场景转换 / 情绪外化 / 标志手法
只输出 markdown 本体（从第一条 ### 开始，不要解释）。

——风格分析——
{json.dumps(analysis, ensure_ascii=False, indent=1)}

——语料（引文只能从这里取）——
{_body(samples)}"""


def verify_exemplar_quotes(md: str, corpus_text: str) -> tuple[str, int, list[str]]:
    """逐字校验范例引文（溯源硬保证）：引文不在语料中的整条剔除。
    返回（净化后的 md，剔除条数，剔除标签列表）。"""
    entries = re.split(r"^###\s+", md, flags=re.M)[1:]
    kept, dropped, labels = [], 0, []
    for e in entries:
        quotes = re.findall(r"^>\s?(.*)$", e, flags=re.M)
        ok = any(q.strip().strip("》>") and q.strip().strip("》>") in corpus_text
                 for q in quotes)
        if ok:
            kept.append("### " + e.strip())
        else:
            dropped += 1
            labels.append(e.splitlines()[0].strip() if e.splitlines() else "?")
    return "\n\n".join(kept) + ("\n" if kept else ""), dropped, labels


def profile_prompt(analysis: dict, exemplars_md: str, metrics_note: str) -> str:
    return f"""基于风格分析与范例档案，写 profile.md（文风档案）。硬性要求：
- 九章骨架，h2 章节标题一字不差：## 三百字精华 / ## 叙事视角与人称 /
  ## 句式与节奏 / ## 词汇与用典 / ## 对话风格 / ## 场景与结构 /
  ## 情感与氛围 / ## 生成指导 / ## 禁用清单
- 「生成指导」必须是映射表：每行"遇 X 场景 → 用 Y 手法 → 参考范例 N"（N=范例序号）
- 「句式与节奏」须引用实测锚点：{metrics_note}
- 每个判断尽量能追溯到范例编号或指标；不确定的写"待校订"
只输出 markdown 本体。

——风格分析——
{json.dumps(analysis, ensure_ascii=False, indent=1)}

——范例档案（生成指导引用其序号）——
{exemplars_md}"""


def trio_prompt(analysis: dict, top_chars: list[str], exemplars_md: str) -> str:
    return f"""基于风格分析与高频字数据，产出三件档案。只输出 JSON：
{{"card_md": "card.md 本体（≤400 字，从三百字精华压缩；超长会被校验拒绝）",
 "lexicon_md": "lexicon.md 本体（## 标志词 / ## 句式模板 / ## 禁用清单；标志词结合高频字）",
 "limits_md": "limits.md 本体（逐维标注【可模仿|部分可模仿|难模仿】，诚实标注）"}}

——高频字（lexicon 参考口径：字频序）——
{'、'.join(top_chars[:40])}

——风格分析——
{json.dumps(analysis, ensure_ascii=False, indent=1)}

——范例档案——
{exemplars_md[:1500]}"""


def thought_prompt(analysis: dict) -> str:
    return f"""基于风格分析的思想四问，写 thought.md（思想层档案，v0.3 六节）。
硬性要求：
- 六节 h2 标题：## 选题地平线 / ## 立意动作 / ## 观察清单 / ## 意象系统 /
  ## 价值姿态 / ## 禁区
- 「立意动作」与「观察清单」每条必须指认依据篇目（来自分析中的立意动作.依据）——
  不可溯源的条目不要写
- 「价值姿态」落成可执行指令（如"叙述者后退半步，让事实并置，禁直接评判"）
- 必须包含一行词表（格式一字不差）：`motif 词表：词1、词2、…`
  （10–30 个，取自意象族提案——脚本将按语料频率验证，低于 1.5/千字自动剔除）
只输出 markdown 本体。

——风格分析——
{json.dumps(analysis, ensure_ascii=False, indent=1)}"""


# ---- 盲测（v0.8.0）：A/B 出题与对局生成 ----

BLIND_TOPIC_MAX_TOKENS = 1200
BLIND_GEN_MAX_TOKENS = 1500


def blind_topics_prompt(profile_text: str) -> str:
    return f"""基于以下文风档案，设计 3 道 A/B 盲测题（测"带档案 vs 不带档案"的
生成差异）。每题格式一字不差：

## 题 N：短标题

提示：第一人称，200–300 字。<一个具体、日常、有落差的场景命题>

期望特征（判卷 checklist）：
- [ ] <该作者风格的可判特征，3–5 条，每条可肉眼核对>

要求：题面场景须中性（不自带该作者的标志性元素，否则裸模型也能沾边）；
checklist 覆盖句式节奏/对话/收尾等可判维度。只输出 markdown 本体。

——文风档案——
{profile_text[:4000]}"""


def blind_packed_prompt(topic_prompt: str, pack_ctx: str) -> str:
    return f"""请严格按下方「文风档案」的纪律写作。

{topic_prompt}

硬性要求：句式节奏、对话方式、收尾姿态全部按档案执行；禁用清单逐条遵守；
篇幅 200–300 字。只输出正文本身（不要标题、不要解释）。

——文风档案——
{pack_ctx}"""


def blind_canon_prompt(topic_prompt: str, canon_ctx: str) -> str:
    """canon 臂（v0.13.2）：只给世界观锚定、不给文风档案——考世界观贴合
    （must 落实/ban 不出现/设定不自造），与风格维度独立测量。"""
    return f"""请严格按下方「世界观锚定」材料写作。

{topic_prompt}

硬性要求：must 术语按自然方式落实，ban 术语绝对不出现；设定/地名/组织
以材料为准，不得自造；篇幅 200–300 字。只输出正文本身（不要标题、不要解释）。

——世界观锚定——
{canon_ctx}"""


def blind_both_prompt(topic_prompt: str, pack_ctx: str, canon_ctx: str) -> str:
    """混合臂（v0.13.2）：文风档案 + 世界观锚定同时给——双问题分开计分。"""
    return f"""请同时遵守下方「文风档案」与「世界观锚定」两份材料。

{topic_prompt}

硬性要求：文风句式/对话/收尾按档案执行；世界观术语与设定按锚定材料落实
（must 落实、ban 不出现、不自造）；篇幅 200–300 字。只输出正文本身
（不要标题、不要解释）。

——文风档案——
{pack_ctx}

——世界观锚定——
{canon_ctx}"""


def blind_plain_prompt(topic_prompt: str) -> str:
    return f"""{topic_prompt}

只输出正文本身（不要标题、不要解释）。"""
