# -*- coding: utf-8 -*-
"""creation：创作环提示词与状态机辅助（v0.6.5：防缩水修订纪律）。

蓝本 = style-apply 两级共创（照搬不发明）：
  第一级·立意确认：依 thought.md 提 2–3 个立意方向（题材角度+拟用立意动作
  【引条目】+价值姿态落点）
  第二级·拍子表确认：开场承接/场景/结尾钩子，每拍一行（写什么、出现谁、
  给读者什么）+ 调子声明（无 registers 写"不指定"）+ 二创原作锚点
生成严格按拍子推进，不新增情节线；收尾检查为思想层硬性条目的模型化实现。
"""
from __future__ import annotations

import json
import re


def _repair_truncated(text: str) -> str:
    """best-effort 修复被 max_tokens 截断的 JSON：补引号、去尾逗号、闭合括号。"""
    stack: list[str] = []
    in_str = esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    out = text + ('"' if in_str else "")
    out = re.sub(r"[,:\s]+$", "", out)
    out = re.sub(r",\s*(?=[}\]]|$)", "", out)
    for ch in reversed(stack):
        out += "}" if ch == "{" else "]"
    json.loads(out)  # 仍失败则抛给调用方
    return out


def extract_json(text: str) -> dict:
    """从模型回复中提取第一个 JSON 对象（容忍围栏/废话/max_tokens 截断——
    截断时按括号栈 best-effort 补齐，真实场景（立意 2–3 项被 1200 token
    截断）实测可救回前几项）。"""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start < 0:
        raise ValueError("模型回复中未找到 JSON")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    try:
        return json.loads(_repair_truncated(text[start:]))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"模型回复中 JSON 未闭合且无法修复（{exc}）") from exc


SYSTEM = ("你是严格的网文章节共创助手。所有输出必须是可解析的 JSON 或纯正文，"
          "不要寒暄、不要解释流程。风格约束来自装配上下文中的风格包档案，"
          "必须严格遵守其中的 profile/thought/lexicon/limits。")

SYSTEM_EN = ("You are a strict co-writer of fiction chapters. Every output must be "
             "parseable JSON or plain prose — no greetings, no explanation of your "
             "process. Style constraints come from the style pack in the assembly "
             "context; you must obey its profile / thought / lexicon / limits exactly.")


def _is_en(lang: str) -> bool:
    """语言判定：'en'/'en-US' 均算英文；None/空/zh* 走中文分支。"""
    return str(lang or "zh").strip().lower().startswith("en")


def system_prompt(lang: str = "zh") -> str:
    """按目标语言取 system 提示（英文稿用英文 system，避免中文腔泄漏）。"""
    return SYSTEM_EN if _is_en(lang) else SYSTEM


def _words_of(text: str) -> list[str]:
    """英文词切分（与 splib.words_of 同正则，此处不依赖 splib 以保持 web 层轻量）。"""
    return re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", text or "")


def unit(lang: str = "zh") -> str:
    """长度单位：中文=字，英文=words（用于提示词与 UI 文案）。"""
    return "words" if _is_en(lang) else "字"


def outline_prompt(chapter_no: int, title: str, keywords: list[str],
                   context_blocks: list[str], user_notes: str,
                   lang: str = "zh") -> str:
    if _is_en(lang):
        return f"""Propose 2–3 angle options for chapter {chapter_no} (title: "{title}").

Requirements (stage 1 · chosen angle): each option = a subject angle + a stance action
that must cite an item number and name from the style pack's thought.md "stance
actions" + where the value stance lands. The angles must serve this chapter's
keywords: {', '.join(keywords) or '(none)'}.{(' Author notes: ' + user_notes) if user_notes else ''}

Output JSON only:
{{"options": [{{"title": "option name", "angle": "subject angle", "action": "stance action (cite item)", "stance": "where the value stance lands"}}], "recommended": 0}}

—— assembly context below ——
{chr(10).join(context_blocks)}"""
    return f"""请为第 {chapter_no} 章（题：《{title}》）提出 2–3 个立意方向。

要求（第一级·立意确认）：每个方向 = 题材角度 + 拟用立意动作（必须引用风格包
thought.md「立意动作」中的条目编号与名称）+ 价值姿态落点。立意要服务本章
关键词：{'、'.join(keywords) or '（无）'}。{('用户补充：' + user_notes) if user_notes else ''}

只输出 JSON：
{{"options": [{{"title": "方向名", "angle": "题材角度", "action": "立意动作（引条目）", "stance": "价值姿态落点"}}], "recommended": 0}}

——以下是装配上下文——
{chr(10).join(context_blocks)}"""


def beats_prompt(chapter_no: int, title: str, chosen: dict,
                 context_blocks: list[str], canon_note: str,
                 target_chars: int = 0, lang: str = "zh") -> str:
    if _is_en(lang):
        en_note = (f"\nTarget length for this chapter is about {target_chars} words — "
                   f"scale the number and detail of beats accordingly (short chapter = "
                   f"lean, long chapter = room to breathe)." if target_chars else "")
        return f"""Chapter {chapter_no} (title: "{title}") has a chosen angle:
option: {chosen.get('title', '')}
angle: {chosen.get('angle', '')}
stance action: {chosen.get('action', '')}
value stance: {chosen.get('stance', '')}

Produce the beat sheet for this chapter (stage 2 · beat sheet): opening hook / scene 1 /
scene 2 / closing hook (4–8 beats). One line per beat stating [what happens, who appears,
what the reader gets].{en_note}
Also add one line "tone note" (write "unspecified" when the pack has no register
sections) and one line "canon anchor" (terms / characters / fact red lines used in this
chapter; write "none" for non-derivative work).{canon_note}

Output JSON only:
{{"beats": [{{"no": 1, "beat": "……"}}], "tone_note": "……", "canon_anchor": "……"}}

—— assembly context below ——
{chr(10).join(context_blocks)}"""
    length_note = (f"\n本章目标约 {target_chars} 字——拍子数量与详略按此配比"
                   f"（短章精简、长章给场景留呼吸）。" if target_chars else "")
    return f"""第 {chapter_no} 章（题：《{title}》）已选定立意：
方向：{chosen.get('title', '')}
角度：{chosen.get('angle', '')}
立意动作：{chosen.get('action', '')}
价值姿态：{chosen.get('stance', '')}

请产出本章拍子表（第二级·拍子表确认）：开场承接 / 场景 1 / 场景 2 / 结尾钩子
（可 4–8 拍），每拍一行，写明【写什么、出现谁、给读者什么】。{length_note}
并附一行"调子声明"（无调子分区写"不指定"）与一行"原作锚点"（本章用到的
术语/人物/事实红线；非二创写"无"）。{canon_note}

只输出 JSON：
{{"beats": [{{"no": 1, "beat": "……"}}], "tone_note": "……", "canon_anchor": "……"}}

——以下是装配上下文——
{chr(10).join(context_blocks)}"""


def reroll_beat_prompt(chapter_no: int, title: str, chosen: dict,
                       beats: list[dict], index: int,
                       context_blocks: list[str], target_chars: int = 0,
                       lang: str = "zh") -> str:
    if _is_en(lang):
        nb = "\n".join(f"beat {b['no']}: {b['beat']}" for b in beats
                       if abs((b.get("no") or 0) - index) <= 1)
        en_note = (f"\nTarget length for this chapter is about {target_chars} words — "
                   f"this beat's weight must match the whole sheet." if target_chars else "")
        return f"""Chapter {chapter_no} (title: "{title}") angle: {chosen.get('title', '')} — {chosen.get('angle', '')}.
Current beat sheet:
{nb}
{en_note}
Re-roll beat {index}: connect naturally with its neighbours and carry the same narrative
duty (setup / escalation / hook), but take a clearly different direction.

Output JSON only: {{"no": {index}, "beat": "……"}}

—— assembly context below ——
{chr(10).join(context_blocks)}"""
    neighbors = "\n".join(f"拍{b['no']}：{b['beat']}" for b in beats
                          if abs((b.get("no") or 0) - index) <= 1)
    length_note = (f"\n本章目标约 {target_chars} 字——此拍的体量须与整表配比一致。"
                   if target_chars else "")
    return f"""第 {chapter_no} 章（题：《{title}》）立意：{chosen.get('title', '')}——{chosen.get('angle', '')}。
现有拍子表：
{neighbors}
{length_note}
请重掷第 {index} 拍：与相邻拍自然衔接、承担相同的叙事职责（承接/推进/钩子），
但给出明显不同的走向。

只输出 JSON：{{"no": {index}, "beat": "……"}}

——以下是装配上下文——
{chr(10).join(context_blocks)}"""


def prose_prompt(chapter_no: int, title: str, chosen: dict, beats: list[dict],
                 tone_note: str, canon_anchor: str,
                 context_blocks: list[str], target_chars: int,
                 lang: str = "zh") -> str:
    beat_lines = "\n".join(f"拍{b.get('no')}：{b.get('beat')}" for b in beats)
    if _is_en(lang):
        en_beats = "\n".join(f"beat {b.get('no')}: {b.get('beat')}" for b in beats)
        return f"""Write the prose of chapter {chapter_no} (title: "{title}") in English.

Angle: {chosen.get('title', '')} — {chosen.get('angle', '')} (action: {chosen.get('action', '')}; stance: {chosen.get('stance', '')})
Beat sheet (follow strictly, add no plot line):
{en_beats}
Tone note: {tone_note or 'unspecified'}｜Canon anchor: {canon_anchor or 'none'}

Hard requirements:
- Obey the language discipline of the style pack in the assembly context exactly: the
  profile's sentence rhythm and dialogue layering, the lexicon's signature words and
  forbidden list, the limits' caveats, thought's forbidden zones (especially the ending).
- Length about {target_chars} words (hard floor {int(target_chars * 0.85)} words, cap
  {int(target_chars * 1.2)} words); do not pad to fill, do not wrap up early.
- Apply the thought-layer ending check: do not build a lyrical monument for a character,
  do not console the reader, do not state the theme; only materialized closure or plain
  speech grounded in concrete fact is allowed.

Output the prose only (no title, no explanation).


—— assembly context below ——
{chr(10).join(context_blocks)}"""
    return f"""请写第 {chapter_no} 章正文（题：《{title}》）。

立意：{chosen.get('title', '')}——{chosen.get('angle', '')}（动作：{chosen.get('action', '')}；姿态：{chosen.get('stance', '')}）
拍子表（严格按此推进，不新增情节线）：
{beat_lines}
调子声明：{tone_note or '不指定'}｜原作锚点：{canon_anchor or '无'}

硬性要求：
- 严格使用装配上下文中风格包档案的语言纪律：profile 的句式节奏与对话分层、
  lexicon 的签名词与禁用清单、limits 的分寸警告、thought 的禁区（尤其收尾）。
- 篇幅约 {target_chars} 字（合格下限 {int(target_chars * 0.85)} 字，上限
  {int(target_chars * 1.2)} 字）；不为凑数注水，也不提前收笔。
- 收尾执行思想层收尾检查：不给人物立抒情碑、不安慰读者、不点题升华；
  物化收束或实事托住的直抒才合法。

只输出正文本身（不要标题、不要解释）。


——以下是装配上下文——
{chr(10).join(context_blocks)}"""


def revise_prompt(chapter_no: int, title: str, beats: list[dict],
                  context_blocks: list[str], draft: str,
                  gate_reports_text: str, target_chars: int = 0,
                  lang: str = "zh") -> str:
    beat_lines = chr(10).join(f"拍{b.get('no')}：{b.get('beat')}" for b in beats)
    n = len(_words_of(draft)) if _is_en(lang) else len(draft)
    goal = target_chars or n
    if _is_en(lang):
        en_beats = chr(10).join(f"beat {b.get('no')}: {b.get('beat')}" for b in beats)
        en_len = (f"\n- Length discipline: the draft is about {n} words; the revision must "
                  f"stay about {goal} words — **never below {int(goal * 0.9)} words and "
                  f"never above {int(goal * 1.2)} words**.")
        return f"""Revise the prose of chapter {chapter_no} (title: "{title}") according to the review report.

Hard requirements:
- Keep plot, beat structure, angle, jokes and closing hook **unchanged** — touch the
  language layer only, and add no plot line;{en_len}
- **Never merge fragmented paragraphs by deleting plot, dialogue or scenes** — merging
  applies to layout fragments only; if you fall short of the target, expand detail and
  action from what already happens; shrinking fails the task;
- Address every item the report names: for sentence / paragraph length being too short,
  merge fragments so the text can breathe — combine two or three sentences into one
  12–22 word paragraph, and never run more than 3 consecutive very short lines
  (≤6 words each);
- Leave everything the report did not name as untouched as possible; self-check once
  before output.

—— review report (advisory, address item by item) ——
{gate_reports_text}

—— current prose (revision target) ——
{draft}

—— beat sheet (structure must not change) ——
{en_beats}

—— style context ——
{chr(10).join(context_blocks)}

Output the complete revised prose only (no title, no explanation)."""
    length_note = (f"\n- 篇幅纪律：原文约 {n} 字，修订后仍约 {goal} 字、"
                   f"**不得低于 {int(goal * 0.9)} 字，也不得超过 {int(goal * 1.2)} 字**。")
    return f"""请按验收报告修订第 {chapter_no} 章正文（题：《{title}》）。

硬性要求：
- 情节、拍子结构、立意、笑点与收尾钩子**全部保留**——只动语言层，不新增情节线；{length_note}
- **严禁靠删情节、删对白、缩写场景来"合并碎段"**——合并只针对排版碎行，
  字数不够就从已有情节里展开细节与动作补足，缩水即不合格；
- 验收报告点名的每一条都要处理：句长/段长类超差（过短）就把碎段合并出呼吸——
  把两三句合成 12–22 字的段落，超短段（≤6 字）连续不超过 3 行；
- 报告没点名的部分尽量少动；改完自查一遍再输出。

——验收报告（advisory，逐条处理）——
{gate_reports_text}

——当前正文（修订对象）——
{draft}

——拍子表（结构不得变）——
{beat_lines}

——风格上下文——
{chr(10).join(context_blocks)}

只输出修订后的完整正文（不要标题、不要解释）。"""


def ending_check_prompt(title: str, draft_tail: str,
                        lang: str = "zh") -> str:
    if _is_en(lang):
        return f"""Run the thought-layer ending check on the closing paragraphs of "{title}" (hard items):
1. Does it build a lyrical monument for a character (freezing them in an image,
   memorial-style closure)?
2. Does it console the reader (warm reassurance, cheap sentiment)?
3. Does it state the theme outright?

Output JSON only: {{"violation": true/false, "reason": "one-line evidence quoting the text"}}

—— closing paragraphs ——
{draft_tail}"""
    return f"""请对《{title}》的结尾段做思想层收尾检查（硬性条目）：
1. 是否在给人物立抒情碑（用意象为角色定格、树碑立传式收束）？
2. 是否在安慰读者（给温暖保证、给廉价比 sentiment）？
3. 是否在点题升华（把主题说破）？

只输出 JSON：{{"violation": true/false, "reason": "一句话依据（引用原文）"}}

——结尾段——
{draft_tail}"""


def rewrite_prompt(chapter_no: int, title: str, beats: list[dict],
                   context_blocks: list[str], text: str,
                   fragment: str, instruction: str,
                   lang: str = "zh") -> str:
    """局部改写（v0.9.3）：只动指定片段，其余逐字保留，输出整章。"""
    beat_lines = chr(10).join(f"拍{b.get('no')}：{b.get('beat')}" for b in beats)
    if _is_en(lang):
        en_beats = chr(10).join(f"beat {b.get('no')}: {b.get('beat')}" for b in beats)
        return f"""Rewrite one passage of chapter {chapter_no} "{title}".

Target passage (change this only):
"{fragment}"

Rewrite instruction: {instruction}

Hard requirements:
- Rewrite only the passage above; **keep every other word of the prose byte-identical**
  (including line breaks and paragraph order);
- The rewrite obeys the style context's discipline (sentence rhythm / dialogue /
  forbidden list / ending posture);
- Add no plot line, change neither the angle nor the beat structure.
Output the **complete revised chapter** (no title, no explanation, no change markers).

—— beat sheet (structure must not change) ——
{en_beats}

—— style context ——
{chr(10).join(context_blocks)}

—— current full prose ——
{text}"""
    return f"""请对第 {chapter_no} 章《{title}》做局部改写。

改写对象（只改这一段）：
「{fragment}」

改写指令：{instruction}

硬性要求：
- 只改写上方片段；**其余正文逐字保留、一字不动**（包括换行与段落顺序）；
- 改写遵守风格上下文的档案纪律（句式/对话/禁用清单/收尾姿态）；
- 不新增情节线、不改立意与拍子结构。
输出改写后的**完整整章正文**（不要标题、不要解释、不要标注改动处）。

——拍子表（结构不得变）——
{beat_lines}

——风格上下文——
{chr(10).join(context_blocks)}

——当前整章正文——
{text}"""


def memory_digest_prompt(chapter_no: int, title: str, beats: list[dict],
                         text: str, lang: str = "zh") -> str:
    """交付后登记提取（judge 路由）：digest/状态变更/伏笔。
    只提取正文与拍子中**实际发生**的内容——不推测、不补设定；
    风险分级由脚本判定（不由模型自评）。"""
    beat_lines = chr(10).join(f"拍{b.get('no')}：{b.get('beat', '')[:80]}"
                              for b in beats)
    if _is_en(lang):
        en_beats = chr(10).join(f"beat {b.get('no')}: {b.get('beat', '')[:80]}"
                               for b in beats)
        return f"""Extract memory registrations from the prose and beats of chapter {chapter_no} "{title}".

Output JSON only:
{{"digest": "summary of this chapter in ≤120 words (prior context for the next chapter)",
  "changes": [{{"entity": "character / place / object name (the name as written in the text)",
                "field": "state/location/possession/mood/relationship field",
                "value": "new state after this chapter (≤60 words)",
                "note": "basis (quote or point to the event, ≤60 words)"}}],
  "foreshadow": ["titles of hooks planted for later payoff (≤20 words each, empty array if none)"]}}

Discipline: register only what **actually happens** in this chapter — otherwise empty
arrays; never speculate or invent canon. Use the literal names from the prose (no pronouns).

—— beat sheet ——
{en_beats}

—— prose ——
{text[:6000]}"""
    return f"""从第 {chapter_no} 章《{title}》正文与拍子中提取记忆登记项。

只输出 JSON：
{{"digest": "本章 120 字内摘要（给下一章当前情）",
  "changes": [{{"entity": "人物/地点/物件名（用文中出现的名字）",
                "field": "state/location/possession/mood/关系类字段",
                "value": "本章之后的新状态（≤60 字）",
                "note": "依据（引用或指认情节，≤60 字）"}}],
  "foreshadow": ["本章埋下待回收的钩子标题（≤20 字，无则空数组）"]}}

纪律：只登记**本章实际发生**的变更——没有就给空数组，绝不推测或补设定；
entity 用正文原文名（不用代词）。

——拍子表——
{beat_lines}

——正文——
{text[:6000]}"""
