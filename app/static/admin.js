// DBAgent Admin — 管理前端 JS
const BASE = '/api/admin';

let _token = localStorage.getItem('dbagent_admin_token') || '';
// 缓存的选项数据
let _knownUsers = [];
let _knownSchemas = [];  // [{schema_id, database_name}]
let _namespacesByKey = {}; // key = "schema_id/database_name" → [namespace_names]

// ── 初始化 ──
document.addEventListener('DOMContentLoaded', () => {
  if (_token) {
    document.getElementById('adminToken').value = _token;
    connect();
  }
  // Tab switching
  document.querySelectorAll('.tabs button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'overview') loadOverview();
      if (btn.dataset.tab === 'users') loadUserList();
      if (btn.dataset.tab === 'sqlmem') loadSqlMemStatus();
    });
  });
  // Enter key on token input
  document.getElementById('adminToken').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') connect();
  });
});

// ── Helpers ──
function authHeaders() { return { 'Authorization': 'Bearer ' + _token }; }

function api(method, path, body) {
  const opts = { method, headers: { ...authHeaders() } };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  return fetch(BASE + path, opts).then(r => {
    if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.statusText); });
    const ct = r.headers.get('content-type') || '';
    return ct.includes('application/json') ? r.json() : r.text();
  });
}

// 调用非 admin 前缀的端点（如 /api/hdc/*），仍带 admin token
function apiAbs(method, path, body) {
  const opts = { method, headers: { ...authHeaders() } };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  return fetch(path, opts).then(r => {
    if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.statusText); }).catch(() => { throw new Error(r.statusText); });
    const ct = r.headers.get('content-type') || '';
    return ct.includes('application/json') ? r.json() : r.text();
  });
}

function toast(msg, type) {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.getElementById('toastContainer').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function esc(s) { return (s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

// ── Auth ──
async function connect() {
  _token = document.getElementById('adminToken').value.trim();
  if (!_token) { toast('请输入 Admin Token', 'error'); return; }
  localStorage.setItem('dbagent_admin_token', _token);
  try {
    await api('GET', '/overview');
    setAuth(true);
    await Promise.all([loadOptions(), loadOverview()]);
  } catch (e) {
    if (e.message.includes('503')) { toast('Admin API 未配置', 'error'); }
    else if (e.message.includes('401') || e.message.includes('403')) { toast('Token 无效', 'error'); }
    else { toast('连接失败: ' + e.message, 'error'); }
    setAuth(false);
  }
}

function setAuth(ok) {
  const dot = document.getElementById('authDot');
  dot.className = 'status-dot ' + (ok ? 'ok' : 'err');
  dot.title = ok ? '已认证' : '未认证';
}

// ── Options (dropdown data) ──
async function loadOptions() {
  try {
    const [users, schemas] = await Promise.all([
      api('GET', '/options/users'),
      api('GET', '/options/schemas'),
    ]);
    _knownUsers = users;
    _knownSchemas = schemas;
    populateUserDropdowns();
    populateSchemaDropdowns();
  } catch (e) { console.warn('Options load failed:', e); }
}

function populateUserDropdowns() {
  const ids = ['mapUser', 'mapFilterUser', 'seedUser', 'recUser'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const current = el.value;
    const isFilter = id === 'mapFilterUser' || id === 'recUser';
    // 过滤类下拉：全部用户；选择类下拉：-- 选择用户 --
    el.innerHTML = isFilter ? '<option value="">全部用户</option>' : '<option value="">-- 选择用户 --</option>';
    // mapUser（创建映射）和 mapFilterUser 需要通配符 * 选项
    if (id === 'mapUser' || id === 'mapFilterUser') {
      el.innerHTML += '<option value="*">* （全局默认）</option>';
    }
    _knownUsers.forEach(u => { el.innerHTML += `<option value="${u}">${u}</option>`; });
    if (current) el.value = current;
  });
}

function populateSchemaDropdowns() {
  const ids = ['hdcBrowseSchemaDb', 'mapSchemaDb', 'mapFilterSchemaDb', 'recDb', 'hdcKbSchemaDb'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const current = el.value;
    const hasAll = el.querySelector('option[value=""]')?.textContent.includes('全部');
    el.innerHTML = hasAll ? '<option value="">全部数据库</option>' : '<option value="">-- 选择数据库 --</option>';
    _knownSchemas.forEach(s => {
      const key = `${s.schema_id}/${s.database_name}`;
      el.innerHTML += `<option value="${key}">${s.schema_id} / ${s.database_name}</option>`;
    });
    if (current) el.value = current;
  });
}

function parseSchemaKey(key) {
  if (!key) return [null, null];
  const idx = key.indexOf('/');
  if (idx < 0) return [null, null];
  return [parseInt(key.slice(0, idx)), key.slice(idx + 1)];
}

// ── Overview ──
async function loadOverview() {
  if (!_token) return;
  try {
    const data = await api('GET', '/overview');
    document.getElementById('overviewStats').innerHTML = `
      <div class="stat-card"><div class="label">用户数</div><div class="value">${data.distinct_users}</div></div>
      <div class="stat-card alt-1"><div class="label">会话数</div><div class="value">${data.total_sessions}</div></div>
      <div class="stat-card alt-2"><div class="label">SQL 记忆</div><div class="value">${data.sql_memory_records}</div></div>
      <div class="stat-card alt-3"><div class="label">映射数据库</div><div class="value">${data.mapped_hdc_namespaces?.length || 0}</div></div>`;
    const ns = data.mapped_hdc_namespaces || [];
    document.getElementById('overviewMappings').innerHTML = ns.length
      ? '<table><tr><th>Schema ID</th><th>Database</th><th>Namespace 数</th></tr>' + ns.map(n => `<tr><td>${n.schema_id}</td><td>${n.database_name}</td><td>${n.namespace_count}</td></tr>`).join('') + '</table>'
      : '<div class="empty">暂无映射</div>';
  } catch (e) { toast('概览加载失败: ' + e.message, 'error'); }
}

// ── Users ──
async function loadUserList() {
  try {
    const overview = await api('GET', '/overview');
    const mappings = await api('GET', '/hdc-mappings');
    const users = await api('GET', '/options/users');

    // Build per-user HDC mapping lookup
    const userMappings = {};
    mappings.forEach(m => {
      if (!userMappings[m.user_id]) userMappings[m.user_id] = [];
      userMappings[m.user_id].push(m);
    });

    // Build per-user SQL memory count lookup (batch query stats)
    const userMemCounts = {};
    try {
      const stats = await api('GET', '/sql-memory/stats');
      if (stats && stats.database_distribution) {
        // Approximate: total records / user count as rough estimate
        // Better: do per-user queries
        for (const u of users) {
          try {
            const recs = await api('GET', `/sql-memory/records?user_id=${encodeURIComponent(u)}&limit=1`);
            userMemCounts[u] = recs.total || 0;
          } catch (_) { userMemCounts[u] = 0; }
        }
      }
    } catch (_) {}

    let html = '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap">';
    html += '<button class="btn btn-danger btn-sm" onclick="purgeUsers()">🗑 批量注销</button>';
    html += '<span style="font-size:0.78rem;color:var(--muted)">勾选后点击注销，将清除该用户的所有会话、HDC 映射和 SQL 记忆</span>';
    html += '</div>';

    html += '<div class="user-grid">';
    users.forEach(u => {
      const mCount = (userMappings[u] || []).length;
      const memCount = userMemCounts[u] || 0;
      const initial = u.charAt(0).toUpperCase();
      html += '<div class="user-card">' +
        '<label class="user-card-check">' +
          `<input type="checkbox" class="user-checkbox" value="${esc(u)}">` +
        '</label>' +
        '<div class="user-card-avatar">' + esc(initial) + '</div>' +
        '<div class="user-card-body">' +
          `<div class="user-card-name" title="${esc(u)}">${esc(u)}</div>` +
          `<div class="user-card-meta">` +
            `<span title="HDC 映射">🔗 ${mCount}</span>` +
            `<span title="SQL 记忆">🧠 ${memCount}</span>` +
          `</div>` +
        '</div>' +
        `<button class="btn btn-secondary btn-sm user-card-btn" onclick="showUserDetail('${esc(u)}')">详情</button>` +
      '</div>';
    });
    html += '</div>';
    if (users.length === 0) html += '<div class="empty">暂无用户</div>';
    document.getElementById('userListTable').innerHTML = html;
  } catch (e) { toast('用户列表加载失败: ' + e.message, 'error'); }
}

function toggleSelectAllUsers() {
  const checked = document.getElementById('selectAllUsers').checked;
  document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = checked);
}

async function purgeUsers() {
  const selected = [];
  document.querySelectorAll('.user-checkbox:checked').forEach(cb => selected.push(cb.value));
  if (selected.length === 0) { toast('请先勾选要注销的用户', 'error'); return; }
  if (!confirm(`确定要注销 ${selected.length} 个用户吗？\n\n这将删除他们的：\n- 所有会话记录\n- 所有 HDC namespace 映射\n- 所有 SQL 记忆记录\n\n此操作不可撤销！`)) return;

  try {
    const result = await api('POST', '/users/purge', { user_ids: selected });
    const parts = [];
    parts.push(`${result.deleted_users.length} 个用户已注销`);
    if (result.deleted_sessions > 0) parts.push(`\u{1F5D1} ${result.deleted_sessions} 个会话`);
    if (result.deleted_mappings > 0) parts.push(`\u{1F517} ${result.deleted_mappings} 个映射`);
    if (result.deleted_sql_memories > 0) parts.push(`\u{1F9E0} ${result.deleted_sql_memories} 条记忆`);
    toast(parts.join(' · '), 'success');
    if (result.failed_users.length > 0) {
      toast(`注销失败: ${result.failed_users.join(', ')}`, 'error');
    }
    loadUserList();
  } catch (e) { toast('注销失败: ' + e.message, 'error'); }
}

async function showUserDetail(userId) {
  document.getElementById('userDetailSection').style.display = 'block';
  document.getElementById('userDetail').innerHTML = '<div class="loading">加载中...</div>';

  try {
    // Fetch per-user HDC mappings
    const mappings = await api('GET', `/hdc-mappings?user_id=${encodeURIComponent(userId)}`);
    // Fetch per-user SQL memory stats
    let memStats = null;
    try { memStats = await api('GET', `/sql-memory/stats?user_id=${encodeURIComponent(userId)}`); } catch (_) {}
    // Fetch per-user SQL memory records count
    let memCount = 0;
    try { const r = await api('GET', `/sql-memory/records?user_id=${encodeURIComponent(userId)}&limit=1`); memCount = r.total; } catch (_) {}

    let html = `<div class="stat-grid" style="margin-bottom:16px">`;
    html += `<div class="stat-card"><div class="label">用户</div><div class="value" style="font-size:1.1rem">${esc(userId)}</div></div>`;
    html += `<div class="stat-card"><div class="label">HDC 映射数</div><div class="value">${mappings.length}</div></div>`;
    html += `<div class="stat-card"><div class="label">SQL 记忆数</div><div class="value">${memCount}</div></div>`;
    html += `</div>`;

    // HDC mappings for this user
    html += `<h3>HDC Mappings</h3>`;
    if (mappings.length > 0) {
      html += '<table><tr><th>Schema ID</th><th>Database</th><th>Namespace</th><th>更新时间</th><th></th></tr>';
      mappings.forEach(m => {
        html += '<tr>' +
          `<td>${m.schema_id}</td><td>${esc(m.database_name)}</td><td><span class="badge-tag">${esc(m.hdc_namespace)}</span></td>` +
          `<td>${esc(m.updated_at)}</td>` +
          `<td><button class="btn btn-danger btn-sm" onclick="deleteMapping('${esc(m.user_id)}',${m.schema_id},'${esc(m.database_name)}')">删除</button></td>` +
          '</tr>';
      });
      html += '</table>';
    } else {
      html += '<div class="empty">该用户暂无 HDC 映射</div>';
    }

    // SQL Memory stats for this user
    if (memStats) {
      html += `<h3 style="margin-top:20px">SQL Memory 统计</h3>`;
      html += `<div class="stat-grid" style="margin-bottom:12px">`;
      if (memStats.daily_histogram) {
        const days = Object.keys(memStats.daily_histogram).sort().slice(-5);
        html += `<div class="stat-card"><div class="label">最近活跃</div><div class="value" style="font-size:1rem">${days.length > 0 ? days[days.length-1] : 'N/A'}</div></div>`;
      }
      html += `</div>`;
      if (memStats.table_distribution && Object.keys(memStats.table_distribution).length > 0) {
        html += '<h4>常用表</h4>';
        const sorted = Object.entries(memStats.table_distribution).sort((a,b) => b[1] - a[1]).slice(0, 10);
        html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:16px">';
        sorted.forEach(([t, c]) => { html += `<span class="badge-tag">${esc(t)} (${c})</span>`; });
        html += '</div>';
      }
    }

    document.getElementById('userDetail').innerHTML = html;
  } catch (e) { document.getElementById('userDetail').innerHTML = `<div class="empty">加载失败: ${esc(e.message)}</div>`; }
}

// ── HDC ──
async function browseNamespaces() {
  const key = document.getElementById('hdcBrowseSchemaDb').value;
  if (!key) return;
  const [sid, db] = parseSchemaKey(key);
  if (!sid || !db) return;
  try {
    const data = await api('GET', `/hdc/namespaces/${sid}/${db}`);
    document.getElementById('namespaceList').innerHTML = data.length
      ? data.map((n, i) => {
          const colors = ['teal','sky','amber','rose','violet'];
          return `<span class="badge-tag ${colors[i % colors.length]}">${n}</span>`;
        }).join(' ')
      : '<div class="empty">无可用 namespace</div>';
    // Also populate the create-mapping namespace dropdown
    const nsSelect = document.getElementById('mapNs');
    nsSelect.innerHTML = '<option value="">-- 选择 namespace --</option>';
    data.forEach(n => { nsSelect.innerHTML += `<option value="${n}">${n}</option>`; });
    _namespacesByKey[key] = data;
  } catch (e) { toast('浏览失败: ' + e.message, 'error'); }
}

async function onMapSchemaChange() {
  const key = document.getElementById('mapSchemaDb').value;
  const nsSelect = document.getElementById('mapNs');
  if (!key) { nsSelect.innerHTML = '<option value="">-- 选择数据库 --</option>'; return; }
  // 有缓存直接用
  if (_namespacesByKey[key]) {
    nsSelect.innerHTML = '<option value="">-- 选择 namespace --</option>';
    _namespacesByKey[key].forEach(n => { nsSelect.innerHTML += `<option value="${n}">${n}</option>`; });
    return;
  }
  // 没有缓存，自动拉取
  nsSelect.innerHTML = '<option value="">加载中...</option>';
  const [sid, db] = parseSchemaKey(key);
  if (!sid || !db) { nsSelect.innerHTML = '<option value="">-- 无效数据库 --</option>'; return; }
  try {
    const data = await api('GET', `/hdc/namespaces/${sid}/${db}`);
    _namespacesByKey[key] = data;
    nsSelect.innerHTML = '<option value="">-- 选择 namespace --</option>';
    data.forEach(n => { nsSelect.innerHTML += `<option value="${n}">${n}</option>`; });
  } catch (e) {
    nsSelect.innerHTML = '<option value="">-- 加载失败 --</option>';
  }
}

async function createMapping() {
  const user = document.getElementById('mapUser').value;
  const key = document.getElementById('mapSchemaDb').value;
  const ns = document.getElementById('mapNs').value;
  if (!user) { toast('请选择用户', 'error'); return; }
  if (!key) { toast('请选择数据库', 'error'); return; }
  if (!ns) { toast('请选择 namespace（先浏览）', 'error'); return; }
  const [sid, db] = parseSchemaKey(key);
  if (!sid || !db) return;

  try {
    await api('POST', '/hdc-mappings', { user_id: user, schema_id: sid, database_name: db, hdc_namespace: ns });
    toast('映射已创建', 'success');
    listMappings();
  } catch (e) { toast('创建失败: ' + e.message, 'error'); }
}

async function listMappings() {
  const user = document.getElementById('mapFilterUser').value;
  const key = document.getElementById('mapFilterSchemaDb').value;
  const [sid, db] = parseSchemaKey(key);
  const params = [];
  if (user) params.push(`user_id=${encodeURIComponent(user)}`);
  if (sid && db) { params.push(`schema_id=${sid}`); params.push(`database_name=${encodeURIComponent(db)}`); }
  const qs = params.length ? '?' + params.join('&') : '';
  try {
    const data = await api('GET', '/hdc-mappings' + qs);
    document.getElementById('mappingTable').innerHTML = data.length
      ? '<table><tr><th>用户</th><th>Schema ID</th><th>Database</th><th>Namespace</th><th>更新时间</th><th></th></tr>'
        + data.map(m => `<tr>
          <td>${m.user_id}</td><td>${m.schema_id}</td><td>${m.database_name}</td><td><span class="badge-tag">${m.hdc_namespace}</span></td>
          <td>${(m.updated_at||'').slice(0,19)}</td>
          <td><button class="btn btn-danger btn-sm" onclick="deleteMapping('${m.user_id}',${m.schema_id},'${esc(m.database_name)}')">删除</button></td>
        </tr>`).join('') + '</table>'
      : '<div class="empty">暂无映射</div>';
  } catch (e) { toast('查询失败: ' + e.message, 'error'); }
}

async function deleteMapping(uid, sid, db) {
  if (!confirm(`确认删除 ${uid} / ${db} 的映射？`)) return;
  try {
    await api('DELETE', `/hdc-mappings?user_id=${encodeURIComponent(uid)}&schema_id=${sid}&database_name=${encodeURIComponent(db)}`);
    toast('已删除', 'success');
    listMappings();
  } catch (e) { toast('删除失败: ' + e.message, 'error'); }
}

// ── HDC 知识库管理（构建/更新/状态/删除）──
const _hdcPollers = {};  // task_id → interval

async function hdcKbListNamespaces() {
  const { sid, db } = _hdcKbParams();
  if (!sid || !db) { toast('请先选择 Schema / DB', 'error'); return; }
  const resultEl = document.getElementById('hdcKbResult');
  resultEl.innerHTML = '<div class="loading">查询 namespace...</div>';
  try {
    const data = await api('GET', `/hdc/namespaces/${sid}/${encodeURIComponent(db)}`);
    if (!data.length) {
      resultEl.innerHTML = '<div class="empty">该数据库下无 namespace</div>';
      return;
    }
    let html = '<h4 style="margin:0 0 8px">可用 Namespace</h4>';
    html += '<div style="display:flex;flex-wrap:wrap;gap:8px">';
    data.forEach(ns => {
      html += `<div class="user-card" style="padding:6px 10px;gap:8px">
        <span class="badge-tag" style="font-size:0.85rem">${esc(ns)}</span>
        <button class="btn btn-secondary btn-sm" onclick="document.getElementById('hdcKbNs').value='${esc(ns)}'" title="填入 Namespace 输入框">填入</button>
        <button class="btn btn-danger btn-sm" onclick="hdcKbDeleteOneNs('${esc(ns)}')" title="只删该 namespace">删</button>
      </div>`;
    });
    html += '</div>';
    html += '<div class="empty" style="margin-top:8px">点"填入"可快速选定单个 namespace 用于构建/更新/状态查询</div>';
    resultEl.innerHTML = html;
  } catch (e) { resultEl.innerHTML = `<div class="empty">查询失败: ${esc(e.message)}</div>`; }
}

async function hdcKbDeleteOneNs(ns) {
  const { sid, db } = _hdcKbParams();
  if (!sid || !db) { toast('请先选择 Schema / DB', 'error'); return; }
  if (!confirm(`确认只删除 namespace <${ns}>？\n\n数据库 ${db} 的其他 namespace 不受影响。此操作不可撤销！`)) return;
  const resultEl = document.getElementById('hdcKbResult');
  resultEl.innerHTML = `<div class="loading">删除 namespace ${esc(ns)}...</div>`;
  try {
    const delPath = `/api/hdc/${encodeURIComponent(db)}?schema_id=${sid}&namespace=${encodeURIComponent(ns)}`;
    const data = await apiAbs('DELETE', delPath);
    toast(`已删除 namespace ${ns}`, 'success');
    resultEl.innerHTML = `<div>✅ 已删除 ${esc(db)} / ${esc(ns)}</div>`;
    // 刷新列表
    hdcKbListNamespaces();
  } catch (e) { resultEl.innerHTML = `<div class="empty">删除失败: ${esc(e.message)}</div>`; }
}

function _hdcKbParams() {
  const key = document.getElementById('hdcKbSchemaDb').value;
  const [sid, db] = parseSchemaKey(key);
  const ns = (document.getElementById('hdcKbNs').value || '').trim();
  let tables = (document.getElementById('hdcKbTables').value || '').trim();
  tables = tables ? tables.split(',').map(t => t.trim()).filter(Boolean) : null;
  return { sid, db, ns: ns || null, tables };
}

async function hdcKbAction(action) {
  const { sid, db, ns, tables } = _hdcKbParams();
  if (!sid || !db) { toast('请先选择 Schema / DB', 'error'); return; }
  const resultEl = document.getElementById('hdcKbResult');

  if (action === 'status') {
    resultEl.innerHTML = '<div class="loading">查询中...</div>';
    try {
      let statusPath = `/api/hdc/status/${encodeURIComponent(db)}?schema_id=${sid}`;
      if (ns) statusPath += `&namespace=${encodeURIComponent(ns)}`;
      const data = await apiAbs('GET', statusPath);
      let html = `<div class="stat-grid">`;
      html += `<div class="stat-card"><div class="label">数据库</div><div class="value" style="font-size:1rem">${esc(db)}</div></div>`;
      html += `<div class="stat-card"><div class="label">存在</div><div class="value">${data.exists ? '✅ 是' : '❌ 否'}</div></div>`;
      html += `<div class="stat-card"><div class="label">Namespace 数</div><div class="value">${data.namespace_count ?? 0}</div></div>`;
      html += `<div class="stat-card"><div class="label">总表数</div><div class="value">${data.total_tables ?? 0}</div></div>`;
      html += `</div>`;
      if (data.namespaces && data.namespaces.length) {
        html += `<h4 style="margin:12px 0 6px">Namespace 明细</h4>`;
        html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
        data.namespaces.forEach(ns => {
          html += `<span class="badge-tag" style="font-size:0.8rem;padding:4px 10px">${esc(ns.name)} · ${ns.table_count} 表</span>`;
        });
        html += '</div>';
      }
      if (data.error) html += `<div class="empty">错误: ${esc(data.error)}</div>`;
      resultEl.innerHTML = html;
    } catch (e) { resultEl.innerHTML = `<div class="empty">查询失败: ${esc(e.message)}</div>`; }
    return;
  }

  if (action === 'delete') {
    const scope = ns ? `namespace <strong>${esc(ns)}</strong>` : `<strong>整个数据库（含全部 namespace）</strong>`;
    if (!confirm(`确认删除 ${esc(db)} 的 ${scope}？\n\n此操作不可撤销！${ns ? '' : '\n如只想删单个 namespace，请在 Namespace 输入框填写后再点删除。'}`)) return;
    resultEl.innerHTML = '<div class="loading">删除中...</div>';
    try {
      let delPath = `/api/hdc/${encodeURIComponent(db)}?schema_id=${sid}`;
      if (ns) delPath += `&namespace=${encodeURIComponent(ns)}`;
      const data = await apiAbs('DELETE', delPath);
      toast(ns ? `已删除 namespace ${ns}` : `已删除 ${db} 全部 HDC 数据`, 'success');
      let html = `<div>✅ 已删除 ${esc(db)}${ns ? ' / ' + esc(ns) : ''} 的 HDC 数据</div>`;
      if (data.deleted_uris?.length) html += `<div class="mono" style="font-size:0.75rem;color:var(--muted);margin-top:6px">已删路径: ${data.deleted_uris.map(esc).join('<br>')}</div>`;
      resultEl.innerHTML = html;
      // 删除后刷新 namespace 浏览列表（如果可见）
      if (typeof browseNamespaces === 'function') {
        const browseSel = document.getElementById('hdcBrowseSchemaDb');
        if (browseSel && browseSel.value === `${sid}/${db}`) browseNamespaces();
      }
    } catch (e) { resultEl.innerHTML = `<div class="empty">删除失败: ${esc(e.message)}</div>`; }
    return;
  }

  // generate / update / dry_run / rebuild 都是异步任务
  const payload = { schema_id: sid, database_name: db };
  if (ns) payload.namespace = ns;
  if (tables) payload.tables = tables;
  let endpoint, label;
  if (action === 'generate') { endpoint = '/api/hdc/generate'; label = '构建'; }
  else if (action === 'update') { endpoint = '/api/hdc/update'; payload.dry_run = false; label = '增量更新'; }
  else if (action === 'dry_run') { endpoint = '/api/hdc/update'; payload.dry_run = true; label = '检测变更'; }
  else if (action === 'rebuild') { endpoint = '/api/hdc/update'; payload.rebuild = true; label = '重建摘要'; }

  if ((action === 'generate' || action === 'update' || action === 'rebuild') &&
      !confirm(`确认对 ${db}${ns ? '/' + ns : ''} 执行 ${label}？${action === 'generate' ? '全量构建会调用 LLM，耗时较长。' : ''}`)) return;

  resultEl.innerHTML = `<div class="loading">${label}任务提交中...</div>`;
  try {
    const data = await apiAbs('POST', endpoint, payload);
    toast(`${label}任务已提交`, 'success');
    _pollHdcTask(data.task_id, label, resultEl);
  } catch (e) { resultEl.innerHTML = `<div class="empty">${label}失败: ${esc(e.message)}</div>`; }
}

function _pollHdcTask(taskId, label, resultEl) {
  // 清理旧轮询
  if (_hdcPollers[taskId]) clearInterval(_hdcPollers[taskId]);

  const render = (task) => {
    const status = task.status;
    const phase = task.progress?.phase || '';
    const dot = status === 'completed' ? '✅' : status === 'failed' ? '❌' : '⏳';
    let html = `<div><strong>${dot} ${label}</strong> — 状态: ${esc(status)}`;
    if (phase) html += ` · 阶段: ${esc(phase)}`;
    if (task.progress?.tables_total) html += ` · ${task.progress.tables_done || 0}/${task.progress.tables_total} 表`;
    html += '</div>';
    if (task.result) {
      const r = task.result;
      if (status === 'failed') {
        html += `<div class="empty">错误: ${esc(r.error || JSON.stringify(r))}</div>`;
      } else if (r.changed === false) {
        html += '<div class="empty">无变更</div>';
      } else if (r.changed === true || r.dry_run) {
        html += `<div>新增 ${r.new || 0} · 变更 ${r.changed_tables || 0} · 删除 ${r.deleted || 0}</div>`;
        if (r.new_tables?.length) html += `<div style="margin-top:4px"><strong>新增表:</strong> ${r.new_tables.map(t => `<span class="badge-tag">${esc(t)}</span>`).join('')}</div>`;
        if (r.changed_table_names?.length) html += `<div style="margin-top:4px"><strong>变更表:</strong> ${r.changed_table_names.map(t => `<span class="badge-tag">${esc(t)}</span>`).join('')}</div>`;
        if (r.deleted_tables?.length) html += `<div style="margin-top:4px"><strong>删除表:</strong> ${r.deleted_tables.map(t => `<span class="badge-tag">${esc(t)}</span>`).join('')}</div>`;
      } else {
        html += `<pre class="mono" style="max-height:200px;overflow:auto;margin-top:8px">${esc(JSON.stringify(r, null, 2))}</pre>`;
      }
    }
    html += `<div style="font-size:0.75rem;color:var(--muted);margin-top:6px">task_id: ${esc(taskId)}</div>`;
    resultEl.innerHTML = html;
  };

  const poll = async () => {
    try {
      const task = await apiAbs('GET', `/api/hdc/tasks/${taskId}`);
      render(task);
      if (task.status === 'completed' || task.status === 'failed') {
        clearInterval(_hdcPollers[taskId]);
        delete _hdcPollers[taskId];
      }
    } catch (e) {
      resultEl.innerHTML = `<div class="empty">轮询失败: ${esc(e.message)}</div>`;
      clearInterval(_hdcPollers[taskId]);
      delete _hdcPollers[taskId];
    }
  };
  poll();
  _hdcPollers[taskId] = setInterval(poll, 2000);
}

// ── SQL Memory ──
async function loadSqlMemStatus() {
  if (!_token) return;
  try {
    const data = await api('GET', '/sql-memory/status');
    document.getElementById('sqlMemStats').innerHTML = `
      <div class="stat-card"><div class="label">总记录</div><div class="value">${data.total_records}</div></div>
      <div class="stat-card"><div class="label">Embedding 覆盖率</div><div class="value">${(data.embedding_coverage * 100).toFixed(0)}%</div></div>
      <div class="stat-card"><div class="label">最早</div><div class="value" style="font-size:0.9rem">${data.earliest_record || '--'}</div></div>
      <div class="stat-card"><div class="label">最晚</div><div class="value" style="font-size:0.9rem">${data.latest_record || '--'}</div></div>`;
  } catch (e) { /* sql memory may be disabled */ }
}

function toggleSeedExample() {
  const el = document.getElementById('seedExample');
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function showSeedExample(type) {
  document.getElementById('seedExampleJson').style.display = type === 'json' ? 'block' : 'none';
  document.getElementById('seedExampleCsv').style.display = type === 'csv' ? 'block' : 'none';
  document.getElementById('seedTabJson').style.fontWeight = type === 'json' ? '600' : 'normal';
  document.getElementById('seedTabCsv').style.fontWeight = type === 'csv' ? '600' : 'normal';
}

async function seedFromFile() {
  const user = document.getElementById('seedUser').value;
  if (!user) { toast('请选择目标用户', 'error'); return; }
  const file = document.getElementById('seedFile').files[0];
  if (!file) { toast('请选择 JSON 或 CSV 文件', 'error'); return; }

  try {
    const text = await file.text();
    const name = file.name.toLowerCase();
    let records;

    if (name.endsWith('.csv')) {
      records = parseCsvToRecords(text);
      if (!records.length) { toast('CSV 解析失败或无有效数据', 'error'); return; }
    } else {
      // JSON
      let data;
      try { data = JSON.parse(text); } catch { toast('JSON 解析失败', 'error'); return; }
      records = Array.isArray(data) ? data : (data.records || []);
      if (!records.length) { toast('文件中无记录', 'error'); return; }
    }

    const result = await api('POST', '/sql-memory/seed', { user_id: user, records });
    document.getElementById('seedResult').innerHTML = `<div style="color:#22c55e;margin-top:8px">✅ 灌入完成: ${result.success} 成功, ${result.failed} 失败 (共 ${result.total} 条)</div>`;
    loadSqlMemStatus();
  } catch (e) { toast('灌入失败: ' + e.message, 'error'); }
}

// ── CSV 解析 ──
function parseCsvToRecords(text) {
  // 按行分割，支持 \r\n 和 \n
  const lines = text.split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 2) return []; // 至少需要表头 + 1 行数据

  const headers = parseCsvLine(lines[0]);
  // 列名映射：支持中英文列名
  const colMap = {};
  headers.forEach((h, i) => {
    const key = h.trim().toLowerCase();
    if (key.includes('question') || key.includes('问题') || key.includes('提问')) colMap.question = i;
    else if (key.includes('sql') || key === 'sql') colMap.sql = i;
    else if (key.includes('table') || key.includes('表名') || key.includes('表')) colMap.table_names = i;
    else if (key.includes('database') || key.includes('db') || key.includes('数据库') || key.includes('库')) colMap.database_name = i;
    else if (key.includes('schema') || key === 'schema_id') colMap.schema_id = i;
    else if (key.includes('row_count') || key.includes('行数') || key.includes('结果行数')) colMap.row_count = i;
    else if (key.includes('column') || key.includes('列名') || key.includes('字段')) colMap.column_names = i;
  });

  // 必须至少有 question 和 sql 列
  if (colMap.question === undefined || colMap.sql === undefined) {
    console.warn('CSV 缺少 question/sql 列，表头:', headers.join(', '));
    return [];
  }

  const records = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const question = (cols[colMap.question] || '').trim();
    const sql = (cols[colMap.sql] || '').trim();
    if (!question || !sql) continue;

    const rec = { question, sql };

    // 表名：逗号分隔
    if (colMap.table_names !== undefined) {
      const raw = (cols[colMap.table_names] || '').trim();
      rec.table_names = raw ? raw.split(/[,;，；]/).map(s => s.trim()).filter(Boolean) : [];
    } else {
      rec.table_names = [];
    }

    rec.database_name = colMap.database_name !== undefined ? (cols[colMap.database_name] || '').trim() : '';
    rec.schema_id = colMap.schema_id !== undefined ? (parseInt(cols[colMap.schema_id]) || 0) : 0;

    // 执行结果
    const result = {};
    if (colMap.row_count !== undefined) {
      const n = parseInt(cols[colMap.row_count]);
      if (!isNaN(n)) result.row_count = n;
    }
    if (colMap.column_names !== undefined) {
      const raw = (cols[colMap.column_names] || '').trim();
      result.column_names = raw ? raw.split(/[,;，；]/).map(s => s.trim()).filter(Boolean) : [];
    }
    if (Object.keys(result).length) rec.execution_result = result;

    records.push(rec);
  }

  return records;
}

// 简易 CSV 行解析（支持引号包裹的字段）
function parseCsvLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < line.length && line[i + 1] === '"') { current += '"'; i++; }
        else { inQuotes = false; }
      } else { current += ch; }
    } else {
      if (ch === '"') { inQuotes = true; }
      else if (ch === ',') { result.push(current); current = ''; }
      else { current += ch; }
    }
  }
  result.push(current);
  return result;
}

let _recOffset = 0;
async function listRecords(offset) {
  _recOffset = offset;
  const user = document.getElementById('recUser').value;
  const dbKey = document.getElementById('recDb').value;
  const [, db] = parseSchemaKey(dbKey);
  const status = document.getElementById('recStatus').value;
  const limit = parseInt(document.getElementById('recLimit').value) || 20;
  const params = new URLSearchParams({ limit, offset });
  if (user) params.set('user_id', user);
  if (db) params.set('database_name', db);
  if (status) params.set('status', status);

  try {
    const data = await api('GET', '/sql-memory/records?' + params);
    if (!data.records.length) {
      document.getElementById('recordTable').innerHTML = '<div class="empty">无记录</div>';
      document.getElementById('recordPager').innerHTML = '';
      return;
    }
    document.getElementById('recordTable').innerHTML = '<table><tr><th>用户</th><th>问题</th><th>SQL</th><th>表</th><th>DB</th><th>状态</th><th>Emb</th><th>时间</th><th></th></tr>'
      + data.records.map(r => {
        const stColors = { success: 'teal', empty: 'amber', error: 'rose' };
        const stColor = stColors[r.execution_status] || 'sky';
        return `<tr>
        <td>${r.user_id}</td>
        <td class="truncate" title="${esc(r.question)}">${esc(r.question)}</td>
        <td class="mono truncate" title="${esc(r.sql_text)}">${esc(r.sql_text)}</td>
        <td>${(r.table_names||[]).map(t => `<span class="badge-tag sky">${t}</span>`).join('')}</td>
        <td>${r.database_name}</td>
        <td><span class="badge-tag ${stColor}">${r.execution_status}</span></td>
        <td>${r.has_embedding ? '<span class="badge-tag teal">✓</span>' : '<span class="badge-tag rose">✗</span>'}</td>
        <td>${(r.created_at||'').slice(0,16)}</td>
        <td><button class="btn btn-danger btn-sm" onclick="deleteRecord('${esc(r.id)}')">删除</button></td>
      </tr>`;
      }).join('') + '</table>';
    document.getElementById('recordPager').innerHTML = `
      <button class="btn btn-secondary btn-sm" onclick="listRecords(${Math.max(0, offset - limit)})" ${offset === 0 ? 'disabled' : ''}>← 上一页</button>
      <span style="margin:0 8px;font-size:0.85rem">${offset + 1}–${offset + data.records.length} / ${data.total}</span>
      <button class="btn btn-secondary btn-sm" onclick="listRecords(${offset + limit})" ${offset + limit >= data.total ? 'disabled' : ''}>下一页 →</button>`;
  } catch (e) { toast('查询失败: ' + e.message, 'error'); }
}

async function cleanRecords() {
  if (!confirm('确认清理过期记录？默认删除超过 TTL (90天) 的记录。')) return;
  try {
    const r = await api('DELETE', '/sql-memory/clean', {});
    toast(`已删除 ${r.deleted_count} 条记录`, 'success');
    loadSqlMemStatus();
  } catch (e) { toast('清理失败: ' + e.message, 'error'); }
}

async function deleteRecord(recordId) {
  if (!confirm('确认删除该条 SQL 记忆记录？此操作不可撤销。')) return;
  try {
    await api('DELETE', `/sql-memory/records/${encodeURIComponent(recordId)}`);
    toast('已删除 1 条记录', 'success');
    listRecords(_recOffset);  // 刷新当前列表
    loadSqlMemStatus();       // 刷新状态概览
  } catch (e) { toast('删除失败: ' + e.message, 'error'); }
}

async function reEmbed() {
  if (!confirm('确认重建所有 embedding？可能需要较长时间。')) return;
  try {
    const r = await api('POST', '/sql-memory/re-embed', {});
    toast(`已重建 ${r.updated_count} 条记录`, 'success');
    loadSqlMemStatus();
  } catch (e) { toast('重建失败: ' + e.message, 'error'); }
}

async function loadStats() {
  try {
    const data = await api('GET', '/sql-memory/stats');
    const parts = [];
    if (data.table_distribution && Object.keys(data.table_distribution).length)
      parts.push('<h4>表分布</h4>' + Object.entries(data.table_distribution).map(([k,v]) => `<span class="badge-tag">${k}: ${v}</span>`).join(' '));
    if (data.database_distribution && Object.keys(data.database_distribution).length)
      parts.push('<h4>数据库分布</h4>' + Object.entries(data.database_distribution).map(([k,v]) => `<span class="badge-tag">${k}: ${v}</span>`).join(' '));
    if (data.daily_histogram && Object.keys(data.daily_histogram).length)
      parts.push('<h4>每日统计</h4>' + Object.entries(data.daily_histogram).slice(-14).map(([k,v]) => `${k}: ${v}`).join('<br>'));
    if (data.mined_patterns)
      parts.push('<h4>模式挖掘</h4>' + JSON.stringify(data.mined_patterns).slice(0, 500));
    document.getElementById('statsResult').innerHTML = parts.length ? parts.join('<hr style="margin:12px 0">') : '<div class="empty">无数据</div>';
  } catch (e) { toast('统计加载失败: ' + e.message, 'error'); }
}