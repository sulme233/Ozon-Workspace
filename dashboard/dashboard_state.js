const uiState = {
  query: '',
  status: 'all',
  sort: 'health-asc',
  storeCode: '',
  quickFilter: 'all',
  expandedStoreCodes: [],
  focusedModuleKey: '',
  auth: {
    authenticated: false,
    bootstrap: { has_admin_user: false, can_bootstrap: false },
    session: null,
  },
  adminStores: [],
  editingStoreCode: '',
  storeVersions: [],
  auditLogs: [],
  adminWorkspaceOpen: false,
};

function getResults(nextPayload) {
  return Array.isArray((nextPayload || {}).results) ? nextPayload.results : [];
}

function getStoreCardId(item) {
  return String(item?.store_code || item?.store_name || 'unknown').trim();
}

function findStoreByCode(nextPayload, storeCode) {
  const code = String(storeCode || '').trim();
  if (!code) return null;
  return getResults(nextPayload).find((item) => String(item?.store_code || '').trim() === code) || null;
}

function isStoreExpanded(item) {
  const id = getStoreCardId(item);
  return uiState.expandedStoreCodes.includes(id);
}

function ensureStoreExpanded(item) {
  const id = getStoreCardId(item);
  if (!id || uiState.expandedStoreCodes.includes(id)) return;
  uiState.expandedStoreCodes = [...uiState.expandedStoreCodes, id];
}

function toggleStoreExpanded(item) {
  const id = getStoreCardId(item);
  if (!id) return;
  if (uiState.expandedStoreCodes.includes(id)) {
    uiState.expandedStoreCodes = uiState.expandedStoreCodes.filter((value) => value !== id);
  } else {
    uiState.expandedStoreCodes = [...uiState.expandedStoreCodes, id];
  }
}

function sortRecords(records) {
  const next = [...records];
  const sortKey = uiState.sort;
  next.sort((a, b) => {
    if (sortKey === 'health-desc') return b.health - a.health || b.sales - a.sales;
    if (sortKey === 'sales-desc') return b.sales - a.sales || a.health - b.health;
    if (sortKey === 'risk-desc') return b.flags + b.errors - (a.flags + a.errors) || a.health - b.health;
    if (sortKey === 'ads-desc') return b.adSpend - a.adSpend || a.health - b.health;
    return a.health - b.health || b.flags + b.errors - (a.flags + a.errors);
  });
  return next;
}

function getCandidateRecords(nextPayload) {
  return sortRecords(
    getResults(nextPayload)
      .map(getStoreRecord)
      .filter((record) => {
        if (uiState.status !== 'all' && (record.item.status || 'error') !== uiState.status) {
          return false;
        }
        if (!matchesQuickFilter(record.item)) {
          return false;
        }
        return true;
      }),
  );
}

function getStoreSwitchOptions(nextPayload) {
  return getCandidateRecords(nextPayload)
    .map((record) => ({
      store_code: String(record.item.store_code || '').trim(),
      store_name: String(record.item.store_name || '').trim(),
      status: String(record.item.status || 'unknown').trim(),
      health_score: Number(record.item.health_score || 0),
      currency: getStoreCurrency(record.item),
    }))
    .filter((item) => item.store_code);
}

function ensureStoreSelection(nextPayload) {
  const options = getStoreSwitchOptions(nextPayload);
  if (!uiState.storeCode) {
    uiState.storeCode = options[0]?.store_code || '';
    return;
  }
  const exists = options.some((item) => item.store_code === uiState.storeCode);
  if (!exists) {
    uiState.storeCode = options[0]?.store_code || '';
  }
}

function filterRecords(records) {
  return records.filter((record) => {
    if (uiState.storeCode && String(record.item.store_code || '').trim() !== uiState.storeCode) {
      return false;
    }
    return true;
  });
}

function getFilteredResults(nextPayload) {
  return filterRecords(getCandidateRecords(nextPayload)).map((record) => record.item);
}

function getVisibleRecords(nextPayload) {
  return filterRecords(getCandidateRecords(nextPayload));
}

function getSelectedRecords(nextPayload) {
  const visibleRecords = getVisibleRecords(nextPayload);
  if (uiState.storeCode) {
    return visibleRecords.filter((record) => String(record.item.store_code || '').trim() === uiState.storeCode);
  }
  return visibleRecords.slice(0, 1);
}

function getExpandableRecords(nextPayload) {
  return uiState.storeCode ? getSelectedRecords(nextPayload) : getVisibleRecords(nextPayload);
}

function getActiveStoreCode(nextPayload) {
  if (uiState.storeCode) return uiState.storeCode;
  const first = getVisibleRecords(nextPayload)[0]?.item || getResults(nextPayload)[0] || {};
  return String(first.store_code || '').trim();
}

function setExpandedStoreIds(storeIds) {
  uiState.expandedStoreCodes = Array.from(new Set(storeIds.filter(Boolean)));
}
