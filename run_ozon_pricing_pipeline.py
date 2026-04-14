from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from ozon_lib import (
    OzonConfigError,
    cli_error,
    fetch_product_prices,
    load_config,
    print_json,
    ru_num,
    run_store_pipeline,
    select_stores,
)


def analyze_store_pricing(store: Dict[str, Any]) -> Dict[str, Any]:
    items = fetch_product_prices(store, limit=200)
    low_margin_candidates = 0
    deep_discount_count = 0
    no_price_count = 0
    no_buybox_count = 0
    risky_items: List[Dict[str, Any]] = []

    for item in items:
        price = ru_num(item.get('price'))
        old_price = ru_num(item.get('old_price'))
        min_price = ru_num(item.get('min_price'))
        visibility = item.get('visibility_details') or {}
        has_price = bool(visibility.get('has_price', True))

        if not has_price or price <= 0:
            no_price_count += 1

        price_indexes = item.get('price_indexes') or {}
        external_index = price_indexes.get('external_index_data') or {}
        buybox_price = ru_num(external_index.get('minimal_price'))
        if buybox_price <= 0:
            no_buybox_count += 1

        discount_pct = round(((old_price - price) / old_price * 100), 2) if old_price > 0 and price > 0 else 0.0
        price_gap_pct = round(((price - min_price) / price * 100), 2) if price > 0 and min_price > 0 else 0.0
        is_deep_discount = discount_pct >= 30
        is_low_margin = min_price > 0 and price > 0 and price_gap_pct <= 5

        if is_deep_discount:
            deep_discount_count += 1
        if is_low_margin:
            low_margin_candidates += 1

        if (not has_price) or is_deep_discount or is_low_margin:
            risky_items.append({
                'offer_id': item.get('offer_id'),
                'product_id': item.get('product_id'),
                'price': round(price, 2),
                'old_price': round(old_price, 2),
                'min_price': round(min_price, 2),
                'discount_pct': discount_pct,
                'price_gap_to_min_pct': price_gap_pct,
                'has_price': has_price,
            })

    summary = {
        'priced_items_count': len(items),
        'no_price_count': no_price_count,
        'no_buybox_price_count': no_buybox_count,
        'deep_discount_count': deep_discount_count,
        'low_margin_candidates_count': low_margin_candidates,
    }
    return {
        **get_store_identity(store),
        'status': 'ok',
        'summary': summary,
        'risky_items_preview': risky_items[:20],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ozon 商品价格风险分析流水线')
    parser.add_argument('--store', type=str, default='', help='指定店铺名称或店铺代号')
    return parser


def main() -> None:
    try:
        args = build_parser().parse_args()
        config = load_config()
        store_filter = (args.store or '').strip()
        selected, results = run_store_pipeline(
            config=config,
            store_filter=store_filter,
            analyzer=analyze_store_pricing,
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
