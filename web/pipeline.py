# -*- coding: utf-8 -*-
"""pipeline：创作管线声明（v0.13.9 示波器）——单一事实源。

泳道视图（serial 页管线面板）与后续一切管线可视化都从这里取步骤定义。
拓扑暂不可编辑（家法：装配在生成前/门禁在交付前/记忆在确认后——工序顺序
经灾厄前线+泰拉灾厄两轮实战钉死，开放拖拽=邀请用户重踩坑）；编辑性后续
版本给参数层（节点面板：门禁勾选/思考档/预算）与开关层。

kind 三色：script=零 token 脚本执法 / llm=花 token 模型调用 / human=花
时间的人工工序（跳读测试/四道过滤/简报点头）——三色标注本身就是教育
工具：一眼看懂钱烧在哪、闸立在哪、哪些事只有人能干。
"""
from __future__ import annotations

MANIFEST_VERSION = 1

STEPS: list[dict] = [
    {"id": "g0", "name": "G0 简报", "kind": "human",
     "note": "七字段拍子表+钩子——用户填，写作的锚"},
    {"id": "assemble", "name": "装配", "kind": "script",
     "note": "六源表按上下文预算裁剪成写作上下文（prio 从高到低裁）",
     "inputs": ["bible/*", "canon/*", "outline.md", "记忆·前情",
                "硬数字表", "上一章结尾", "风格包"]},
    {"id": "generate", "name": "生成", "kind": "llm",
     "note": "写作路由单发（空稿/截断自动加倍重试≤3，思考档 v0.13.8）",
     "params": ["route（write/write_mass）", "思考档", "max_tokens"]},
    {"id": "gate_fp", "name": "fp_check", "kind": "script",
     "note": "风格指纹验收（逐指标阈值+真迹留一 Delta）"},
    {"id": "gate_borrow", "name": "borrow_check", "kind": "script",
     "note": "借句检查（≥12 字逐字重叠=必修）"},
    {"id": "gate_ai_cliche", "name": "ai_cliche_check", "kind": "script",
     "note": "AI 腔黑名单"},
    {"id": "gate_numbers", "name": "numbers_check", "kind": "script",
     "note": "数字对照（长篇：表内/表外/事实三分类，advisory）"},
    {"id": "gate_names", "name": "names_check", "kind": "script",
     "note": "专名/人物状态/卡面禁语（长篇）"},
    {"id": "review", "name": "人审", "kind": "human",
     "note": "跳读测试（哪里想快进）+ 四道过滤——不归任何机制，当前未留痕"},
    {"id": "save", "name": "交付", "kind": "script",
     "note": "落 manuscript/ + 会话记录（sessions/*.json 留痕）+ 成本入账"},
    {"id": "memory", "name": "记忆登记", "kind": "llm",
     "note": "digest 提取→隔离区→确认→下章前情（在记忆页执行）"},
]


def manifest() -> dict:
    return {"version": MANIFEST_VERSION, "steps": STEPS}
