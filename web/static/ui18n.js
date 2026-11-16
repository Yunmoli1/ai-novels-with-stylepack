// -*- coding: utf-8 -*-
// ui18n.js（v0.13.19）：界面语言切换——中文界面 / English UI。
// 机制：词典（zh→en 精确匹配文本节点）+ TreeWalker 扫描；只动静态铬件
// （导航/表单标签/按钮/标题），PRE/CODE/TEXTAREA（草稿与门禁报告）永不触碰。
// 覆盖边界：动态面板（G0/单元卡编辑器/装配预览表格）重建后回中文——v1 已知
// 限制，逐步把高频渲染串迁入词典。偏好存 localStorage stylepack.ui_lang。
(function () {
  const I18N = {
    "门户": "Home", "包浏览": "Packs", "canon 包": "Canon packs",
    "盲测判读台": "Blind judging", "工作台": "Workbench", "浏览": "Browse",
    "创作": "Create", "连载台": "Serial desk", "蒸馏": "Distill",
    "项目档案": "Bible editor", "历史与成本": "History & cost",
    "模型配置": "Model config",
    "项目": "Project", "＋ 新建项目": "＋ New project", "新建项目": "New project",
    "开新弧": "New arc", "弧末漂移网": "Drift-net", "交接汇总": "Handover",
    "量产连跑": "Batch run", "设定工坊": "Setting forge", "单元卡": "Unit cards",
    "管线": "Pipeline", "看板/历史": "Board/History", "档案编辑器": "Bible editor",
    "风格包": "Style pack", "章节号": "Chapter no.", "章节题": "Chapter title",
    "关键词（顿号分隔）": "Keywords (、 separated)", "字数挡位": "Length tier",
    "自定义…": "Custom…", "装配预览": "Assemble preview",
    "📌 设为默认": "📌 Set default", "跟随包": "Follow pack",
    "调子声明": "Tone note", "原作锚点": "Canon anchor", "稿数": "Drafts",
    "流式": "Stream", "生成正文": "Generate prose", "采用稿": "Use draft",
    "导出合并 txt": "Export merged txt", "记忆·隔离区": "Memory · quarantine",
    "（不锚定）": "(no anchor)", "生成候选": "Generate options",
    "重新生成候选": "Regenerate options",
    "锁定此立意 → 生成拍子表": "Lock concept → generate beats",
    "第一级 · 立意确认": "Level 1 · Concept",
    "第二级 · 拍子表": "Level 2 · Beats", "拍子表": "Beats",
    "生成现场": "Live generation", "生成正文": "Generate prose",
    "点「生成候选」。": "Click \"Generate options\".",
    "开始引导（四步走完即可创作）": "Onboarding (4 steps)",
    "单章快写": "Quick single chapter",
    "连载管理台": "Serial desk", "方案槽": "Slots",
    "约束口·硬标准面板": "Constraints panel",
    "编辑档案": "Edit bible", "刷新本章简报": "Refresh brief",
    "主角状态": "Hero state", "弧线位置": "Arc position",
    "伏笔动作": "Foreshadow", "出场口癖": "Verbal tics",
    "结尾钩子": "Ending hook", "衔接上一章": "Bridge prev. chapter",
    "跳读测试": "Skim test", "对话出声读": "Dialogue read-aloud",
    "人格锚点对照": "Persona anchor check", "讲古打断": "Narration interrupt",
    "情绪停留": "Emotion dwell",
    "参考池": "Ref pool",
    "📌 存为项目参考池": "📌 Save as project ref pool",
    "单元题": "Unit title", "章号": "Chapter nos.",
    "开端": "Opening", "推进": "Development", "转折": "Turn", "落点": "Landing",
    "单元末钩子": "Ending hook", "涉及术语/伏笔": "Terms / foreshadow",
    "长度带": "Length band", "确认封卡": "Confirm seal",
    "💾 保存": "💾 Save", "✅ 批准——解锁生成": "✅ Approve — unlock",
    "常驻": "Resident",
    "仅监听 127.0.0.1": "Local-only 127.0.0.1",
    "key 只存服务端": "Keys stay server-side",
    "sessions 不入库": "sessions not committed",
  };
  const SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, PRE: 1, CODE: 1 };

  function uiLang() {
    try { return localStorage.getItem('stylepack.ui_lang') || 'zh'; }
    catch (e) { return 'zh'; }
  }
  function setUiLang(v) {
    try { localStorage.setItem('stylepack.ui_lang', v); } catch (e) {}
  }

  function sweep(root) {
    const en = uiLang() === 'en';
    const walker = document.createTreeWalker(root || document.body,
      NodeFilter.SHOW_TEXT, {
        acceptNode: n => (n.parentElement && SKIP[n.parentElement.tagName]) ||
          !n.nodeValue.trim() ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
      });
    let hits = 0;
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (!en) {  // 切回中文：还原带 _orig 的节点
        if (n._orig !== undefined) { n.nodeValue = n._orig; delete n._orig; hits += 1; }
        continue;
      }
      const key = n.nodeValue.trim();
      const enText = I18N[key];
      if (enText !== undefined) {
        if (n._orig === undefined) n._orig = n.nodeValue;
        n.nodeValue = n._orig.replace(key, enText);
        hits += 1;
      }
    }
    return hits;
  }

  function toggleUiLang() {
    setUiLang(uiLang() === 'en' ? 'zh' : 'en');
    applyUiLang();
  }

  function applyUiLang() {
    sweep(document.body);
    const btn = document.getElementById('btn_uilang');
    if (btn) btn.textContent = uiLang() === 'en' ? '中文界面' : 'EN 界面';
  }

  // 数据重渲染后动态面板回中文——挂少量关键渲染后的补扫（v1 静态铬件已够）
  window.sweepI18n = () => { if (uiLang() === 'en') sweep(document.body); };
  window.toggleUiLang = toggleUiLang;

  document.addEventListener('DOMContentLoaded', () => {
    applyUiLang();
    const btn = document.getElementById('btn_uilang');
    if (btn) btn.onclick = toggleUiLang;
  });
})();
