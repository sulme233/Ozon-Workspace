from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict

from ozon_db import bootstrap_admin_user, count_admin_users, write_admin_audit_log


SESSION_COOKIE_NAME = 'ozon_dashboard_session'


def cookie_max_age_seconds(hours: int) -> int:
    return max(int(hours or 24), 1) * 3600


def env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name) or '').strip().lower()
    if not raw:
        return default
    return raw in {'1', 'true', 'yes', 'y', 'on'}


def env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def parse_cookies(cookie_header: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in str(cookie_header or '').split(';'):
        chunk = part.strip()
        if not chunk or '=' not in chunk:
            continue
        key, value = chunk.split('=', 1)
        cookies[key.strip()] = value.strip()
    return cookies


def get_admin_bootstrap_status(*, db_path: str) -> Dict[str, Any]:
    has_admin = count_admin_users(db_path=db_path) > 0
    env_username = str(os.environ.get('OZON_ADMIN_USERNAME') or '').strip()
    env_password = str(os.environ.get('OZON_ADMIN_PASSWORD') or '').strip()
    return {
        'enabled': True,
        'has_admin_user': has_admin,
        'can_bootstrap': not has_admin,
        'env_bootstrap_ready': bool(env_username and env_password),
    }


def bootstrap_admin_from_env_if_needed(*, db_path: str) -> Dict[str, Any]:
    status = get_admin_bootstrap_status(db_path=db_path)
    if status['has_admin_user']:
        return {'status': 'skipped', 'reason': 'admin_exists'}
    username = str(os.environ.get('OZON_ADMIN_USERNAME') or '').strip()
    password = str(os.environ.get('OZON_ADMIN_PASSWORD') or '')
    if not username or not password:
        return {'status': 'skipped', 'reason': 'env_missing'}
    user = bootstrap_admin_user(username, password, db_path=db_path)
    write_admin_audit_log(
        'auth.bootstrap.env',
        actor_username=user['username'],
        target_type='admin_user',
        target_id=user['username'],
        detail={'source': 'environment'},
        db_path=db_path,
    )
    return {'status': 'ok', 'user': user}


def get_client_ip(headers: Any, client_address: Any) -> str:
    forwarded = str(headers.get('X-Forwarded-For') or '').strip() if headers else ''
    if forwarded:
        return forwarded.split(',', 1)[0].strip()
    real_ip = str(headers.get('X-Real-IP') or '').strip() if headers else ''
    if real_ip:
        return real_ip
    try:
        return str(client_address[0] if client_address else '')
    except Exception:
        return ''


def is_login_rate_limited(refresh_state: Dict[str, Any], key: str) -> bool:
    now_ts = dt.datetime.now(dt.UTC).timestamp()
    window_seconds = int(refresh_state.get('login_rate_window_seconds') or 300)
    max_attempts = int(refresh_state.get('login_rate_max_attempts') or 8)
    with refresh_state['auth_lock']:
        attempts = [ts for ts in refresh_state['login_failures'].get(key, []) if now_ts - float(ts) <= window_seconds]
        refresh_state['login_failures'][key] = attempts
        return len(attempts) >= max_attempts


def record_login_failure(refresh_state: Dict[str, Any], key: str) -> None:
    now_ts = dt.datetime.now(dt.UTC).timestamp()
    window_seconds = int(refresh_state.get('login_rate_window_seconds') or 300)
    with refresh_state['auth_lock']:
        attempts = [ts for ts in refresh_state['login_failures'].get(key, []) if now_ts - float(ts) <= window_seconds]
        attempts.append(now_ts)
        refresh_state['login_failures'][key] = attempts


def clear_login_failures(refresh_state: Dict[str, Any], key: str) -> None:
    with refresh_state['auth_lock']:
        refresh_state['login_failures'].pop(key, None)
