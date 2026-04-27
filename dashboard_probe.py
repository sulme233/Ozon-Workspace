from __future__ import annotations

from typing import Any, Dict

from ozon_lib import (
    fetch_fbs_postings,
    fetch_fbs_unfulfilled_postings,
    fetch_perf_campaigns,
    fetch_product_prices,
    fetch_warehouses,
    get_store_identity,
    load_config,
    require_positive_int,
    select_stores,
    today_range,
)


def run_ozon_live_probe(
    *,
    store_filter: str = '',
    days: int = 7,
    request_timeout: int = 30,
    now_text_func=None,
    load_config_func=load_config,
    select_stores_func=select_stores,
    today_range_func=today_range,
    fetch_perf_campaigns_func=fetch_perf_campaigns,
    fetch_product_prices_func=fetch_product_prices,
    fetch_warehouses_func=fetch_warehouses,
    fetch_fbs_postings_func=fetch_fbs_postings,
    fetch_fbs_unfulfilled_postings_func=fetch_fbs_unfulfilled_postings,
) -> Dict[str, Any]:
    require_positive_int(days, field='days')
    require_positive_int(request_timeout, field='request_timeout')

    config = load_config_func()
    selected = select_stores_func(config, store_filter)
    store = selected[0]
    identity = get_store_identity(store)
    start, end = today_range_func(days=days)
    now_value = now_text_func() if now_text_func else ''

    result: Dict[str, Any] = {
        **identity,
        'days': days,
        'date_from': start.isoformat(),
        'date_to': end.isoformat(),
        'status': 'ok',
        'generated_at': now_value,
        'errors': [],
        'warnings': [],
        'checks': {},
    }

    try:
        campaigns = fetch_perf_campaigns_func(store, timeout=request_timeout)
        sku_campaigns = [item for item in campaigns if str(item.get('advObjectType')) == 'SKU']
        result['checks']['campaigns'] = {
            'total_count': len(campaigns),
            'sku_count': len(sku_campaigns),
        }
    except Exception as exc:
        result['errors'].append({'module': 'campaigns', 'error': str(exc)})
        result['checks']['campaigns'] = {'total_count': 0, 'sku_count': 0}

    try:
        prices = fetch_product_prices_func(store, limit=100, timeout=request_timeout)
        no_price = 0
        discounted = 0
        for item in prices:
            price = (item.get('price') or {})
            price_value = float(price.get('price') or 0) if isinstance(price, dict) else 0.0
            old_price_value = float(price.get('old_price') or 0) if isinstance(price, dict) else 0.0
            if price_value <= 0:
                no_price += 1
            if old_price_value > 0 and price_value > 0 and price_value < old_price_value:
                discounted += 1
        result['checks']['prices'] = {
            'sample_count': len(prices),
            'no_price_count': no_price,
            'discounted_count': discounted,
        }
    except Exception as exc:
        result['errors'].append({'module': 'prices', 'error': str(exc)})
        result['checks']['prices'] = {'sample_count': 0, 'no_price_count': 0, 'discounted_count': 0}

    try:
        warehouses = fetch_warehouses_func(store, limit=200, timeout=request_timeout)
        inactive_statuses = {'DISABLED', 'ARCHIVED', 'BLOCKED', 'INACTIVE'}
        active_count = 0
        inactive_count = 0
        for warehouse in warehouses:
            status = str(warehouse.get('status') or '').strip().upper()
            if status and status in inactive_statuses:
                inactive_count += 1
            else:
                active_count += 1
        result['checks']['warehouses'] = {
            'count': len(warehouses),
            'active_count': active_count,
            'inactive_count': inactive_count,
        }
    except Exception as exc:
        result['errors'].append({'module': 'warehouses', 'error': str(exc)})
        result['checks']['warehouses'] = {'count': 0, 'active_count': 0, 'inactive_count': 0}

    since = f'{start.isoformat()}T00:00:00Z'
    to = f'{end.isoformat()}T23:59:59Z'
    try:
        postings = fetch_fbs_postings_func(
            store,
            since=since,
            to=to,
            statuses=[],
            limit=100,
            timeout=request_timeout,
        )
        status_counts: Dict[str, int] = {}
        for posting in postings:
            status = str(posting.get('status') or 'unknown')
            status_counts[status] = int(status_counts.get(status) or 0) + 1
        result['checks']['postings'] = {
            'sample_count': len(postings),
            'status_counts': status_counts,
        }
    except Exception as exc:
        result['errors'].append({'module': 'postings', 'error': str(exc)})
        result['checks']['postings'] = {'sample_count': 0, 'status_counts': {}}

    try:
        unfulfilled = fetch_fbs_unfulfilled_postings_func(store, limit=100, timeout=request_timeout)
        result['checks']['unfulfilled'] = {'count': len(unfulfilled)}
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if 'mismatch between cutoff' in lowered or ('cutoff' in lowered and 'delivery date' in lowered):
            result['warnings'].append({'module': 'unfulfilled', 'warning': message})
        else:
            result['errors'].append({'module': 'unfulfilled', 'error': message})
        result['checks']['unfulfilled'] = {'count': 0}

    if result['errors']:
        result['status'] = 'partial' if result['checks'] else 'error'
    return result
