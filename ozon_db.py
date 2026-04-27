from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sqlite3
from typing import Any, Dict, List, Optional


WORKSPACE = pathlib.Path(__file__).resolve().parent
DEFAULT_DB_PATH = pathlib.Path(os.environ.get('OZON_DB_PATH') or (WORKSPACE / 'dashboard' / 'data' / 'ozon_metrics.db'))
PASSWORD_SCHEME = 'pbkdf2_sha256'
PASSWORD_ITERATIONS = 200_000


def utc_now_text() -> str:
    return dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M:%S')


def _connect(db_path: pathlib.Path | str | None = None) -> tuple[sqlite3.Connection, pathlib.Path]:
    path = pathlib.Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    try:
        conn.execute('PRAGMA journal_mode=WAL')
    except sqlite3.DatabaseError:
        pass
    return conn, path


def ensure_db(db_path: pathlib.Path | str | None = None) -> str:
    conn, path = _connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT NOT NULL,
                days INTEGER NOT NULL,
                store_filter TEXT NOT NULL DEFAULT '',
                max_workers INTEGER NOT NULL DEFAULT 1,
                include_details INTEGER NOT NULL DEFAULT 0,
                store_count INTEGER NOT NULL DEFAULT 0,
                ok_count INTEGER NOT NULL DEFAULT 0,
                partial_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                flagged_count INTEGER NOT NULL DEFAULT 0,
                total_sales_amount REAL NOT NULL DEFAULT 0,
                total_ad_expense_rub REAL NOT NULL DEFAULT 0,
                total_ad_revenue_rub REAL NOT NULL DEFAULT 0,
                total_unfulfilled_orders INTEGER NOT NULL DEFAULT 0,
                total_no_price_items INTEGER NOT NULL DEFAULT 0,
                total_risky_skus INTEGER NOT NULL DEFAULT 0,
                avg_health_score REAL NOT NULL DEFAULT 0,
                summary_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS store_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                generated_at TEXT NOT NULL,
                store_name TEXT NOT NULL DEFAULT '',
                store_code TEXT NOT NULL DEFAULT '',
                currency TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'unknown',
                health_score INTEGER NOT NULL DEFAULT 0,
                sales_amount REAL NOT NULL DEFAULT 0,
                ad_expense_rub REAL NOT NULL DEFAULT 0,
                ad_revenue_rub REAL NOT NULL DEFAULT 0,
                ad_roas REAL NOT NULL DEFAULT 0,
                unfulfilled_orders INTEGER NOT NULL DEFAULT 0,
                no_price_count INTEGER NOT NULL DEFAULT 0,
                risky_sku_count INTEGER NOT NULL DEFAULT 0,
                flags_json TEXT NOT NULL DEFAULT '[]',
                errors_json TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_generated_at ON snapshots(generated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_store_metrics_snapshot_id ON store_metrics(snapshot_id);
            CREATE INDEX IF NOT EXISTS idx_store_metrics_store_code_time ON store_metrics(store_code, generated_at DESC);

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS admin_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                revoked_at TEXT,
                ip_address TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(user_id) REFERENCES admin_users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_username TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT '',
                target_id TEXT NOT NULL DEFAULT '',
                detail_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS store_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_name TEXT NOT NULL,
                store_code TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
                currency TEXT NOT NULL DEFAULT 'CNY',
                notes TEXT NOT NULL DEFAULT '',
                marketplace_id TEXT NOT NULL DEFAULT '',
                seller_client_id TEXT NOT NULL DEFAULT '',
                seller_api_key TEXT NOT NULL DEFAULT '',
                perf_client_id TEXT NOT NULL DEFAULT '',
                perf_client_secret TEXT NOT NULL DEFAULT '',
                source_json_synced_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS store_config_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                version INTEGER NOT NULL,
                action TEXT NOT NULL DEFAULT 'update',
                actor_username TEXT NOT NULL DEFAULT '',
                config_json TEXT NOT NULL,
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(store_code, version)
            );

            CREATE INDEX IF NOT EXISTS idx_admin_sessions_user_id ON admin_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires_at ON admin_sessions(expires_at DESC);
            CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_created_at ON admin_audit_logs(created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_store_configs_enabled ON store_configs(enabled, store_code);
            CREATE INDEX IF NOT EXISTS idx_store_config_versions_code_time ON store_config_versions(store_code, version DESC);
            """
        )
        conn.commit()
    finally:
        conn.close()
    return str(path)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()


def hash_password(password: str, *, salt: str | None = None, iterations: int = PASSWORD_ITERATIONS) -> str:
    secret = str(password or '')
    if not secret:
        raise ValueError('password cannot be empty')
    salt_text = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', secret.encode('utf-8'), salt_text.encode('utf-8'), iterations)
    return f'{PASSWORD_SCHEME}${iterations}${salt_text}${digest.hex()}'


def verify_password(password: str, password_hash: str) -> bool:
    text = str(password_hash or '').strip()
    parts = text.split('$')
    if len(parts) != 4:
        return False
    scheme, iterations_text, salt, expected = parts
    if scheme != PASSWORD_SCHEME:
        return False
    try:
        iterations = int(iterations_text)
    except Exception:
        return False
    actual = hash_password(password, salt=salt, iterations=iterations)
    return hmac.compare_digest(actual, text)


def _row_to_admin_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        'id': int(row['id']),
        'username': str(row['username']),
        'is_active': bool(row['is_active']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'last_login_at': row['last_login_at'],
    }


def count_admin_users(*, db_path: pathlib.Path | str | None = None) -> int:
    ensure_db(db_path)
    conn, _ = _connect(db_path)
    try:
        row = conn.execute('SELECT COUNT(*) AS count FROM admin_users').fetchone()
        return int((row or {})['count'] if row is not None else 0)
    finally:
        conn.close()


def create_admin_user(
    username: str,
    password: str,
    *,
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    ensure_db(db_path)
    name = str(username or '').strip()
    if not name:
        raise ValueError('username cannot be empty')
    if not str(password or ''):
        raise ValueError('password cannot be empty')
    now = utc_now_text()
    conn, _ = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO admin_users (username, password_hash, is_active, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (name, hash_password(password), now, now),
        )
        conn.commit()
        row = conn.execute(
            'SELECT id, username, is_active, created_at, updated_at, last_login_at FROM admin_users WHERE id = ?',
            (int(cursor.lastrowid),),
        ).fetchone()
        if row is None:
            raise RuntimeError('failed to reload created admin user')
        return _row_to_admin_user(row)
    finally:
        conn.close()


def list_admin_users(*, db_path: pathlib.Path | str | None = None) -> List[Dict[str, Any]]:
    ensure_db(db_path)
    conn, _ = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, username, is_active, created_at, updated_at, last_login_at
            FROM admin_users
            ORDER BY id ASC
            """
        ).fetchall()
        return [_row_to_admin_user(row) for row in rows]
    finally:
        conn.close()


def get_admin_user_by_username(
    username: str,
    *,
    db_path: pathlib.Path | str | None = None,
) -> Optional[Dict[str, Any]]:
    ensure_db(db_path)
    name = str(username or '').strip()
    if not name:
        return None
    conn, _ = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, username, is_active, created_at, updated_at, last_login_at
            FROM admin_users
            WHERE username = ? COLLATE NOCASE
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        return _row_to_admin_user(row) if row is not None else None
    finally:
        conn.close()


def set_admin_password(
    username: str,
    password: str,
    *,
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    ensure_db(db_path)
    name = str(username or '').strip()
    if not name:
        raise ValueError('username cannot be empty')
    if not str(password or ''):
        raise ValueError('password cannot be empty')
    now = utc_now_text()
    conn, _ = _connect(db_path)
    try:
        cursor = conn.execute(
            'UPDATE admin_users SET password_hash = ?, updated_at = ? WHERE username = ? COLLATE NOCASE',
            (hash_password(password), now, name),
        )
        if int(cursor.rowcount or 0) <= 0:
            raise ValueError(f'admin user not found: {name}')
        conn.commit()
        row = conn.execute(
            'SELECT id, username, is_active, created_at, updated_at, last_login_at FROM admin_users WHERE username = ? COLLATE NOCASE',
            (name,),
        ).fetchone()
        return _row_to_admin_user(row)
    finally:
        conn.close()


def set_admin_active(
    username: str,
    is_active: bool,
    *,
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    ensure_db(db_path)
    name = str(username or '').strip()
    if not name:
        raise ValueError('username cannot be empty')
    now = utc_now_text()
    conn, _ = _connect(db_path)
    try:
        cursor = conn.execute(
            'UPDATE admin_users SET is_active = ?, updated_at = ? WHERE username = ? COLLATE NOCASE',
            (1 if is_active else 0, now, name),
        )
        if int(cursor.rowcount or 0) <= 0:
            raise ValueError(f'admin user not found: {name}')
        if not is_active:
            conn.execute(
                """
                UPDATE admin_sessions
                SET revoked_at = ?
                WHERE user_id = (SELECT id FROM admin_users WHERE username = ? COLLATE NOCASE)
                  AND revoked_at IS NULL
                """,
                (now, name),
            )
        conn.commit()
        row = conn.execute(
            'SELECT id, username, is_active, created_at, updated_at, last_login_at FROM admin_users WHERE username = ? COLLATE NOCASE',
            (name,),
        ).fetchone()
        return _row_to_admin_user(row)
    finally:
        conn.close()


def revoke_admin_sessions_for_user(
    username: str,
    *,
    db_path: pathlib.Path | str | None = None,
) -> int:
    ensure_db(db_path)
    name = str(username or '').strip()
    if not name:
        raise ValueError('username cannot be empty')
    conn, _ = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            UPDATE admin_sessions
            SET revoked_at = ?
            WHERE user_id = (SELECT id FROM admin_users WHERE username = ? COLLATE NOCASE)
              AND revoked_at IS NULL
            """,
            (utc_now_text(), name),
        )
        conn.commit()
        return int(cursor.rowcount or 0)
    finally:
        conn.close()


def bootstrap_admin_user(
    username: str,
    password: str,
    *,
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    ensure_db(db_path)
    conn, _ = _connect(db_path)
    try:
        row = conn.execute('SELECT COUNT(*) AS count FROM admin_users').fetchone()
        if row is not None and int(row['count']) > 0:
            raise ValueError('admin user already exists')
    finally:
        conn.close()
    return create_admin_user(username, password, db_path=db_path)


def authenticate_admin_user(
    username: str,
    password: str,
    *,
    db_path: pathlib.Path | str | None = None,
) -> Optional[Dict[str, Any]]:
    ensure_db(db_path)
    name = str(username or '').strip()
    if not name or not str(password or ''):
        return None
    conn, _ = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, username, password_hash, is_active, created_at, updated_at, last_login_at
            FROM admin_users
            WHERE username = ? COLLATE NOCASE
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        if row is None or not bool(row['is_active']):
            return None
        if not verify_password(password, str(row['password_hash'] or '')):
            return None
        now = utc_now_text()
        conn.execute('UPDATE admin_users SET last_login_at = ?, updated_at = ? WHERE id = ?', (now, now, int(row['id'])))
        conn.commit()
        refreshed = conn.execute(
            'SELECT id, username, is_active, created_at, updated_at, last_login_at FROM admin_users WHERE id = ?',
            (int(row['id']),),
        ).fetchone()
        return _row_to_admin_user(refreshed) if refreshed is not None else None
    finally:
        conn.close()


def create_admin_session(
    user_id: int,
    *,
    ip_address: str = '',
    user_agent: str = '',
    ttl_hours: int = 24,
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    ensure_db(db_path)
    ttl = max(int(ttl_hours or 24), 1)
    now_dt = dt.datetime.now(dt.UTC)
    now = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    expires_at = (now_dt + dt.timedelta(hours=ttl)).strftime('%Y-%m-%d %H:%M:%S')
    token = secrets.token_urlsafe(32)
    token_hash = _hash_session_token(token)
    conn, _ = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO admin_sessions (user_id, token_hash, created_at, expires_at, last_seen_at, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(user_id), token_hash, now, expires_at, now, str(ip_address or ''), str(user_agent or '')),
        )
        conn.commit()
        return {
            'id': int(cursor.lastrowid),
            'token': token,
            'created_at': now,
            'expires_at': expires_at,
            'ttl_hours': ttl,
        }
    finally:
        conn.close()


def get_admin_session(
    token: str,
    *,
    touch: bool = True,
    db_path: pathlib.Path | str | None = None,
) -> Optional[Dict[str, Any]]:
    ensure_db(db_path)
    raw_token = str(token or '').strip()
    if not raw_token:
        return None
    token_hash = _hash_session_token(raw_token)
    now = utc_now_text()
    conn, _ = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT s.id, s.user_id, s.created_at, s.expires_at, s.last_seen_at, s.revoked_at,
                   u.username, u.is_active, u.created_at AS user_created_at,
                   u.updated_at AS user_updated_at, u.last_login_at
            FROM admin_sessions s
            JOIN admin_users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        if row['revoked_at']:
            return None
        if not bool(row['is_active']):
            return None
        if str(row['expires_at']) <= now:
            conn.execute('UPDATE admin_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL', (now, int(row['id'])))
            conn.commit()
            return None
        if touch:
            conn.execute('UPDATE admin_sessions SET last_seen_at = ? WHERE id = ?', (now, int(row['id'])))
            conn.commit()
        return {
            'session_id': int(row['id']),
            'user': {
                'id': int(row['user_id']),
                'username': str(row['username']),
                'is_active': bool(row['is_active']),
                'created_at': row['user_created_at'],
                'updated_at': row['user_updated_at'],
                'last_login_at': row['last_login_at'],
            },
            'created_at': row['created_at'],
            'expires_at': row['expires_at'],
            'last_seen_at': now if touch else row['last_seen_at'],
        }
    finally:
        conn.close()


def revoke_admin_session(token: str, *, db_path: pathlib.Path | str | None = None) -> bool:
    ensure_db(db_path)
    raw_token = str(token or '').strip()
    if not raw_token:
        return False
    conn, _ = _connect(db_path)
    try:
        cursor = conn.execute(
            'UPDATE admin_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL',
            (utc_now_text(), _hash_session_token(raw_token)),
        )
        conn.commit()
        return int(cursor.rowcount or 0) > 0
    finally:
        conn.close()


def write_admin_audit_log(
    action: str,
    *,
    actor_username: str = '',
    target_type: str = '',
    target_id: str = '',
    detail: Optional[Dict[str, Any]] = None,
    db_path: pathlib.Path | str | None = None,
) -> int:
    ensure_db(db_path)
    conn, _ = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO admin_audit_logs (actor_username, action, target_type, target_id, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(actor_username or '').strip(),
                str(action or '').strip(),
                str(target_type or '').strip(),
                str(target_id or '').strip(),
                json.dumps(detail or {}, ensure_ascii=False),
                utc_now_text(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_admin_audit_logs(*, limit: int = 50, db_path: pathlib.Path | str | None = None) -> List[Dict[str, Any]]:
    ensure_db(db_path)
    capped = min(max(limit, 1), 500)
    conn, _ = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, actor_username, action, target_type, target_id, detail_json, created_at
            FROM admin_audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (capped,),
        ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            try:
                detail = json.loads(row['detail_json'] or '{}')
            except Exception:
                detail = {}
            result.append(
                {
                    'id': int(row['id']),
                    'actor_username': str(row['actor_username'] or ''),
                    'action': str(row['action'] or ''),
                    'target_type': str(row['target_type'] or ''),
                    'target_id': str(row['target_id'] or ''),
                    'detail': detail,
                    'created_at': row['created_at'],
                }
            )
        return result
    finally:
        conn.close()


def _row_to_store_config(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        'id': int(row['id']),
        'store_name': str(row['store_name'] or '').strip(),
        'store_code': str(row['store_code'] or '').strip(),
        'enabled': bool(row['enabled']),
        'timezone': str(row['timezone'] or 'Asia/Shanghai').strip(),
        'currency': str(row['currency'] or 'CNY').strip().upper(),
        'notes': str(row['notes'] or '').strip(),
        'marketplace_id': str(row['marketplace_id'] or '').strip(),
        'seller_api': {
            'client_id': str(row['seller_client_id'] or '').strip(),
            'api_key': str(row['seller_api_key'] or '').strip(),
        },
        'performance_api': {
            'client_id': str(row['perf_client_id'] or '').strip(),
            'client_secret': str(row['perf_client_secret'] or '').strip(),
        },
        'source_json_synced_at': row['source_json_synced_at'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def _store_version_summary(store: Dict[str, Any]) -> Dict[str, Any]:
    seller = store.get('seller_api') or {}
    perf = store.get('performance_api') or {}
    return {
        'store_name': str(store.get('store_name') or '').strip(),
        'store_code': str(store.get('store_code') or '').strip(),
        'enabled': bool(store.get('enabled', True)),
        'timezone': str(store.get('timezone') or '').strip(),
        'currency': str(store.get('currency') or '').strip(),
        'marketplace_id': str(store.get('marketplace_id') or '').strip(),
        'has_seller_client_id': bool(str(seller.get('client_id') or '').strip()),
        'has_seller_api_key': bool(str(seller.get('api_key') or '').strip()),
        'has_perf_client_id': bool(str(perf.get('client_id') or '').strip()),
        'has_perf_client_secret': bool(str(perf.get('client_secret') or '').strip()),
    }


def _row_to_store_config_version(row: sqlite3.Row, *, include_config: bool = False) -> Dict[str, Any]:
    try:
        summary = json.loads(row['summary_json'] or '{}')
    except Exception:
        summary = {}
    item: Dict[str, Any] = {
        'id': int(row['id']),
        'store_code': str(row['store_code'] or ''),
        'version': int(row['version']),
        'action': str(row['action'] or ''),
        'actor_username': str(row['actor_username'] or ''),
        'summary': summary,
        'created_at': row['created_at'],
    }
    if include_config:
        try:
            item['config'] = json.loads(row['config_json'] or '{}')
        except Exception:
            item['config'] = {}
    return item


def create_store_config_version(
    store: Dict[str, Any],
    *,
    action: str = 'update',
    actor_username: str = '',
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    ensure_db(db_path)
    code = str(store.get('store_code') or '').strip()
    if not code:
        raise ValueError('store_code is required')
    conn, _ = _connect(db_path)
    try:
        row = conn.execute(
            'SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM store_config_versions WHERE store_code = ?',
            (code,),
        ).fetchone()
        version = int(row['next_version'] if row is not None else 1)
        cursor = conn.execute(
            """
            INSERT INTO store_config_versions (store_code, version, action, actor_username, config_json, summary_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                version,
                str(action or 'update').strip(),
                str(actor_username or '').strip(),
                json.dumps(store, ensure_ascii=False, sort_keys=True),
                json.dumps(_store_version_summary(store), ensure_ascii=False, sort_keys=True),
                utc_now_text(),
            ),
        )
        conn.commit()
        saved = conn.execute(
            """
            SELECT id, store_code, version, action, actor_username, config_json, summary_json, created_at
            FROM store_config_versions
            WHERE id = ?
            """,
            (int(cursor.lastrowid),),
        ).fetchone()
        if saved is None:
            raise RuntimeError('failed to reload store config version')
        return _row_to_store_config_version(saved, include_config=False)
    finally:
        conn.close()


def list_store_config_versions(
    store_code: str,
    *,
    limit: int = 20,
    include_config: bool = False,
    db_path: pathlib.Path | str | None = None,
) -> List[Dict[str, Any]]:
    ensure_db(db_path)
    code = str(store_code or '').strip()
    if not code:
        return []
    capped = min(max(int(limit or 20), 1), 200)
    conn, _ = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, store_code, version, action, actor_username, config_json, summary_json, created_at
            FROM store_config_versions
            WHERE store_code = ?
            ORDER BY version DESC
            LIMIT ?
            """,
            (code, capped),
        ).fetchall()
        return [_row_to_store_config_version(row, include_config=include_config) for row in rows]
    finally:
        conn.close()


def get_store_config_version(
    store_code: str,
    version: int,
    *,
    db_path: pathlib.Path | str | None = None,
) -> Optional[Dict[str, Any]]:
    ensure_db(db_path)
    code = str(store_code or '').strip()
    if not code:
        return None
    conn, _ = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, store_code, version, action, actor_username, config_json, summary_json, created_at
            FROM store_config_versions
            WHERE store_code = ? AND version = ?
            LIMIT 1
            """,
            (code, int(version)),
        ).fetchone()
        return _row_to_store_config_version(row, include_config=True) if row is not None else None
    finally:
        conn.close()


def rollback_store_config_to_version(
    store_code: str,
    version: int,
    *,
    actor_username: str = '',
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    target = get_store_config_version(store_code, version, db_path=db_path)
    if target is None:
        raise ValueError(f'store config version not found: {store_code}#{version}')
    config = target.get('config') if isinstance(target.get('config'), dict) else None
    if not config:
        raise ValueError(f'store config version is empty: {store_code}#{version}')
    restored = upsert_store_config(config, original_store_code=store_code, db_path=db_path)
    create_store_config_version(
        restored,
        action=f'rollback:{version}',
        actor_username=actor_username,
        db_path=db_path,
    )
    return restored


def list_store_configs(*, include_disabled: bool = True, db_path: pathlib.Path | str | None = None) -> List[Dict[str, Any]]:
    ensure_db(db_path)
    conn, _ = _connect(db_path)
    try:
        if include_disabled:
            rows = conn.execute(
                """
                SELECT id, store_name, store_code, enabled, timezone, currency, notes, marketplace_id,
                       seller_client_id, seller_api_key, perf_client_id, perf_client_secret,
                       source_json_synced_at, created_at, updated_at
                FROM store_configs
                ORDER BY store_code ASC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, store_name, store_code, enabled, timezone, currency, notes, marketplace_id,
                       seller_client_id, seller_api_key, perf_client_id, perf_client_secret,
                       source_json_synced_at, created_at, updated_at
                FROM store_configs
                WHERE enabled = 1
                ORDER BY store_code ASC
                """
            ).fetchall()
        return [_row_to_store_config(row) for row in rows]
    finally:
        conn.close()


def get_store_config(store_code: str, *, db_path: pathlib.Path | str | None = None) -> Optional[Dict[str, Any]]:
    ensure_db(db_path)
    code = str(store_code or '').strip()
    if not code:
        return None
    conn, _ = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, store_name, store_code, enabled, timezone, currency, notes, marketplace_id,
                   seller_client_id, seller_api_key, perf_client_id, perf_client_secret,
                   source_json_synced_at, created_at, updated_at
            FROM store_configs
            WHERE store_code = ?
            LIMIT 1
            """,
            (code,),
        ).fetchone()
        return _row_to_store_config(row) if row is not None else None
    finally:
        conn.close()


def upsert_store_config(
    store: Dict[str, Any],
    *,
    original_store_code: str = '',
    source_json_synced_at: str | None = None,
    db_path: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    ensure_db(db_path)
    current = str(original_store_code or store.get('store_code') or '').strip()
    if not current:
        raise ValueError('store_code is required')
    seller = store.get('seller_api') or {}
    perf = store.get('performance_api') or {}
    now = utc_now_text()
    conn, _ = _connect(db_path)
    try:
        existing = conn.execute('SELECT id FROM store_configs WHERE store_code = ? LIMIT 1', (current,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO store_configs (
                    store_name, store_code, enabled, timezone, currency, notes, marketplace_id,
                    seller_client_id, seller_api_key, perf_client_id, perf_client_secret,
                    source_json_synced_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(store.get('store_name') or '').strip(),
                    str(store.get('store_code') or '').strip(),
                    1 if store.get('enabled', True) else 0,
                    str(store.get('timezone') or 'Asia/Shanghai').strip(),
                    str(store.get('currency') or 'CNY').strip().upper(),
                    str(store.get('notes') or '').strip(),
                    str(store.get('marketplace_id') or '').strip(),
                    str(seller.get('client_id') or '').strip(),
                    str(seller.get('api_key') or '').strip(),
                    str(perf.get('client_id') or '').strip(),
                    str(perf.get('client_secret') or '').strip(),
                    source_json_synced_at,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE store_configs
                SET store_name = ?,
                    store_code = ?,
                    enabled = ?,
                    timezone = ?,
                    currency = ?,
                    notes = ?,
                    marketplace_id = ?,
                    seller_client_id = ?,
                    seller_api_key = ?,
                    perf_client_id = ?,
                    perf_client_secret = ?,
                    source_json_synced_at = COALESCE(?, source_json_synced_at),
                    updated_at = ?
                WHERE store_code = ?
                """,
                (
                    str(store.get('store_name') or '').strip(),
                    str(store.get('store_code') or '').strip(),
                    1 if store.get('enabled', True) else 0,
                    str(store.get('timezone') or 'Asia/Shanghai').strip(),
                    str(store.get('currency') or 'CNY').strip().upper(),
                    str(store.get('notes') or '').strip(),
                    str(store.get('marketplace_id') or '').strip(),
                    str(seller.get('client_id') or '').strip(),
                    str(seller.get('api_key') or '').strip(),
                    str(perf.get('client_id') or '').strip(),
                    str(perf.get('client_secret') or '').strip(),
                    source_json_synced_at,
                    now,
                    current,
                ),
            )
        conn.commit()
        final_code = str(store.get('store_code') or current).strip()
        row = conn.execute(
            """
            SELECT id, store_name, store_code, enabled, timezone, currency, notes, marketplace_id,
                   seller_client_id, seller_api_key, perf_client_id, perf_client_secret,
                   source_json_synced_at, created_at, updated_at
            FROM store_configs
            WHERE store_code = ?
            LIMIT 1
            """,
            (final_code,),
        ).fetchone()
        if row is None:
            raise RuntimeError('failed to reload upserted store config')
        return _row_to_store_config(row)
    finally:
        conn.close()


def seed_store_configs(
    stores: List[Dict[str, Any]],
    *,
    overwrite: bool = False,
    db_path: pathlib.Path | str | None = None,
) -> int:
    ensure_db(db_path)
    synced_at = utc_now_text()
    conn, _ = _connect(db_path)
    try:
        existing_count = int((conn.execute('SELECT COUNT(*) AS count FROM store_configs').fetchone() or {'count': 0})['count'])
        if existing_count > 0 and not overwrite:
            return 0
    finally:
        conn.close()
    inserted = 0
    if overwrite:
        conn, _ = _connect(db_path)
        try:
            conn.execute('DELETE FROM store_configs')
            conn.commit()
        finally:
            conn.close()
    for store in stores:
        upsert_store_config(store, original_store_code=str(store.get('store_code') or ''), source_json_synced_at=synced_at, db_path=db_path)
        inserted += 1
    return inserted


def save_snapshot(payload: Dict[str, Any], db_path: pathlib.Path | str | None = None) -> int:
    ensure_db(db_path)
    conn, _ = _connect(db_path)
    try:
        summary = payload.get('summary') or {}
        generated_at = str(payload.get('generated_at') or '')
        values = (
            generated_at,
            _safe_int(payload.get('days'), 0),
            str(payload.get('store_filter') or ''),
            _safe_int(payload.get('max_workers'), 1),
            1 if payload.get('include_details') else 0,
            _safe_int(summary.get('store_count'), 0),
            _safe_int(summary.get('ok_count'), 0),
            _safe_int(summary.get('partial_count'), 0),
            _safe_int(summary.get('error_count'), 0),
            _safe_int(summary.get('flagged_count'), 0),
            _safe_float(summary.get('total_sales_amount'), 0.0),
            _safe_float(summary.get('total_ad_expense_rub'), 0.0),
            _safe_float(summary.get('total_ad_revenue_rub'), 0.0),
            _safe_int(summary.get('total_unfulfilled_orders'), 0),
            _safe_int(summary.get('total_no_price_items'), 0),
            _safe_int(summary.get('total_risky_skus'), 0),
            _safe_float(summary.get('avg_health_score'), 0.0),
            json.dumps(summary, ensure_ascii=False),
            json.dumps(payload, ensure_ascii=False),
        )
        cursor = conn.execute(
            """
            INSERT INTO snapshots (
                generated_at, days, store_filter, max_workers, include_details,
                store_count, ok_count, partial_count, error_count, flagged_count,
                total_sales_amount, total_ad_expense_rub, total_ad_revenue_rub,
                total_unfulfilled_orders, total_no_price_items, total_risky_skus, avg_health_score,
                summary_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        snapshot_id = int(cursor.lastrowid)

        for item in payload.get('results') or []:
            overview = item.get('overview') or {}
            conn.execute(
                """
                INSERT INTO store_metrics (
                    snapshot_id, generated_at, store_name, store_code, currency, status, health_score,
                    sales_amount, ad_expense_rub, ad_revenue_rub, ad_roas,
                    unfulfilled_orders, no_price_count, risky_sku_count, flags_json, errors_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    generated_at,
                    str(item.get('store_name') or ''),
                    str(item.get('store_code') or ''),
                    str(item.get('currency') or ''),
                    str(item.get('status') or 'unknown'),
                    _safe_int(item.get('health_score'), 0),
                    _safe_float(overview.get('sales_amount'), 0.0),
                    _safe_float(overview.get('ad_expense_rub'), 0.0),
                    _safe_float(overview.get('ad_revenue_rub'), 0.0),
                    _safe_float(overview.get('ad_roas'), 0.0),
                    _safe_int(overview.get('unfulfilled_orders_count'), 0),
                    _safe_int(overview.get('no_price_count'), 0),
                    _safe_int(overview.get('risky_sku_count'), 0),
                    json.dumps(item.get('flags') or [], ensure_ascii=False),
                    json.dumps(item.get('errors') or [], ensure_ascii=False),
                ),
            )

        conn.commit()
        return snapshot_id
    finally:
        conn.close()


def _row_to_snapshot(row: sqlite3.Row) -> Dict[str, Any]:
    summary = {
        'store_count': int(row['store_count']),
        'ok_count': int(row['ok_count']),
        'partial_count': int(row['partial_count']),
        'error_count': int(row['error_count']),
        'flagged_count': int(row['flagged_count']),
        'total_sales_amount': float(row['total_sales_amount']),
        'total_ad_expense_rub': float(row['total_ad_expense_rub']),
        'total_ad_revenue_rub': float(row['total_ad_revenue_rub']),
        'total_unfulfilled_orders': int(row['total_unfulfilled_orders']),
        'total_no_price_items': int(row['total_no_price_items']),
        'total_risky_skus': int(row['total_risky_skus']),
        'avg_health_score': float(row['avg_health_score']),
    }
    if 'summary_json' in row.keys():
        try:
            stored_summary = json.loads(row['summary_json'] or '{}')
        except Exception:
            stored_summary = {}
        if isinstance(stored_summary, dict):
            for key in (
                'total_sales_amount_cny',
                'total_ad_expense_cny',
                'total_ad_revenue_cny',
                'total_low_stock_warehouses',
                'overall_roas',
            ):
                if key in stored_summary:
                    summary[key] = stored_summary[key]

    return {
        'id': int(row['id']),
        'generated_at': row['generated_at'],
        'days': int(row['days']),
        'store_filter': row['store_filter'],
        'max_workers': int(row['max_workers']),
        'include_details': bool(row['include_details']),
        'summary': summary,
        'created_at': row['created_at'],
    }


def list_snapshots(*, limit: int = 20, db_path: pathlib.Path | str | None = None) -> List[Dict[str, Any]]:
    ensure_db(db_path)
    capped = min(max(limit, 1), 200)
    conn, _ = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, generated_at, days, store_filter, max_workers, include_details,
                   store_count, ok_count, partial_count, error_count, flagged_count,
                   total_sales_amount, total_ad_expense_rub, total_ad_revenue_rub,
                   total_unfulfilled_orders, total_no_price_items, total_risky_skus, avg_health_score,
                   summary_json, created_at
            FROM snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (capped,),
        ).fetchall()
        return [_row_to_snapshot(row) for row in rows]
    finally:
        conn.close()


def get_latest_snapshot(*, include_payload: bool = False, db_path: pathlib.Path | str | None = None) -> Optional[Dict[str, Any]]:
    ensure_db(db_path)
    conn, _ = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, generated_at, days, store_filter, max_workers, include_details,
                   store_count, ok_count, partial_count, error_count, flagged_count,
                   total_sales_amount, total_ad_expense_rub, total_ad_revenue_rub,
                   total_unfulfilled_orders, total_no_price_items, total_risky_skus, avg_health_score,
                   summary_json, payload_json, created_at
            FROM snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        snapshot = _row_to_snapshot(row)
        if include_payload:
            try:
                snapshot['payload'] = json.loads(row['payload_json'])
            except Exception:
                snapshot['payload'] = None
        return snapshot
    finally:
        conn.close()


def list_store_trends(
    store_code: str,
    *,
    limit: int = 30,
    db_path: pathlib.Path | str | None = None,
) -> List[Dict[str, Any]]:
    ensure_db(db_path)
    code = str(store_code or '').strip()
    if not code:
        return []
    capped = min(max(limit, 1), 365)
    conn, _ = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT generated_at, store_name, store_code, currency, status, health_score,
                   sales_amount, ad_expense_rub, ad_revenue_rub, ad_roas,
                   unfulfilled_orders, no_price_count, risky_sku_count, flags_json, errors_json
            FROM store_metrics
            WHERE store_code = ?
            ORDER BY generated_at DESC, id DESC
            LIMIT ?
            """,
            (code, capped),
        ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            try:
                flags = json.loads(row['flags_json'] or '[]')
            except Exception:
                flags = []
            try:
                errors = json.loads(row['errors_json'] or '[]')
            except Exception:
                errors = []
            result.append(
                {
                    'generated_at': row['generated_at'],
                    'store_name': row['store_name'],
                    'store_code': row['store_code'],
                    'currency': row['currency'],
                    'status': row['status'],
                    'health_score': int(row['health_score']),
                    'sales_amount': float(row['sales_amount']),
                    'ad_expense_rub': float(row['ad_expense_rub']),
                    'ad_revenue_rub': float(row['ad_revenue_rub']),
                    'ad_roas': float(row['ad_roas']),
                    'unfulfilled_orders': int(row['unfulfilled_orders']),
                    'no_price_count': int(row['no_price_count']),
                    'risky_sku_count': int(row['risky_sku_count']),
                    'flags': flags,
                    'errors': errors,
                }
            )
        return result
    finally:
        conn.close()
