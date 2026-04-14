from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from ozon_lib import (
    OzonConfigError,
    cli_error,
    fetch_finance_transactions,
    load_config,
    print_json,
    require_positive_int,
    run_store_pipeline,
    select_stores,
)


def summarize_transactions(operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    sales_amount = 0.0
    service_amount = 0.0
    refund_amount = 0.0
    orders_count = 0
    sales_ops = 0
    service_ops = 0
    refund_ops = 0

    for op in operations:
        amount = float(op.get('amount') or 0)
        op_type = str(op.get('type') or '')
        op_name = str(op.get('operation_type_name') or '')
        lower_name = op_name.lower()

        if op_type == 'orders' or 'продажа' in lower_name or 'sale' in lower_name:
            sales_amount += amount
            sales_ops += 1
            orders_count += 1
        elif op_type == 'services' or 'service' in lower_name or 'услуг' in lower_name:
            service_amount += amount
            service_ops += 1
        elif 'refund' in lower_name or 'возврат' in lower_name:
            refund_amount += amount
            refund_ops += 1

    return {
        'sales_amount': round(sales_amount, 2),
        'service_amount': round(service_amount, 2),
        'refund_amount': round(refund_amount, 2),
        'orders_count_estimated': orders_count,
        'sales_ops': sales_ops,
        'service_ops': service_ops,
        'refund_ops': refund_ops,
        'ops_count': len(operations),
        'net_before_services': round(sales_amount + refund_amount, 2),
        'net_after_services': round(sales_amount + refund_amount + service_amount, 2),
    }


def analyze_store_sales(store: Dict[str, Any], days: int = 7) -> Dict[str, Any]:
    operations = fetch_finance_transactions(store, days=days)
    summary = summarize_transactions(operations)
    preview = []
    for op in operations[:20]:
        preview.append({
            'operation_id': op.get('operation_id'),
            'operation_type_name': op.get('operation_type_name'),
            'type': op.get('type'),
            'amount': op.get('amount'),
            'posting': op.get('posting'),
            'date': op.get('operation_date'),
        })
    return {
        **get_store_identity(store),
        'status': 'ok',
        'days': days,
        'summary': summary,
        'operations_preview': preview,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ozon 销售分析流水线')
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
            analyzer=analyze_store_sales,
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
