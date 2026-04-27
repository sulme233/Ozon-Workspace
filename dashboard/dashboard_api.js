async function fetchApiJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

async function postApiJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

async function fetchLatestPayloadFromDb() {
  const response = await fetchApiJson('/api/dashboard/latest');
  if (!response || response.status !== 'ok' || !response.payload) {
    throw new Error('SQLite 中暂无可用快照');
  }
  return response.payload;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollRefreshJob(
  jobId,
  { timeoutMs = 15 * 60 * 1000, intervalMs = 2000, onProgress = null } = {},
) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const statusRes = await fetchApiJson(`/api/refresh/status?job_id=${encodeURIComponent(jobId)}`);
    const job = statusRes.job || {};
    const status = job.status || 'unknown';
    if (status === 'ok') return job;
    if (status === 'error') throw new Error(job.error || '刷新失败');
    if (typeof onProgress === 'function') {
      onProgress(status, Math.round((Date.now() - started) / 1000), job);
    }
    await sleep(intervalMs);
  }
  throw new Error('刷新任务超时');
}
