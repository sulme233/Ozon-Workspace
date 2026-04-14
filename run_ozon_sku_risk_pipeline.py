from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from run_ozon_logistics_pipeline import analyze_store_logistics
from run_ozon_pricing_pipeline import analyze_store_pricing
from ozon_lib import OzonConfigError, get_store_identity, load_config, select_stores


def build_price_map(pricing_result: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    result: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in pricing_result.get('risky_items_preview', []):
        key = (str(item.get('offer_id') or ''), str(item.get('product_id') or ''))
        result[key] = item
    return result


REASON_WEIGHTS = {
    '无可用库存': 100,
    '商品无价格': 90,
    '可用库存偏低': 70,
    '预留占比较高': 50,
    '折扣过深': 40,
    '接近最低价': 30,
}


def calc_risk_score(reasons: Iterable[str], free_stock: int, reserved: int, present: int) -> int:
    score = sum(REASON_WEIGHTS.get(reason, 10) for reason in reasons)
    if free_stock <= 0:
        score += 20
    elif free_stock <= 5:
        score += max(0, 6 - free_stock) * 3
    if present > 0 and reserved > 0:
        score += min(int(reserved / max(present, 1) * 20), 20)
    return score


def summarize_reason_counts(risky_skus: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in risky_skus:
        for reason in item.get('reasons', []):
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def summarize_warehouse_counts(risky_skus: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in risky_skus:
        key = str(item.get('warehouse_name') or '未知仓库')
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def sort_risky_skus(risky_skus: List[Dict[str, Any]], sort_by: str, descending: bool) -> List[Dict[str, Any]]:
    sorters = {
        'risk_score': lambda item: (float(item.get('risk_score') or 0), -float(item.get('free_stock') or 0)),
        'free_stock': lambda item: (float(item.get('free_stock') or 0), -float(item.get('risk_score') or 0)),
        'reserved': lambda item: (float(item.get('reserved') or 0), float(item.get('risk_score') or 0)),
        'discount_pct': lambda item: (float(item.get('discount_pct') or 0), float(item.get('risk_score') or 0)),
        'price_gap_to_min_pct': lambda item: (float(item.get('price_gap_to_min_pct') or 0), float(item.get('risk_score') or 0)),
        'warehouse_name': lambda item: (str(item.get('warehouse_name') or ''), -float(item.get('risk_score') or 0)),
        'sku': lambda item: (str(item.get('sku') or ''), -float(item.get('risk_score') or 0)),
    }
    sorter = sorters[sort_by]
    return sorted(risky_skus, key=sorter, reverse=descending)


def filter_risky_skus(
    risky_skus: List[Dict[str, Any]],
    *,
    reason_keyword: str = '',
    warehouse_keyword: str = '',
    sku_keyword: str = '',
) -> List[Dict[str, Any]]:
    reason_keyword = reason_keyword.strip()
    warehouse_keyword = warehouse_keyword.strip()
    sku_keyword = sku_keyword.strip()
    result: List[Dict[str, Any]] = []
    for item in risky_skus:
        if reason_keyword and not any(reason_keyword in str(reason) for reason in item.get('reasons', [])):
            continue
        if warehouse_keyword and warehouse_keyword not in str(item.get('warehouse_name') or ''):
            continue
        if sku_keyword and sku_keyword not in str(item.get('sku') or '') and sku_keyword not in str(item.get('offer_id') or ''):
            continue
        result.append(item)
    return result


def export_risky_skus_csv(rows: List[Dict[str, Any]], output_path: str) -> Path:
    path = Path(output_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'store_name', 'store_code', 'sku', 'offer_id', 'product_id', 'warehouse_name',
        'present', 'reserved', 'free_stock', 'price', 'old_price', 'min_price',
        'discount_pct', 'price_gap_to_min_pct', 'risk_score', 'reasons',
    ]
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **{key: row.get(key) for key in fieldnames if key != 'reasons'},
                'reasons': ' | '.join(row.get('reasons', [])),
            })
    return path


def analyze_store_sku_risk(store: Dict[str, Any]) -> Dict[str, Any]:
    logistics = analyze_store_logistics(store)
    pricing = analyze_store_pricing(store)
    price_map = build_price_map(pricing)

    risky_skus: List[Dict[str, Any]] = []
    for item in logistics.get('stock_items_preview', []):
        offer_id = str(item.get('offer_id') or '')
        product_id = str(item.get('product_id') or '')
        price_item = price_map.get((offer_id, product_id), {})
        present = int(item.get('present') or 0)
        reserved = int(item.get('reserved') or 0)
        free_stock = int(item.get('free_stock') or 0)
        has_price = bool(price_item.get('has_price', True)) if price_item else True
        discount_pct = float(price_item.get('discount_pct') or 0)
        gap_pct = float(price_item.get('price_gap_to_min_pct') or 0)

        reasons: List[str] = []
        if free_stock <= 0:
            reasons.append('无可用库存')
        elif free_stock <= 5:
            reasons.append('可用库存偏低')
        if reserved > 0 and present > 0 and reserved / max(present, 1) >= 0.3:
            reasons.append('预留占比较高')
        if not has_price:
            reasons.append('商品无价格')
        if discount_pct >= 30:
            reasons.append('折扣过深')
        if gap_pct > 0 and gap_pct <= 5:
            reasons.append('接近最低价')

        if reasons:
            risk_score = calc_risk_score(reasons, free_stock=free_stock, reserved=reserved, present=present)
            risky_skus.append({
                **get_store_identity(store),
                'sku': item.get('sku'),
                'offer_id': item.get('offer_id'),
                'product_id': item.get('product_id'),
                'warehouse_name': item.get('warehouse_name'),
                'present': present,
                'reserved': reserved,
                'free_stock': free_stock,
                'price': price_item.get('price'),
                'old_price': price_item.get('old_price'),
                'min_price': price_item.get('min_price'),
                'discount_pct': discount_pct,
                'price_gap_to_min_pct': gap_pct,
                'risk_score': risk_score,
                'reasons': reasons,
            })

    risky_skus = sort_risky_skus(risky_skus, sort_by='risk_score', descending=True)
    summary = {
        'risky_sku_count': len(risky_skus),
        'out_of_stock_sku_count': len([x for x in risky_skus if '无可用库存' in x['reasons']]),
        'low_free_stock_sku_count': len([x for x in risky_skus if '可用库存偏低' in x['reasons']]),
        'no_price_sku_count': len([x for x in risky_skus if '商品无价格' in x['reasons']]),
        'deep_discount_sku_count': len([x for x in risky_skus if '折扣过深' in x['reasons']]),
        'reason_counts': summarize_reason_counts(risky_skus),
    }
    return {
        **get_store_identity(store),
        'status': 'ok',
        'summary': summary,
        'sku_risks': risky_skus,
        'sku_risks_preview': risky_skus[:30],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ozon SKU 风险明细流水线')
    parser.add_argument('--store', type=str, default='', help='指定店铺名称或店铺代号')
    parser.add_argument('--sort-by', type=str, default='risk_score', choices=['risk_score', 'free_stock', 'reserved', 'discount_pct', 'price_gap_to_min_pct', 'warehouse_name', 'sku'], help='风险 SKU 排序字段')
    parser.add_argument('--ascending', action='store_true', help='按升序排序，默认降序')
    parser.add_argument('--reason', type=str, default='', help='按风险原因关键字筛选，如 无可用库存 / 商品无价格')
    parser.add_argument('--warehouse', type=str, default='', help='按仓库名称关键字筛选')
    parser.add_argument('--sku-keyword', type=str, default='', help='按 SKU 或 Offer 关键字筛选')
    parser.add_argument('--max-items', type=int, default=30, help='返回明细条数上限，默认 30，0 表示全部')
    parser.add_argument('--export-csv', type=str, default='', help='导出筛选后的风险 SKU 明细到 CSV 文件')
    parser.add_argument('--include-all', action='store_true', help='在 JSON 结果中包含完整 sku_risks 明细，默认仅保留 preview')
    return parser


def main() -> None:
    try:
        args = build_parser().parse_args()
        config = load_config()
        results = []
        export_rows: List[Dict[str, Any]] = []
        store_filter = (args.store or '').strip()
        selected = select_stores(config, store_filter)

        for store in selected:
            try:
                result = analyze_store_sku_risk(store)
                filtered_rows = filter_risky_skus(
                    result.get('sku_risks', []),
                    reason_keyword=args.reason,
                    warehouse_keyword=args.warehouse,
                    sku_keyword=args.sku_keyword,
                )
                sorted_rows = sort_risky_skus(filtered_rows, sort_by=args.sort_by, descending=not args.ascending)
                preview_limit = None if (args.max_items or 0) <= 0 else args.max_items
                result['sku_risks_preview'] = sorted_rows[:preview_limit] if preview_limit else sorted_rows
                result['filtered_summary'] = {
                    'filtered_risky_sku_count': len(sorted_rows),
                    'reason': args.reason,
                    'warehouse': args.warehouse,
                    'sku_keyword': args.sku_keyword,
                    'sort_by': args.sort_by,
                    'ascending': bool(args.ascending),
                    'max_items': args.max_items,
                    'reason_counts': summarize_reason_counts(sorted_rows),
                    'warehouse_counts': summarize_warehouse_counts(sorted_rows),
                }
                if not args.include_all:
                    result.pop('sku_risks', None)
                export_rows.extend(sorted_rows)
                results.append(result)
            except Exception as exc:
                results.append({
                    **get_store_identity(store),
                    'status': 'error',
                    'error': str(exc),
                })
        export_path = ''
        if args.export_csv:
            export_path = str(export_risky_skus_csv(export_rows, args.export_csv))
        print(json.dumps({
            'store_filter': store_filter,
            'sort_by': args.sort_by,
            'ascending': bool(args.ascending),
            'reason': args.reason,
            'warehouse': args.warehouse,
            'sku_keyword': args.sku_keyword,
            'max_items': args.max_items,
            'include_all': bool(args.include_all),
            'export_csv': export_path,
            'store_count': len(selected),
            'results': results,
        }, ensure_ascii=False, indent=2))
    except OzonConfigError as exc:
        raise SystemExit(str(exc))


if __name__ == '__main__':
    main()
