const embeddedPayload = JSON.parse(document.getElementById('embedded-payload').textContent);
let payload = embeddedPayload;
let dataOpsRequestId = 0;

function isServeMode() {
  return location.protocol !== 'file:';
}

function statusLabel(status) {
  const text = {
    ok: '正常',
    partial: '告警降级',
    error: '失败',
    no_campaigns: '无广告活动',
  };
  return text[status] || status || '未知';
}

function statusTone(status) {
  if (status === 'ok') return 'ok';
  if (status === 'partial') return 'partial';
  if (status === 'no_campaigns') return 'neutral';
  return 'error';
}

function healthTone(score) {
  if (score >= 80) return 'healthy';
  if (score >= 55) return 'watch';
  return 'risk';
}

function healthBadge(score) {
  if (score >= 80) return 'good-tone';
  if (score >= 55) return 'warn-tone';
  return 'bad-tone';
}

function setStatus(message) {
  const el = document.getElementById('status-line');
  if (el) el.textContent = message;
}

function getModuleWarnings(module) {
  return Array.isArray((module || {}).warnings) ? module.warnings : [];
}

function getStoreWarningCount(item) {
  return MODULE_DEFINITIONS.reduce((total, [key]) => total + getModuleWarnings(item[key]).length, 0);
}

function getStoreErrorCount(item) {
  return Array.isArray(item?.errors) ? item.errors.length : 0;
}

function getModuleErrorCount(item) {
  return MODULE_DEFINITIONS.reduce((total, [key]) => {
    const status = String((item?.[key] || {}).status || 'unknown');
    return total + (status === 'error' ? 1 : 0);
  }, 0);
}

function getStoreQuickFlags(item) {
  const adAlerts = getAdAlerts(item);
  const skuRisks = getSkuPreview(item);
  const warningCount = getStoreWarningCount(item);
  const errorCount = getStoreErrorCount(item);
  const moduleErrorCount = getModuleErrorCount(item);
  const riskCount = Array.isArray(item?.flags) ? item.flags.length : 0;
  return {
    hasRisk: riskCount > 0,
    hasWarnings: warningCount > 0,
    hasErrors: errorCount > 0 || moduleErrorCount > 0 || String(item?.status || '') === 'error',
    hasAdAlerts: adAlerts.length > 0,
    hasSkuRisk: skuRisks.length > 0,
    riskCount,
    warningCount,
    errorCount,
    moduleErrorCount,
  };
}

function isStoreActionable(item) {
  const flags = getStoreQuickFlags(item);
  return flags.hasRisk || flags.hasWarnings || flags.hasErrors || flags.hasAdAlerts || flags.hasSkuRisk;
}

function matchesQuickFilter(item) {
  const flags = getStoreQuickFlags(item);
  if (uiState.quickFilter === 'risk') return flags.hasRisk;
  if (uiState.quickFilter === 'warnings') return flags.hasWarnings;
  if (uiState.quickFilter === 'errors') return flags.hasErrors;
  if (uiState.quickFilter === 'ads') return flags.hasAdAlerts;
  if (uiState.quickFilter === 'sku') return flags.hasSkuRisk;
  return true;
}

function focusStore(nextPayload, storeCode, options = {}) {
  const { preserveFilters = false, moduleKey = '' } = options;
  const item = findStoreByCode(nextPayload, storeCode);
  if (!item) return;
  if (!preserveFilters) {
    uiState.status = 'all';
    uiState.quickFilter = 'all';
  }
  uiState.storeCode = String(item.store_code || '').trim();
  uiState.focusedModuleKey = moduleKey || '';
  ensureStoreExpanded(item);
  renderDashboard(nextPayload);

  requestAnimationFrame(() => {
    const card = document.querySelector(`[data-store-card="${escapeSelectorValue(getStoreCardId(item))}"]`);
    if (!card) return;

    const target = uiState.focusedModuleKey
      ? card.querySelector(`[data-module-card="${escapeSelectorValue(uiState.focusedModuleKey)}"]`)
      : card;

    (target || card).scrollIntoView({ behavior: 'smooth', block: 'start' });
    card.classList.add('store-card-flash');
    setTimeout(() => card.classList.remove('store-card-flash'), 1400);

    if (target) {
      target.classList.add('module-card-flash');
      setTimeout(() => target.classList.remove('module-card-flash'), 1600);
    }
  });
}

function getActionPriorityRows(nextPayload) {
  return getResults(nextPayload)
    .map((item) => {
      const record = getStoreRecord(item);
      const quickFlags = getStoreQuickFlags(item);
      const score = quickFlags.riskCount * 3 + quickFlags.warningCount * 2 + quickFlags.errorCount * 4 + quickFlags.moduleErrorCount * 3 + Math.max(0, 80 - record.health) + (quickFlags.hasAdAlerts ? 8 : 0) + (quickFlags.hasSkuRisk ? 6 : 0);
      return {
        item,
        record,
        quickFlags,
        score,
      };
    })
    .sort((a, b) => b.score - a.score || a.record.health - b.record.health || b.record.sales - a.record.sales)
    .slice(0, 6);
}

function buildActionItems(item) {
  const overview = item.overview || {};
  const actions = [];
  if (getStoreErrorCount(item) || getModuleErrorCount(item)) {
    actions.push({ module: '数据', priority: '高', text: '处理模块错误，先恢复数据完整性', score: 100 });
  }
  if (Number(overview.ad_expense_rub || 0) > 0 && Number(overview.ad_orders || 0) === 0) {
    actions.push({ module: '广告', priority: '高', text: '广告有花费无订单，检查投放对象、价格和详情页', score: 92 });
  }
  if (Number(overview.no_price_count || 0) > 0) {
    actions.push({ module: '价格', priority: '高', text: `修复 ${whole(overview.no_price_count)} 个无价格商品`, score: 86 });
  }
  if (Number(overview.risky_sku_count || 0) > 0) {
    actions.push({ module: 'SKU', priority: '中', text: `处理 ${whole(overview.risky_sku_count)} 个风险 SKU`, score: 78 });
  }
  if (Number(overview.unfulfilled_orders_count || 0) > 0) {
    actions.push({ module: '履约', priority: '中', text: `跟进 ${whole(overview.unfulfilled_orders_count)} 个待履约订单`, score: 72 });
  }
  if (Number(overview.empty_stock_warehouses_count || 0) > 0 || Number(overview.low_stock_warehouses_count || 0) > 0) {
    actions.push({ module: '库存', priority: '中', text: '检查空库存/低库存仓库，确认补货和可售状态', score: 66 });
  }
  return actions;
}

function getTodayActionRows(nextPayload) {
  return getFilteredResults(nextPayload)
    .flatMap((item) => buildActionItems(item).map((action) => ({ item, action })))
    .sort((a, b) => b.action.score - a.action.score || Number(a.item.health_score || 0) - Number(b.item.health_score || 0))
    .slice(0, 8);
}

function getExportActionRows(nextPayload) {
  const generatedAt = String(nextPayload?.generated_at || ((nextPayload?.refresh_info || {}).generated_at) || '').trim();
  return getFilteredResults(nextPayload)
    .flatMap((item) => {
      const overview = item.overview || {};
      return buildActionItems(item).map((action) => ({
        generated_at: generatedAt,
        store_name: String(item.store_name || ''),
        store_code: String(item.store_code || ''),
        status: statusLabel(item.status),
        health_score: Number(item.health_score || 0),
        module: action.module,
        priority: action.priority,
        action: action.text,
        sales_cny: toRmb(overview.sales_amount, item),
        ad_spend_cny: toRmb(overview.ad_expense_rub, item),
        unfulfilled_orders: Number(overview.unfulfilled_orders_count || 0),
        no_price_items: Number(overview.no_price_count || 0),
        risky_skus: Number(overview.risky_sku_count || 0),
        source_filter: getUiLabelMap()[uiState.quickFilter] || uiState.quickFilter || 'all',
      }));
    })
    .sort((a, b) => {
      const priorityRank = { 高: 3, 中: 2, 低: 1 };
      return (priorityRank[b.priority] || 0) - (priorityRank[a.priority] || 0) || a.health_score - b.health_score;
    });
}

function csvCell(value) {
  const text = String(value ?? '');
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function actionRowsToCsv(rows) {
  const columns = [
    ['generated_at', '数据时间'],
    ['store_name', '店铺'],
    ['store_code', '店铺编码'],
    ['status', '状态'],
    ['health_score', '健康分'],
    ['module', '模块'],
    ['priority', '优先级'],
    ['action', '建议动作'],
    ['sales_cny', '销售额CNY'],
    ['ad_spend_cny', '广告花费CNY'],
    ['unfulfilled_orders', '待履约订单'],
    ['no_price_items', '无价格商品'],
    ['risky_skus', '风险SKU'],
    ['source_filter', '页面筛选'],
  ];
  return [
    columns.map(([, label]) => csvCell(label)).join(','),
    ...rows.map((row) => columns.map(([key]) => csvCell(row[key])).join(',')),
  ].join('\r\n');
}

function downloadTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function exportActionList(format) {
  const rows = getExportActionRows(payload);
  if (!rows.length) {
    setStatus('当前筛选范围暂无可导出的动作清单。');
    return;
  }
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
  if (format === 'json') {
    downloadTextFile(`ozon_actions_${stamp}.json`, JSON.stringify({ exported_at: new Date().toISOString(), rows }, null, 2), 'application/json;charset=utf-8');
  } else {
    downloadTextFile(`ozon_actions_${stamp}.csv`, `\ufeff${actionRowsToCsv(rows)}`, 'text/csv;charset=utf-8');
  }
  setStatus(`已导出 ${whole(rows.length)} 条动作清单（${format.toUpperCase()}）。`);
}

function buildActionSummary(row) {
  const summary = [];
  if (row.quickFlags.errorCount || row.quickFlags.moduleErrorCount) {
    summary.push(`错误 ${whole(row.quickFlags.errorCount + row.quickFlags.moduleErrorCount)}`);
  }
  if (row.quickFlags.warningCount) {
    summary.push(`告警 ${whole(row.quickFlags.warningCount)}`);
  }
  if (row.quickFlags.hasAdAlerts) {
    summary.push('广告异常');
  }
  if (row.quickFlags.hasSkuRisk) {
    summary.push('SKU 风险');
  }
  if (row.quickFlags.riskCount) {
    summary.push(`风险标记 ${whole(row.quickFlags.riskCount)}`);
  }
  return summary.length ? summary.join(' · ') : '当前无重点异常';
}

function buildStoreActionLine(item) {
  const overview = item.overview || {};
  const candidates = [];
  if (getStoreErrorCount(item) || getModuleErrorCount(item)) {
    candidates.push('先处理模块错误，恢复数据完整性');
  }
  if (Number(overview.ad_expense_rub || 0) > 0 && Number(overview.ad_orders || 0) === 0) {
    candidates.push('广告有花费无订单，优先排查投放转化');
  }
  if (Number(overview.no_price_count || 0) > 0) {
    candidates.push('修复无价格商品');
  }
  if (Number(overview.risky_sku_count || 0) > 0) {
    candidates.push('处理 SKU 风险清单');
  }
  if (Number(overview.unfulfilled_orders_count || 0) > 0) {
    candidates.push('跟进待履约订单');
  }
  if (Number(overview.empty_stock_warehouses_count || 0) > 0 || Number(overview.low_stock_warehouses_count || 0) > 0) {
    candidates.push('检查低库存与空库存仓库');
  }
  return candidates.slice(0, 2).join('；') || '当前优先级较低，保持监控';
}

function buildStoreImpactLine(item) {
  const overview = item.overview || {};
  return [
    `销售 ${moneyRmb(overview.sales_amount, item)}`,
    `广告 ${moneyRmb(overview.ad_expense_rub, item)}`,
    `待履约 ${whole(overview.unfulfilled_orders_count)}`,
    `风险 SKU ${whole(overview.risky_sku_count)}`,
  ].join(' · ');
}

function getSkuPreview(item) {
  const skuRisk = item.sku_risk || {};
  return skuRisk.sku_risks_preview || skuRisk.sku_risks || [];
}

function getAdAlerts(item) {
  const ads = item.ads || {};
  return ads.alerts || [];
}

function getStoreSearchText(item) {
  return [
    item.store_name,
    item.store_code,
    ...(item.flags || []),
    ...(item.insights || []),
    ...(item.recommendations || []),
  ]
    .join(' ')
    .toLowerCase();
}

function normalizeInsightText(line, item) {
  const text = String(line || '').trim();
  if (!text) return '';
  return text
    .replace(/广告花费\s+(-?[\d,.]+)/g, (_, value) => `广告花费 ${moneyRmb(value, item)}`)
    .replace(/广告销售额\s+(-?[\d,.]+)/g, (_, value) => `广告销售额 ${moneyRmb(value, item)}`)
    .replace(/销售额\s+(-?[\d,.]+)/g, (_, value) => `销售额 ${moneyRmb(value, item)}`)
    .replace(/退款\s+(-?[\d,.]+)/g, (_, value) => `退款 ${moneyRmb(value, item)}`)
    .replace(/服务费\s+(-?[\d,.]+)/g, (_, value) => `服务费 ${moneyRmb(value, item)}`)
    .replace(/(ROAS\s+)(-?[\d,.]+)/g, (_, prefix, value) => `${prefix}${money(value)}`);
}

function normalizeTextList(lines, item) {
  return (Array.isArray(lines) ? lines : []).map((line) => normalizeInsightText(line, item)).filter(Boolean);
}

function getStoreRecord(item) {
  const overview = item.overview || {};
  return {
    item,
    health: Number(item.health_score || 0),
    sales: toRmb(overview.sales_amount, item),
    adSpend: toRmb(overview.ad_expense_rub, item),
    flags: (item.flags || []).length,
    errors: (item.errors || []).length,
  };
}

function renderStoreSwitcher(nextPayload) {
  const select = document.getElementById('stores-select');
  if (!select) return;

  const options = getStoreSwitchOptions(nextPayload);
  if (uiState.storeCode && !options.some((item) => item.store_code === uiState.storeCode)) {
    uiState.storeCode = '';
  }

  select.innerHTML = options
    .map(
      (item) =>
        `<option value="${escapeHtml(item.store_code)}">${escapeHtml(`${item.store_name} (${item.store_code}) · ${getCurrencyTypeLabel(item.currency)} · 健康 ${item.health_score} · ${statusLabel(item.status)}`)}</option>`,
    )
    .join('');
  select.value = uiState.storeCode;
}

function renderHero(nextPayload) {
  const summary = nextPayload.summary || {};
  const refreshInfo = nextPayload.refresh_info || {};
  const dataSource = nextPayload.data_source === 'sqlite' ? 'SQLite' : '嵌入快照';
  const snapshotId = nextPayload.snapshot_id || refreshInfo.snapshot_id || '-';
  const dbPath = nextPayload.db_path || refreshInfo.db_path || '-';
  const activeQuickFilter = getUiLabelMap()[uiState.quickFilter] || '全部关注';
  const activeStore = findStoreByCode(nextPayload, uiState.storeCode);
  const currency = getStoreCurrency(activeStore);
  const currencyType = getCurrencyTypeLabel(currency);
  const selectedStoreLabel = activeStore ? `${activeStore.store_name || activeStore.store_code}（${currencyType}）` : '未选择店铺';

  document.getElementById('hero-desc').textContent =
    `统计周期 ${nextPayload.days || 0} 天，当前店铺：${selectedStoreLabel}，当前聚焦：${activeQuickFilter}，金额统一按人民币展示，生成时间：${nextPayload.generated_at || '-'}，数据源：${dataSource}，快照 #${snapshotId}`;

  document.getElementById('hero-stats').innerHTML = [
    ['最近刷新', refreshInfo.generated_at || nextPayload.generated_at || '-'],
    ['覆盖店铺', `${summary.store_count || 0}`],
    ['异常关注', `${summary.flagged_count || 0}`],
    ['平均健康分', `${summary.avg_health_score || 0}`],
  ]
    .map(
      ([label, value]) => `
        <div class="hero-stat">
          <div class="label">${escapeHtml(label)}</div>
          <div class="value">${escapeHtml(value)}</div>
        </div>
      `,
    )
    .join('');

  document.getElementById('overview-grid').innerHTML = [
    ['近周期销售额', moneySummary(summary.total_sales_amount_cny ?? summary.total_sales_amount), `店铺 ${summary.store_count || 0} 家，正常 ${summary.ok_count || 0} 家`],
    ['广告花费', moneySummary(summary.total_ad_expense_cny ?? summary.total_ad_expense_rub), `广告销售额 ${moneySummary(summary.total_ad_revenue_cny ?? summary.total_ad_revenue_rub)}，ROAS ${money(summary.overall_roas)}`],
    ['履约关注', whole(summary.total_unfulfilled_orders), `低库存仓库 ${whole(summary.total_low_stock_warehouses)} 个`],
    ['价格与SKU风险', whole(summary.total_no_price_items), `风险 SKU ${whole(summary.total_risky_skus)} 个`],
  ]
    .map(
      ([label, value, sub]) => `
        <article class="metric-card">
          <div class="label">${escapeHtml(label)}</div>
          <div class="value">${escapeHtml(value)}</div>
          <div class="sub">${escapeHtml(sub)}</div>
        </article>
      `,
    )
    .join('');

  document.getElementById('footer-text').textContent =
    `最近刷新：${refreshInfo.generated_at || nextPayload.generated_at || '-'}；数据源：${dataSource}；快照 #${snapshotId}；数据库：${dbPath}`;
}

function renderAttention(nextPayload) {
  const results = getFilteredResults(nextPayload);
  const records = sortRecords(results.map(getStoreRecord));
  const topRiskStores = records.slice(0, 5);
  const visibleCodes = new Set(results.map((item) => String(item.store_code || '').trim()));
  const actionRows = getActionPriorityRows(nextPayload).filter((row) => visibleCodes.has(String(row.item.store_code || '').trim()));
  const todayActions = getTodayActionRows(nextPayload);
  const errorRows = results
    .flatMap((item) =>
      (item.errors || []).map((error) => ({
        store_name: item.store_name,
        store_code: item.store_code,
        module: error.module || 'unknown',
        moduleKey: getModuleKeyByLabel(error.module || ''),
        error: error.error || '',
      })),
    )
    .concat(
      results.flatMap((item) =>
        MODULE_DEFINITIONS.filter(([key]) => String((item[key] || {}).status || 'unknown') === 'error').map(([key, name]) => ({
          store_name: item.store_name,
          store_code: item.store_code,
          module: name,
          moduleKey: key,
          error: (item[key] || {}).error || '模块执行失败，当前仅展示错误状态。',
        })),
      ),
    )
    .slice(0, 10);

  const adRows = results
    .flatMap((item) =>
      getAdAlerts(item).map((alert) => ({
        store_name: item.store_name,
        currency: getStoreCurrency(item),
        campaign_name: alert.campaign_name || alert.campaign_id || '-',
        expense_rub: alert.expense_rub || 0,
        orders: alert.orders || 0,
        action: alert.action || '-',
      })),
    )
    .slice(0, 10);

  const panels = [
    {
      title: '今日动作清单',
      desc: `从当前筛选范围提取 ${whole(todayActions.length)} 条最值得先做的动作。`,
      body: todayActions.length
        ? `<div class="list action-list">${todayActions
            .map(
              ({ item, action }) => `
                <button class="list-item interactive-row action-item" type="button" data-focus-store="${escapeHtml(item.store_code || '')}">
                  <strong><span class="priority-pill ${action.priority === '高' ? 'high' : 'medium'}">${escapeHtml(action.priority)}</span>${escapeHtml(action.module)} · ${escapeHtml(item.store_name || '-')}</strong>
                  <span>${escapeHtml(action.text)}</span>
                  <small>${escapeHtml(item.store_code || '')} · 健康 ${whole(item.health_score)} · ${escapeHtml(statusLabel(item.status))}</small>
                </button>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">当前筛选范围暂无明确待办。</div>',
    },
    {
      title: '行动优先级',
      desc: `基于当前筛选范围生成优先级，候选 ${whole(results.length)} 家店铺。`,
      body: actionRows.length
        ? `<div class="list">${actionRows
            .map(
              (row) => `
                <button class="list-item interactive-row" type="button" data-focus-store="${escapeHtml(row.item.store_code || '')}">
                  <strong>${escapeHtml(row.item.store_name || '-')} <span class="muted">${escapeHtml(row.item.store_code || '')}</span></strong>
                  <span>健康 ${row.record.health} · ${escapeHtml(buildActionSummary(row))}</span>
                </button>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">暂无待优先处理店铺。</div>',
    },
    {
      title: '重点店铺',
      desc: `当前筛选范围内健康分低、风险高的前 ${whole(Math.min(topRiskStores.length, 5))} 家。`,
      body: topRiskStores.length
        ? `<div class="list">${topRiskStores
            .map(
              (record) => `
                <button class="list-item interactive-row" type="button" data-focus-store="${escapeHtml(record.item.store_code || '')}">
                  <strong>${escapeHtml(record.item.store_name || '-')} <span class="muted">${escapeHtml(record.item.store_code || '')}</span></strong>
                  <span>健康 ${record.health}，风险 ${record.flags}，错误 ${record.errors}，销售额 ${moneySummary(record.sales)}</span>
                </button>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">暂无重点店铺。</div>',
    },
    {
      title: '模块错误',
      desc: `当前筛选范围内共发现 ${whole(errorRows.length)} 条模块错误。`,
      body: errorRows.length
        ? `<div class="list">${errorRows
            .map(
              (row) => `
                <button class="list-item interactive-row" type="button" data-focus-store="${escapeHtml(row.store_code || '')}" data-focus-module="${escapeHtml(row.moduleKey || '')}">
                  <strong>${escapeHtml(row.store_name || '-')} · ${escapeHtml(row.module)}</strong>
                  <small>${escapeHtml(row.error)}</small>
                </button>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">暂无模块错误。</div>',
    },
    {
      title: '广告告警',
      desc: `当前筛选范围内花费高但转化低的广告告警 ${whole(adRows.length)} 条。`,
      body: adRows.length
        ? `<div class="list">${adRows
            .map(
              (row) => `
                <div class="list-item">
                  <strong>${escapeHtml(row.store_name || '-')} · ${escapeHtml(row.campaign_name)}</strong>
                  <span>花费 ${moneyRmb(row.expense_rub, { currency: row.currency })}，订单 ${whole(row.orders)}，动作 ${escapeHtml(row.action)}</span>
                </div>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">暂无广告告警。</div>',
    },
  ];

  document.getElementById('attention-grid').innerHTML = panels
    .map(
      (panel) => `
        <article class="board-card">
          <div class="board-head">
            <div>
              <h2>${escapeHtml(panel.title)}</h2>
              <p>${escapeHtml(panel.desc)}</p>
            </div>
          </div>
          ${panel.body}
        </article>
      `,
    )
    .join('');

  document.querySelectorAll('[data-focus-store]').forEach((button) => {
    button.addEventListener('click', () => {
      const storeCode = button.getAttribute('data-focus-store') || '';
      const moduleKey = button.getAttribute('data-focus-module') || '';
      focusStore(nextPayload, storeCode, { moduleKey });
    });
  });
}

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

function getTrendMoneyValue(item, key) {
  return toRmb(item?.[key], item);
}

function getTrendActionText(item) {
  const issues = [];
  if (Number(item?.unfulfilled_orders || 0) > 0) {
    issues.push(`待履约 ${whole(item.unfulfilled_orders)}`);
  }
  if (Number(item?.no_price_count || 0) > 0) {
    issues.push(`无价格 ${whole(item.no_price_count)}`);
  }
  if (Number(item?.risky_sku_count || 0) > 0) {
    issues.push(`风险 SKU ${whole(item.risky_sku_count)}`);
  }
  return issues.length ? issues.join(' · ') : '暂无经营动作风险';
}

function renderTrendPoint(item) {
  return `
    <div class="list-item">
      <strong>${escapeHtml(item.generated_at || '-')}</strong>
      <span>健康 ${whole(item.health_score)} | 销售额 ${moneySummary(getTrendMoneyValue(item, 'sales_amount'))} | 广告 ${moneySummary(getTrendMoneyValue(item, 'ad_expense_rub'))} | ROAS ${money(item.ad_roas)}</span>
      <small>待履约 ${whole(item.unfulfilled_orders)} | 无价格 ${whole(item.no_price_count)} | 风险 SKU ${whole(item.risky_sku_count)} | ${escapeHtml(getTrendActionText(item))}</small>
    </div>
  `;
}

function renderDataOps(nextPayload) {
  const container = document.getElementById('data-grid');
  if (!container) return;

  if (!isServeMode()) {
    container.innerHTML = `
      <article class="board-card">
        <div class="board-head"><div><h2>数据与接口</h2><p>需要 --serve 模式。</p></div></div>
        <div class="empty">请使用 --serve 启动后查看后端诊断信息。</div>
      </article>
    `;
    return;
  }

  const requestId = ++dataOpsRequestId;
  const activeStoreCode = getActiveStoreCode(nextPayload);
  const trendUrl = activeStoreCode
    ? `/api/stores/trend?store_code=${encodeURIComponent(activeStoreCode)}&limit=10`
    : null;

  container.innerHTML = `
    <article class="board-card"><div class="board-head"><div><h2>快照历史</h2><p>加载中...</p></div></div></article>
    <article class="board-card"><div class="board-head"><div><h2>店铺趋势</h2><p>加载中...</p></div></div></article>
    <article class="board-card"><div class="board-head"><div><h2>API 覆盖</h2><p>加载中...</p></div></div></article>
  `;

  Promise.all([
    fetchApiJson('/api/snapshots?limit=6'),
    trendUrl ? fetchApiJson(trendUrl) : Promise.resolve({ status: 'ok', points: [] }),
    fetchApiJson('/api/ozon-api/catalog?group=all'),
  ])
    .then(([snapshotsRes, trendRes, catalogRes]) => {
      if (requestId !== dataOpsRequestId) return;
      const snapshots = snapshotsRes.snapshots || [];
      const points = trendRes.points || [];
      const catalog = catalogRes.catalog || {};
      const endpoints = catalog.endpoints || [];

      const snapshotBody = snapshots.length
        ? `<div class="list">${snapshots
            .map(
              (item) => `
                <div class="list-item">
                  <strong>${escapeHtml(item.generated_at || '-')}</strong>
                  <span>店铺 ${whole((item.summary || {}).store_count)} | 销售额 ${moneySummary((item.summary || {}).total_sales_amount_cny ?? (item.summary || {}).total_sales_amount)}</span>
                </div>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">暂无快照。</div>';

      const trendBody = points.length
        ? `<div class="list">${points
            .map(renderTrendPoint)
            .join('')}</div>`
        : `<div class="empty">${escapeHtml(activeStoreCode || 'N/A')} 暂无趋势数据。</div>`;

      const catalogBody = endpoints.length
        ? `<div class="list">${endpoints
            .slice(0, 8)
            .map(
              (item) => `
                <div class="list-item">
                  <strong>${escapeHtml(item.method || '')} ${escapeHtml(item.path || '')}</strong>
                  <span>${escapeHtml(item.description || '')}（${escapeHtml(item.group || '-')})</span>
                </div>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">接口目录为空。</div>';

      container.innerHTML = `
        <article class="board-card"><div class="board-head"><div><h2>快照历史</h2><p>最近落库记录</p></div></div>${snapshotBody}</article>
        <article class="board-card"><div class="board-head"><div><h2>店铺趋势</h2><p>${escapeHtml(activeStoreCode || 'N/A')} 的滚动变化</p></div></div>${trendBody}</article>
        <article class="board-card"><div class="board-head"><div><h2>API 覆盖</h2><p>总计 ${whole(catalog.total_count || 0)} 个接口</p></div></div>${catalogBody}</article>
      `;
    })
    .catch((error) => {
      if (requestId !== dataOpsRequestId) return;
      container.innerHTML = `
        <article class="board-card">
          <div class="board-head"><div><h2>数据与接口</h2><p>加载失败</p></div></div>
          <div class="empty">${escapeHtml(error.message || '未知错误')}</div>
        </article>
      `;
    });
}

function renderStatusFilters(nextPayload) {
  const summary = nextPayload.summary || {};
  const buttons = [
    { id: 'all', label: '全部', count: summary.store_count || 0 },
    { id: 'ok', label: '正常', count: summary.ok_count || 0 },
    { id: 'partial', label: '部分异常', count: summary.partial_count || 0 },
    { id: 'error', label: '失败', count: summary.error_count || 0 },
  ];
  const quickButtons = [
    { id: 'all', label: '全部关注' },
    { id: 'risk', label: '只看风险' },
    { id: 'warnings', label: '只看告警' },
    { id: 'errors', label: '只看错误' },
    { id: 'ads', label: '广告异常' },
    { id: 'sku', label: 'SKU 风险' },
  ];

  document.getElementById('status-filter-group').innerHTML = `
    <div class="filter-block">
      <div class="filter-block-title">运行状态</div>
      <div class="filter-group-inner">
        ${buttons
          .map(
            (button) => `
              <button class="btn filter ${uiState.status === button.id ? 'active' : ''}" data-status="${button.id}" type="button">
                ${escapeHtml(button.label)} · ${escapeHtml(button.count)}
              </button>
            `,
          )
          .join('')}
      </div>
    </div>
    <div class="filter-block">
      <div class="filter-block-title">快速聚焦</div>
      <div class="filter-group-inner">
        ${quickButtons
          .map(
            (button) => `
              <button class="btn filter ${uiState.quickFilter === button.id ? 'active' : ''}" data-quick-filter="${button.id}" type="button">
                ${escapeHtml(button.label)}
              </button>
            `,
          )
          .join('')}
      </div>
    </div>
  `;

  document.querySelectorAll('[data-status]').forEach((button) => {
    button.addEventListener('click', () => {
      uiState.status = button.getAttribute('data-status') || 'all';
      ensureStoreSelection(payload);
      renderHero(payload);
      renderAttention(payload);
      renderStoreSwitcher(payload);
      renderStores(payload);
      renderStatusFilters(payload);
      renderDataOps(payload);
    });
  });

  document.querySelectorAll('[data-quick-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      uiState.quickFilter = button.getAttribute('data-quick-filter') || 'all';
      ensureStoreSelection(payload);
      renderHero(payload);
      renderAttention(payload);
      renderStoreSwitcher(payload);
      renderStores(payload);
      renderStatusFilters(payload);
      renderDataOps(payload);
    });
  });
}

function renderViewActionState(nextPayload) {
  const records = getExpandableRecords(nextPayload);
  const expanded = records.filter((record) => uiState.expandedStoreCodes.includes(getStoreCardId(record.item))).length;
  const actionable = records.filter((record) => isStoreActionable(record.item)).length;
  const expandAllBtn = document.getElementById('expand-all-btn');
  const expandRiskBtn = document.getElementById('expand-risk-btn');
  const collapseAllBtn = document.getElementById('collapse-all-btn');
  if (expandAllBtn) expandAllBtn.textContent = `展开当前店铺 (${whole(records.length)})`;
  if (expandRiskBtn) expandRiskBtn.textContent = `只展开异常店铺 (${whole(actionable)})`;
  if (collapseAllBtn) collapseAllBtn.textContent = `全部收起 (${whole(expanded)})`;
}

function rerenderStoreWorkspace() {
  ensureStoreSelection(payload);
  renderHero(payload);
  renderAttention(payload);
  renderStoreSwitcher(payload);
  renderStatusFilters(payload);
  renderDataOps(payload);
  renderStores(payload);
}

function expandCurrentStores(mode) {
  const records = getExpandableRecords(payload);
  if (mode === 'collapse') {
    setExpandedStoreIds([]);
  } else if (mode === 'risk') {
    setExpandedStoreIds(records.filter((record) => isStoreActionable(record.item)).map((record) => getStoreCardId(record.item)));
  } else {
    setExpandedStoreIds(records.map((record) => getStoreCardId(record.item)));
  }
  rerenderStoreWorkspace();
}

function moduleTone(status) {
  if (status === 'ok') return 'ok';
  if (status === 'partial') return 'warn';
  if (status === 'no_campaigns') return 'neutral';
  return 'error';
}

function moduleMetricText(key, module, item) {
  const status = (module || {}).status || 'unknown';
  const summary = (module || {}).summary || {};
  const warnings = getModuleWarnings(module);

  if (status === 'partial' && warnings.length) {
    return `告警 ${whole(warnings.length)} 条，已降级显示可用数据。`;
  }
  if (key === 'sales') {
    return `估算订单 ${whole(summary.orders_count_estimated)}，销售额 ${moneyRmb(summary.sales_amount, item)}`;
  }
  if (key === 'ads') {
    if (status === 'no_campaigns') return '当前店铺暂无广告活动，不计为失败。';
    return `活动 ${whole(summary.campaign_count)}，ROAS ${money(summary.overall_roas)}`;
  }
  if (key === 'orders') {
    return `待履约 ${whole(summary.unfulfilled_count)}，待发运 ${whole(summary.awaiting_deliver_count)}`;
  }
  if (key === 'pricing') {
    return `无价商品 ${whole(summary.no_price_count)}，大折扣 ${whole(summary.deep_discount_count)}`;
  }
  if (key === 'logistics') {
    return `仓库 ${whole(summary.warehouse_count)}，低库存 ${whole(summary.low_stock_warehouses_count)}`;
  }
  if (key === 'sku_risk') {
    return `风险 SKU ${whole(summary.risky_sku_count)}，缺货 ${whole(summary.out_of_stock_sku_count)}`;
  }
  return `状态：${statusLabel(status)}`;
}

function buildModuleStatus(item) {
  return MODULE_DEFINITIONS
    .map(([key, name]) => {
      const module = item[key] || {};
      const status = module.status || 'unknown';
      const focused = uiState.focusedModuleKey === key;
      return `
        <div class="module-card ${moduleTone(status)} ${focused ? 'focused' : ''}" data-module-card="${escapeHtml(key)}">
          <strong>${escapeHtml(name)} · ${escapeHtml(statusLabel(status))}</strong>
          <span>${escapeHtml(moduleMetricText(key, module, item))}</span>
        </div>
      `;
    })
    .join('');
}

function renderLogisticsDetail(item) {
  const logistics = item.logistics || {};
  const summary = logistics.summary || {};
  const warehouses = (logistics.warehouses || []).slice(0, 6);
  const notes = summary.stock_health_notes || [];

  return `
    <div class="store-section">
      <h4>物流模块（仓库与库存）</h4>
      <ul class="bullets">
        <li>仓库数: ${whole(summary.warehouse_count)}</li>
        <li>配送方式数: ${whole(summary.delivery_methods_count)}</li>
        <li>样本现货: ${whole(summary.stock_present_sample_total)}，预留: ${whole(summary.stock_reserved_sample_total)}</li>
        <li>预留占比: ${pct(summary.stock_reserved_ratio_pct)}</li>
        <li>低库存仓库: ${whole(summary.low_stock_warehouses_count)}，空库存仓库: ${whole(summary.empty_stock_warehouses_count)}</li>
      </ul>
      ${notes.length ? `<div class="chips">${notes.map((line) => `<span class="chip">${escapeHtml(line)}</span>`).join('')}</div>` : '<div class="empty">暂无仓库健康备注。</div>'}
      ${warehouses.length
        ? `<ul class="bullets">${warehouses
            .map(
              (row) => `<li>${escapeHtml(row.name || row.warehouse_id || '-')} · 状态 ${escapeHtml(row.status || '-')} · 现货 ${whole(row.stock_present_sample)} · 预留 ${whole(row.stock_reserved_sample)}</li>`,
            )
            .join('')}</ul>`
        : '<div class="empty">暂无仓库预览数据。</div>'}
    </div>
  `;
}

function renderStores(nextPayload) {
  const records = getSelectedRecords(nextPayload);
  const visibleRecords = getVisibleRecords(nextPayload);
  const selectedStoreText = uiState.storeCode ? `，当前店铺：${uiState.storeCode}` : '，当前模式：下拉切换单店展示';
  const quickFilterText = uiState.quickFilter !== 'all' ? `，快速聚焦：${getUiLabelMap()[uiState.quickFilter] || uiState.quickFilter}` : '';
  const expandedCount = uiState.expandedStoreCodes.length ? `，展开卡片：${uiState.expandedStoreCodes.length}` : '';
  document.getElementById('filter-note').textContent =
    `当前渲染 ${records.length} / 可选 ${visibleRecords.length} / 总店铺 ${getResults(nextPayload).length} 家${selectedStoreText}${quickFilterText}${expandedCount}。`;

  if (!records.length) {
    document.getElementById('stores').innerHTML = '<div class="empty">没有匹配当前筛选条件的店铺。</div>';
    return;
  }

  document.getElementById('stores').innerHTML = records
    .map((record) => {
      const item = record.item;
      const overview = item.overview || {};
      const flags = item.flags || [];
      const insights = normalizeTextList(item.insights, item);
      const recommendations = normalizeTextList(item.recommendations, item);
      const errors = item.errors || [];
      const warnings = MODULE_DEFINITIONS
        .flatMap(([key, name]) => getModuleWarnings(item[key]).map((warning) => `${name}: ${warning}`))
        .slice(0, 8);
      const warningCount = getStoreWarningCount(item);
      const moduleErrorCount = getModuleErrorCount(item);
      const totalErrorCount = errors.length + moduleErrorCount;
      const skuRisks = getSkuPreview(item).slice(0, 6);
      const adAlerts = getAdAlerts(item).slice(0, 5);
      const expanded = isStoreExpanded(item);
      const toggleText = expanded ? '收起详情' : '展开详情';
      const actionLine = buildStoreActionLine(item);
      const impactLine = buildStoreImpactLine(item);

      return `
        <article class="store-card ${healthTone(record.health)} ${expanded ? 'expanded' : 'collapsed'}" data-store-card="${escapeHtml(getStoreCardId(item))}">
          <div class="store-head">
            <div>
              <div class="store-kicker">${escapeHtml(statusLabel(item.status))} · ${escapeHtml(getCurrencyTypeLabel(getStoreCurrency(item)))} · 金额按人民币展示 · 汇率 ${escapeHtml(`1 ${getStoreCurrency(item)} = ${money(getRmbRate(getStoreCurrency(item), item))} CNY`)}</div>
              <div class="store-title"><h3>${escapeHtml(item.store_name || '-')}</h3><span>${escapeHtml(item.store_code || '')}</span></div>
              <div class="store-summary"><strong>下一步：</strong>${escapeHtml(actionLine)}</div>
              <div class="store-impact-line">${escapeHtml(impactLine)}</div>
              <div class="badges" style="margin-top:12px;">
                <span class="badge ${statusTone(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
                <span class="badge ${healthBadge(record.health)}">健康 ${escapeHtml(record.health)}</span>
                <span class="badge">风险 ${escapeHtml(flags.length)}</span>
                <span class="badge warn-tone">告警 ${escapeHtml(warningCount)}</span>
                <span class="badge ${totalErrorCount ? 'bad-tone' : ''}">错误 ${escapeHtml(totalErrorCount)}</span>
              </div>
            </div>
            <div class="store-head-actions">
              <div class="store-health">
                <div class="score-line"><div><div class="caption">健康分</div><div class="score">${escapeHtml(record.health)}</div></div></div>
                <div class="health-bar"><span style="width:${Math.max(0, Math.min(record.health, 100))}%;"></span></div>
              </div>
              <button class="btn secondary toggle-store-btn" type="button" data-toggle-store="${escapeHtml(getStoreCardId(item))}">${toggleText}</button>
            </div>
          </div>

          <section class="store-metrics">
            <div class="mini-panel"><div class="label">销售额</div><div class="value">${moneyRmb(overview.sales_amount, item)}</div><div class="sub">退款 ${moneyRmb(overview.refund_amount, item)} · 服务费 ${moneyRmb(overview.service_amount, item)}</div></div>
            <div class="mini-panel"><div class="label">广告花费</div><div class="value">${moneyRmb(overview.ad_expense_rub, item)}</div><div class="sub">广告销售额 ${moneyRmb(overview.ad_revenue_rub, item)} · ROAS ${money(overview.ad_roas)}</div></div>
            <div class="mini-panel"><div class="label">履约关注</div><div class="value">${whole(overview.unfulfilled_orders_count)}</div><div class="sub">待包装 ${whole(overview.awaiting_packaging_count)} · 待发运 ${whole(overview.awaiting_deliver_count)}</div></div>
            <div class="mini-panel"><div class="label">价格风险</div><div class="value">${whole(overview.no_price_count)}</div><div class="sub">大折扣 ${whole(overview.deep_discount_count)} · 低毛利 ${whole(overview.low_margin_candidates_count)}</div></div>
            <div class="mini-panel"><div class="label">物流仓库</div><div class="value">${whole(overview.warehouse_count)}</div><div class="sub">空库存 ${whole(overview.empty_stock_warehouses_count)} · 预留占比 ${pct(overview.stock_reserved_ratio_pct)}</div></div>
            <div class="mini-panel"><div class="label">SKU 风险</div><div class="value">${whole(overview.risky_sku_count)}</div><div class="sub">无库存 ${whole(overview.out_of_stock_sku_count)} · 低可用 ${whole(overview.low_free_stock_sku_count)}</div></div>
          </section>

          <div class="store-detail-shell ${expanded ? 'expanded' : 'collapsed'}">
            <section class="store-columns">
              <div class="store-section"><h4>风险标记</h4><div class="chips">${(flags.length ? flags : ['暂无重点风险']).map((flag) => `<span class="chip">${escapeHtml(flag)}</span>`).join('')}</div></div>
              <div class="store-section"><h4>模块状态总览</h4><div class="module-grid">${buildModuleStatus(item)}</div></div>
              <div class="store-section"><h4>经营洞察</h4>${insights.length ? `<ul class="bullets">${insights.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>` : '<div class="empty">暂无洞察。</div>'}</div>
              <div class="store-section"><h4>建议动作</h4>${recommendations.length ? `<ul class="bullets">${recommendations.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>` : '<div class="empty">暂无建议。</div>'}</div>
            </section>

            <section class="detail-grid">
              <div class="store-section">
                <h4>广告告警明细</h4>
                ${adAlerts.length
                  ? `<ul class="bullets">${adAlerts.map((row) => `<li>${escapeHtml(row.campaign_name || row.campaign_id || '-')} · 花费 ${moneyRmb(row.expense_rub, item)} · 订单 ${whole(row.orders)} · ${escapeHtml(row.action || '-')}</li>`).join('')}</ul>`
                  : '<div class="empty">暂无广告告警。</div>'}
              </div>
              <div class="store-section">
                <h4>SKU 风险预览</h4>
                ${skuRisks.length
                  ? `<ul class="bullets">${skuRisks.map((row) => `<li>${escapeHtml(row.sku ?? '-')} · ${escapeHtml((row.reasons || []).join(' / '))}</li>`).join('')}</ul>`
                  : '<div class="empty">暂无 SKU 风险预览。</div>'}
              </div>
              <div class="store-section">
                <h4>模块告警</h4>
                ${warnings.length
                  ? `<ul class="bullets">${warnings.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>`
                  : '<div class="empty">暂无模块告警。</div>'}
              </div>
              <div class="store-section">
                <h4>模块错误</h4>
                ${totalErrorCount
                  ? `<ul class="bullets">${errors.map((err) => `<li>${escapeHtml((err.module || 'unknown') + ': ' + (err.error || ''))}</li>`).join('')}${MODULE_DEFINITIONS.filter(([key]) => String((item[key] || {}).status || 'unknown') === 'error').map(([, name]) => `<li>${escapeHtml(name + ': 模块执行失败')}</li>`).join('')}</ul>`
                  : '<div class="empty">暂无模块错误。</div>'}
              </div>
              ${renderLogisticsDetail(item)}
            </section>
          </div>
        </article>
      `;
    })
    .join('');

  renderViewActionState(nextPayload);

  document.querySelectorAll('[data-toggle-store]').forEach((button) => {
    button.addEventListener('click', () => {
      const storeId = button.getAttribute('data-toggle-store') || '';
      const item = getResults(nextPayload).find((row) => getStoreCardId(row) === storeId);
      if (!item) return;
      toggleStoreExpanded(item);
      rerenderStoreWorkspace();
    });
  });
}

function renderDashboard(nextPayload) {
  payload = nextPayload || embeddedPayload;
  ensureStoreSelection(payload);
  renderHero(payload);
  renderAttention(payload);
  renderStoreSwitcher(payload);
  renderDataOps(payload);
  renderStatusFilters(payload);
  renderStores(payload);
  renderAdminWorkspaceState();
}

async function reloadLatestData(options = {}) {
  const { silent = false } = options;
  try {
    if (!silent) {
      setStatus('正在从 SQLite 加载最新快照...');
    }
    if (!isServeMode()) {
      renderDashboard(payload);
      if (!silent) {
        setStatus('当前为静态模式，已使用页面内嵌快照。');
      }
      return;
    }
    const nextPayload = await fetchLatestPayloadFromDb();
    renderDashboard(nextPayload);
    if (!silent) {
      setStatus(`SQLite 快照加载完成：#${nextPayload.snapshot_id || '-'} · ${nextPayload.generated_at || '-'}`);
    }
  } catch (error) {
    setStatus(`加载失败：${error.message}`);
  }
}

function getControlElements() {
  const days = document.getElementById('cfg-days');
  const storeSelect = document.getElementById('cfg-store-select');
  const storeFilter = document.getElementById('cfg-store-filter');
  const limitCampaigns = document.getElementById('cfg-limit-campaigns');
  const maxWorkers = document.getElementById('cfg-max-workers');
  const includeDetails = document.getElementById('cfg-include-details');
  const keepHistory = document.getElementById('cfg-keep-history');
  const writeDb = document.getElementById('cfg-write-db');
  const dbPath = document.getElementById('cfg-db-path');
  if (!days || !storeSelect || !storeFilter || !limitCampaigns || !maxWorkers || !includeDetails || !keepHistory || !writeDb || !dbPath) {
    return null;
  }
  return { days, storeSelect, storeFilter, limitCampaigns, maxWorkers, includeDetails, keepHistory, writeDb, dbPath };
}

function readWebConfig() {
  const controls = getControlElements();
  if (!controls) return {};
  syncStoreFilterWithSelect();
  const config = {
    days: Math.max(1, Number(controls.days.value || 7)),
    store_filter: (controls.storeFilter.value || '').trim(),
    limit_campaigns: Math.max(0, Number(controls.limitCampaigns.value || 0)),
    max_workers: Math.max(1, Number(controls.maxWorkers.value || 1)),
    include_details: Boolean(controls.includeDetails.checked),
    keep_history: Boolean(controls.keepHistory.checked),
    write_db: true,
  };
  const dbPath = (controls.dbPath.value || '').trim();
  if (dbPath) config.db_path = dbPath;
  return config;
}

function applyWebConfig(config) {
  const controls = getControlElements();
  if (!controls || !config) return;
  controls.days.value = String(config.days ?? 7);
  controls.storeFilter.value = String(config.store_filter ?? '');
  controls.limitCampaigns.value = String(config.limit_campaigns ?? 0);
  controls.maxWorkers.value = String(config.max_workers ?? 4);
  controls.includeDetails.checked = Boolean(config.include_details);
  controls.keepHistory.checked = Boolean(config.keep_history);
  controls.writeDb.checked = true;
  controls.dbPath.value = String(config.db_path ?? '');
  syncStoreSelectWithFilter();
  uiState.storeCode = controls.storeSelect.value || uiState.storeCode;
}

function syncStoreSelectWithFilter() {
  const controls = getControlElements();
  if (!controls) return;
  const filter = (controls.storeFilter.value || '').trim();
  const options = Array.from(controls.storeSelect.options || []);
  const matched = options.find((option) => option.value === filter);
  controls.storeSelect.value = matched ? matched.value : (options[0]?.value || '');
}

function syncStoreFilterWithSelect() {
  const controls = getControlElements();
  if (!controls) return;
  controls.storeFilter.value = controls.storeSelect.value || '';
}

async function loadStoreOptions() {
  const controls = getControlElements();
  if (!controls || !isServeMode()) return;
   if (!isAuthenticated()) {
    controls.storeSelect.innerHTML = '<option value="">请先登录后台</option>';
    return;
  }
  const result = await fetchApiJson('/api/stores');
  const stores = result.stores || [];
  const current = (controls.storeFilter.value || '').trim();
  const options = stores
    .map((store) => {
      const code = String(store.store_code || '').trim();
      const name = String(store.store_name || '').trim();
      const currency = getStoreCurrency(store);
      const label = `${name || code || '未命名店铺'}${code ? ` (${code})` : ''} · ${getCurrencyTypeLabel(currency)}`;
      return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
    })
    .join('');
  controls.storeSelect.innerHTML = options;
  controls.storeFilter.value = current;
  syncStoreSelectWithFilter();
}

async function loadWebConfig() {
  const controls = getControlElements();
  if (!controls || !isServeMode()) return;
  if (!isAuthenticated()) return;
  const result = await fetchApiJson('/api/config');
  applyWebConfig(result.config || {});
}

async function saveWebConfig() {
  const controls = getControlElements();
  if (!controls || !isServeMode()) return;
  const result = await postApiJson('/api/config', readWebConfig());
  applyWebConfig(result.config || {});
}

function getProbeOutputElement() {
  return document.getElementById('probe-output');
}

function formatProbeSummary(probe) {
  if (!probe) return '暂无探测结果。';
  const checks = probe.checks || {};
  const campaigns = checks.campaigns || {};
  const prices = checks.prices || {};
  const warehouses = checks.warehouses || {};
  const postings = checks.postings || {};
  const unfulfilled = checks.unfulfilled || {};
  const warnings = probe.warnings || [];
  const errors = probe.errors || [];
  return [
    `店铺: ${probe.store_name || '-'} (${probe.store_code || '-'})`,
    `状态: ${probe.status || 'unknown'} · 窗口: ${probe.date_from || '-'} ~ ${probe.date_to || '-'}`,
    `广告活动: 总 ${whole(campaigns.total_count)} / SKU ${whole(campaigns.sku_count)}`,
    `价格: 样本 ${whole(prices.sample_count)} / 无价 ${whole(prices.no_price_count)} / 折扣 ${whole(prices.discounted_count)}`,
    `仓库: 总 ${whole(warehouses.count)} / 正常 ${whole(warehouses.active_count)} / 异常 ${whole(warehouses.inactive_count)}`,
    `订单: 样本 ${whole(postings.sample_count)} / 待履约 ${whole(unfulfilled.count)}`,
    warnings.length ? `告警: ${warnings.map((x) => `${x.module}:${x.warning}`).join(' | ')}` : '告警: 无',
    errors.length ? `错误: ${errors.map((x) => `${x.module}:${x.error}`).join(' | ')}` : '错误: 无',
  ].join(' | ');
}

function renderProbeResult(probe) {
  const el = getProbeOutputElement();
  if (!el) return;
  el.textContent = formatProbeSummary(probe);
}

async function loadLatestProbe() {
  if (!isServeMode()) return;
  if (!isAuthenticated()) return;
  const res = await fetchApiJson('/api/ozon/probe/latest');
  renderProbeResult(res.probe || null);
}

async function runOzonProbe() {
  const probeBtn = document.getElementById('probe-btn');
  if (!probeBtn) return;
  probeBtn.disabled = true;
  try {
    setStatus('正在执行 Ozon 实时探测...');
    const cfg = readWebConfig();
    const result = await postApiJson('/api/ozon/probe', {
      store_filter: cfg.store_filter || '',
      days: cfg.days || 7,
      request_timeout: 30,
    });
    renderProbeResult(result.probe || null);
    setStatus(`探测完成：${(result.probe || {}).status || 'ok'}`);
  } catch (error) {
    setStatus(`探测失败：${error.message}`);
  } finally {
    probeBtn.disabled = false;
  }
}

async function refreshData() {
  const btn = document.getElementById('refresh-btn');
  if (!btn) return;
  btn.disabled = true;
  try {
    setStatus('正在刷新看板数据...');
    const response = await fetch('/api/refresh?save=1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(readWebConfig()),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);

    if (result.status === 'accepted') {
      const jobId = result.job_id || ((result.job || {}).id);
      if (!jobId) throw new Error('刷新任务缺少 job_id');
      const finishedJob = await pollRefreshJob(jobId, {
        onProgress: (status, elapsedSeconds) => {
          setStatus(`刷新任务执行中（${status}，${elapsedSeconds}秒）...`);
        },
      });
      await reloadLatestData();
      const generatedAt = ((finishedJob.result || {}).generated_at) || '-';
      setStatus(`刷新完成：${generatedAt}`);
      return;
    }

    if (result.status !== 'ok') {
      throw new Error(result.error || `刷新状态异常：${result.status || 'unknown'}`);
    }

    await reloadLatestData();
    setStatus(`刷新完成：${result.generated_at || '-'}`);
  } catch (error) {
    setStatus(`刷新失败：${error.message}`);
  } finally {
    btn.disabled = false;
  }
}

const storesSelect = document.getElementById('stores-select');
const sortSelect = document.getElementById('sort-select');
if (storesSelect) {
  storesSelect.addEventListener('change', (event) => {
    uiState.storeCode = event.target.value || '';
    uiState.focusedModuleKey = '';
    renderDashboard(payload);
  });
}
if (sortSelect) {
  sortSelect.addEventListener('change', (event) => {
    uiState.sort = event.target.value || 'health-asc';
    renderStoreSwitcher(payload);
    renderStores(payload);
    renderDataOps(payload);
  });
}

document.getElementById('refresh-btn').addEventListener('click', refreshData);
document.getElementById('reload-btn').addEventListener('click', reloadLatestData);

const controls = getControlElements();
if (controls) {
  controls.storeSelect.addEventListener('change', () => {
    syncStoreFilterWithSelect();
  });
}

const saveConfigBtn = document.getElementById('save-config-btn');
const probeBtn = document.getElementById('probe-btn');
const exportActionsCsvBtn = document.getElementById('export-actions-csv-btn');
const exportActionsJsonBtn = document.getElementById('export-actions-json-btn');
const expandAllBtn = document.getElementById('expand-all-btn');
const expandRiskBtn = document.getElementById('expand-risk-btn');
const collapseAllBtn = document.getElementById('collapse-all-btn');
const adminWorkspaceToggle = document.getElementById('admin-workspace-toggle');
if (saveConfigBtn) {
  saveConfigBtn.addEventListener('click', async () => {
    try {
      saveConfigBtn.disabled = true;
      await saveWebConfig();
      setStatus('页面配置已保存。');
    } catch (error) {
      setStatus(`保存配置失败：${error.message}`);
    } finally {
      saveConfigBtn.disabled = false;
    }
  });
}
if (probeBtn) {
  probeBtn.addEventListener('click', runOzonProbe);
}
if (exportActionsCsvBtn) {
  exportActionsCsvBtn.addEventListener('click', () => exportActionList('csv'));
}
if (exportActionsJsonBtn) {
  exportActionsJsonBtn.addEventListener('click', () => exportActionList('json'));
}
if (expandAllBtn) {
  expandAllBtn.addEventListener('click', () => expandCurrentStores('all'));
}
if (expandRiskBtn) {
  expandRiskBtn.addEventListener('click', () => expandCurrentStores('risk'));
}
if (collapseAllBtn) {
  collapseAllBtn.addEventListener('click', () => expandCurrentStores('collapse'));
}
if (adminWorkspaceToggle) {
  adminWorkspaceToggle.addEventListener('click', () => {
    uiState.adminWorkspaceOpen = !uiState.adminWorkspaceOpen;
    renderAdminWorkspaceState();
  });
}

if (!isServeMode()) {
  updateProtectedUiState();
  setStatus('当前为静态模式。请使用 --serve 启动以启用刷新和接口诊断。');
}

renderDashboard(payload);
Promise.all([
  loadAuthStatus(),
  reloadLatestData({ silent: true }).catch(() => null),
]).then(() => refreshAdminPanels()).catch((error) => setStatus(`初始化失败：${error.message}`));
