const nf = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 });
const intf = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
const MODULE_DEFINITIONS = [
  ['sales', '销售模块'],
  ['ads', '广告模块'],
  ['orders', '订单模块'],
  ['pricing', '价格模块'],
  ['logistics', '物流模块'],
  ['sku_risk', 'SKU 风险模块'],
];

const money = (value) => nf.format(Number(value || 0));
const whole = (value) => intf.format(Number(value || 0));
const pct = (value) => `${nf.format(Number(value || 0))}%`;

function getStoreCurrency(item) {
  return String(item?.currency || '').trim().toUpperCase() || 'CNY';
}

function getCurrencyTypeLabel(currency) {
  return ['USD'].includes(currency) ? '美金店铺' : '人民币店铺';
}

function getRmbRate(currency, item) {
  const rate = Number(item?.exchange_rate_to_cny);
  if (Number.isFinite(rate) && rate > 0) return rate;
  const code = String(currency || '').trim().toUpperCase();
  if (['CNY', 'RMB', 'CNH'].includes(code)) return 1;
  if (code === 'USD') return 7.2;
  return 1;
}

function toRmb(value, item) {
  return Number(value || 0) * getRmbRate(getStoreCurrency(item), item);
}

function moneyRmb(value, item) {
  return `¥${money(toRmb(value, item))}`;
}

function moneySummary(value) {
  return `¥${money(Number(value || 0))}`;
}

function moneySummaryWithSource(value, currency) {
  const current = String(currency || '').trim().toUpperCase();
  if (!current || ['CNY', 'RMB', 'CNH'].includes(current)) {
    return moneySummary(value);
  }
  return `¥${money(Number(value || 0))}（原币 ${current}）`;
}

function getModuleLabel(moduleKey) {
  const match = MODULE_DEFINITIONS.find(([key]) => key === moduleKey);
  return match ? match[1] : moduleKey || 'unknown';
}

function getModuleKeyByLabel(moduleLabel) {
  const normalized = String(moduleLabel || '').trim();
  const exact = MODULE_DEFINITIONS.find(([key, name]) => key === normalized || name === normalized);
  if (exact) return exact[0];
  const partial = MODULE_DEFINITIONS.find(([, name]) => normalized && name.includes(normalized));
  return partial ? partial[0] : '';
}

function getUiLabelMap() {
  return {
    all: '全部关注',
    risk: '只看风险',
    warnings: '只看告警',
    errors: '只看错误',
    ads: '广告异常',
    sku: 'SKU 风险',
  };
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeSelectorValue(value) {
  if (window.CSS && typeof window.CSS.escape === 'function') {
    return window.CSS.escape(String(value ?? ''));
  }
  return String(value ?? '').replace(/[^a-zA-Z0-9_-]/g, '\\$&');
}
