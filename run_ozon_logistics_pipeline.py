from __future__ import annotations

import argparse
from typing import Any, Dict, List

from ozon_lib import (
    OzonConfigError,
    cli_error,
    fetch_warehouses,
    get_store_identity,
    load_config,
    print_json,
    request_json,
    run_store_pipeline,
    seller_headers,
)


def analyze_store_logistics(store: Dict[str, Any]) -> Dict[str, Any]:
    headers = seller_headers(store)
    warehouses = fetch_warehouses(store, limit=200, timeout=60)

    warehouse_items: List[Dict[str, Any]] = []
    delivery_methods_total = 0
    stock_present_total = 0
    stock_reserved_total = 0
    low_stock_warehouses = 0
    high_reserved_warehouses = 0
    empty_stock_warehouses = 0
    stock_health_notes: List[str] = []
    stock_items_preview: List[Dict[str, Any]] = []

    for warehouse in warehouses[:10]:
        warehouse_id = warehouse.get('warehouse_id')
        warehouse_name = warehouse.get('name') or str(warehouse_id or '-')

        methods_data = request_json(
            'POST',
            'https://api-seller.ozon.ru/v2/delivery-method/list',
            headers=headers,
            json_body={
                'cursor': '',
                'filter': {'warehouse_ids': [str(warehouse_id)]},
                'limit': 100,
                'sort_dir': 'ASC',
            },
            timeout=60,
            error_context=f'Failed to fetch delivery methods for warehouse {warehouse_name}',
        )
        methods = methods_data.get('delivery_methods', []) if isinstance(methods_data, dict) else []
        delivery_methods_total += len(methods)

        stocks_data = request_json(
            'POST',
            'https://api-seller.ozon.ru/v1/product/info/warehouse/stocks',
            headers=headers,
            json_body={'cursor': '', 'limit': 50, 'warehouse_id': warehouse_id},
            timeout=60,
            error_context=f'Failed to fetch stock sample for warehouse {warehouse_name}',
        )
        stocks = stocks_data.get('stocks', []) if isinstance(stocks_data, dict) else []

        present_sum = 0
        reserved_sum = 0
        for stock in stocks:
            present = int(stock.get('present') or 0)
            reserved = int(stock.get('reserved') or 0)
            present_sum += present
            reserved_sum += reserved
            if len(stock_items_preview) < 80:
                stock_items_preview.append({
                    'sku': stock.get('sku'),
                    'product_id': stock.get('product_id'),
                    'offer_id': stock.get('offer_id'),
                    'warehouse_id': stock.get('warehouse_id'),
                    'warehouse_name': warehouse_name,
                    'present': present,
                    'reserved': reserved,
                    'free_stock': int(stock.get('free_stock') or 0),
                    'updated_at': stock.get('updated_at'),
                })

        stock_present_total += present_sum
        stock_reserved_total += reserved_sum
        reserved_ratio = round((reserved_sum / present_sum * 100), 2) if present_sum > 0 else 0.0

        if present_sum == 0:
            empty_stock_warehouses += 1
            stock_health_notes.append(f'Warehouse {warehouse_name} has zero sampled stock')
        elif present_sum <= 20:
            low_stock_warehouses += 1
            stock_health_notes.append(f'Warehouse {warehouse_name} has low sampled stock: {present_sum}')

        if reserved_sum > 0 and (present_sum == 0 or reserved_ratio >= 30):
            high_reserved_warehouses += 1
            stock_health_notes.append(f'Warehouse {warehouse_name} has high reserved ratio: {reserved_ratio}%')

        warehouse_items.append({
            'warehouse_id': warehouse_id,
            'name': warehouse.get('name'),
            'status': warehouse.get('status'),
            'delivery_methods_count': len(methods),
            'stock_present_sample': present_sum,
            'stock_reserved_sample': reserved_sum,
            'stock_reserved_ratio_pct': reserved_ratio,
            'stock_sample_count': len(stocks),
        })

    summary = {
        'warehouse_count': len(warehouses),
        'delivery_methods_count': delivery_methods_total,
        'stock_present_sample_total': stock_present_total,
        'stock_reserved_sample_total': stock_reserved_total,
        'stock_reserved_ratio_pct': round((stock_reserved_total / stock_present_total * 100), 2) if stock_present_total else 0,
        'low_stock_warehouses_count': low_stock_warehouses,
        'high_reserved_warehouses_count': high_reserved_warehouses,
        'empty_stock_warehouses_count': empty_stock_warehouses,
        'stock_health_notes': stock_health_notes[:5],
    }
    return {
        **get_store_identity(store),
        'status': 'ok',
        'summary': summary,
        'warehouses': warehouse_items,
        'stock_items_preview': stock_items_preview,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ozon logistics pipeline')
    parser.add_argument('--store', type=str, default='', help='Filter by store name or store code')
    return parser


def main() -> None:
    try:
        args = build_parser().parse_args()
        config = load_config()
        store_filter = (args.store or '').strip()
        selected, results = run_store_pipeline(
            config=config,
            store_filter=store_filter,
            analyzer=analyze_store_logistics,
        )
        print_json({
            'store_filter': store_filter,
            'store_count': len(selected),
            'results': results,
        })
    except OzonConfigError as exc:
        cli_error(exc)


if __name__ == '__main__':
    main()
