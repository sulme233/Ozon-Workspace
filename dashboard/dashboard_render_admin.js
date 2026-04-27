function isAuthenticated() {
  return Boolean((uiState.auth || {}).authenticated);
}

function getAuthPanelElement() {
  return document.getElementById('auth-panel-body');
}

function getAdminStoreBodyElement() {
  return document.getElementById('admin-store-body');
}

function getAdminAuditBodyElement() {
  return document.getElementById('admin-audit-body');
}

function getAdminStoreDraft(store = {}) {
  return {
    store_name: String(store.store_name || ''),
    store_code: String(store.store_code || ''),
    enabled: store.enabled !== false,
    timezone: String(store.timezone || 'Asia/Shanghai'),
    currency: String(store.currency || 'CNY'),
    notes: String(store.notes || ''),
    marketplace_id: String(store.marketplace_id || ''),
    seller_api: {
      client_id: String(((store.seller_api || {}).client_id) || ''),
      api_key: '',
    },
    performance_api: {
      client_id: String(((store.performance_api || {}).client_id) || ''),
      client_secret: '',
    },
  };
}

function renderAuthPanel() {
  const container = getAuthPanelElement();
  if (!container) return;
  const auth = uiState.auth || {};
  const bootstrap = auth.bootstrap || {};
  if (auth.authenticated) {
    const username = (((auth.session || {}).user) || {}).username || 'admin';
    container.innerHTML = `
      <div class="toolbar-grid">
        <div class="mini-panel">
          <div class="label">当前账号</div>
          <div class="value">${escapeHtml(username)}</div>
          <div class="sub">已登录，可进行配置刷新、店铺维护和 key 更新。</div>
        </div>
      </div>
      <div class="toolbar">
        <button id="logout-btn" class="btn secondary" type="button">退出登录</button>
      </div>
    `;
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', async () => {
        try {
          logoutBtn.disabled = true;
          await postApiJson('/api/auth/logout', {});
          await loadAuthStatus();
          await refreshAdminPanels();
          setStatus('已退出后台登录。');
        } catch (error) {
          setStatus(`退出登录失败：${error.message}`);
        } finally {
          logoutBtn.disabled = false;
        }
      });
    }
    return;
  }

  if (bootstrap.can_bootstrap) {
    container.innerHTML = `
      <div class="toolbar-grid">
        <label class="field">
          <span class="field-label">初始化管理员账号</span>
          <input id="bootstrap-username" class="input" type="text" placeholder="管理员用户名">
        </label>
        <label class="field">
          <span class="field-label">初始化密码</span>
          <input id="bootstrap-password" class="input" type="password" placeholder="请输入后台密码">
        </label>
      </div>
      <div class="toolbar">
        <button id="bootstrap-btn" class="btn primary" type="button">初始化管理员</button>
      </div>
    `;
    const bootstrapBtn = document.getElementById('bootstrap-btn');
    if (bootstrapBtn) {
      bootstrapBtn.addEventListener('click', async () => {
        const username = (document.getElementById('bootstrap-username') || {}).value || '';
        const password = (document.getElementById('bootstrap-password') || {}).value || '';
        try {
          bootstrapBtn.disabled = true;
          await postApiJson('/api/auth/bootstrap', { username, password });
          await postApiJson('/api/auth/login', { username, password });
          await loadAuthStatus();
          await refreshAdminPanels();
          setStatus('管理员初始化并登录成功。');
        } catch (error) {
          setStatus(`初始化管理员失败：${error.message}`);
        } finally {
          bootstrapBtn.disabled = false;
        }
      });
    }
    return;
  }

  container.innerHTML = `
    <div class="toolbar-grid">
      <label class="field">
        <span class="field-label">用户名</span>
        <input id="login-username" class="input" type="text" placeholder="管理员用户名">
      </label>
      <label class="field">
        <span class="field-label">密码</span>
        <input id="login-password" class="input" type="password" placeholder="后台登录密码">
      </label>
    </div>
    <div class="toolbar">
      <button id="login-btn" class="btn primary" type="button">登录后台</button>
    </div>
  `;
  const loginBtn = document.getElementById('login-btn');
  if (loginBtn) {
    loginBtn.addEventListener('click', async () => {
      const username = (document.getElementById('login-username') || {}).value || '';
      const password = (document.getElementById('login-password') || {}).value || '';
      try {
        loginBtn.disabled = true;
        await postApiJson('/api/auth/login', { username, password });
        await loadAuthStatus();
        await refreshAdminPanels();
        setStatus('后台登录成功。');
      } catch (error) {
        setStatus(`后台登录失败：${error.message}`);
      } finally {
        loginBtn.disabled = false;
      }
    });
  }
}

function renderAdminStores() {
  const container = getAdminStoreBodyElement();
  if (!container) return;
  if (!isAuthenticated()) {
    container.innerHTML = '<div class="empty">登录后可管理店铺、修改基础信息和更新 key。</div>';
    return;
  }
  const stores = Array.isArray(uiState.adminStores) ? uiState.adminStores : [];
  const activeCode = uiState.editingStoreCode || (stores[0] || {}).store_code || '';
  const active = stores.find((item) => String(item.store_code || '') === activeCode) || null;
  const draft = getAdminStoreDraft(active || {});
  container.innerHTML = `
    <div class="toolbar-grid">
      <label class="field">
        <span class="field-label">已配置店铺</span>
        <select id="admin-store-select" class="select">
          <option value="">新建店铺</option>
          ${stores.map((store) => `<option value="${escapeHtml(store.store_code || '')}" ${activeCode === store.store_code ? 'selected' : ''}>${escapeHtml(`${store.store_name || '-'} (${store.store_code || '-'})`)}</option>`).join('')}
        </select>
      </label>
    </div>
    <div class="toolbar-grid">
      <label class="field"><span class="field-label">店铺名称</span><input id="admin-store-name" class="input" type="text" value="${escapeHtml(draft.store_name)}"></label>
      <label class="field"><span class="field-label">店铺编码</span><input id="admin-store-code" class="input" type="text" value="${escapeHtml(draft.store_code)}" placeholder="如 ozon_a"></label>
      <label class="field"><span class="field-label">时区</span><input id="admin-store-timezone" class="input" type="text" value="${escapeHtml(draft.timezone)}"></label>
      <label class="field"><span class="field-label">币种</span><input id="admin-store-currency" class="input" type="text" value="${escapeHtml(draft.currency)}"></label>
      <label class="field"><span class="field-label">Marketplace ID</span><input id="admin-store-marketplace-id" class="input" type="text" value="${escapeHtml(draft.marketplace_id)}"></label>
      <label class="field"><span class="field-label">启用店铺</span><input id="admin-store-enabled" type="checkbox" ${draft.enabled ? 'checked' : ''}></label>
    </div>
    <div class="toolbar-grid">
      <label class="field"><span class="field-label">Seller Client ID</span><input id="admin-seller-client-id" class="input" type="text" value="${escapeHtml(draft.seller_api.client_id)}"></label>
      <label class="field"><span class="field-label">Seller API Key</span><input id="admin-seller-api-key" class="input" type="password" placeholder="留空表示保留原值"></label>
      <label class="field"><span class="field-label">Performance Client ID</span><input id="admin-perf-client-id" class="input" type="text" value="${escapeHtml(draft.performance_api.client_id)}"></label>
      <label class="field"><span class="field-label">Performance Client Secret</span><input id="admin-perf-client-secret" class="input" type="password" placeholder="留空表示保留原值"></label>
    </div>
    <div class="toolbar-grid">
      <label class="field"><span class="field-label">备注</span><input id="admin-store-notes" class="input" type="text" value="${escapeHtml(draft.notes)}"></label>
    </div>
    <div class="filter-row">
      <div class="filter-note">Seller Key: ${(active && (active.seller_api || {}).api_key_masked) ? escapeHtml(active.seller_api.api_key_masked) : '未设置'} | Performance Secret: ${(active && (active.performance_api || {}).client_secret_masked) ? escapeHtml(active.performance_api.client_secret_masked) : '未设置'}</div>
    </div>
    <div class="toolbar">
      <button id="admin-store-save-btn" class="btn primary" type="button">保存店铺配置</button>
      <button id="admin-store-versions-btn" class="btn secondary" type="button" ${activeCode ? '' : 'disabled'}>加载版本历史</button>
    </div>
    <div id="admin-store-versions" class="list">${renderStoreVersionItems()}</div>
  `;
  const select = document.getElementById('admin-store-select');
  if (select) {
    select.addEventListener('change', (event) => {
      uiState.editingStoreCode = event.target.value || '';
      renderAdminStores();
    });
  }
  const saveBtn = document.getElementById('admin-store-save-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', saveAdminStore);
  }
  const versionsBtn = document.getElementById('admin-store-versions-btn');
  if (versionsBtn) {
    versionsBtn.addEventListener('click', loadStoreVersions);
  }
  document.querySelectorAll('[data-rollback-version]').forEach((button) => {
    button.addEventListener('click', () => rollbackStoreVersion(button.getAttribute('data-rollback-version') || ''));
  });
}

function renderStoreVersionItems() {
  const versions = Array.isArray(uiState.storeVersions) ? uiState.storeVersions : [];
  if (!versions.length) return '<div class="empty">未加载版本历史。</div>';
  return versions
    .map((item) => {
      const summary = item.summary || {};
      return `
        <div class="list-item">
          <strong>#${escapeHtml(item.version)} · ${escapeHtml(item.action || '-')} · ${escapeHtml(item.created_at || '-')}</strong>
          <span>${escapeHtml(item.actor_username || '-')} | ${escapeHtml(summary.store_name || '-')} | ${escapeHtml(summary.currency || '-')} | ${summary.enabled ? '启用' : '停用'}</span>
          <div class="toolbar version-actions"><button class="btn secondary" type="button" data-rollback-version="${escapeHtml(item.version)}">回滚到此版本</button></div>
        </div>
      `;
    })
    .join('');
}

function renderAuditLogs() {
  const container = getAdminAuditBodyElement();
  if (!container) return;
  if (!isAuthenticated()) {
    container.innerHTML = '<div class="empty">登录后可查看操作审计。</div>';
    return;
  }
  const logs = Array.isArray(uiState.auditLogs) ? uiState.auditLogs : [];
  container.innerHTML = logs.length
    ? `<div class="list">${logs.map((log) => `
        <div class="list-item">
          <strong>${escapeHtml(log.created_at || '-')} · ${escapeHtml(log.action || '-')}</strong>
          <span>${escapeHtml(log.actor_username || '-')} | ${escapeHtml(log.target_type || '-')} | ${escapeHtml(log.target_id || '-')}</span>
        </div>`).join('')}</div>`
    : '<div class="empty">暂无审计记录。</div>';
}

async function loadAuthStatus() {
  if (!isServeMode()) return;
  const result = await fetchApiJson('/api/auth/status');
  uiState.auth = {
    authenticated: Boolean(result.authenticated),
    bootstrap: result.bootstrap || {},
    session: result.session || null,
  };
  renderAuthPanel();
  updateProtectedUiState();
}

async function loadAdminStores() {
  if (!isServeMode() || !isAuthenticated()) {
    uiState.adminStores = [];
    uiState.storeVersions = [];
    renderAdminStores();
    return;
  }
  const result = await fetchApiJson('/api/admin/stores');
  uiState.adminStores = result.stores || [];
  if (!uiState.editingStoreCode && uiState.adminStores.length) {
    uiState.editingStoreCode = uiState.adminStores[0].store_code || '';
  }
  if (uiState.editingStoreCode) {
    await loadStoreVersions({ silent: true });
  }
  renderAdminStores();
}

async function loadStoreVersions(options = {}) {
  const { silent = false } = options;
  const storeCode = uiState.editingStoreCode || '';
  if (!storeCode || !isAuthenticated()) {
    uiState.storeVersions = [];
    if (!silent) renderAdminStores();
    return;
  }
  try {
    const result = await fetchApiJson(`/api/admin/stores/versions?store_code=${encodeURIComponent(storeCode)}&limit=10`);
    uiState.storeVersions = result.versions || [];
    if (!silent) setStatus(`已加载 ${uiState.storeVersions.length} 条店铺配置版本。`);
  } catch (error) {
    if (!silent) setStatus(`加载版本历史失败：${error.message}`);
  }
  if (!silent) renderAdminStores();
}

async function rollbackStoreVersion(versionText) {
  const version = Number(versionText || 0);
  const storeCode = uiState.editingStoreCode || '';
  if (!storeCode || !version) return;
  const ok = window.confirm(`确认将 ${storeCode} 回滚到版本 #${version}？当前配置会生成新版本记录。`);
  if (!ok) return;
  try {
    await postApiJson('/api/admin/stores/rollback', { store_code: storeCode, version });
    await refreshAdminPanels();
    setStatus(`店铺 ${storeCode} 已回滚到版本 #${version}。`);
  } catch (error) {
    setStatus(`回滚失败：${error.message}`);
  }
}

async function loadAuditLogs() {
  if (!isServeMode() || !isAuthenticated()) {
    uiState.auditLogs = [];
    renderAuditLogs();
    return;
  }
  const result = await fetchApiJson('/api/admin/audit-logs?limit=20');
  uiState.auditLogs = result.logs || [];
  renderAuditLogs();
}

async function refreshAdminPanels() {
  renderAuthPanel();
  if (!isAuthenticated()) {
    uiState.adminStores = [];
    uiState.storeVersions = [];
    uiState.auditLogs = [];
    renderProbeResult(null);
    renderAdminStores();
    renderAuditLogs();
    updateProtectedUiState();
    return;
  }
  await Promise.all([loadAdminStores(), loadAuditLogs(), loadStoreOptions(), loadWebConfig(), loadLatestProbe()]);
  updateProtectedUiState();
}

function updateProtectedUiState() {
  const disabled = !isServeMode() || !isAuthenticated();
  const refreshBtn = document.getElementById('refresh-btn');
  const reloadBtn = document.getElementById('reload-btn');
  const saveConfigBtn = document.getElementById('save-config-btn');
  const probeBtn = document.getElementById('probe-btn');
  if (refreshBtn) refreshBtn.disabled = disabled;
  if (reloadBtn) reloadBtn.disabled = disabled;
  if (saveConfigBtn) saveConfigBtn.disabled = disabled;
  if (probeBtn) probeBtn.disabled = disabled;
}

function renderAdminWorkspaceState() {
  const panels = [
    document.getElementById('auth-panel'),
    document.getElementById('admin-store-panel'),
    document.getElementById('admin-audit-panel'),
  ].filter(Boolean);
  panels.forEach((panel) => panel.classList.toggle('is-collapsed', !uiState.adminWorkspaceOpen));
  const toggle = document.getElementById('admin-workspace-toggle');
  if (toggle) {
    toggle.textContent = uiState.adminWorkspaceOpen ? '收起后台管理' : '展开后台管理';
    toggle.setAttribute('aria-expanded', uiState.adminWorkspaceOpen ? 'true' : 'false');
  }
}

async function saveAdminStore() {
  const saveBtn = document.getElementById('admin-store-save-btn');
  if (!saveBtn) return;
  const originalStoreCode = uiState.editingStoreCode || '';
  const payloadBody = {
    original_store_code: originalStoreCode,
    store: {
      store_name: (document.getElementById('admin-store-name') || {}).value || '',
      store_code: (document.getElementById('admin-store-code') || {}).value || '',
      timezone: (document.getElementById('admin-store-timezone') || {}).value || '',
      currency: (document.getElementById('admin-store-currency') || {}).value || '',
      marketplace_id: (document.getElementById('admin-store-marketplace-id') || {}).value || '',
      notes: (document.getElementById('admin-store-notes') || {}).value || '',
      enabled: Boolean((document.getElementById('admin-store-enabled') || {}).checked),
      seller_api: {
        client_id: (document.getElementById('admin-seller-client-id') || {}).value || '',
        api_key: (document.getElementById('admin-seller-api-key') || {}).value || '',
      },
      performance_api: {
        client_id: (document.getElementById('admin-perf-client-id') || {}).value || '',
        client_secret: (document.getElementById('admin-perf-client-secret') || {}).value || '',
      },
    },
  };
  try {
    saveBtn.disabled = true;
    const result = await postApiJson('/api/admin/stores', payloadBody);
    uiState.editingStoreCode = ((result.store || {}).store_code) || payloadBody.store.store_code || '';
    await refreshAdminPanels();
    setStatus(`店铺配置已保存：${uiState.editingStoreCode || '-'}`);
  } catch (error) {
    setStatus(`保存店铺配置失败：${error.message}`);
  } finally {
    saveBtn.disabled = false;
  }
}
