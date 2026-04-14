from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from ozon_lib import (
    OzonApiError,
    OzonConfigError,
    cli_error,
    fetch_fbs_postings,
    fetch_fbs_unfulfilled_postings,
    get_store_identity,
    load_config,
    print_json,
    require_positive_int,
    run_store_pipeline,
    select_stores,
    utc_day_range,
)


def summarize_statuses(postings: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for posting in postings:
        status = str(posting.get('status') or 'unknown').strip() or 'unknown'
        counts[status] = counts.get(status, 0) + 1
    return counts


def analyze_store_orders(store: Dict[str, Any], days: int = 7) -> Dict[str, Any]:
    since, to = utc_day_range(days=days)
    recent = fetch_fbs_postings(store, since=since, to=to, limit=200)
    warnings: List[str] = []
    try:
        unfulfilled = fetch_fbs_unfulfilled_postings(store, limit=200)
    except OzonApiError as exc:
        # Some stores reject unfulfilled query windows; keep recent postings result.
        warnings.append(str(exc))
        unfulfilled = []

    status_counts = summarize_statuses(recent)
    preview = []
    legal_orders = 0
    shipment_attention_count = 0

    for posting in unfulfilled:
        if posting.get('is_legal'):
            legal_orders += 1
        if posting.get('shipment_date'):
            shipment_attention_count += 1

    for posting in (unfulfilled[:10] or recent[:10]):
        analytics = posting.get('analytics_data') or {}
        preview.append({
            'posting_number': posting.get('posting_number'),
            'status': posting.get('status'),
            'substatus': posting.get('substatus'),
            'shipment_date': posting.get('shipment_date'),
            'delivering_date': posting.get('delivering_date'),
            'warehouse_id': posting.get('warehouse_id'),
            'is_legal': bool(posting.get('is_legal')),
            'city': analytics.get('city'),
            'region': analytics.get('region'),
        })

    summary = {
        'recent_postings_count': len(recent),
        'unfulfilled_count': len(unfulfilled),
        'awaiting_packaging_count': status_counts.get('awaiting_packaging', 0),
        'awaiting_deliver_count': status_counts.get('awaiting_deliver', 0),
        'awaiting_registration_count': status_counts.get('awaiting_registration', 0),
        'delivering_count': status_counts.get('delivering', 0),
        'delivered_count': status_counts.get('delivered', 0),
        'cancelled_count': status_counts.get('cancelled', 0),
        'legal_orders_count': legal_orders,
        'shipment_attention_count': shipment_attention_count,
        'status_counts': status_counts,
    }
    return {
        **get_store_identity(store),
        'status': 'partial' if warnings else 'ok',
        'days': days,
        'summary': summary,
        'postings_preview': preview,
        'warnings': warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ozon FBS 订单履约分析流水线')
    parser.add_argument('--days', type=int, default=7, help='统计天数，默认 7')
    parser.add_argument('--store', type=str, default='', help='指定店铺名称或店铺代号')
    return parser


def main() -> None:
    try:
        args = build_parser().parse_args()
        require_positive_int(args.days, field='days')
        config = load_config()
        store_filter = (args.store or '').strip()
        selected, results = run_store_pipeline(
            config=config,
            store_filter=store_filter,
            analyzer=analyze_store_orders,
            analyzer_kwargs={'days': args.days},
        )
        print_json({
            'days': args.days,
            'store_filter': store_filter,
            'store_count': len(selected),
            'results': results,
        })
    except OzonConfigError as exc:
        cli_error(exc)


if __name__ == '__main__':
    main()
