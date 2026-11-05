const S = { assembly: null, session_id: '', chosen: null, beats: [],
            drafts: [], lastOptions: null, stage: -1, modelLabel: '-',
            slots: [], activeSlot: null, packVersions: {},
            batchNo: 0, batchStart: 0, projects: [],
            g0: null, g0info: null, g0Skip: false };
const STAGES = ['装配', '立意', '拍子', '生成', '门禁', '交付'];
// v0.13.1 分家：create=单章快写 / serial=连载管理台——长篇件只在 serial 激活
const PAGE = document.body.dataset.page || 'create';
const $ = id => document.getElementById(id);
const esc = s => (s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || JSON.stringify(d));
  return d;
}
async function sse(url, body, onEvent) {
  const resp = await fetch(url, { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  if (!resp.ok || !resp.body) {
    const d = await resp.json().catch(() => ({}));
    throw new Error(d.detail || ('HTTP ' + resp.status));
  }
  const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = '';
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let ev = 'message', data = '';
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (data) { try { onEvent(ev, JSON.parse(data)); } catch (e) {} }
    }
  }
}
function setStage(i) {
  S.stage = Math.max(S.stage, i);
  $('stagebar').innerHTML = STAGES.map((name, k) =>
    `<span class="stage ${k < S.stage ? 'done' : ''} ${k === S.stage ? 'cur' : ''}">${name}</span>`).join('');
}
function updateMeta() {
  $('genmeta').textContent = `模型：${S.modelLabel}｜目标正文 ≈ ${targetChars() || '未设'} 字`;
}
function keywords() { return $('keywords').value.split(/[、,，]/).map(s => s.trim()).filter(Boolean); }
function tierChange() {
  const custom = $('char_tier').value === 'custom';
  $('target_chars').style.display = custom ? '' : 'none';
  if (!custom) $('target_chars').value = $('char_tier').value;
  updateMeta();
}
function targetChars() {
  const n = +$('target_chars').value || 0;
  return n >= 300 && n <= 20000 ? n : 0;
}
async function init() {
  setStage(-1);
  const d = await (await fetch('/app/api/projects')).json();
  S.projects = d.projects || [];
  $('project').innerHTML = d.projects.map(p => `<option value="${p.name}">${p.name}${p.pinned ? '（钉扎：' + p.pinned.pack + ' v' + p.pinned.version + '）' : ''}</option>`).join('');
  syncArcBtn();
  maybeRedirectLongform();
  S.packVersions = {};
  (d.packs || []).forEach(p => S.packVersions[p.name] = p.version || '');
  $('pack').innerHTML = d.packs.map(p => `<option value="${p.name}">${p.name}</option>`).join('');
  try {
    const c = await (await fetch('/app/api/config')).json();
    const w = (c.routing || {}).write || {};
    S.modelLabel = (w.provider || '?') + '/' + (w.model || '未配置');
  } catch (e) {}
  updateMeta();
  loadPresets();
  loadSlots();
  renderOnboard(d);
}
async function renderOnboard(d) {
  if (!$('ob_steps')) return;  // 连载台无引导面板（分区共存：缺元素即跳过）
  const cfg = await (await fetch('/app/api/config')).json();
  const hasKey = (cfg.providers || []).some(p => p.has_key);
  const hasRoute = (cfg.routing || {}).write;
  const hasProject = (d.projects || []).length > 0;
  const w = (cfg.routing || {}).write || {};
  const box = $('ob_steps');
  const step = (ok, label, act) => `<div style="margin:4px 0">${ok ? '✅' : '⬜'} ${label}${act || ''}</div>`;
  const allDone = hasKey && hasRoute && hasProject;
  if (allDone) { $('onboard').style.display = 'none'; return; }
  $('onboard').style.display = '';
  box.innerHTML =
    step(hasKey, '① 配置模型 key（', !hasKey ? '<a href="/app/config">去配置</a>）' : '）✓') +
    step(!!hasRoute, '② 给写作模块选模型（', !hasRoute ? '<a href="/app/config">去选</a>）' : '）✓') +
    step(hasProject, '③ 建一个写作项目（', !hasProject ? '<button class="btn ghost" onclick="newProject()">新建</button>）' : '）✓') +
    step(false, '④ 选风格包 → 装配预览 → 写第一章');
}
const chr10 = () => String.fromCharCode(10);
const ARC_ZH = '一二三四五六七八九十';
async function newProject() {
  const name = prompt('项目名（一本书一个项目，中英文均可）：');
  if (!name) return;
  const longform = confirm('启用长篇模式？' + chr10() + '（卷/弧/章结构 + 硬数字表 + 写作防线/宪法模板。' + chr10() + '10 万字以上连载选【确定】；短篇/轻量选【取消】）');
  const mode = longform ? 'longform' : 'light';
  let pack = '';
  try {
    const packs = (await (await fetch('/app/api/projects')).json()).packs;
    pack = prompt('初始风格包（钉扎；可留空跳过）：' + chr10() + packs.map(p => p.name).join(chr10()), '') || '';
  } catch (e) {}
  try {
    const r = await post('/app/api/projects/create', { name, mode, pack: pack || null });
    toast(`项目 ${r.name} 已建：${r.notes.join('；')}`, 'good');
    const d = await (await fetch('/app/api/projects')).json();
    S.projects = d.projects || [];
    syncArcBtn();
    $('project').innerHTML = d.projects.map(p => `<option value="${p.name}">${p.name}${p.pinned ? '（钉扎：' + p.pinned.pack + ' v' + p.pinned.version + '）' : ''}</option>`).join('');
    $('project').value = r.name;
    switchProject();
    renderOnboard(d);
  } catch (e) { toast(e.message, 'bad'); }
}
function maybeRedirectLongform() {
  // v0.13.1 分家：单章页遇到长篇项目 → 送连载台（约束口/预算/连跑都在那）
  if (PAGE !== 'create') return;
  const cur = (S.projects || []).find(p => p.name === $('project').value);
  if (cur && cur.longform) {
    toast('「' + cur.name + '」是长篇项目——已为你转到连载台', 'bad');
    location.href = '/app/serial';
  }
}
function syncArcBtn() {
  if (!$('btn_arc')) return;  // 单章页无长篇工具条（0.13.1 摘除）
  const cur = (S.projects || []).find(p => p.name === $('project').value);
  const lf = !!(cur && cur.longform);
  $('btn_arc').style.display = lf ? '' : 'none';
  $('btn_net').style.display = lf ? '' : 'none';
  $('btn_ho').style.display = lf ? '' : 'none';
  $('btn_batch').style.display = lf ? '' : 'none';
  if ($('btn_forge')) $('btn_forge').style.display = lf ? '' : 'none';
}
async function newArc() {
  const title = prompt('弧名（本弧的张力主题，如：敲门与旧账）：');
  if (!title) return;
  const start = prompt('起始章号：');
  if (!start) return;
  const end = prompt('结束章号（单弧建议 ≤20 章）：');
  if (!end) return;
  const anchors = prompt('原作锚点（本弧必落的原作元素，逗号分隔）：');
  if (anchors === null) return;
  const tension = prompt('张力设计（本弧的冲突与代价）：');
  if (tension === null) return;
  const hooks = prompt('勾稽点（与其他弧/伏笔的勾连）：');
  if (hooks === null) return;
  const per = prompt('单章字数目标：', '3500');
  if (!per) return;
  let numbers = [];
  const numsRaw = prompt('硬数字（开弧定账，一条一行，格式：账目=口径；留空跳过）：');
  if (numsRaw) {
    numbers = numsRaw.split(chr10()).map(s => {
      const i = s.indexOf('=');
      return i > 0 ? { name: s.slice(0, i).trim(), value: s.slice(i + 1).trim() } : null;
    }).filter(Boolean);
  }
  try {
    const r = await post('/app/api/longform/arc_create', {
      project: $('project').value, title, start: +start, end: +end,
      anchors, tension, hooks, per_chapter: +per, numbers });
    toast(`弧${ARC_ZH[r.arc_no - 1] || r.arc_no}《${title}》已立：卷纲 + 硬数字表已落盘`, 'good');
  } catch (e) { toast(e.message, 'bad'); }
}
// ---- 方案槽 ----
async function switchProject() {
  S.activeSlot = null;
  syncArcBtn();
  maybeRedirectLongform();
  $('title').value = ''; $('keywords').value = '';  // 新项目新章节：清残留
  $('step_g0').style.display = 'none';
  S.g0info = null; S.g0 = null; S.g0Skip = false;
  await loadPresets(); await loadSlots();
  try {  // 章节号推荐：manuscript 最大 +1（防错乱致锚定失效）
    const n = await (await fetch('/app/api/next_chapter?project='
      + encodeURIComponent($('project').value))).json();
    if (n.next) $('chapter_no').value = n.next;
  } catch (e) {}
  await loadG0();
}
async function loadSlots() {
  try {
    const p = $('project').value;
    if (!p) { S.slots = []; renderSlots(); return; }
    const d = await (await fetch('/app/api/slots?project=' + encodeURIComponent(p))).json();
    S.slots = d.slots || [];
    renderSlots();
  } catch (e) {}
}
function slotLabel(s) {
  return s.name || (s.chosen && s.chosen.title) || s.title || `章${s.chapter_no}`;
}
function renderSlots() {
  $('slotchips').innerHTML = S.slots.map((s, idx) => {
    const i = idx + 1;
    if (!s) return `<span class="stage" style="opacity:.35">槽${i}（空）</span>`;
    const cur = S.activeSlot === i ? ' cur' : '';
    const tip = `章${s.chapter_no}${s.title ? '《' + s.title + '》' : ''}｜包 ${s.pack} v${s.pack_version || '?'}｜关键词：${(s.keywords || []).join('、') || '无'}`;
    return `<span class="stage${cur} chip" onclick="loadSlot(${i})" title="${esc(tip)}">槽${i} ${s.locked ? '🔒' : ''}·${esc(slotLabel(s))}`
      + `<span class="act" onclick="event.stopPropagation()">`
      + `<a href="javascript:void(0)" onclick="toggleLock(${i})">${s.locked ? '解锁' : '锁定'}</a>｜`
      + `<a href="javascript:void(0)" onclick="nameSlot(${i})">名</a>｜`
      + `<a href="javascript:void(0)" onclick="clearSlot(${i})">清</a></span></span>`;
  }).join('');
}
async function captureSlot() {
  try {
    const d = await post('/app/api/slots/capture', {
      project: $('project').value, pack: $('pack').value,
      chapter_no: +$('chapter_no').value, keywords: keywords(),
      target_chars: targetChars(), title: $('title').value });
    S.activeSlot = d.slot.id;
    await loadSlots();
  } catch (e) { toast(e.message, 'bad'); }
}
async function slotPatch(i, fields) {
  if (!i) return;
  try {
    const d = await post('/app/api/slots/update',
      { project: $('project').value, slot_id: i, ...fields });
    if (S.slots[i - 1]) S.slots[i - 1] = d.slot;
    renderSlots();
  } catch (e) {}
}
async function toggleLock(i) {
  const s = S.slots[i - 1];
  if (s) await slotPatch(i, { locked: !s.locked });
}
async function nameSlot(i) {
  const s = S.slots[i - 1];
  if (!s) return;
  const n = prompt('方案名（留空清除，自动名取立意方向）：', s.name || '');
  if (n === null) return;
  await slotPatch(i, { name: n.trim() });
}
async function clearSlot(i) {
  if (!confirm(`清空方案槽 ${i}？（对应配置与上次稿将被删除）`)) return;
  try {
    await post('/app/api/slots/clear', { project: $('project').value, slot_id: i });
    if (S.activeSlot === i) S.activeSlot = null;
    await loadSlots();
  } catch (e) { toast(e.message, 'bad'); }
}
async function loadSlot(i) {
  const s = S.slots[i - 1];
  if (!s) return;
  S.activeSlot = i;
  S.drafts = []; S.batchNo = 0;
  $('drafts').innerHTML = ''; $('savebox').style.display = 'none';
  $('gen_out').textContent = '';
  $('project').value = s.project; $('pack').value = s.pack;
  $('chapter_no').value = s.chapter_no; $('title').value = s.title || '';
  $('keywords').value = (s.keywords || []).join('、');
  const tc = s.target_chars || 0;
  const tiers = ['1500', '2500', '4000', '6000'];
  if (tc && tiers.includes(String(tc))) {
    $('char_tier').value = String(tc); $('target_chars').style.display = 'none';
  } else {
    $('char_tier').value = 'custom'; $('target_chars').style.display = '';
  }
  $('target_chars').value = tc || 2500;
  updateMeta();
  S.req = { project: s.project, pack: s.pack, chapter_no: s.chapter_no,
            keywords: s.keywords || [], target_chars: tc };
  try {
    S.assembly = await post('/app/api/assemble', S.req);
    renderAssembly();
    setStage(0);
    $('step_outline').style.display = '';
    $('options').innerHTML = '<p class="meta">方案已恢复（装配重放完成）。可直接锁定原立意，或「生成候选」重提方向。</p>'
      + '<button class="btn" onclick="doOutline()">生成候选</button>';
  } catch (e) { alert('装配重放失败：' + e.message); return; }
  if (s.chosen) {
    S.chosen = s.chosen;
    $('chosen_json').value = JSON.stringify(s.chosen, null, 2);
    setStage(1);
  }
  if (s.beats && s.beats.length) {
    S.beats = s.beats;
    $('step_beats').style.display = '';
    renderBeats(s.tone_note || '不指定', s.canon_anchor || '无');
  }
  if (Array.isArray(s.drafts) && s.drafts.length) {  // 批次恢复（v0.7.3）
    S.drafts = s.drafts.map(d => ({ ...d }));
    S.batchNo = Math.max(...S.drafts.map(d => d.batch || 0));
    S.batchStart = S.drafts.length;
    renderDrafts(); setStage(4);
    $('gen_out').textContent = `已恢复 ${new Set(S.drafts.map(d => d.batch)).size} 批草稿`
      + '（收尾检查需重跑；可继续生成新批）';
  } else if (s.latest_draft && s.latest_draft.text) {
    S.drafts = [{ ...s.latest_draft, batch: 0, label: '上次稿' }];
    S.batchStart = 1;
    renderDrafts();
  }
  const curV = S.packVersions[s.pack];
  if (s.pack_version && curV && curV !== s.pack_version)
    $('gen_out').textContent = `⚠ 包已从 v${s.pack_version} 升到 v${curV}，装配内容可能随包更新变化`;
  renderSlots();
  await loadG0();  // 槽随项目/章节走：G0 简报与图纸门同步刷新
}
async function loadPresets() {
  try {
    const q = 'project=' + encodeURIComponent($('project').value || '')
            + '&pack=' + encodeURIComponent($('pack').value || '');
    const p = await (await fetch('/app/api/presets?' + q)).json();
    $('tone_list').innerHTML = (p.tones || []).map(t => `<option value="${esc(t)}">`).join('');
    $('anchor_list').innerHTML = (p.anchors || []).map(t => `<option value="${esc(t)}">`).join('');
  } catch (e) {}
}
// ---- 步骤流 ----
async function doAssemble() {
  S.req = { project: $('project').value, pack: $('pack').value,
    chapter_no: +$('chapter_no').value, keywords: keywords(),
    target_chars: targetChars() };
  try {
    S.assembly = await post('/app/api/assemble', S.req);
  } catch (e) {
    if (String(e.message).includes('拆账强制')
        && confirm(e.message + chr10() + chr10() + '显式确认越过？（防线：无拆账不开工——先在网页补交付是正路）')) {
      S.allowUnbilled = true;
      S.req.allow_unbilled = true;
      return doAssemble();
    }
    return toast(e.message, 'bad');
  }
  renderAssembly();
  await loadG0();
  $('step_outline').style.display = '';
  setStage(0);
  $('options').innerHTML = '<p class="meta">点「生成候选」让写作模型按 thought.md 立意动作提 2–3 个方向。</p><button class="btn" onclick="doOutline()">生成候选</button>';
  captureSlot();  // 装配成功自动入槽（同配置复用原槽）
}
// ---- G0 写前简报（v0.11.1 B-1，长篇模式）----
const G0_FIELDS = [['anchor', '原作锚点'], ['hero_state', '主角状态'],
  ['arc_pos', '弧线位置'], ['foreshadow', '伏笔动作'], ['quirks', '出场口癖'],
  ['ending_hook', '结尾钩子'], ['bridge', '衔接上一章']];
async function loadG0() {
  S.g0 = null; S.g0info = null; S.g0Skip = false;
  S.bstate = null; S.overBudget = false; S.allowUnbilled = false;
  if (PAGE !== 'serial' || !$('step_g0')) return;  // 单章快写：无 G0/预算/图纸（分家）
  if (!$('project').value) return;
  try {
    const d = await (await fetch('/app/api/longform/g0?project='
      + encodeURIComponent($('project').value)
      + '&chapter_no=' + (+$('chapter_no').value || 0))).json();
    if (!d.longform) return;
    S.g0info = d; S.g0 = { ...(d.brief || {}) };
    if (!S.g0.chapter_type) S.g0.chapter_type = 'mass';  // C-4：默认量产章
    renderG0();
  } catch (e) {}
}
function g0Ready() {
  if (!S.g0info) return true;   // 轻量项目/未开弧：不受 G0 管（回归零变化）
  if (S.g0Skip) return true;    // 显式跳过（交付留痕）
  if (S.g0info.arc && !S.g0info.arc_confirmed) return false;  // 图纸门 G-0.5
  return G0_FIELDS.every(([k]) => {
    const el = $('g0_' + k); return el && el.value.trim();
  });
}
function renderG0() {
  const d = S.g0info;
  const probeTag = d.probe ? '｜<span style="color:var(--warn)">🎯 探针章</span>' : '';
  const bp = (d.blueprint_changed || []).length ? `
    <div class="panel" style="border:1px solid var(--bad);margin:6px 0">
      <strong style="color:var(--bad)">⚠ 图纸变更未确认：${d.blueprint_changed.map(esc).join('、')}</strong>
      <p class="meta">基线确认后图纸被改动——已写章节可能基于旧图纸。建议先回扫再写作。</p>
      <div class="genrow">
        <button class="btn ghost" onclick="retroscan()">账本回扫（--all，0 token）</button>
        <button class="btn ghost" onclick="reconfirmBlueprint()">我已核对变更，重新确认图纸</button>
      </div>
      <pre class="meta" id="rs_out" style="display:none;white-space:pre-wrap;max-height:200px;overflow:auto"></pre>
    </div>` : '';
  const arcCard = d.arc ? `
    <div class="panel" style="margin:6px 0">
      <strong>弧简报卡（G-0.5 图纸门）· 弧${d.arc.no}《${esc(d.arc.title)}》第${d.arc.start}-${d.arc.end}章</strong>${probeTag}
      <p class="meta">锚点：${esc(d.arc.anchors)}｜张力：${esc(d.arc.tension)}</p>
      <p class="meta">勾稽点：${esc(d.arc.hooks)}｜章数字数：${esc(d.arc.size)}</p>
      ${d.numbers_section ? '<pre class="meta" style="white-space:pre-wrap;max-height:130px;overflow:auto">' + esc(d.numbers_section) + '</pre>' : ''}
      ${d.arc_confirmed
        ? '<p class="meta" style="color:var(--good)">✓ 图纸已确认（弧前已对照原作过目，留痕于卷纲）</p>'
        : `<button class="btn" onclick="confirmArc(${d.arc.no})">确认图纸：我已对照原作过目本弧简报卡</button>`}
    </div>` : '';
  $('step_g0').innerHTML = `<h3>写前简报 G0（七字段——缺一不生成，预填自弧块/记忆，可改）</h3>${bp}${arcCard}
    ${G0_FIELDS.map(([k, label]) =>
      `<label>${label}<input id="g0_${k}" style="width:100%" value="${esc((S.g0 || {})[k] || '')}" oninput="g0Input()"></label>`).join('')}
    ${d.arc ? `<label>章类型（量产走 write_mass 便宜档，关键章走高档写作模型）
      <select id="g0_ctype" onchange="g0Input()">
        <option value="mass" ${(S.g0 || {}).chapter_type !== 'key' ? 'selected' : ''}>量产章（默认）</option>
        <option value="key" ${(S.g0 || {}).chapter_type === 'key' ? 'selected' : ''}>关键章</option>
      </select></label>` : ''}
    <p class="meta"><a href="javascript:void(0)" onclick="skipG0()">跳过 G0（高级用户——将留痕于交付记录）</a>
    ${d.probe ? '｜<strong>本弧前 2 章为探针章：交付时要求显式验收，探针未过不连跑</strong>' : ''}</p>`;
  $('step_g0').style.display = '';
  if (d.arc && !d.arc_confirmed) $('btn_generate').disabled = true;
}
function g0Input() {
  if (!S.g0) return;
  G0_FIELDS.forEach(([k]) => { const el = $('g0_' + k); if (el) S.g0[k] = el.value; });
  const ct = $('g0_ctype'); if (ct) S.g0.chapter_type = ct.value;
  $('btn_generate').disabled = !g0Ready();
}
// ---- 预算三态（v0.11.2 C-3）：预警闸/止损闸/三出路 ----
function budgetBlocked() {
  if (S.bstate && S.bstate.state === 'halt' && !S.overBudget) {
    renderBudget();
    toast('⛔ 止损闸已触发——生成/修订已锁，看预算面板三出路', 'bad');
    return true;
  }
  if (S.bstate && S.bstate.state === 'warning' && !S.overBudget
      && !confirm(`⚠ 预警闸：本章已烧 ${Math.round(S.bstate.spend / 1000)}k / 预算 ${Math.round(S.bstate.chapter_budget / 1000)}k tokens——继续？`))
    return true;
  return false;
}
function renderBudget() {
  const b = S.bstate, box = $('budgetbox');
  if (!box) return;  // 单章页无预算钱包（0.13.1 摘除）
  if (!S.g0info || !b) { box.style.display = 'none'; return; }
  const k = n => Math.round((n || 0) / 1000);
  const color = b.state === 'halt' ? 'var(--bad)' : b.state === 'warning' ? 'var(--warn,#c80)' : 'var(--good)';
  const icon = b.state === 'halt' ? '⛔ 止损闸' : b.state === 'warning' ? '⚠ 预警闸' : '✓';
  let html = `<h3 style="margin:4px 0">预算·本章钱包</h3>
    <p class="meta" style="color:${color}">${icon} 本章已烧 ${k(b.spend)}k / 预算 ${k(b.chapter_budget)}k（止损线 ${k(b.halt_line)}k）</p>
    <p class="meta">拆账：生成 ${k(b.breakdown && b.breakdown.gen)}k · 修订 ${k(b.breakdown && b.breakdown.rev)}k · 其他 ${k(b.breakdown && b.breakdown.other)}k${b.ledger_tokens ? ` · 账本历史 ${k(b.ledger_tokens)}k` : ''}</p>`;
  if (b.state === 'halt')
    html += `<div class="genrow"><a class="btn ghost" href="/app/config">换模型（去配置）</a>
      <button class="btn ghost" onclick="raiseBudget()">调高预算</button>
      <button class="btn ghost" onclick="giveUpChapter()">放弃本章</button></div>
      <p class="meta"><a href="javascript:void(0)" onclick="overBudget()">我知道在超支，仍要继续（显式确认，G4 最高指令权）</a></p>`;
  box.innerHTML = html; box.style.display = '';
}
async function raiseBudget() {
  const b = (S.g0info && S.g0info.budget) || {};
  const cb = prompt('新单章预算（tokens）：', b.chapter_budget || 150000);
  if (!cb) return;
  const ab = prompt('新弧预算（tokens）：', b.arc_budget || 1500000);
  if (!ab) return;
  const hm = prompt('止损倍数：', b.halt_multiplier || 2);
  if (!hm) return;
  try {
    const r = await post('/app/api/longform/budget', { project: $('project').value,
      chapter_budget: +cb, arc_budget: +ab, halt_multiplier: +hm, rev: b.rev || 0 });
    S.g0info.budget = r;
    budgetRefresh();
    toast('预算已调整并落盘 budget.json（rev+1）', 'good');
  } catch (e) { toast(e.message, 'bad'); }
}
function budgetRefresh() {  // 预算调整后按当前消耗重算三态
  const b = S.bstate; if (!b) return;
  const nb = (S.g0info && S.g0info.budget) || {};
  b.chapter_budget = nb.chapter_budget || b.chapter_budget;
  b.halt_line = Math.round(b.chapter_budget * (nb.halt_multiplier || 2));
  b.state = b.spend >= b.halt_line ? 'halt' : b.spend >= b.chapter_budget ? 'warning' : 'normal';
  renderBudget();
}
function giveUpChapter() {
  if (!confirm('放弃本章？草稿从现场清空（方案槽与 sessions 里的旧稿仍在）。')) return;
  S.bstate = null; S.overBudget = false;
  $('budgetbox').style.display = 'none';
  $('drafts').innerHTML = ''; S.drafts = []; S.batchNo = 0; S.batchStart = 0;
  $('savebox').style.display = 'none';
  toast('已放弃本章——新会话从装配重来', 'good');
}
function overBudget() {
  if (!confirm('显式确认：我知道本章已超止损线，仍要继续生成/修订（本次会话内有效）。')) return;
  S.overBudget = true;
  toast('已解锁本次超支——换模型仍是更便宜的杠杆', 'warn');
}
// ---- 弧末治理（v0.11.3 阶段 D）：漂移网 / 交接汇总 / 图纸变更 ----
function currentArcNo() {
  const a = S.g0info && S.g0info.arc;
  return a ? a.no : 0;
}
async function retroscan() {
  try {
    const r = await post('/app/api/longform/retroscan',
      { project: $('project').value });
    const el = $('rs_out');
    if (el) {
      el.style.display = '';
      el.textContent = r.report || '（无输出）';
    }
    toast(r.exit_code === 0 ? '回扫完成：无发现项' : '回扫完成：有发现项，见报告', r.exit_code === 0 ? 'good' : 'bad');
  } catch (e) { toast(e.message, 'bad'); }
}
async function reconfirmBlueprint() {
  if (!confirm('确认图纸基线重置？前提：你已核对全部变更（必要时先跑回扫）。')) return;
  try {
    await post('/app/api/longform/blueprint_confirm', { project: $('project').value });
    toast('图纸基线已重置（blueprint.json）', 'good');
    loadG0();
  } catch (e) { toast(e.message, 'bad'); }
}
function showArcTool(title, text, note) {
  $('arctools').style.display = '';
  $('arctools').innerHTML = `<h3>${esc(title)}</h3>
    ${note ? `<p class="meta">${esc(note)}</p>` : ''}
    <textarea id="at_text" rows="14" style="width:100%">${esc(text)}</textarea>
    <div class="genrow">
      <button class="btn ghost" onclick="navigator.clipboard.writeText(document.getElementById('at_text').value).then(()=>toast('已复制全文','good'))">复制全文</button>
      <span id="at_out" class="meta"></span>
    </div>`;
  $('arctools').scrollIntoView({ behavior: 'smooth' });
}
async function arcNet() {
  const no = prompt('漂移网目标弧号：', currentArcNo() || '1');
  if (!no) return;
  try {
    const d = await (await fetch('/app/api/longform/arcanet?project='
      + encodeURIComponent($('project').value) + '&arc_no=' + (+no))).json();
    showArcTool(`弧${no}《${d.arc.title}》漂移网指令包（复制到独立会话/子代理执行）`,
      d.prompt, `审查范围：第 ${d.chapters[0]}-${d.chapters[1]} 章——清单模式（硬数字逐条+伏笔动作+节拍落位），不做五维全量。`);
    $('arctools').innerHTML += `
      <details><summary class="meta">审查完成？粘贴报告归档（整合/一致性报告/，永不覆盖）</summary>
        <textarea id="at_report" rows="6" style="width:100%"></textarea>
        <button class="btn" onclick="archiveNet(${+no})">归档报告</button></details>`;
  } catch (e) { toast(e.message, 'bad'); }
}
async function archiveNet(no) {
  const rep = $('at_report').value;
  if (!rep.trim()) return toast('报告为空', 'bad');
  try {
    const r = await post('/app/api/longform/arcanet/archive',
      { project: $('project').value, arc_no: no, report: rep });
    $('at_out').textContent = '已归档：' + r.file;
    toast('漂移网报告已归档', 'good');
  } catch (e) { toast(e.message, 'bad'); }
}
async function handoverDoc() {
  try {
    const d = await (await fetch('/app/api/longform/handover?project='
      + encodeURIComponent($('project').value))).json();
    showArcTool('一键交接汇总（草稿——进度/成本/断点/伏笔/待办）', d.markdown, '');
    $('arctools').innerHTML += `
      <div class="genrow"><button class="btn ghost" onclick="saveHandover()">落盘草稿（项目根，永不覆盖手写版）</button></div>`;
  } catch (e) { toast(e.message, 'bad'); }
}
async function saveHandover() {
  try {
    const r = await post('/app/api/longform/handover/save',
      { project: $('project').value, markdown: $('at_text').value });
    $('at_out').textContent = '已落盘：' + r.file;
    toast('交接草稿已落盘项目根', 'good');
  } catch (e) { toast(e.message, 'bad'); }
}
async function batchTrend() {
  const a = prompt('趋势报告起始章：', (S.batchPlanData ? S.batchPlanData.start : '') || $('chapter_no').value);
  if (!a) return;
  const b = prompt('结束章：', (S.batchPlanData ? S.batchPlanData.end : '') || a);
  if (!b) return;
  try {
    const r = await post('/app/api/longform/batch/report',
      { project: $('project').value, pack: $('pack').value,
        start: +a, end: +b });
    showArcTool(`批后趋势报告（第${a}-${b}章 fp_check --per-file）`,
      r.report || '（无输出）',
      r.exit_code === 0 ? '' : '⚠ 有越界项——对照报告逐章核');
    $('at_out').textContent = '已归档：' + r.file;
  } catch (e) { toast(e.message, 'bad'); }
}
// ---- 量产连跑（v0.12）：前端循环（J1）+ 每站复用既有执法 + 红即停 ----
async function batchPlan() {
  const start = prompt('连跑起始章（须为未交付的新章）：', $('chapter_no').value || '1');
  if (!start) return;
  const count = prompt('连跑章数（1–10，自动截断到弧末）：', '5');
  if (!count) return;
  try {
    const d = await (await fetch('/app/api/longform/batch/plan?project='
      + encodeURIComponent($('project').value) + '&start=' + (+start)
      + '&count=' + (+count))).json();
    S.batchPlanData = d;
    renderBatchPlan(d);
  } catch (e) { toast(e.message, 'bad'); }
}
function renderBatchPlan(d) {
  const k = n => Math.round((n || 0) / 1000);
  const rows = d.rows.map((r, i) => {
    const key = r.brief.chapter_type === 'key';
    const tags = (r.probe ? ' <span style="color:var(--warn)">🎯探针（不进连跑）</span>' : '')
      + (key ? ` <span style="color:var(--bad)">关键章·摘出（${esc(r.key_reason)}）</span>` : '');
    return `<tr><td>第${r.chapter_no}章</td><td>${esc(r.brief.arc_pos)}</td><td>${tags}</td>
      <td><input id="bp_title_${i}" value="${esc(r.title)}" style="width:100px"></td>
      <td><input id="bp_bridge_${i}" value="${esc(r.brief.bridge)}" style="width:140px" placeholder="上章钩子自动链"></td>
      <td><input id="bp_hook_${i}" style="width:140px" placeholder="本章结尾钩子"></td>
      <td><input id="bp_kw_${i}" value="${esc((r.keywords || []).join('、'))}" style="width:150px"></td>
      <td><select id="bp_ct_${i}"><option value="mass" ${!key ? 'selected' : ''}>量产</option><option value="key" ${key ? 'selected' : ''}>关键</option></select></td></tr>`;
  }).join('');
  $('arctools').style.display = '';
  $('arctools').innerHTML = `<h3>量产连跑·章计划表（预审一次 = 冻结 N 章简报）</h3>
    <p class="meta">预估成本 ≈ ${k(d.estimate_tokens)}k tokens（近 ${d.samples} 章中位数 × ${d.rows.length} 章${d.samples ? '' : '；无历史数据，凭你确认'}）｜
    量产路由：${d.write_mass ? '✓ write_mass 已配置' : '<span style="color:var(--bad)">未配置——回退 write（若是思考模型贵 6-9 倍，建议先配置）</span>'}
    ${d.clamped ? '｜⚠ 已按弧末截断' : ''}｜探针章 ${d.probe_rows} 章不进连跑</p>
    <table><thead><tr><th>章</th><th>弧位</th><th></th><th>题</th><th>衔接（上章钩）</th><th>结尾钩子</th><th>关键词</th><th>类型</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="meta">铁律：门红即停（无自动修订）· 不跨弧末 · 探针/关键章自动摘出 · 预警停等人 · halt 终止 · 黄灯连击×3 停</p>
    <div class="genrow">
      <button class="btn" onclick="batchStart()">开始连跑（${d.rows.filter(r => r.brief.chapter_type !== 'key' && !r.probe).length} 章）</button>
      <button class="btn ghost" onclick="batchTrend()">批后趋势报告</button>
      <span id="bp_out" class="meta"></span></div>
    <div id="batchlog" class="panel" style="max-height:260px;overflow:auto;white-space:pre-wrap;font-size:12.5px"></div>`;
  $('arctools').scrollIntoView({ behavior: 'smooth' });
}
function blog(s) {
  const el = $('batchlog');
  if (el) { el.textContent += s + chr10(); el.scrollTop = el.scrollHeight; }
}
async function batchStart() {
  const d = S.batchPlanData;
  if (!d) return;
  const rows = d.rows.map((r, i) => ({
    ...r,
    title: $('bp_title_' + i).value.trim() || r.title,
    keywords: $('bp_kw_' + i).value.split(/[、,，]/).map(s => s.trim()).filter(Boolean),
    brief: { ...r.brief,
      ending_hook: $('bp_hook_' + i).value.trim(),
      bridge: $('bp_bridge_' + i).value.trim(),
      chapter_type: $('bp_ct_' + i).value }
  }));
  for (let i = 1; i < rows.length; i++)   // 钩子链：上行结尾钩子 → 下行衔接
    rows[i].brief.bridge = rows[i - 1].brief.ending_hook;
  const queue = rows.filter(r => r.brief.chapter_type === 'mass' && !r.probe);
  if (!queue.length) return toast('没有可连跑的章（全是探针/关键章——先手写验收它们）', 'bad');
  if (!d.write_mass && !confirm('量产路由 write_mass 未配置——若 write 是思考模型，成本 6-9 倍。仍要开始？')) return;
  if (!confirm(`冻结 ${queue.length} 章简报并开始连跑？预估 ≈ ${Math.round(d.estimate_tokens / 1000)}k tokens。`)) return;
  S.batchRun = { queue, stop: false, warnStreak: 0 };
  $('bp_out').textContent = '连跑中……';
  for (const row of queue) {
    if (!(await batchChapter(row))) {
      blog('⛔ 连跑终止。断点=最后交付章——重开页面从 N+1 重新预审即可续。');
      $('bp_out').textContent = '已终止';
      return;
    }
  }
  blog('✅ 批量完成：' + queue.length + ' 章全部交付。建议批后跑一次指纹趋势与隔离区人审。');
  $('bp_out').textContent = '批量完成。';
}
function batchPause() {
  return new Promise(resolve => {
    blog('  （等人在场：继续 / 终止）');
    const bar = document.createElement('div');
    bar.className = 'genrow';
    bar.innerHTML = '<button class="btn">继续下一章</button><button class="btn ghost">终止连跑</button>';
    $('arctools').appendChild(bar);
    const [yes, no] = bar.querySelectorAll('button');
    yes.onclick = () => { bar.remove(); resolve(true); };
    no.onclick = () => { bar.remove(); resolve(false); };
  });
}
async function batchChapter(row) {
  const n = row.chapter_no;
  blog(`—— 第${n}章《${row.title}》开始：简报已冻结`);
  const sid = 'batch-' + n + '-' + (Date.now() % 1000000);
  const base = { project: $('project').value, pack: $('pack').value,
    chapter_no: n, title: row.title, keywords: row.keywords,
    target_chars: targetChars(), session_id: sid };
  try {
    blog('  ① 立意（自动取推荐）……');
    const o = await post('/app/api/outline', { ...base, user_notes: '', g0: row.brief });
    const chosen = (o.options || [])[o.recommended || 0] || (o.options || [])[0];
    if (!chosen) { blog('  ⛔ 立意无候选——红停'); return false; }
    blog('  ② 拍子表……');
    const b = await post('/app/api/beats', { ...base, chosen, g0: row.brief });
    const beats = b.beats || [];
    blog('  ③ 正文生成（单发 1 稿）……');
    const g = await post('/app/api/generate', { ...base, chosen, beats,
      tone_note: b.tone_note || '不指定', canon_anchor: b.canon_anchor || '无',
      n_drafts: 1, g0: row.brief });
    if (g.budget && g.budget.state === 'halt') { blog('  ⛔ 预算止损线——终止'); return false; }
    const dr = (g.drafts || [])[0];
    if (!dr || !(dr.text || '').trim()) { blog('  ⛔ 空稿——红停'); return false; }
    const len = dr.text.length, tgt = targetChars() || 2500;
    let yellow = false;
    const fpX = (dr.fp_check || {}).exit_code, bwX = (dr.borrow_check || {}).exit_code;
    if ((fpX !== undefined && fpX !== 0) || (bwX !== undefined && bwX !== 0)) {
      blog(`  ⛔ 门禁红（fp=${fpX}/borrow=${bwX}）——无自动修订，铁律停`); return false; }
    if ((dr.usage || {}).finish_reason === 'length') {
      blog('  ⛔ 重试触顶仍截断——红停'); return false; }
    const nc = dr.numbers_check;
    if (nc && (nc.report || '').includes('表外·设定级候选')) {
      blog('  ⛔ 表外设定级数字——停等人裁决（落账/豁免/改文）'); return false; }
    const nmc = dr.names_check;
    if (nmc && nmc.exit_code === 1) {
      const rep = nmc.report || '';
      if (rep.includes('[专名错写]') || rep.includes('[状态冲突]')) {
        blog('  ⛔ 专名总账门红（错写/状态冲突）——红停，见报告裁决');
        return false;
      }
      yellow = true; blog('  🟡 卡面禁语同现——黄级，供人扫');
    }
    if (len < 2200 || len > tgt * 1.5) {
      blog(`  ⛔ 字数越界：${len} 字（界 2200–${Math.round(tgt * 1.5)}）——红停`); return false; }
    if (nc && nc.exit_code === 1) { yellow = true; blog('  🟡 数字对照有发现项（场景级）'); }
    if ((dr.ai_cliche || {}).exit_code === 1) { yellow = true; blog('  🟡 AI 腔密度偏高'); }
    if (Math.abs(len - tgt) / tgt > 0.15) { yellow = true; blog(`  🟡 字数偏差 >15%：${len}/${tgt}`); }
    blog(`  ④ 交付（${len} 字）……`);
    const sv = await post('/app/api/save', { ...base, text: dr.text, chosen,
      beats, tone_note: b.tone_note || '不指定', canon_anchor: b.canon_anchor || '无',
      checks: { fp_check: dr.fp_check, borrow_check: dr.borrow_check },
      usage: dr.usage, g0: row.brief });
    blog('  ⑤ 记忆登记与 digest 校验……');
    const md = await post('/app/api/memory/delta', { project: base.project,
      chapter_no: n, title: row.title, text: dr.text, beats, session_id: sid });
    if (!(md.digest || '').length || md.digest.length < 10) {
      blog('  ⛔ digest 异常（空/过短）——坏前情会传染，红停'); return false; }
    const pd = await (await fetch('/app/api/memory/pending?project='
      + encodeURIComponent(base.project))).json();
    const riskOf = {};
    ['high', 'medium', 'low'].forEach(rk =>
      (pd.groups[rk] || []).forEach(x => { riskOf[x.id] = rk; }));
    const mine = (md.proposed || []).map(p => p.id).filter(id => riskOf[id]);
    if (mine.some(id => riskOf[id] !== 'low')) {
      blog('  ⛔ 中/高风险记忆 delta（正史级变更）——停，隔离区人审'); return false; }
    const lowIds = mine.filter(id => riskOf[id] === 'low');
    if (lowIds.length) await post('/app/api/memory/merge',
      { project: base.project, ids: lowIds, force: false });
    if (sv.budget) {
      S.bstate = sv.budget; renderBudget();
      if (sv.budget.state === 'halt') { blog('  ⛔ 预算止损线——终止'); return false; }
      if (sv.budget.state === 'warning') {
        blog(`  ⚠ 预警：本章 ${Math.round(sv.budget.spend / 1000)}k / 预算 ${Math.round(sv.budget.chapter_budget / 1000)}k——连跑暂停`);
        if (!(await batchPause())) { blog('⏸ 人选择终止。'); return false; }
        blog('  ▶ 人确认继续。');
      }
    }
    S.batchRun.warnStreak = yellow ? S.batchRun.warnStreak + 1 : 0;
    if (S.batchRun.warnStreak >= 3) {
      blog('  ⛔ 黄灯连击 ×3——漂移趋势，停（批后建议跑指纹趋势）'); return false; }
    blog(`  ✓ 第${n}章 交付完成（${len} 字）`);
    return true;
  } catch (e) {
    blog('  ⛔ 异常：' + e.message + '——红停（断点=最后交付章）');
    return false;
  }
}
async function confirmArc(no) {
  try {
    await post('/app/api/longform/arc_confirm',
      { project: $('project').value, arc_no: no });
    if (S.g0info) S.g0info.arc_confirmed = true;
    renderG0(); g0Input();
    toast('图纸确认已留痕（outline.md 弧块）', 'good');
  } catch (e) { toast(e.message, 'bad'); }
}
function skipG0() {
  if (!confirm('跳过 G0 七字段简报？跳过将留痕于交付记录（防线：简报质量=本章质量上限）。')) return;
  S.g0Skip = true;
  $('btn_generate').disabled = !g0Ready();
}
function g0Payload() {
  if (!S.g0info) return {};
  return S.g0Skip ? { skipped: true } : (S.g0 || {});
}
function renderAssembly() {
  const rows = S.assembly.items.map(i =>
    `<tr${i.dropped ? ' style="opacity:.4"' : ''}><td>${i.kind}</td><td>${i.source}</td>
     <td>${i.chars}</td><td>${i.est_tokens}${i.dropped ? '（预算裁掉）' : ''}</td>
     <td style="max-width:340px">${esc(i.excerpt)}</td></tr>`).join('');
  const pend = S.assembly.pending_memory
    ? `<p class="meta" style="color:var(--bad)">⚠ 隔离区有 ${S.assembly.pending_memory} 条未合并记忆登记——建议先在下方「记忆·隔离区」合并再开工（state drift 防线：旧状态会污染下一章前情）</p>` : '';
  $('assembly').style.display = '';
  $('assembly').innerHTML = `<h3>装配预览（所见即所发）</h3>
    <table><thead><tr><th>类型</th><th>来源</th><th>字数</th><th>token 估算</th><th>摘录</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="meta">合计 ${S.assembly.total_chars} 字 ≈ ${S.assembly.total_est_tokens} token / 预算 ${S.assembly.budget_tokens}
    ${S.assembly.within_budget ? '✓ 预算内' : '⚠ 超预算（记忆项已裁）'}｜目标正文 ≈ ${targetChars() || '未设'} 字</p>${pend}`;
}
async function doOutline() {
  $('options').innerHTML = '<p class="meta">模型生成中……</p>';
  try {
    const d = await post('/app/api/outline', {...S.req, title: $('title').value,
      user_notes: '', target_chars: targetChars(), session_id: S.session_id,
      g0: g0Payload(), allow_unbilled: S.allowUnbilled === true,
      allow_over_budget: S.overBudget === true });
    if (d.budget) { S.bstate = d.budget; renderBudget(); }
    S.session_id = d.session_id; S.lastOptions = d;
    const rec = d.recommended || 0;
    $('options').innerHTML = (d.options || []).map((o, i) =>
      `<label style="display:block;margin:6px 0"><input type="radio" name="opt" value="${i}" ${i === rec ? 'checked' : ''} onchange="pickOption(${i})">
       <strong>${o.title}</strong>｜${o.angle}<br><span class="meta">动作：${o.action}｜姿态：${o.stance}</span></label>`).join('');
    pickOption(rec);
    setStage(1);
  } catch (e) {
    $('options').innerHTML = `<p style="color:var(--bad)">${e.message}</p>
      <p class="meta">可在下方"已选方向"里照格式手写（或修好截断的 JSON）后直接锁定；也可点"重新生成候选"重试。</p>`;
  }
}
function pickOption(i) {
  if (S.lastOptions && S.lastOptions.options[i])
    $('chosen_json').value = JSON.stringify(S.lastOptions.options[i], null, 2);
}
function lockChosen() {
  try { S.chosen = JSON.parse($('chosen_json').value); }
  catch (e) { return toast('已选方向不是合法 JSON', 'bad'); }
  $('step_beats').style.display = '';
  $('beats').innerHTML = '<p class="meta">点「生成拍子表」。</p><button class="btn" onclick="doBeats()">生成拍子表</button>';
  slotPatch(S.activeSlot, { chosen: S.chosen });
}
async function doBeats() {
  $('beats').innerHTML = '<p class="meta">模型生成中……</p>';
  try {
    const d = await post('/app/api/beats', {...S.req, title: $('title').value,
      chosen: S.chosen, target_chars: targetChars(), session_id: S.session_id,
      g0: g0Payload(), allow_unbilled: S.allowUnbilled === true,
      allow_over_budget: S.overBudget === true });
    if (d.budget) { S.bstate = d.budget; renderBudget(); }
    S.session_id = d.session_id; S.beats = d.beats || [];
    renderBeats(d.tone_note || '不指定', d.canon_anchor || '无');
  } catch (e) {
    $('beats').innerHTML = `<p style="color:var(--bad)">${e.message}</p>
      <button class="btn ghost" onclick="doBeats()">重试</button>`;
  }
}
function renderBeats(tone, anchor) {
  $('beats').innerHTML = S.beats.map(b =>
    `<div class="panel"><strong>拍${b.no}</strong>
     <textarea rows="2" style="margin-top:6px;width:100%" oninput="S.beats[${b.no - 1}].beat = this.value">${esc(b.beat)}</textarea>
     <button class="btn ghost" onclick="reroll(${b.no})">重掷此拍</button></div>`).join('');
  $('tone_note').value = tone; $('canon_anchor').value = anchor;
  $('btn_generate').disabled = !g0Ready();
  if (!g0Ready() && S.g0info)
    $('gen_out').textContent = S.g0info.arc && !S.g0info.arc_confirmed
      ? '图纸未确认：先过目弧简报卡并点「确认图纸」'
      : 'G0 七字段未填全（或点「跳过 G0」留痕）';
  else $('gen_out').textContent = '拍子就绪，可生成正文。';
  setStage(2);
  slotPatch(S.activeSlot, { beats: S.beats, tone_note: tone, canon_anchor: anchor });
}
async function reroll(no) {
  try {
    const d = await post('/app/api/reroll_beat', {...S.req, title: $('title').value,
      chosen: S.chosen, beats: S.beats, index: no,
      target_chars: targetChars(), session_id: S.session_id, g0: g0Payload() });
    S.beats[no - 1] = d.beat; renderBeats($('tone_note').value, $('canon_anchor').value);
  } catch (e) { toast(e.message, 'bad'); }
}
// ---- 生成现场（草稿按批累积，保留最近 5 批）----
function cardHtml(dr, i) {
  const gate = rep => rep ? `<pre class="meta" style="white-space:pre-wrap">${(rep.report || '').replace(/</g, '&lt;')}</pre>` : '';
  const badge = dr.revision ? `<span class="meta">｜已按报告修订 ${dr.revision} 轮</span>` : '';
  const trunc = dr.usage && dr.usage.finish_reason === 'length'
    ? '｜<span style="color:var(--bad)">⚠ 输出被截断——建议再修订一次或换非思考模型</span>' : '';
  const n = (dr.text || '').length;
  const emptyMark = n ? `｜正文 ${n} 字`
    : '｜<span style="color:var(--bad)">⚠ 正文为空（0 字）——勿交付</span>';
  const diffBox = (dr.prevText && dr.prevText !== dr.text)
    ? `<details><summary class="meta">对比修订前（红=删 绿=增）</summary>${diffHtml(dr.prevText, dr.text)}</details>` : '';
  return `<div class="panel" id="card_${i}"><strong>${dr.label || '稿'}</strong>（${dr.usage.completion_tokens || '?'} tokens）${emptyMark}${trunc}${badge}
    <div class="passage streambox">${(dr.text || '').replace(/</g, '&lt;')}</div>${diffBox}
    <details><summary class="meta">fp_check / borrow_check / ai_cliche / numbers_check / names_check 报告（advisory，不是门）</summary>${gate(dr.fp_check)}${gate(dr.borrow_check)}${gate(dr.numbers_check)}${gate(dr.names_check)}</details>
    <button class="btn" onclick="reviseDraft(${i})">按报告修订</button>
    <button class="btn ghost" onclick="rewriteFragment(${i})">局部改写</button>
    <button class="btn ghost" onclick="endingCheck(${i})">收尾检查（判官模型）</button>
    <span id="end_${i}" class="meta"></span></div>`;
}
function refreshPick() {
  $('pick').innerHTML = S.drafts.map((d, i) =>
    d ? `<option value="${i}">${d.label || '稿'}</option>` : '').join('');
  $('savebox').style.display = S.drafts.some(d => d) ? '' : 'none';
}
function renderDrafts() {
  $('drafts').innerHTML = S.drafts.map((dr, i) =>
    dr ? cardHtml(dr, i) : '').join('');
  refreshPick();
}
function streamCardHtml(i, label) {
  return `<div class="panel" id="card_${i}"><strong>${label}</strong>（生成中<span id="live_${i}" class="meta">……</span>）
    <div class="passage streambox" id="box_${i}"></div></div>`;
}
function appendStream(i, text) {
  const box = $('box_' + i) || $('rbox_' + i);
  if (!box) return;
  box.appendChild(document.createTextNode(text));
  box.scrollTop = box.scrollHeight;
}
function replaceStream(i, text, chars) {
  const box = $('box_' + i) || $('rbox_' + i);
  if (!box) return;
  box.textContent = '';
  box.appendChild(document.createTextNode(text));
  box.scrollTop = box.scrollHeight;
  const live = $('live_' + i);
  if (live) live.textContent = `……已生成 ${chars} 字`;
}
function capBatches() {
  // 保留最近 5 批：新一批入列前挤掉最旧批
  while (new Set(S.drafts.filter(d => d).map(d => d.batch)).size >= 5) {
    const oldest = S.drafts.find(d => d).batch;
    S.drafts = S.drafts.filter(d => !d || d.batch !== oldest);
  }
}
function serializeBatches() {  // 批次落盘（slots）：轻量字段，刷新可恢复
  return S.drafts.filter(d => d && d.text).map(d => ({
    batch: d.batch, label: d.label, text: d.text,
    revision: d.revision || 0,
    usage: { completion_tokens: d.usage && d.usage.completion_tokens,
             model: d.usage && d.usage.model,
             finish_reason: d.usage && d.usage.finish_reason },
    fp_check: d.fp_check, borrow_check: d.borrow_check }));
}
function persistBatches() {  // 批次与最新稿一并写回当前槽
  slotPatch(S.activeSlot, { drafts: serializeBatches(), latest_draft: pickLatest() });
}
async function doGenerate() {
  if (!S.beats.length) return toast('先完成拍子表', 'bad');
  capBatches();
  renderDrafts();  // 被挤掉的最旧批卡片同步消失
  S.batchNo += 1;
  S.batchStart = S.drafts.length;
  if (budgetBlocked()) { S.batchNo -= 1; S.batchStart = S.drafts.length; return; }
  $('btn_generate').disabled = true;
  $('gen_out').textContent = '连接中……';
  $('savebox').style.display = 'none';
  setStage(3);
  const body = {...S.req, title: $('title').value, chosen: S.chosen,
    beats: S.beats, tone_note: $('tone_note').value,
    canon_anchor: $('canon_anchor').value, target_chars: targetChars(),
    n_drafts: +$('n_drafts').value, session_id: S.session_id,
    g0: g0Payload(), allow_over_budget: S.overBudget === true };
  try {
    if ($('use_stream').checked) {
      await sse('/app/api/generate_stream', body, onGenEvent);
    } else {
      const d = await post('/app/api/generate', body);
      S.session_id = d.session_id;
      if (d.budget) { S.bstate = d.budget; renderBudget(); }
      d.drafts.forEach((dr, k) => {
        const label = `批${S.batchNo}·稿${k + 1}`;
        S.drafts[S.batchStart + k] = { ...dr, batch: S.batchNo, label };
      });
      $('gen_out').textContent = `完成（${d.assembly_tokens} token 上下文）`;
      renderDrafts(); setStage(4);
      persistBatches();
    }
  } catch (e) { $('gen_out').textContent = '失败：' + e.message; }
  $('btn_generate').disabled = false;
}
function pickLatest() {
  const done = S.drafts.filter(d => d && d.text);
  return done.length ? { text: done[done.length - 1].text,
    usage: done[done.length - 1].usage, fp_check: done[done.length - 1].fp_check,
    borrow_check: done[done.length - 1].borrow_check,
    revision: done[done.length - 1].revision || 0 } : null;
}
function onGenEvent(ev, d) {
  if (ev === 'session') {
    S.session_id = d.session_id; S.modelLabel = d.model || S.modelLabel;
    if (d.budget) { S.bstate = d.budget; renderBudget(); }
    updateMeta();
  } else if (ev === 'draft_start') {
    const f = S.batchStart + d.index;
    S.drafts[f] = null;
    $('drafts').insertAdjacentHTML('beforeend',
      streamCardHtml(f, `批${S.batchNo}·稿${d.index + 1}`));
    $('gen_out').textContent = `批${S.batchNo}·稿${d.index + 1} 生成中……`;
  } else if (ev === 'delta') {
    appendStream(S.batchStart + d.index, d.text);
    const live = $('live_' + (S.batchStart + d.index));
    if (live) live.textContent = `……已生成 ${d.chars} 字`;
  } else if (ev === 'replace') {
    replaceStream(S.batchStart + d.index, d.text, d.chars);
  } else if (ev === 'reasoning') {
    const live = $('live_' + (S.batchStart + d.index));
    if (live) live.textContent = '……模型思考中（reasoning）';
  } else if (ev === 'status') {
    $('gen_out').textContent = d.message;
  } else if (ev === 'draft_done') {
    const f = S.batchStart + d.index;
    const label = `批${S.batchNo}·稿${d.index + 1}`;
    S.drafts[f] = { text: d.text, usage: d.usage, fp_check: d.fp_check,
                    borrow_check: d.borrow_check, ai_cliche: d.ai_cliche,
                    numbers_check: d.numbers_check, names_check: d.names_check,
                    batch: S.batchNo, label };
    const card = $('card_' + f);
    if (card) card.outerHTML = cardHtml(S.drafts[f], f);
    refreshPick(); setStage(4);  // 只换本稿卡片——别稿可能仍在流式
    persistBatches();
  } else if (ev === 'error') {
    $('gen_out').textContent = '失败：' + d.message;
  } else if (ev === 'all_done') {
    if (d.budget) { S.bstate = d.budget; renderBudget(); }
    if (!S.drafts.some(x => x && x.batch === S.batchNo)) return;
    const hot = S.drafts.filter(x => x && x.batch === S.batchNo
                                    && x.usage && x.usage.retries >= 2);
    if (hot.length)
      $('gen_out').innerHTML = `本批完成。⚠ ${esc(hot[0].label)} 经 `
        + `${hot[0].usage.retries} 次截断重试（消耗 `
        + `${Math.round((hot[0].usage.completion_tokens || 0) / 1000)}k tokens、`
        + `耗时约 ×${hot[0].usage.retries + 1}）——建议给写作路由换非思考模型`;
    else
      $('gen_out').textContent = '本批完成——可再点「生成正文」加一批对比，或直接采用交付。';
  }
}
async function reviseDraft(i) {
  const d = S.drafts[i];
  if (!(d.text || '').trim()) return toast('空稿无需修订——若反复为空多半是思考模型耗尽 max_tokens', 'bad');
  if (budgetBlocked()) return;
  if (S.bstate && S.bstate.state === 'warning' && !S.overBudget
      && !confirm(`⚠ 预警闸：本章已烧 ${Math.round(S.bstate.spend / 1000)}k / 预算 ${Math.round(S.bstate.chapter_budget / 1000)}k tokens——继续修订？`)) return;
  if (!confirm(`按报告修订会重写【${d.label}】的语言层（结构/立意/收尾保留），继续？`)) return;
  const body = {...S.req, title: $('title').value, chosen: S.chosen || {},
    beats: S.beats, text: d.text,
    reports: { fp_check: d.fp_check, borrow_check: d.borrow_check, ending: d.ending || null },
    revision: d.revision || 0, target_chars: targetChars(), session_id: S.session_id,
    allow_over_budget: S.overBudget === true };
  const card = $('card_' + i);
  if (card) card.innerHTML = `<strong>${d.label}</strong>（修订生成中<span class="meta">……</span>）
    <div class="passage streambox" id="rbox_${i}"></div>`;
  const oldText = d.text;
  const apply = r => {
    S.drafts[i] = { ...S.drafts[i], prevText: oldText, text: r.text, usage: r.usage,
      fp_check: r.fp_check, borrow_check: r.borrow_check, ai_cliche: r.ai_cliche,
      revision: r.revision, ending: null };
    if (r.budget) { S.bstate = r.budget; renderBudget(); }
    renderDrafts(); setStage(4);
    persistBatches();
  };
  try {
    if ($('use_stream').checked) {
      await sse('/app/api/revise_stream', body, (ev, r) => {
        if (ev === 'session') { S.session_id = r.session_id;
          if (r.budget) { S.bstate = r.budget; renderBudget(); } }
        else if (ev === 'delta') appendStream(i, r.text);
        else if (ev === 'replace') replaceStream(i, r.text, r.chars);
        else if (ev === 'status' || ev === 'error') {
          $('gen_out').textContent = r.message;
          if (ev === 'error') renderDrafts();  // 恢复卡片原状
        } else if (ev === 'revised_done') apply({ ...r, revision: r.revision });
      });
    } else {
      const r = await post('/app/api/revise', body);
      S.session_id = r.session_id;
      apply(r);
    }
  } catch (e) { toast('修订失败：' + e.message, 'bad'); renderDrafts(); }
}
async function endingCheck(i) {
  $('end_' + i).textContent = '判官检查中……';
  try {
    const d = await post('/app/api/ending_check', { project: $('project').value,
      title: $('title').value, text: S.drafts[i].text, session_id: S.session_id });
    const v = d.ending_check;
    S.drafts[i].ending = v;
    $('end_' + i).innerHTML = v.violation
      ? `<span style="color:var(--bad)">⚠ ${v.reason}——按纪律应重写收尾再交付</span>`
      : `<span style="color:var(--good)">✓ ${v.reason}</span>`;
  } catch (e) { $('end_' + i).textContent = '失败：' + e.message; }
}
function diffHtml(a, b) {  // 段落级 LCS：保序对齐，其余标增/删
  const A = a.split(/\n+/).filter(x => x.trim()), B = b.split(/\n+/).filter(x => x.trim());
  const n = A.length, m = B.length;
  const dp = Array.from({length: n + 1}, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      dp[i][j] = A[i] === B[j] ? dp[i+1][j+1] + 1 : Math.max(dp[i+1][j], dp[i][j+1]);
  let i = 0, j = 0, out = '';
  const e = t => t.replace(/</g, '&lt;');
  while (i < n && j < m) {
    if (A[i] === B[j]) { out += `<p style="color:var(--muted)">${e(A[i])}</p>`; i++; j++; }
    else if (dp[i+1][j] >= dp[i][j+1]) { out += `<p style="color:var(--bad);text-decoration:line-through">${e(A[i++])}</p>`; }
    else { out += `<p style="color:var(--good)">${e(B[j++])}</p>`; }
  }
  while (i < n) out += `<p style="color:var(--bad);text-decoration:line-through">${e(A[i++])}</p>`;
  while (j < m) out += `<p style="color:var(--good)">${e(B[j++])}</p>`;
  return `<div class="passage" style="max-height:40vh;overflow:auto;font-size:13.5px">${out}</div>`;
}
async function doSave() {
  const i = +$('pick').value;
  const d = S.drafts[i];
  if (!d) return toast('还没有可交付的稿', 'bad');
  if (!(d.text || '').trim()) return toast('草稿为空，拒绝交付——请重新生成', 'bad');
  if (!$('title').value.trim() && !confirm('章节题为空，将保存为「未命名」，继续？')) return;
  if (!d.ending && !confirm('【收尾检查】此稿还没跑、或修订后没重跑（思想层硬性条目）。仍要交付？')) return;
  if (S.g0info && S.g0info.probe && !confirm(
    '【探针章】本章是本弧前 2 章之一（图纸探针）。请确认已通读并验收本稿——探针未过不连跑。继续交付？')) return;
  const r = await post('/app/api/save', {...S.req, title: $('title').value,
    text: d.text, chosen: S.chosen || {}, beats: S.beats,
    tone_note: $('tone_note').value, canon_anchor: $('canon_anchor').value,
    checks: { fp_check: d.fp_check, borrow_check: d.borrow_check,
              ending: d.ending || null },
    usage: d.usage, target_chars: targetChars(), session_id: S.session_id,
    g0: g0Payload() });
  const nums = r.numbers_check;
  const numLine = nums
    ? `｜数字对照：<span style="color:${nums.exit_code === 0 ? 'var(--good)' : 'var(--bad)'}">${nums.exit_code === 0 ? '✓ 无表外项' : '⚠ 有发现项（落账/豁免/改文，详见交付记录）'}</span>`
    : '';
  $('save_out').innerHTML = `已交付 ✓ ${r.manuscript}｜会话已存 sessions/（可复判）${numLine}`
    + (r.session_totals && r.session_totals.tokens
      ? `｜本章累计 ${Math.round(r.session_totals.tokens / 1000)}k tokens / ${r.session_totals.calls} 次调用`
      : '');
  setStage(5);
  memoryDelta();  // 交付后自动登记（隔离区）
}
// ---- 局部改写 / 导出（v0.9.3）----
async function rewriteFragment(i) {
  const d = S.drafts[i];
  if (!d || !(d.text || '').trim()) return alert('空稿');
  const fragment = prompt(`局部改写——粘贴要改的片段（须原样取自本稿）：`);
  if (!fragment) return;
  if (!d.text.includes(fragment)) return alert('片段不在本稿中——请原样粘贴');
  const instruction = prompt('改写指令（如：更冷一点 / 加两句环境 / 对话缩短）：');
  if (!instruction) return;
  if (!confirm(`按"${instruction}"改写该片段？其余正文要求逐字保留。`)) return;
  const card = $('card_' + i);
  if (card) card.innerHTML = `<strong>${d.label}</strong>（局部改写中<span class="meta">……</span>）
    <div class="passage streambox" id="rbox_${i}"></div>`;
  try {
    const r = await post('/app/api/rewrite', {...S.req, title: $('title').value,
      chosen: S.chosen || {}, beats: S.beats, text: d.text,
      fragment, instruction, session_id: S.session_id });
    S.session_id = r.session_id;
    S.drafts[i] = { ...d, prevText: d.text, text: r.text, usage: r.usage,
      fp_check: r.fp_check, borrow_check: r.borrow_check, ai_cliche: r.ai_cliche,
      ending: null };
    renderDrafts();
    if (r.kept_warning)
      $('gen_out').innerHTML = `<span style="color:var(--bad)">⚠ 局部改写保留率仅 ${r.kept_ratio}（<0.6）——模型动了片段之外的内容，建议回退（本批旧稿仍在）或再改</span>`;
    else
      $('gen_out').textContent = `局部改写完成（其余保留率 ${r.kept_ratio}）`;
    persistBatches();
  } catch (e) { toast('改写失败：' + e.message, 'bad'); renderDrafts(); }
}
async function doExport() {
  const a = prompt('导出起始章号：', $('chapter_no').value || '1');
  if (!a) return;
  const b = prompt('导出结束章号：', $('chapter_no').value || '1');
  if (!b) return;
  const r = await fetch('/app/api/export', { method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ project: $('project').value,
                           chapter_from: +a, chapter_to: +b }) });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    return alert('导出失败：' + (d.detail || r.status));
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const aEl = document.createElement('a');
  aEl.href = url; aEl.download = `${$('project').value}-${a}-${b}.txt`;
  aEl.click(); URL.revokeObjectURL(url);
}
// ---- 记忆·隔离区（v0.9.0）----
async function memoryDelta() {
  const i = +$('pick').value;
  const d = S.drafts[i];
  if (!d || !S.beats.length) return;
  try {
    const r = await post('/app/api/memory/delta', {
      project: $('project').value, chapter_no: +$('chapter_no').value,
      title: $('title').value || '未命名', text: d.text, beats: S.beats,
      session_id: S.session_id });
    $('memorybox').style.display = '';
    $('save_out').innerHTML += `｜已登记记忆 ${r.proposed.length} 条（隔离区）`;
    if ($('sumcard')) renderSummaryCard(r);  // 连载台：总结卡显性化
    loadPending();
  } catch (e) {
    $('memorybox').style.display = '';
    $('mem_list').innerHTML = `<p class="meta">登记失败：${e.message}（可稍后手动重试交付或忽略）</p>`;
  }
}
async function loadPending() {
  try {
    const v = await (await fetch('/app/api/memory/pending?project='
      + encodeURIComponent($('project').value))).json();
    if (!v.total) {
      $('mem_list').innerHTML = '<p class="meta">隔离区为空（低风险项已合并或无变更）。</p>';
      return;
    }
    const row = it => `<div class="genrow"><code>${esc(it.entity)}.${esc(it.field)}</code>
      <span class="meta">${esc(it.value)}</span>
      <button class="btn ghost" onclick="memMerge(${it.id}, false)">合并</button>
      <button class="btn ghost" onclick="memMerge(${it.id}, true)">确认高风险合并</button></div>`;
    let html = '';
    for (const [rk, label] of [['high', '🔴 高风险（逐条确认）'],
                                ['medium', '🟡 中风险'], ['low', '🟢 低风险（可直接合并）']]) {
      const g = (v.groups[rk] || []);
      if (g.length)
        html += `<p class="meta">${label} ${g.length} 条</p>` + g.map(row).join('');
    }
    $('mem_list').innerHTML = html;
  } catch (e) { $('mem_list').innerHTML = '<p class="meta">' + e.message + '</p>'; }
}
async function memMerge(id, force) {
  if (force && !confirm('确认合并该高风险变更？（core 实体变动/伏笔，将写入正式记忆）')) return;
  try {
    const r = await post('/app/api/memory/merge', {
      project: $('project').value, ids: [id], force });
    if (r.blocked && r.blocked.length)
      alert('该条为中/高风险，须点"确认高风险合并"');
    loadPending();
  } catch (e) { toast(e.message, 'bad'); }
}
function renderSummaryCard(r) {
  // v0.13.0 连载台：交付总结显性化（数据全部来自现有 propose_delta，零新提取）
  const items = (r.proposed || []).map(p =>
    `<div class="genrow"><code>${esc(p.entity)}.${esc(p.field)}</code>` +
    `<span class="meta">${esc(p.value || '')}${p.risk ? '｜' + esc(p.risk) : ''}</span></div>`
  ).join('') || '<p class="meta">（无状态变更登记）</p>';
  $('sumcard_body').innerHTML =
    `<p class="meta"><strong>本章摘要：</strong>${esc(r.digest || '')}</p>${items}` +
    `<p class="meta">扫一眼确认无误 → 下方隔离区合并，下一章装配自动带前情。</p>`;
  $('sumcard').style.display = '';
}
init();
