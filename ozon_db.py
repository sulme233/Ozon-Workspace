from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Any, Dict, List, Optional


WORKSPACE = pathlib.Path(__file__).resolve().parent
DEFAULT_DB_PATH = WORKSPACE / 'dashboard' / 'data' / 'ozon_metrics.db'


def _connect(db_path: pathlib.Path | str | None = None) -> tuple[sqlite3.Connection, pathlib.Path]:
    path = pathlib.Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
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
    return {
        'id': int(row['id']),
        'generated_at': row['generated_at'],
        'days': int(row['days']),
        'store_filter': row['store_filter'],
        'max_workers': int(row['max_workers']),
        'include_details': bool(row['include_details']),
        'summary': {
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
        },
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
                   total_unfulfilled_orders, total_no_price_items, total_risky_skus, avg_health_score, created_at
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
                   payload_json, created_at
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
