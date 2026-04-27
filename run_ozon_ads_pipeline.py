from __future__ import annotations

import argparse
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from ozon_lib import (
    OzonApiError,
    OzonConfigError,
    cli_error,
    get_perf_token,
    get_store_identity,
    load_config,
    parse_csv_semicolon,
    perf_headers,
    print_json,
    request_csv,
    request_json,
    require_non_negative_int,
    require_positive_int,
    ru_num,
    run_store_pipeline,
    today_range,
)


def is_future_interval_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return 'future' in message or 'будущ' in message


def pick_value(row: Dict[str, Any], keys: List[str], default: Any = '0') -> Any:
    for key in keys:
        if key in row:
            return row.get(key, default)
    return default


def classify_ad_row(clicks: int, carts: int, orders: int, expense: float, roas: float) -> Dict[str, str]:
    if orders >= 3 and roas >= 8:
        return {
            'action': '强力放量',
            'abnormal_type': '高表现',
            'risk': '高',
            'reason': '活动有订单且投产高，建议优先放量。',
        }
    if clicks >= 30 and carts > 0 and orders == 0:
        return {
            'action': '重点优化转化',
            'abnormal_type': '有加购无转化',
            'risk': '中',
            'reason': '已有点击和加购，但暂无订单，优先检查价格、主图、评价和详情页。',
        }
    if clicks >= 30 and orders == 0 and expense > 0:
        return {
            'action': '观察优化',
            'abnormal_type': '有点击无转化',
            'risk': '中',
            'reason': '已有点击和花费，但暂无订单，建议持续观察并优化转化。',
        }
    if expense > 0 and orders == 0:
        return {
            'action': '观察优化',
            'abnormal_type': '低转化',
            'risk': '低',
            'reason': '已有花费但暂无订单，样本较小，继续观察。',
        }
    return {
        'action': '继续投放',
        'abnormal_type': '正常',
        'risk': '低',
        'reason': '当前数据量有限，先持续跟踪。',
    }


def fetch_campaign_objects(
    headers: Dict[str, str],
    campaign_ids: List[str],
    *,
    max_workers: int = 8,
) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}

    if not campaign_ids:
        return result

    workers = max(1, min(max_workers, len(campaign_ids)))
    if workers == 1:
        for cid in campaign_ids:
            try:
                data = request_json(
                    'GET',
                    f'https://api-performance.ozon.ru/api/client/campaign/{cid}/objects',
                    headers=headers,
                    timeout=30,
                    error_context=f'Failed to fetch campaign objects for {cid}',
                )
                result[cid] = data.get('list', []) if isinstance(data, dict) else []
            except Exception:
                result[cid] = []
        return result

    def fetch_one(cid: str) -> tuple[str, List[Dict[str, Any]]]:
        try:
            data = request_json(
                'GET',
                f'https://api-performance.ozon.ru/api/client/campaign/{cid}/objects',
                headers=headers,
                timeout=30,
                error_context=f'Failed to fetch campaign objects for {cid}',
            )
            return cid, data.get('list', []) if isinstance(data, dict) else []
        except Exception:
            return cid, []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(fetch_one, cid): cid for cid in campaign_ids}
        for future in as_completed(future_map):
            cid = future_map[future]
            try:
                key, payload = future.result()
                result[key] = payload
            except Exception:
                result[cid] = []
    return result


def analyze_store_ads(
    store: Dict[str, Any],
    days: int = 7,
    limit_campaigns: int | None = None,
    object_workers: int = 8,
) -> Dict[str, Any]:
    start, end = today_range(days=days)
    token = get_perf_token(store)
    headers = perf_headers(token)

    campaigns_data = request_json(
        'GET',
        'https://api-performance.ozon.ru/api/client/campaign',
        headers=headers,
        timeout=30,
        error_context='Failed to fetch campaigns',
    )
    campaigns = campaigns_data.get('list', []) if isinstance(campaigns_data, dict) else []
    sku_campaigns = [c for c in campaigns if str(c.get('advObjectType')) == 'SKU']
    campaign_ids = [str(c.get('id')) for c in sku_campaigns if c.get('id')]
    if limit_campaigns:
        campaign_ids = campaign_ids[:limit_campaigns]

    if not campaign_ids:
        return {
            **get_store_identity(store),
            'status': 'no_campaigns',
            'date_from': start.isoformat(),
            'date_to': end.isoformat(),
            'summary': {},
            'detail': [],
            'alerts': [],
        }

    query = [('campaignIds', cid) for cid in campaign_ids] + [('dateFrom', start.isoformat()), ('dateTo', end.isoformat())]
    try:
        csv_text = request_csv(
            'GET',
            'https://api-performance.ozon.ru/api/client/statistics/campaign/product',
            headers=headers,
            params=query,
            timeout=60,
            error_context='Failed to fetch product campaign statistics',
        )
    except OzonApiError as exc:
        # Some accounts reject same-day ranges as future intervals; retry on yesterday.
        if not is_future_interval_error(exc):
            raise
        fallback_end = end - dt.timedelta(days=1)
        fallback_start = fallback_end - dt.timedelta(days=max(days - 1, 0))
        query = [('campaignIds', cid) for cid in campaign_ids] + [
            ('dateFrom', fallback_start.isoformat()),
            ('dateTo', fallback_end.isoformat()),
        ]
        csv_text = request_csv(
            'GET',
            'https://api-performance.ozon.ru/api/client/statistics/campaign/product',
            headers=headers,
            params=query,
            timeout=60,
            error_context='Failed to fetch product campaign statistics',
        )
        start, end = fallback_start, fallback_end
    rows = parse_csv_semicolon(csv_text)
    objects_map = fetch_campaign_objects(headers, campaign_ids, max_workers=object_workers)

    detail = []
    alerts = []
    total_expense = total_revenue = total_orders = total_impr = total_clicks = total_carts = 0.0
    high_count = low_count = zero_count = 0
    reasons: List[str] = []

    for row in rows:
        campaign_id = str(pick_value(row, ['ID', 'Campaign ID', 'campaign_id', 'CampaignId'], '')).strip()
        expense = ru_num(pick_value(row, ['Расход, ₽', 'Расход, руб.', 'Expense, ₽', 'Expense, RUB', 'Expense']))
        revenue = ru_num(pick_value(row, ['Продажи, ₽', 'Продажи, руб.', 'Revenue, ₽', 'Revenue, RUB', 'Revenue']))
        orders = int(ru_num(pick_value(row, ['Заказы, шт.', 'Заказы', 'Orders, pcs', 'Orders'])))
        impressions = int(ru_num(pick_value(row, ['Показы', 'Impressions'])))
        clicks = int(ru_num(pick_value(row, ['Клики', 'Clicks'])))
        carts = int(ru_num(pick_value(row, ['В корзину', 'Cart Adds', 'Add to cart'])))
        ctr = ru_num(pick_value(row, ['CTR']))
        cpc = ru_num(
            pick_value(
                row,
                ['Средняя стоимость клика, ₽', 'Средняя цена клика, ₽', 'Avg CPC, ₽', 'Average CPC, ₽', 'CPC'],
            )
        )
        roas = revenue / expense if expense else 0.0
        obj_ids = [str(x.get('id', '')) for x in objects_map.get(campaign_id, [])[:5]]
        rule = classify_ad_row(clicks, carts, orders, expense, roas)

        item = {
            'campaign_id': campaign_id,
            'campaign_name': pick_value(row, ['Название', 'Campaign Name', 'campaign_name'], ''),
            'sku_preview': obj_ids,
            'expense_rub': round(expense, 2),
            'revenue_rub': round(revenue, 2),
            'orders': orders,
            'impressions': impressions,
            'clicks': clicks,
            'cart_adds': carts,
            'ctr_pct': round(ctr * 100 if ctr <= 1 else ctr, 2),
            'avg_cpc_rub': round(cpc, 2),
            'acos_pct': round((expense / revenue * 100) if revenue else 0, 2),
            'roas': round(roas, 2),
            **rule,
        }
        detail.append(item)

        total_expense += expense
        total_revenue += revenue
        total_orders += orders
        total_impr += impressions
        total_clicks += clicks
        total_carts += carts
        if rule['action'] == '强力放量':
            high_count += 1
        if rule['action'] in ('重点优化转化', '观察优化'):
            low_count += 1
        if orders == 0 and expense > 0:
            zero_count += 1
        if rule['reason'] not in reasons:
            reasons.append(rule['reason'])
        if rule['abnormal_type'] != '正常':
            alerts.append(item)

    summary = {
        'date_from': start.isoformat(),
        'date_to': end.isoformat(),
        'campaign_count': len(campaign_ids),
        'advertising_expense_rub': round(total_expense, 2),
        'revenue_rub': round(total_revenue, 2),
        'orders': int(total_orders),
        'impressions': int(total_impr),
        'clicks': int(total_clicks),
        'cart_adds': int(total_carts),
        'avg_ctr_pct': round((total_clicks / total_impr * 100) if total_impr else 0, 2),
        'avg_cpc_rub': round((total_expense / total_clicks) if total_clicks else 0, 2),
        'overall_roas': round((total_revenue / total_expense) if total_expense else 0, 2),
        'high_count': high_count,
        'low_count': low_count,
        'zero_order_count': zero_count,
        'summary_text': '；'.join(reasons[:3]) if reasons else '广告数据已成功拉取，继续观察。',
    }
    return {
        **get_store_identity(store),
        'status': 'ok',
        'summary': summary,
        'detail': detail,
        'alerts': alerts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ozon 广告分析流水线')
    parser.add_argument('--days', type=int, default=7, help='统计天数，默认 7')
    parser.add_argument('--store', type=str, default='', help='指定店铺名称或店铺代号')
    parser.add_argument('--limit-campaigns', type=int, default=0, help='限制广告活动数量，0 表示不限制')
    parser.add_argument('--object-workers', type=int, default=8, help='并发拉取广告对象详情的线程数')
    return parser


def main() -> None:
    try:
        args = build_parser().parse_args()
        require_positive_int(args.days, field='days')
        require_non_negative_int(args.limit_campaigns, field='limit_campaigns')
        require_positive_int(args.object_workers, field='object_workers')
        config = load_config()
        store_filter = (args.store or '').strip()
        selected, results = run_store_pipeline(
            config=config,
            store_filter=store_filter,
            analyzer=analyze_store_ads,
            analyzer_kwargs={
                'days': args.days,
                'limit_campaigns': (args.limit_campaigns or None),
                'object_workers': args.object_workers,
            },
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
