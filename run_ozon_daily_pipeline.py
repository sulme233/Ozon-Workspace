from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from ozon_lib import (
    OzonConfigError,
    cli_error,
    get_store_identity,
    load_config,
    print_json,
    require_non_negative_int,
    require_positive_int,
    select_stores,
)
from run_ozon_ads_pipeline import analyze_store_ads
from run_ozon_logistics_pipeline import analyze_store_logistics
from run_ozon_orders_pipeline import analyze_store_orders
from run_ozon_pricing_pipeline import analyze_store_pricing
from run_ozon_sales_pipeline import analyze_store_sales
from run_ozon_sku_risk_pipeline import analyze_store_sku_risk


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ozon 每日经营总入口')
    parser.add_argument('--days', type=int, default=7, help='统计天数，默认 7')
    parser.add_argument('--store', type=str, default='', help='指定店铺名称或店铺代号')
    parser.add_argument('--limit-campaigns', type=int, default=0, help='广告活动数量限制，0 表示不限制')
    parser.add_argument('--max-workers', type=int, default=4, help='店铺级并发数')
    parser.add_argument('--include-details', action='store_true', help='包含完整模块明细（默认仅输出预览）')
    return parser


def compute_flags(overview: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    ad_expense = float(overview.get('ad_expense_rub') or 0)
    ad_orders = int(overview.get('ad_orders') or 0)
    sales_amount = float(overview.get('sales_amount') or 0)
    warehouse_count = int(overview.get('warehouse_count') or 0)
    unfulfilled_count = int(overview.get('unfulfilled_orders_count') or 0)
    shipment_attention_count = int(overview.get('shipment_attention_count') or 0)
    low_stock_warehouses = int(overview.get('low_stock_warehouses_count') or 0)
    empty_stock_warehouses = int(overview.get('empty_stock_warehouses_count') or 0)
    reserved_ratio = float(overview.get('stock_reserved_ratio_pct') or 0)
    no_price_count = int(overview.get('no_price_count') or 0)
    deep_discount_count = int(overview.get('deep_discount_count') or 0)
    low_margin_candidates = int(overview.get('low_margin_candidates_count') or 0)
    risky_sku_count = int(overview.get('risky_sku_count') or 0)

    if ad_expense > 0 and ad_orders == 0:
        flags.append('广告有花费但无订单')
    if sales_amount <= 0:
        flags.append('近周期销售额为空')
    if warehouse_count == 0:
        flags.append('未获取到仓库信息')
    if shipment_attention_count >= 10:
        flags.append('待发货订单压力较高')
    if unfulfilled_count > 0 and warehouse_count == 0:
        flags.append('有待履约订单但未识别到仓库')
    if empty_stock_warehouses > 0:
        flags.append('存在空库存仓库样本')
    if low_stock_warehouses > 0:
        flags.append('存在低库存仓库样本')
    if reserved_ratio >= 30:
        flags.append('库存预留占比较高')
    if no_price_count > 0:
        flags.append('存在无价格商品')
    if deep_discount_count > 0:
        flags.append('存在大幅折扣商品')
    if low_margin_candidates > 0:
        flags.append('存在低毛利候选商品')
    if risky_sku_count > 0:
        flags.append('存在高风险 SKU')
    return flags


def compute_health_score(result: Dict[str, Any], overview: Dict[str, Any]) -> int:
    score = 100
    errors = result.get('errors') or []
    score -= min(len(errors) * 15, 45)

    ad_expense = float(overview.get('ad_expense_rub') or 0)
    ad_orders = int(overview.get('ad_orders') or 0)
    ad_roas = float(overview.get('ad_roas') or 0)
    sales_amount = float(overview.get('sales_amount') or 0)
    warehouse_count = int(overview.get('warehouse_count') or 0)
    stock_present = int(overview.get('stock_present_sample_total') or 0)
    unfulfilled_count = int(overview.get('unfulfilled_orders_count') or 0)
    cancelled_count = int(overview.get('cancelled_orders_count') or 0)
    shipment_attention_count = int(overview.get('shipment_attention_count') or 0)
    low_stock_warehouses = int(overview.get('low_stock_warehouses_count') or 0)
    reserved_ratio = float(overview.get('stock_reserved_ratio_pct') or 0)
    no_price_count = int(overview.get('no_price_count') or 0)
    deep_discount_count = int(overview.get('deep_discount_count') or 0)
    low_margin_candidates = int(overview.get('low_margin_candidates_count') or 0)
    risky_sku_count = int(overview.get('risky_sku_count') or 0)

    if ad_expense > 0 and ad_orders == 0:
        score -= 20
    if ad_expense > 0 and ad_roas < 2:
        score -= 10
    if sales_amount <= 0:
        score -= 20
    if warehouse_count == 0:
        score -= 15
    if warehouse_count > 0 and stock_present <= 0:
        score -= 10
    if shipment_attention_count >= 10:
        score -= 10
    if cancelled_count >= 5:
        score -= 5
    if unfulfilled_count >= 20:
        score -= 10
    if low_stock_warehouses > 0:
        score -= min(low_stock_warehouses * 5, 15)
    if reserved_ratio >= 30:
        score -= 10
    if no_price_count > 0:
        score -= min(no_price_count * 3, 15)
    if deep_discount_count > 0:
        score -= min(deep_discount_count * 2, 10)
    if low_margin_candidates > 0:
        score -= min(low_margin_candidates * 2, 10)
    if risky_sku_count > 0:
        score -= min(risky_sku_count, 15)
    return max(score, 0)


def build_insights(overview: Dict[str, Any], flags: List[str]) -> List[str]:
    insights: List[str] = []
    ad_expense = float(overview.get('ad_expense_rub') or 0)
    ad_revenue = float(overview.get('ad_revenue_rub') or 0)
    ad_orders = int(overview.get('ad_orders') or 0)
    ad_roas = float(overview.get('ad_roas') or 0)
    ad_spend_ratio = float(overview.get('ad_spend_ratio_pct') or 0)
    sales_amount = float(overview.get('sales_amount') or 0)
    refunds = float(overview.get('refund_amount') or 0)
    services = float(overview.get('service_amount') or 0)
    warehouse_count = int(overview.get('warehouse_count') or 0)
    stock_present = int(overview.get('stock_present_sample_total') or 0)
    stock_reserved = int(overview.get('stock_reserved_sample_total') or 0)
    unfulfilled_count = int(overview.get('unfulfilled_orders_count') or 0)
    awaiting_packaging = int(overview.get('awaiting_packaging_count') or 0)
    awaiting_deliver = int(overview.get('awaiting_deliver_count') or 0)
    delivering = int(overview.get('delivering_count') or 0)
    cancelled_count = int(overview.get('cancelled_orders_count') or 0)
    reserved_ratio = float(overview.get('stock_reserved_ratio_pct') or 0)
    low_stock_warehouses = int(overview.get('low_stock_warehouses_count') or 0)
    empty_stock_warehouses = int(overview.get('empty_stock_warehouses_count') or 0)
    no_price_count = int(overview.get('no_price_count') or 0)
    deep_discount_count = int(overview.get('deep_discount_count') or 0)
    low_margin_candidates = int(overview.get('low_margin_candidates_count') or 0)
    risky_sku_count = int(overview.get('risky_sku_count') or 0)
    out_of_stock_sku_count = int(overview.get('out_of_stock_sku_count') or 0)
    low_free_stock_sku_count = int(overview.get('low_free_stock_sku_count') or 0)

    if ad_expense > 0:
        insights.append(f'广告花费 {ad_expense:.2f}，带来广告销售额 {ad_revenue:.2f}，ROAS {ad_roas:.2f}。')
    if sales_amount > 0:
        insights.append(f'近周期销售额 {sales_amount:.2f}，广告花费占比 {ad_spend_ratio:.2f}%。')
    if refunds != 0 or services != 0:
        insights.append(f'退款金额 {refunds:.2f}，服务费 {services:.2f}，可继续细化利润口径。')
    if warehouse_count > 0:
        insights.append(f'已识别仓库 {warehouse_count} 个，样本库存现货 {stock_present}，预留 {stock_reserved}。')
    if reserved_ratio > 0:
        insights.append(f'样本库存预留占比 {reserved_ratio:.2f}%，可用于判断履约挤压程度。')
    if unfulfilled_count > 0 or delivering > 0:
        insights.append(
            f'近期订单在履约链路中的数量为 {unfulfilled_count + delivering}，其中待包装 {awaiting_packaging}，'
            f'待发运 {awaiting_deliver}，运输中 {delivering}。'
        )
    if cancelled_count > 0:
        insights.append(f'近期取消订单 {cancelled_count} 笔，建议继续补充取消原因分析。')
    if low_stock_warehouses > 0 or empty_stock_warehouses > 0:
        insights.append(f'库存样本中低库存仓库 {low_stock_warehouses} 个，空库存仓库 {empty_stock_warehouses} 个。')
    if no_price_count > 0 or deep_discount_count > 0 or low_margin_candidates > 0:
        insights.append(
            f'价格侧存在无价格商品 {no_price_count} 个，大幅折扣商品 {deep_discount_count} 个，'
            f'低毛利候选商品 {low_margin_candidates} 个。'
        )
    if risky_sku_count > 0:
        insights.append(
            f'SKU 风险明细中共计 {risky_sku_count} 个风险 SKU，其中无库存 {out_of_stock_sku_count} 个，'
            f'低可用库存 {low_free_stock_sku_count} 个。'
        )
    if ad_expense > 0 and ad_orders == 0:
        insights.append('广告已有投入但未形成订单，优先检查投放对象与商品转化链路。')
    if warehouse_count > 0 and stock_present <= 0:
        insights.append('仓库已识别但库存样本为空，建议补查真实库存与可售状态。')
    for flag in flags:
        if flag not in insights:
            insights.append(flag)
    return insights[:6]


def build_recommendations(overview: Dict[str, Any], flags: List[str]) -> List[str]:
    recommendations: List[str] = []
    ad_expense = float(overview.get('ad_expense_rub') or 0)
    ad_orders = int(overview.get('ad_orders') or 0)
    ad_roas = float(overview.get('ad_roas') or 0)
    sales_amount = float(overview.get('sales_amount') or 0)
    warehouse_count = int(overview.get('warehouse_count') or 0)
    reserved = int(overview.get('stock_reserved_sample_total') or 0)
    awaiting_packaging = int(overview.get('awaiting_packaging_count') or 0)
    awaiting_deliver = int(overview.get('awaiting_deliver_count') or 0)
    cancelled_count = int(overview.get('cancelled_orders_count') or 0)
    reserved_ratio = float(overview.get('stock_reserved_ratio_pct') or 0)
    low_stock_warehouses = int(overview.get('low_stock_warehouses_count') or 0)
    empty_stock_warehouses = int(overview.get('empty_stock_warehouses_count') or 0)
    no_price_count = int(overview.get('no_price_count') or 0)
    deep_discount_count = int(overview.get('deep_discount_count') or 0)
    low_margin_candidates = int(overview.get('low_margin_candidates_count') or 0)
    risky_sku_count = int(overview.get('risky_sku_count') or 0)

    if ad_expense > 0 and ad_orders == 0:
        recommendations.append('暂停低转化广告组，优先排查主图、价格、评价和详情页。')
    elif ad_roas >= 8 and ad_orders >= 3:
        recommendations.append('保留高投产广告活动，逐步放量并观察边际成本变化。')

    if sales_amount <= 0:
        recommendations.append('补齐销售口径，检查 finance transaction 与订单维度是否一致。')
    if warehouse_count == 0:
        recommendations.append('排查 Seller API 仓库接口权限或店铺仓库配置是否缺失。')
    if reserved > 0:
        recommendations.append('关注预留库存占用，结合 FBS 订单状态确认是否存在待处理积压。')
    if low_stock_warehouses > 0 or empty_stock_warehouses > 0:
        recommendations.append('补做低库存 SKU 明细，优先处理空库存和低库存仓库对应商品。')
    if reserved_ratio >= 30:
        recommendations.append('预留库存占比较高，建议联动订单履约和补货节奏一起看。')
    if no_price_count > 0:
        recommendations.append('优先修复无价格商品，避免商品可见但无法正常承接流量。')
    if deep_discount_count > 0 or low_margin_candidates > 0:
        recommendations.append('补查促销价、最低价与利润空间，避免为了动销过度压缩毛利。')
    if risky_sku_count > 0:
        recommendations.append('优先处理 SKU 风险明细里的无库存、低库存和无价格商品，形成商品级动作清单。')
    if awaiting_packaging > 0 or awaiting_deliver > 0:
        recommendations.append('建立待包装和待发运监控，优先处理临近 shipment_date 的订单。')
    if cancelled_count > 0:
        recommendations.append('补充取消原因分析，区分买家取消、库存取消和履约取消。')
    if '近周期销售额为空' not in flags and sales_amount > 0:
        recommendations.append('下一步可补商品价格、库存和订单状态指标，形成经营看板闭环。')
    return recommendations[:5]


def merge_store_result(store: Dict[str, Any], days: int, limit_campaigns: int | None) -> Dict[str, Any]:
    identity = get_store_identity(store)
    result: Dict[str, Any] = {
        **identity,
        'days': days,
        'ads': None,
        'orders': None,
        'pricing': None,
        'sku_risk': None,
        'sales': None,
        'logistics': None,
        'status': 'ok',
        'errors': [],
    }

    try:
        result['ads'] = analyze_store_ads(store, days=days, limit_campaigns=limit_campaigns)
    except Exception as exc:
        result['errors'].append({'module': 'ads', 'error': str(exc)})

    try:
        result['orders'] = analyze_store_orders(store, days=days)
    except Exception as exc:
        result['errors'].append({'module': 'orders', 'error': str(exc)})

    try:
        result['pricing'] = analyze_store_pricing(store)
    except Exception as exc:
        result['errors'].append({'module': 'pricing', 'error': str(exc)})

    try:
        result['sku_risk'] = analyze_store_sku_risk(store)
    except Exception as exc:
        result['errors'].append({'module': 'sku_risk', 'error': str(exc)})

    try:
        result['sales'] = analyze_store_sales(store, days=days)
    except Exception as exc:
        result['errors'].append({'module': 'sales', 'error': str(exc)})

    try:
        result['logistics'] = analyze_store_logistics(store)
    except Exception as exc:
        result['errors'].append({'module': 'logistics', 'error': str(exc)})

    if result['errors']:
        result['status'] = (
            'partial'
            if (result['ads'] or result['orders'] or result['pricing'] or result['sku_risk'] or result['sales'] or result['logistics'])
            else 'error'
        )

    ads_summary = ((result.get('ads') or {}).get('summary') or {})
    orders_summary = ((result.get('orders') or {}).get('summary') or {})
    pricing_summary = ((result.get('pricing') or {}).get('summary') or {})
    sku_risk_summary = ((result.get('sku_risk') or {}).get('summary') or {})
    sales_summary = ((result.get('sales') or {}).get('summary') or {})
    logistics_summary = ((result.get('logistics') or {}).get('summary') or {})

    ad_expense = float(ads_summary.get('advertising_expense_rub', 0) or 0)
    ad_revenue = float(ads_summary.get('revenue_rub', 0) or 0)
    sales_amount = float(sales_summary.get('sales_amount', 0) or 0)

    overview = {
        'ad_expense_rub': ad_expense,
        'ad_revenue_rub': ad_revenue,
        'ad_orders': ads_summary.get('orders', 0),
        'ad_roas': round((ad_revenue / ad_expense), 2) if ad_expense else 0,
        'ad_spend_ratio_pct': round((ad_expense / sales_amount * 100), 2) if sales_amount else 0,
        'sales_amount': sales_amount,
        'refund_amount': sales_summary.get('refund_amount', 0),
        'service_amount': sales_summary.get('service_amount', 0),
        'net_after_services': sales_summary.get('net_after_services', 0),
        'estimated_orders_count': sales_summary.get('orders_count_estimated', 0),
        'recent_postings_count': orders_summary.get('recent_postings_count', 0),
        'unfulfilled_orders_count': orders_summary.get('unfulfilled_count', 0),
        'awaiting_packaging_count': orders_summary.get('awaiting_packaging_count', 0),
        'awaiting_deliver_count': orders_summary.get('awaiting_deliver_count', 0),
        'delivering_count': orders_summary.get('delivering_count', 0),
        'cancelled_orders_count': orders_summary.get('cancelled_count', 0),
        'shipment_attention_count': orders_summary.get('shipment_attention_count', 0),
        'priced_items_count': pricing_summary.get('priced_items_count', 0),
        'no_price_count': pricing_summary.get('no_price_count', 0),
        'no_buybox_price_count': pricing_summary.get('no_buybox_price_count', 0),
        'deep_discount_count': pricing_summary.get('deep_discount_count', 0),
        'low_margin_candidates_count': pricing_summary.get('low_margin_candidates_count', 0),
        'risky_sku_count': sku_risk_summary.get('risky_sku_count', 0),
        'out_of_stock_sku_count': sku_risk_summary.get('out_of_stock_sku_count', 0),
        'low_free_stock_sku_count': sku_risk_summary.get('low_free_stock_sku_count', 0),
        'no_price_sku_count': sku_risk_summary.get('no_price_sku_count', 0),
        'deep_discount_sku_count': sku_risk_summary.get('deep_discount_sku_count', 0),
        'warehouse_count': logistics_summary.get('warehouse_count', 0),
        'delivery_methods_count': logistics_summary.get('delivery_methods_count', 0),
        'stock_present_sample_total': logistics_summary.get('stock_present_sample_total', 0),
        'stock_reserved_sample_total': logistics_summary.get('stock_reserved_sample_total', 0),
        'stock_reserved_ratio_pct': logistics_summary.get('stock_reserved_ratio_pct', 0),
        'low_stock_warehouses_count': logistics_summary.get('low_stock_warehouses_count', 0),
        'high_reserved_warehouses_count': logistics_summary.get('high_reserved_warehouses_count', 0),
        'empty_stock_warehouses_count': logistics_summary.get('empty_stock_warehouses_count', 0),
    }
    result['overview'] = overview
    result['flags'] = compute_flags(overview)
    result['health_score'] = compute_health_score(result, overview)
    result['insights'] = build_insights(overview, result['flags'])
    result['recommendations'] = build_recommendations(overview, result['flags'])
    return result


def _store_failure_result(store: Dict[str, Any], *, days: int, error: Exception) -> Dict[str, Any]:
    identity = get_store_identity(store)
    return {
        **identity,
        'days': days,
        'ads': None,
        'orders': None,
        'pricing': None,
        'sku_risk': None,
        'sales': None,
        'logistics': None,
        'status': 'error',
        'errors': [{'module': 'daily', 'error': str(error)}],
        'overview': {},
        'flags': [],
        'health_score': 0,
        'insights': [],
        'recommendations': [],
    }


def merge_store_results(
    stores: List[Dict[str, Any]],
    *,
    days: int,
    limit_campaigns: int | None,
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    if not stores:
        return []

    workers = max(1, min(require_positive_int(max_workers, field='max_workers'), len(stores)))
    if workers == 1:
        return [
            merge_store_result(store, days=days, limit_campaigns=limit_campaigns)
            for store in stores
        ]

    results: List[Dict[str, Any] | None] = [None] * len(stores)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {
            executor.submit(merge_store_result, store, days=days, limit_campaigns=limit_campaigns): index
            for index, store in enumerate(stores)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            store = stores[index]
            try:
                results[index] = future.result()
            except Exception as exc:
                results[index] = _store_failure_result(store, days=days, error=exc)

    return [result for result in results if result is not None]


def _trim_list(value: Any, limit: int) -> Any:
    if isinstance(value, list):
        return value[:limit]
    return value


def _compact_module(
    module: Any,
    *,
    drop_keys: List[str] | None = None,
    list_limits: Dict[str, int] | None = None,
) -> Any:
    if not isinstance(module, dict):
        return module
    compact = dict(module)
    for key in (drop_keys or []):
        compact.pop(key, None)
    for key, limit in (list_limits or {}).items():
        compact[key] = _trim_list(compact.get(key), limit)
    return compact


def compact_store_result(result: Dict[str, Any]) -> Dict[str, Any]:
    compact = dict(result)
    compact['ads'] = _compact_module(
        result.get('ads'),
        drop_keys=['detail'],
        list_limits={'alerts': 20},
    )
    compact['orders'] = _compact_module(
        result.get('orders'),
        list_limits={'postings_preview': 20},
    )
    compact['pricing'] = _compact_module(
        result.get('pricing'),
        list_limits={'risky_items_preview': 30},
    )
    compact['sales'] = _compact_module(
        result.get('sales'),
        list_limits={'operations_preview': 30},
    )
    compact['logistics'] = _compact_module(
        result.get('logistics'),
        list_limits={'warehouses': 30, 'stock_items_preview': 50},
    )
    compact['sku_risk'] = _compact_module(
        result.get('sku_risk'),
        drop_keys=['sku_risks'],
        list_limits={'sku_risks_preview': 50},
    )
    return compact


def compact_store_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [compact_store_result(result) for result in results]


def main() -> None:
    try:
        args = build_parser().parse_args()
        require_positive_int(args.days, field='days')
        require_non_negative_int(args.limit_campaigns, field='limit_campaigns')
        require_positive_int(args.max_workers, field='max_workers')
        config = load_config()
        store_filter = (args.store or '').strip()
        selected: List[Dict[str, Any]] = select_stores(config, store_filter)

        results = merge_store_results(
            selected,
            days=args.days,
            limit_campaigns=(args.limit_campaigns or None),
            max_workers=args.max_workers,
        )
        output_results = results if args.include_details else compact_store_results(results)
        flagged = [
            {
                'store_name': item.get('store_name'),
                'store_code': item.get('store_code'),
                'flags': item.get('flags', []),
            }
            for item in output_results if item.get('flags')
        ]
        print_json({
            'days': args.days,
            'store_filter': store_filter,
            'max_workers': args.max_workers,
            'include_details': bool(args.include_details),
            'store_count': len(selected),
            'flagged_stores': flagged,
            'results': output_results,
        })
    except OzonConfigError as exc:
        cli_error(exc)


if __name__ == '__main__':
    main()
