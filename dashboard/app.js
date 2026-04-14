const embeddedPayload = JSON.parse(document.getElementById('embedded-payload').textContent);
let payload = embeddedPayload;
let dataOpsRequestId = 0;

const uiState = {
  query: '',
  status: 'all',
  sort: 'health-asc',
};

const nf = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 });
const intf = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
const money = (value) => nf.format(Number(value || 0));
const whole = (value) => intf.format(Number(value || 0));
const pct = (value) => `${nf.format(Number(value || 0))}%`;

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function statusLabel(status) {
  return (
    {
      ok: '正常',
      partial: '部分异常',
      error: '失败',
      no_campaigns: '无广告活动',
    }[status] || status || '未知'
  );
}

function statusTone(status) {
  if (status === 'ok') {
    return 'ok';
  }
  if (status === 'partial' || status === 'no_campaigns') {
    return 'partial';
  }
  return 'error';
}

function healthTone(score) {
  if (score >= 80) {
    return 'healthy';
  }
  if (score >= 55) {
    return 'watch';
  }
  return 'risk';
}

function healthBadge(score) {
  if (score >= 80) {
    return 'good-tone';
  }
  if (score >= 55) {
    return 'warn-tone';
  }
  return 'bad-tone';
}

function setStatus(message) {
  document.getElementById('status-line').textContent = message;
}

function getSkuPreview(item) {
  const skuRisk = item.sku_risk || {};
  return skuRisk.sku_risks_preview || skuRisk.sku_risks || [];
}

function getAdAlerts(item) {
  const ads = item.ads || {};
  return ads.alerts || [];
}

function getLogisticsNotes(item) {
  const logistics = item.logistics || {};
  const summary = logistics.summary || {};
  return summary.stock_health_notes || [];
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

function getStoreRecord(item) {
  const overview = item.overview || {};
  return {
    item,
    search: getStoreSearchText(item),
    health: Number(item.health_score || 0),
    sales: Number(overview.sales_amount || 0),
    adSpend: Number(overview.ad_expense_rub || 0),
    flags: (item.flags || []).length,
    errors: (item.errors || []).length,
  };
}

function sortRecords(records) {
  const next = [...records];
  const sortKey = uiState.sort;
  next.sort((a, b) => {
    if (sortKey === 'health-desc') {
      return b.health - a.health || b.sales - a.sales;
    }
    if (sortKey === 'sales-desc') {
      return b.sales - a.sales || a.health - b.health;
    }
    if (sortKey === 'risk-desc') {
      return b.flags + b.errors - (a.flags + a.errors) || a.health - b.health;
    }
    if (sortKey === 'ads-desc') {
      return b.adSpend - a.adSpend || a.health - b.health;
    }
    return a.health - b.health || b.flags + b.errors - (a.flags + a.errors);
  });
  return next;
}

function filterRecords(records) {
  const query = uiState.query.trim().toLowerCase();
  return records.filter((record) => {
    if (uiState.status !== 'all' && (record.item.status || 'error') !== uiState.status) {
      return false;
    }
    if (!query) {
      return true;
    }
    return record.search.includes(query);
  });
}

function renderHero(nextPayload) {
  const summary = nextPayload.summary || {};
  const refreshInfo = nextPayload.refresh_info || {};

  document.getElementById('hero-desc').textContent =
    `统计周期 ${nextPayload.days || 0} 天，店铺筛选：${nextPayload.store_filter || '全部'}，生成时间：${nextPayload.generated_at || '-'}`;

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
    ['近周期销售额', money(summary.total_sales_amount), `共 ${summary.store_count || 0} 家店铺，正常 ${summary.ok_count || 0} 家`],
    ['广告花费', money(summary.total_ad_expense_rub), `广告销售额 ${money(summary.total_ad_revenue_rub)}，整体 ROAS ${money(summary.overall_roas)}`],
    ['履约关注', whole(summary.total_unfulfilled_orders), `低库存仓库 ${whole(summary.total_low_stock_warehouses)} 个`],
    ['价格风险', whole(summary.total_no_price_items), `风险 SKU ${whole(summary.total_risky_skus)} 个`],
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
    `最近刷新：${refreshInfo.generated_at || nextPayload.generated_at || '-'}；数据文件：${refreshInfo.latest_json || '-'}。`;
}

function renderAttention(nextPayload) {
  const results = nextPayload.results || [];
  const records = sortRecords(results.map(getStoreRecord));
  const topRiskStores = records.slice(0, 5);
  const topAdStores = [...records]
    .filter((record) => record.adSpend > 0 || getAdAlerts(record.item).length > 0)
    .sort((a, b) => getAdAlerts(b.item).length - getAdAlerts(a.item).length || b.adSpend - a.adSpend)
    .slice(0, 5);
  const errorRows = results
    .flatMap((item) =>
      (item.errors || []).map((error) => ({
        store_name: item.store_name,
        store_code: item.store_code,
        module: error.module || 'unknown',
        error: error.error || '',
      })),
    )
    .slice(0, 6);

  const panels = [
    {
      title: '重点店铺',
      desc: '优先看健康分低、风险标记多的店铺。',
      body: topRiskStores.length
        ? `<div class="list">${topRiskStores
            .map(
              (record) => `
                <div class="list-item">
                  <strong>${escapeHtml(record.item.store_name || '-')} <span class="muted">${escapeHtml(record.item.store_code || '')}</span></strong>
                  <span>健康分 ${record.health}，风险 ${record.flags} 项，错误 ${record.errors} 个，销售额 ${money(record.sales)}</span>
                </div>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">当前没有可展示的重点店铺。</div>',
    },
    {
      title: '广告机会',
      desc: '广告花费高、告警多的店铺会排在前面。',
      body: topAdStores.length
        ? `<div class="list">${topAdStores
            .map((record) => {
              const alerts = getAdAlerts(record.item);
              const overview = record.item.overview || {};
              return `
                <div class="list-item">
                  <strong>${escapeHtml(record.item.store_name || '-')}</strong>
                  <span>广告花费 ${money(overview.ad_expense_rub)}，ROAS ${money(overview.ad_roas)}，告警 ${alerts.length} 条</span>
                </div>
              `;
            })
            .join('')}</div>`
        : '<div class="empty">当前没有广告异常或投放样本。</div>',
    },
    {
      title: '模块报错',
      desc: '接口异常会直接影响页面可信度，建议先修这一层。',
      body: errorRows.length
        ? `<div class="list">${errorRows
            .map(
              (row) => `
                <div class="list-item">
                  <strong>${escapeHtml(row.store_name || '-')} · ${escapeHtml(row.module)}</strong>
                  <small>${escapeHtml(row.error)}</small>
                </div>
              `,
            )
            .join('')}</div>`
        : '<div class="empty">当前没有模块报错。</div>',
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
}

async function fetchApiJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function renderDataOps(nextPayload) {
  const container = document.getElementById('data-grid');
  if (!container) {
    return;
  }

  if (location.protocol === 'file:') {
    container.innerHTML = `
      <article class="board-card">
        <div class="board-head">
          <div>
            <h2>Data & API</h2>
            <p>Backend API panels are available in serve mode.</p>
          </div>
        </div>
        <div class="empty">Run with --serve to enable snapshot/database/API diagnostics.</div>
      </article>
    `;
    return;
  }

  const requestId = ++dataOpsRequestId;
  const firstStoreCode = ((nextPayload.results || [])[0] || {}).store_code || '';
  const trendUrl = firstStoreCode
    ? `/api/stores/trend?store_code=${encodeURIComponent(firstStoreCode)}&limit=10`
    : '/api/stores/trend?store_code=&limit=10';

  container.innerHTML = `
    <article class="board-card">
      <div class="board-head">
        <div>
          <h2>Snapshot History</h2>
          <p>Loading recent database snapshots...</p>
        </div>
      </div>
    </article>
    <article class="board-card">
      <div class="board-head">
        <div>
          <h2>Store Trend</h2>
          <p>Loading trend for ${escapeHtml(firstStoreCode || 'N/A')}...</p>
        </div>
      </div>
    </article>
    <article class="board-card">
      <div class="board-head">
        <div>
          <h2>Ozon API Coverage</h2>
          <p>Loading mapped endpoints...</p>
        </div>
      </div>
    </article>
  `;

  Promise.all([
    fetchApiJson('/api/snapshots?limit=6'),
    firstStoreCode ? fetchApiJson(trendUrl) : Promise.resolve({ status: 'ok', points: [] }),
    fetchApiJson('/api/ozon-api/catalog?group=all'),
  ])
    .then(([snapshotsRes, trendRes, catalogRes]) => {
      if (requestId !== dataOpsRequestId) {
        return;
      }
      const snapshots = snapshotsRes.snapshots || [];
      const points = trendRes.points || [];
      const catalog = (catalogRes.catalog || {});
      const endpoints = catalog.endpoints || [];
      const currentCount = (catalog.counts || {}).current || 0;
      const plannedCount = (catalog.counts || {}).planned || 0;

      const snapshotBody = snapshots.length
        ? `<div class="list">${snapshots
            .map((item) => `
              <div class="list-item">
                <strong>${escapeHtml(item.generated_at || '-')}</strong>
                <span>Stores ${whole((item.summary || {}).store_count)} | Sales ${money((item.summary || {}).total_sales_amount)} | Ads ${money((item.summary || {}).total_ad_expense_rub)}</span>
              </div>
            `)
            .join('')}</div>`
        : '<div class="empty">No snapshots in database yet.</div>';

      const trendBody = points.length
        ? `<div class="list">${points
            .map((item) => `
              <div class="list-item">
                <strong>${escapeHtml(item.generated_at || '-')}</strong>
                <span>Health ${whole(item.health_score)} | Sales ${money(item.sales_amount)} | Ad ROAS ${money(item.ad_roas)} | Risk SKU ${whole(item.risky_sku_count)}</span>
              </div>
            `)
            .join('')}</div>`
        : `<div class="empty">No trend data for ${escapeHtml(firstStoreCode || 'N/A')}.</div>`;

      const endpointPreview = endpoints.slice(0, 8);
      const catalogBody = endpointPreview.length
        ? `<div class="list">${endpointPreview
            .map((item) => `
              <div class="list-item">
                <strong>${escapeHtml(item.method || '')} ${escapeHtml(item.path || '')}</strong>
                <span>${escapeHtml(item.description || '')} (${escapeHtml(item.group || '-')})</span>
              </div>
            `)
            .join('')}</div>`
        : '<div class="empty">API catalog is empty.</div>';

      container.innerHTML = `
        <article class="board-card">
          <div class="board-head">
            <div>
              <h2>Snapshot History</h2>
              <p>Latest persisted runs from SQLite.</p>
            </div>
          </div>
          ${snapshotBody}
        </article>
        <article class="board-card">
          <div class="board-head">
            <div>
              <h2>Store Trend</h2>
              <p>Rolling points for ${escapeHtml(firstStoreCode || 'N/A')}.</p>
            </div>
          </div>
          ${trendBody}
        </article>
        <article class="board-card">
          <div class="board-head">
            <div>
              <h2>Ozon API Coverage</h2>
              <p>Current ${whole(currentCount)} | Planned ${whole(plannedCount)} | Total ${whole(catalog.total_count || 0)}</p>
            </div>
          </div>
          ${catalogBody}
        </article>
      `;
    })
    .catch((error) => {
      if (requestId !== dataOpsRequestId) {
        return;
      }
      container.innerHTML = `
        <article class="board-card">
          <div class="board-head">
            <div>
              <h2>Data & API</h2>
              <p>Failed to load backend diagnostics.</p>
            </div>
          </div>
          <div class="empty">${escapeHtml(error.message || 'Unknown error')}</div>
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

  document.getElementById('status-filter-group').innerHTML = buttons
    .map(
      (button) => `
        <button class="btn filter ${uiState.status === button.id ? 'active' : ''}" data-status="${button.id}" type="button">
          ${escapeHtml(button.label)} · ${escapeHtml(button.count)}
        </button>
      `,
    )
    .join('');

  document.querySelectorAll('[data-status]').forEach((button) => {
    button.addEventListener('click', () => {
      uiState.status = button.getAttribute('data-status') || 'all';
      renderStores(payload);
      renderStatusFilters(payload);
    });
  });
}

function renderModuleCards(item) {
  const overview = item.overview || {};
  const adsSummary = (item.ads || {}).summary || {};
  const ordersSummary = (item.orders || {}).summary || {};
  const pricingSummary = (item.pricing || {}).summary || {};
  const logisticsSummary = (item.logistics || {}).summary || {};
  const skuRiskSummary = (item.sku_risk || {}).summary || {};
  const salesSummary = (item.sales || {}).summary || {};

  const cards = [
    {
      title: '销售',
      status: item.sales ? statusLabel(item.sales.status) : '未返回',
      meta: `销售额 ${money(overview.sales_amount)} · 订单估算 ${whole(salesSummary.orders_count_estimated || 0)}`,
    },
    {
      title: '广告',
      status: item.ads ? statusLabel(item.ads.status) : '未返回',
      meta: `花费 ${money(overview.ad_expense_rub)} · ROAS ${money(overview.ad_roas)} · 活动 ${whole(adsSummary.campaign_count || 0)}`,
    },
    {
      title: '订单',
      status: item.orders ? statusLabel(item.orders.status) : '未返回',
      meta: `待履约 ${whole(overview.unfulfilled_orders_count)} · 待发运 ${whole(overview.awaiting_deliver_count)} · 发货关注 ${whole(ordersSummary.shipment_attention_count || 0)}`,
    },
    {
      title: '价格',
      status: item.pricing ? statusLabel(item.pricing.status) : '未返回',
      meta: `无价格 ${whole(pricingSummary.no_price_count || 0)} · 大折扣 ${whole(pricingSummary.deep_discount_count || 0)}`,
    },
    {
      title: '库存',
      status: item.logistics ? statusLabel(item.logistics.status) : '未返回',
      meta: `仓库 ${whole(logisticsSummary.warehouse_count || 0)} · 空库存 ${whole(logisticsSummary.empty_stock_warehouses_count || 0)} · 预留占比 ${pct(logisticsSummary.stock_reserved_ratio_pct || 0)}`,
    },
    {
      title: 'SKU 风险',
      status: item.sku_risk ? statusLabel(item.sku_risk.status) : '未返回',
      meta: `风险 SKU ${whole(skuRiskSummary.risky_sku_count || 0)} · 无库存 ${whole(skuRiskSummary.out_of_stock_sku_count || 0)}`,
    },
  ];

  return cards
    .map(
      (card) => `
        <div class="module-card">
          <strong>${escapeHtml(card.title)} · ${escapeHtml(card.status)}</strong>
          <span>${escapeHtml(card.meta)}</span>
        </div>
      `,
    )
    .join('');
}

function renderStores(nextPayload) {
  const records = sortRecords(filterRecords((nextPayload.results || []).map(getStoreRecord)));
  document.getElementById('filter-note').textContent =
    `当前显示 ${records.length} / ${(nextPayload.results || []).length} 家店铺。`;

  if (!records.length) {
    document.getElementById('stores').innerHTML = '<div class="empty">没有匹配当前筛选条件的店铺。</div>';
    return;
  }

  document.getElementById('stores').innerHTML = records
    .map((record) => {
      const item = record.item;
      const overview = item.overview || {};
      const flags = item.flags || [];
      const insights = item.insights || [];
      const recommendations = item.recommendations || [];
      const errors = item.errors || [];
      const skuRisks = getSkuPreview(item).slice(0, 8);
      const adAlerts = getAdAlerts(item).slice(0, 5);
      const logisticsNotes = getLogisticsNotes(item).slice(0, 5);
      const summaryText = ((item.ads || {}).summary || {}).summary_text || '';

      return `
        <article class="store-card ${healthTone(record.health)}">
          <div class="store-head">
            <div>
              <div class="store-kicker">${escapeHtml(statusLabel(item.status))} · ${escapeHtml(item.currency || '')}</div>
              <div class="store-title">
                <h3>${escapeHtml(item.store_name || '-')}</h3>
                <span>${escapeHtml(item.store_code || '')}</span>
              </div>
              <p class="store-summary">${escapeHtml(summaryText || '已聚合该店铺的销售、广告、订单、价格、库存与 SKU 风险数据。')}</p>
              <div class="badges" style="margin-top:12px;">
                <span class="badge ${statusTone(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
                <span class="badge ${healthBadge(record.health)}">健康分 ${escapeHtml(record.health)}</span>
                <span class="badge">风险标记 ${escapeHtml(flags.length)}</span>
                <span class="badge">模块错误 ${escapeHtml(errors.length)}</span>
              </div>
            </div>
            <div class="store-health">
              <div class="score-line">
                <div>
                  <div class="caption">Health Score</div>
                  <div class="score">${escapeHtml(record.health)}</div>
                </div>
                <div class="caption">${escapeHtml(record.health >= 80 ? '稳定' : record.health >= 55 ? '观察' : '优先处理')}</div>
              </div>
              <div class="health-bar"><span style="width:${Math.max(0, Math.min(record.health, 100))}%;"></span></div>
            </div>
          </div>

          <section class="store-metrics">
            <div class="mini-panel">
              <div class="label">销售额</div>
              <div class="value">${money(overview.sales_amount)}</div>
              <div class="sub">退款 ${money(overview.refund_amount)} · 服务费 ${money(overview.service_amount)}</div>
            </div>
            <div class="mini-panel">
              <div class="label">广告花费</div>
              <div class="value">${money(overview.ad_expense_rub)}</div>
              <div class="sub">广告销售额 ${money(overview.ad_revenue_rub)} · ROAS ${money(overview.ad_roas)}</div>
            </div>
            <div class="mini-panel">
              <div class="label">履约链路</div>
              <div class="value">${whole(overview.unfulfilled_orders_count)}</div>
              <div class="sub">待包装 ${whole(overview.awaiting_packaging_count)} · 待发运 ${whole(overview.awaiting_deliver_count)}</div>
            </div>
            <div class="mini-panel">
              <div class="label">价格风险</div>
              <div class="value">${whole(overview.no_price_count)}</div>
              <div class="sub">大折扣 ${whole(overview.deep_discount_count)} · 低毛利候选 ${whole(overview.low_margin_candidates_count)}</div>
            </div>
            <div class="mini-panel">
              <div class="label">仓库样本</div>
              <div class="value">${whole(overview.warehouse_count)}</div>
              <div class="sub">空库存 ${whole(overview.empty_stock_warehouses_count)} · 预留占比 ${pct(overview.stock_reserved_ratio_pct)}</div>
            </div>
            <div class="mini-panel">
              <div class="label">风险 SKU</div>
              <div class="value">${whole(overview.risky_sku_count)}</div>
              <div class="sub">无库存 ${whole(overview.out_of_stock_sku_count)} · 低可用 ${whole(overview.low_free_stock_sku_count)}</div>
            </div>
          </section>

          <section class="store-columns">
            <div class="store-section">
              <h4>风险标签</h4>
              <div class="chips">${(flags.length ? flags : ['当前未识别到明显风险'])
                .map((flag) => `<span class="chip">${escapeHtml(flag)}</span>`)
                .join('')}</div>
            </div>
            <div class="store-section">
              <h4>模块快照</h4>
              <div class="module-grid">${renderModuleCards(item)}</div>
            </div>
            <div class="store-section">
              <h4>经营洞察</h4>
              ${insights.length ? `<ul class="bullets">${insights.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>` : '<div class="empty">暂无洞察。</div>'}
            </div>
            <div class="store-section">
              <h4>优先建议</h4>
              ${recommendations.length ? `<ul class="bullets">${recommendations.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>` : '<div class="empty">暂无建议。</div>'}
            </div>
          </section>

          <section class="detail-grid">
            <div class="store-section">
              <h4>广告告警预览</h4>
              ${adAlerts.length
                ? `
                  <div class="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>活动</th>
                          <th>花费</th>
                          <th>订单</th>
                          <th>ROAS</th>
                          <th>建议动作</th>
                        </tr>
                      </thead>
                      <tbody>
                        ${adAlerts
                          .map(
                            (row) => `
                              <tr>
                                <td>${escapeHtml(row.campaign_name || row.campaign_id || '-')}</td>
                                <td>${money(row.expense_rub)}</td>
                                <td>${whole(row.orders)}</td>
                                <td>${money(row.roas)}</td>
                                <td>${escapeHtml(row.action || '-')}</td>
                              </tr>
                            `,
                          )
                          .join('')}
                      </tbody>
                    </table>
                  </div>
                `
                : '<div class="empty">当前没有广告告警。</div>'}
            </div>

            <div class="store-section">
              <h4>SKU 风险预览</h4>
              ${skuRisks.length
                ? `
                  <div class="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>SKU</th>
                          <th>Offer</th>
                          <th>仓库</th>
                          <th>可用库存</th>
                          <th>价格</th>
                          <th>风险原因</th>
                        </tr>
                      </thead>
                      <tbody>
                        ${skuRisks
                          .map(
                            (row) => `
                              <tr>
                                <td>${escapeHtml(row.sku ?? '-')}</td>
                                <td>${escapeHtml(row.offer_id ?? '-')}</td>
                                <td>${escapeHtml(row.warehouse_name ?? '-')}</td>
                                <td>${whole(row.free_stock)}</td>
                                <td>${row.price == null ? '-' : money(row.price)}</td>
                                <td>${escapeHtml((row.reasons || []).join(' / '))}</td>
                              </tr>
                            `,
                          )
                          .join('')}
                      </tbody>
                    </table>
                  </div>
                `
                : '<div class="empty">当前没有 SKU 风险明细。</div>'}
            </div>

            <div class="store-section">
              <h4>库存与异常说明</h4>
              ${logisticsNotes.length
                ? `<ul class="bullets">${logisticsNotes.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>`
                : '<div class="empty">当前没有库存备注。</div>'}
              <h4 style="margin-top:8px;">模块错误</h4>
              ${errors.length
                ? `<ul class="bullets">${errors.map((error) => `<li>${escapeHtml((error.module || 'unknown') + ': ' + (error.error || ''))}</li>`).join('')}</ul>`
                : '<div class="empty">当前没有模块错误。</div>'}
            </div>
          </section>
        </article>
      `;
    })
    .join('');
}

function renderDashboard(nextPayload) {
  payload = nextPayload || embeddedPayload;
  renderHero(payload);
  renderAttention(payload);
  renderDataOps(payload);
  renderStatusFilters(payload);
  renderStores(payload);
}

async function reloadLatestData() {
  try {
    setStatus('正在读取本地最新快照...');
    const response = await fetch('./data/latest.json', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const nextPayload = await response.json();
    renderDashboard(nextPayload);
    setStatus(`已重新读取本地快照，时间 ${nextPayload.generated_at || '-'}`);
  } catch (error) {
    setStatus(`读取本地快照失败：${error.message}`);
  }
}

async function refreshData() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  try {
    setStatus('正在拉取最新数据并重建看板，这一步可能需要几十秒...');
    const response = await fetch('/api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const result = await response.json();
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    await reloadLatestData();
    setStatus(`刷新完成，时间 ${result.generated_at || '-'}`);
  } catch (error) {
    setStatus(`刷新失败：${error.message}`);
  } finally {
    btn.disabled = false;
  }
}

document.getElementById('stores-search').addEventListener('input', (event) => {
  uiState.query = event.target.value || '';
  renderStores(payload);
});

document.getElementById('sort-select').addEventListener('change', (event) => {
  uiState.sort = event.target.value || 'health-asc';
  renderStores(payload);
});

document.getElementById('refresh-btn').addEventListener('click', refreshData);
document.getElementById('reload-btn').addEventListener('click', reloadLatestData);

if (location.protocol === 'file:') {
  document.getElementById('refresh-btn').disabled = true;
  document.getElementById('reload-btn').disabled = true;
  setStatus('当前是静态文件模式，可直接查看嵌入快照；如需刷新数据，请使用 --serve 启动本地服务。');
}

renderDashboard(payload);
