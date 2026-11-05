
// ---- 连载台专有：项目文件树（只读 + 复用既有执法端点 + OS 逃生门）----
let curSub = '';
const esc = s => (s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
let curFile = '';
async function loadTree(sub) {
  curSub = sub || '';
  try {
    const d = await (await fetch('/app/api/serial/tree?project='
      + encodeURIComponent($('project').value) + '&sub=' + encodeURIComponent(curSub))).json();
    $('tree_crumb').innerHTML = '项目根' + (curSub ? ' / ' + esc(curSub)
      + ` <a href="javascript:void(0)" onclick="loadTree('')">↑ 上一级</a>` : '');
    $('tree').innerHTML = d.entries.map(e => {
      const nm = e.dir
        ? `<span class="nm" onclick="loadTree('${esc(e.rel)}')">📁 ${esc(e.name)}/</span>`
        : `<span class="nm" onclick="previewFile('${esc(e.rel)}')">📄 ${esc(e.name)}</span>`;
      const acts = [];
      if (!e.dir && !e.binary) acts.push(`<a href="javascript:void(0)" onclick="previewFile('${esc(e.rel)}')">预览</a>`);
      if (e.rel.startsWith('manuscript/') && e.rel.endsWith('.md')) {
        acts.push(`<a href="javascript:void(0)" onclick="renameCh('${esc(e.name)}','')">改名</a>`);
        acts.push(`<a href="javascript:void(0)" onclick="deleteCh('${esc(e.name)}')">删除</a>`);
      }
      if (!e.dir) acts.push(`<a href="/app/api/serial/download?project=${encodeURIComponent($('project').value)}&path=${encodeURIComponent(e.rel)}">下载</a>`);
      return `<div class="trow${e.ignored ? ' ig' : ''}" title="${esc(e.source || '')}${e.ignored ? '｜运行态文件（不入库）' : ''}">${nm}
        <span class="src">${esc(e.source || '')}${e.ignored ? ' · 不入库' : ''}｜${(e.size / 1024).toFixed(1)}k</span>${acts.join('')}</div>`;
    }).join('') || '<p class="meta">（空目录）</p>';
  } catch (e) { $('tree').innerHTML = '<p class="meta">' + e.message + '</p>'; }
}
async function previewFile(rel) {
  try {
    const d = await (await fetch('/app/api/serial/file?project='
      + encodeURIComponent($('project').value) + '&path=' + encodeURIComponent(rel))).json();
    curFile = rel;
    $('fileview').style.display = '';
    $('fv_title').textContent = d.path + (d.source ? '｜' + d.source : '')
      + `｜${(d.size / 1024).toFixed(1)}k` + (d.binary ? '｜二进制文件（只可下载）' : '');
    $('fv_text').textContent = d.binary ? '（二进制）' : d.text
      + (d.truncated ? '\n…（已截断，全文用「下载原文件」）' : '');
    $('fileview').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) { toast(e.message, 'bad'); }
}
function downloadFile() {
  if (!curFile) return;
  window.open('/app/api/serial/download?project='
    + encodeURIComponent($('project').value) + '&path=' + encodeURIComponent(curFile));
}
async function openFolder() {
  try {
    const r = await post('/app/api/serial/open_folder', { project: $('project').value });
    toast('已在资源管理器打开：' + r.path, 'good');
  } catch (e) { toast(e.message, 'bad'); }
}
async function renameCh(file, old) {
  const t = prompt('新的章节题（章号保留）：', old || file.replace(/^\d+-/, '').replace(/\.md$/, ''));
  if (t === null || !t.trim()) return;
  try {
    const r = await post('/app/api/history/chapter_rename',
      { project: $('project').value, file, new_title: t });
    toast('已改名 → ' + r.file, 'good');
    loadTree(curSub);
  } catch (e) { toast(e.message, 'bad'); }
}
async function deleteCh(file) {
  if (!confirm(`删除 ${file}？文件移入 manuscript/.trash/ 可手动恢复。`)) return;
  try {
    await post('/app/api/history/chapter_delete',
      { project: $('project').value, file });
    toast('已删除（.trash 可恢复）', 'good');
    loadTree(curSub);
  } catch (e) { toast(e.message, 'bad'); }
}
// 项目切换后刷新树（creation.js 的 switchProject 已跑完自身职责）
document.getElementById('project').addEventListener('change', () => loadTree(''));
loadTree('');
