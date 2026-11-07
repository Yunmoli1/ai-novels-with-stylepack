// -*- coding: utf-8 -*-
// units.js：单元卡面板（v0.13.14，连载台专有）。
// 单元 = 运动 = 1~N 章 = 发布单位 = 验收单位 = 记忆单位；章不需要完整，单元才需要。
// 前置卡（故事卡）=闸门：批准才解锁生成，四行运动弧全文随 G0 进提示词（故事卡不压缩）。
// 后置卡（封卡）=L1 记忆：memory/units.md 原生格式（泰拉灾厄协议，会话互通）。
// 容器不判官：四道过滤+跳读测试 checklist 只记录不判定（人工工序必须留痕）。

function unitOpen() {
  const box = document.getElementById('unitsbox');
  if (!box) return;
  const open = box.style.display === 'none';
  box.style.display = open ? '' : 'none';
  if (open) unitLoad();
}

async function unitLoad() {
  const proj = document.getElementById('project').value;
  if (!proj) return;
  try {
    const d = await (await fetch('/app/api/serial/units?project='
      + encodeURIComponent(proj))).json();
    S.units = d.units || [];
    S.unitCards = d.memory_cards || [];
    S.unitNextId = d.next_id;
    unitRender();
  } catch (e) {
    const out = document.getElementById('units_out');
    if (out) out.textContent = '载入失败：' + e.message;
  }
}

function unitNewForm() {
  document.getElementById('unit_new').style.display = '';
  document.getElementById('unit_new_id').value = S.unitNextId || '';
}

async function unitCreate() {
  const g = id => document.getElementById(id).value.trim();
  const chs = g('unit_new_chs').split(/[,,]/).map(s => +s.trim())
    .filter(n => n > 0);
  try {
    await post('/app/api/serial/units/create', {
      project: document.getElementById('project').value,
      id: g('unit_new_id'), title: g('unit_new_title'), chapters: chs });
    document.getElementById('unit_new').style.display = 'none';
    toast('单元已创建（草稿）——填故事卡后批准', 'good');
    unitLoad();
  } catch (e) { toast(e.message, 'bad'); }
}

const UNIT_FIELDS = [['kai', '开端'], ['tui', '推进'], ['zhe', '转折'],
                     ['luo', '落点']];
const UNIT_CHECKS = ['跳读测试', '对话出声读', '人格锚点对照', '讲古打断',
                     '情绪停留'];

function unitSel(id) { S.unitSel = S.unitSel === id ? '' : id; unitRender(); }
function unitBadge(st) {
  return st === 'approved'
    ? '<span style="color:var(--good)">已批准</span>'
    : st === 'sealed'
      ? '<span style="color:var(--acc,#69c)">已封卡</span>'
      : '<span class="meta">草稿</span>';
}
function unitStoryInput(id, k, v) {
  const u = (S.units || []).find(x => x.id === id);
  if (!u) return;
  u.story = u.story || {};
  u.story[k] = v;
}
function unitTitleInput(id, v) {
  const u = (S.units || []).find(x => x.id === id);
  if (u) u.title = v;
}
function unitChapterInput(id, v) {
  const u = (S.units || []).find(x => x.id === id);
  if (!u) return;
  u.chapters = v.split(/[,,]/).map(s => +s.trim()).filter(n => n > 0);
}

async function unitSave(id) {
  const u = (S.units || []).find(x => x.id === id);
  if (!u) return;
  try {
    await post('/app/api/serial/units/update', {
      project: document.getElementById('project').value,
      id, title: u.title, chapters: u.chapters, story: u.story });
    toast('故事卡已保存（草稿）', 'good');
    unitLoad();
  } catch (e) { toast(e.message, 'bad'); }
}

async function unitApprove(id) {
  const u = (S.units || []).find(x => x.id === id);
  if (!u) return;
  try {
    await post('/app/api/serial/units/update', {
      project: document.getElementById('project').value,
      id, story: u.story, chapters: u.chapters, status: 'approved' });
    toast('已批准——本单元各章生成解锁（故事卡全文随提示词进上下文）', 'good');
    unitLoad();
  } catch (e) { toast(e.message, 'bad'); }
}

async function unitSealDraft(id) {
  const out = document.getElementById('useal_out_' + id);
  if (out) out.textContent = '封卡草拟中（单发调用）……';
  try {
    const r = await post('/app/api/serial/units/seal_draft', {
      project: document.getElementById('project').value, id });
    S.unitSeal = S.unitSeal || {};
    S.unitSeal[id] = r.candidate || {};
    unitRender();
  } catch (e) { if (out) out.textContent = '失败：' + e.message; }
}

async function unitSealConfirm(id) {
  const card = (document.getElementById('useal_ta_' + id) || {}).value || '';
  const chk = {};
  UNIT_CHECKS.forEach(k => {
    const el = document.getElementById('uchk_' + id + '_' + k);
    if (el) chk[k] = el.checked;
  });
  try {
    await post('/app/api/serial/units/seal_confirm', {
      project: document.getElementById('project').value, id, card,
      checklist: chk });
    toast('已封卡——L1 单元卡落 memory/units.md（下一单元装配自动带前情）',
          'good');
    if (S.unitSeal) delete S.unitSeal[id];
    unitLoad();
  } catch (e) { toast(e.message, 'bad'); }
}

function unitRender() {
  const list = document.getElementById('units_list');
  if (!list) return;
  const units = S.units || [];
  if (!units.length) {
    list.innerHTML = '<p class="meta">（尚无单元——点「＋ 新单元」起第一张故事卡）</p>';
    return;
  }
  list.innerHTML = units.map(u => {
    const open = S.unitSel === u.id;
    const chs = (u.chapters || []).map(c => {
      const st = (u.chapters_status || []).find(x => x.no === c);
      return c + (st && st.delivered ? '✓' : '…');
    }).join('、');
    const head = `<div class="panel" style="margin:4px 0;cursor:pointer" onclick="unitSel('${u.id}')">` +
      `<strong>${u.id}《${u.title}》</strong> ${unitBadge(u.status)}｜章：${chs || '（未排）'}</div>`;
    if (!open) return head;
    const s = u.story || {};
    let body = '<div class="panel" style="margin:-2px 0 6px">';
    if (u.status === 'sealed') {
      body += '<p class="meta">已封卡——L1 记忆在 memory/units.md（只读）。</p>' +
        `<pre style="white-space:pre-wrap;font-size:12px">${(u.sealed_card || '')}</pre></div>`;
      return head + body;
    }
    body += `<label>单元题 <input value="${u.title}" oninput="unitTitleInput('${u.id}', this.value)" style="width:200px"></label>` +
      ` <label>章号 <input value="${(u.chapters || []).join(',')}" oninput="unitChapterInput('${u.id}', this.value)" style="width:130px"></label>` +
      '<div class="genrow">' +
      UNIT_FIELDS.map(([k, label]) =>
        `<label style="flex:1 1 45%">${label}<textarea rows="2" style="width:100%" ` +
        `oninput="unitStoryInput('${u.id}', '${k}', this.value)">${(s[k] || '')}</textarea></label>`).join('') +
      '</div>' +
      `<label>单元末钩子 <input value="${(s.hook || '')}" oninput="unitStoryInput('${u.id}', 'hook', this.value)" style="width:320px"></label>` +
      `<label>涉及术语/伏笔 <input value="${(s.refs || '')}" oninput="unitStoryInput('${u.id}', 'refs', this.value)" style="width:260px"></label>` +
      `<label>长度带 <input value="${(s.band || '')}" oninput="unitStoryInput('${u.id}', 'band', this.value)" style="width:130px" placeholder="如 2500-4500"></label>` +
      '<div class="genrow">' +
      `<button class="btn ghost" onclick="unitSave('${u.id}')">💾 保存</button>` +
      (u.status === 'draft'
        ? `<button class="btn" onclick="unitApprove('${u.id}')">✅ 批准——解锁生成</button>`
        : '') +
      `<button class="btn ghost" onclick="unitSealDraft('${u.id}')">🤖 封卡草拟</button>` +
      '</div>';
    if (u.status === 'approved') {
      const done = (u.chapters_status || []).filter(x => x.delivered).length;
      const all = (u.chapters_status || []).length;
      if (!all) {
        body += '<p class="meta">📦 封卡：先排章号并交付。</p>';
      } else if (done < all) {
        body += `<p class="meta">📦 封卡：单元内全章交付后开放（当前 ${done}/${all} 已交付）。</p>`;
      } else {
        const seal = (S.unitSeal || {})[u.id] || {};
        body += '<div class="panel" style="background:var(--panel2,rgba(127,127,127,.08))">' +
          '<p class="meta"><strong>封卡流程</strong>——四道过滤+跳读测试（人工工序，勾选=留痕，不判定质量）：</p>' +
          UNIT_CHECKS.map(k =>
            `<label style="margin-right:10px"><input type="checkbox" id="uchk_${u.id}_${k}"> ${k}</label>`).join('') +
          '<div class="genrow">' +
          `<button class="btn ghost" onclick="unitSealDraft('${u.id}')">🤖 封卡草拟（150-250 字）</button></div>` +
          `<textarea id="useal_ta_${u.id}" rows="4" style="width:100%" placeholder="L1 单元卡草拟后在此编辑——事件链（含结果）/情绪终点/新伏笔线头/人物">${(seal.card || '')}</textarea>` +
          `<p class="meta" id="useal_out_${u.id}">${seal.current_hint ? '快照建议（current.md 手动更新用）：' + seal.current_hint : ''}</p>` +
          `<button class="btn" onclick="unitSealConfirm('${u.id}')">✅ 确认封卡（落 units.md）</button>` +
          '</div>';
      }
    }
    body += '</div>';
    return head + body;
  }).join('');
}

// 数据装载：面板打开时 + 项目切换时（供生成软闸门查询单元状态）
async function unitLoadSilent() {
  const proj = document.getElementById('project') ?
    document.getElementById('project').value : '';
  if (!proj) return;
  try {
    const d = await (await fetch('/app/api/serial/units?project='
      + encodeURIComponent(proj))).json();
    S.units = d.units || [];
    S.unitNextId = d.next_id;
  } catch (e) { /* 静默——闸门缺数据时退化为不拦 */ }
}
