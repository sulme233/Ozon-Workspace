from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List

from ozon_db import DEFAULT_DB_PATH, ensure_db


def refresh_job_view(job: Dict[str, Any]) -> Dict[str, Any]:
    result = job.get('result') if isinstance(job, dict) else None
    result_preview = None
    if isinstance(result, dict):
        result_preview = {
            'status': result.get('status'),
            'store_count': result.get('store_count'),
            'generated_at': result.get('generated_at'),
            'snapshot_id': result.get('snapshot_id'),
        }
    return {
        'id': str(job.get('id', '')),
        'status': str(job.get('status', 'unknown')),
        'created_at': str(job.get('created_at', '')),
        'started_at': job.get('started_at'),
        'finished_at': job.get('finished_at'),
        'error': job.get('error'),
        'result': result_preview,
    }


def get_refresh_job(refresh_state: Dict[str, Any], job_id: str) -> Dict[str, Any] | None:
    with refresh_state['jobs_lock']:
        job = refresh_state['refresh_jobs'].get(job_id)
        return refresh_job_view(job) if isinstance(job, dict) else None


def get_latest_refresh_job(refresh_state: Dict[str, Any]) -> Dict[str, Any] | None:
    with refresh_state['jobs_lock']:
        latest_job_id = refresh_state.get('latest_refresh_job_id')
        if not latest_job_id:
            return None
        job = refresh_state['refresh_jobs'].get(latest_job_id)
        return refresh_job_view(job) if isinstance(job, dict) else None


def trim_refresh_jobs(refresh_state: Dict[str, Any]) -> None:
    max_jobs = int(refresh_state.get('max_refresh_jobs') or 20)
    order: List[str] = refresh_state['refresh_job_order']
    jobs: Dict[str, Dict[str, Any]] = refresh_state['refresh_jobs']
    latest_id = refresh_state.get('latest_refresh_job_id')
    if len(order) <= max_jobs:
        return

    idx = 0
    while len(order) > max_jobs and idx < len(order):
        job_id = order[idx]
        job = jobs.get(job_id) or {}
        status = str(job.get('status', ''))
        if status in {'queued', 'running'} or job_id == latest_id:
            idx += 1
            continue
        order.pop(idx)
        jobs.pop(job_id, None)


def get_refresh_config_snapshot(refresh_state: Dict[str, Any]) -> Dict[str, Any]:
    with refresh_state['config_lock']:
        return {
            'days': int(refresh_state['days']),
            'store_filter': str(refresh_state['store_filter'] or ''),
            'limit_campaigns': refresh_state['limit_campaigns'],
            'max_workers': int(refresh_state['max_workers']),
            'include_details': bool(refresh_state['include_details']),
            'keep_history': bool(refresh_state['keep_history']),
            'write_db': bool(refresh_state['write_db']),
            'db_path': str(refresh_state['db_path']),
        }


def refresh_config_view(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'days': int(config.get('days') or 7),
        'store_filter': str(config.get('store_filter') or ''),
        'limit_campaigns': int(config.get('limit_campaigns') or 0),
        'max_workers': int(config.get('max_workers') or 4),
        'include_details': bool(config.get('include_details')),
        'keep_history': bool(config.get('keep_history')),
        'write_db': bool(config.get('write_db')),
        'db_path': str(config.get('db_path') or ''),
    }


def resolve_refresh_config(refresh_state: Dict[str, Any], config_overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    config = get_refresh_config_snapshot(refresh_state)
    if config_overrides:
        config.update(config_overrides)
    config['db_path'] = str(Path(str(config.get('db_path') or DEFAULT_DB_PATH)).expanduser())
    if bool(config.get('write_db')):
        config['db_path'] = ensure_db(config['db_path'])
    return config


def update_refresh_defaults(refresh_state: Dict[str, Any], config_update: Dict[str, Any]) -> Dict[str, Any]:
    with refresh_state['config_lock']:
        for key, value in config_update.items():
            refresh_state[key] = value

        refresh_state['db_path'] = str(Path(str(refresh_state.get('db_path') or DEFAULT_DB_PATH)).expanduser())
        if bool(refresh_state.get('write_db')):
            refresh_state['db_path'] = ensure_db(refresh_state['db_path'])

        return {
            'days': int(refresh_state['days']),
            'store_filter': str(refresh_state['store_filter'] or ''),
            'limit_campaigns': refresh_state['limit_campaigns'],
            'max_workers': int(refresh_state['max_workers']),
            'include_details': bool(refresh_state['include_details']),
            'keep_history': bool(refresh_state['keep_history']),
            'write_db': bool(refresh_state['write_db']),
            'db_path': str(refresh_state['db_path']),
        }


def enqueue_refresh_job_with_overrides(
    refresh_state: Dict[str, Any],
    *,
    config_overrides: Dict[str, Any] | None = None,
    refresh_dashboard_func: Callable[..., Dict[str, Any]],
    now_text_func: Callable[[], str],
) -> Dict[str, Any]:
    config = resolve_refresh_config(refresh_state, config_overrides=config_overrides)

    with refresh_state['jobs_lock']:
        seq = int(refresh_state.get('refresh_job_seq') or 0) + 1
        refresh_state['refresh_job_seq'] = seq
        job_id = str(seq)
        job = {
            'id': job_id,
            'status': 'queued',
            'created_at': now_text_func(),
            'started_at': None,
            'finished_at': None,
            'result': None,
            'error': None,
            'config': config,
        }
        refresh_state['refresh_jobs'][job_id] = job
        refresh_state['refresh_job_order'].append(job_id)
        refresh_state['latest_refresh_job_id'] = job_id
        trim_refresh_jobs(refresh_state)

    def run_job() -> None:
        with refresh_state['jobs_lock']:
            active_job = refresh_state['refresh_jobs'].get(job_id)
            if not active_job:
                return
            active_job['status'] = 'running'
            active_job['started_at'] = now_text_func()

        try:
            with refresh_state['refresh_lock']:
                job_config = dict(config)
                result = refresh_dashboard_func(
                    days=job_config['days'],
                    store_filter=job_config['store_filter'],
                    limit_campaigns=job_config['limit_campaigns'],
                    max_workers=job_config['max_workers'],
                    include_details=job_config['include_details'],
                    keep_history=job_config['keep_history'],
                    write_db=job_config['write_db'],
                    db_path=job_config['db_path'],
                )
            with refresh_state['jobs_lock']:
                active_job = refresh_state['refresh_jobs'].get(job_id)
                if not active_job:
                    return
                active_job['status'] = 'ok'
                active_job['result'] = result
                active_job['error'] = None
                active_job['finished_at'] = now_text_func()
                refresh_state['latest_refresh_job_id'] = job_id
                trim_refresh_jobs(refresh_state)
        except Exception as exc:
            with refresh_state['jobs_lock']:
                active_job = refresh_state['refresh_jobs'].get(job_id)
                if not active_job:
                    return
                active_job['status'] = 'error'
                active_job['error'] = str(exc)
                active_job['finished_at'] = now_text_func()
                refresh_state['latest_refresh_job_id'] = job_id
                trim_refresh_jobs(refresh_state)

    threading.Thread(target=run_job, name=f'dashboard-refresh-{job_id}', daemon=True).start()
    return refresh_job_view(job)
