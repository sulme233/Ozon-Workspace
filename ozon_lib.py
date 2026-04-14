from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, NoReturn, Optional, Tuple

import requests


WORKSPACE = pathlib.Path(__file__).resolve().parent
DEFAULT_CONFIG = WORKSPACE / 'secrets' / 'ozon_accounts.json'
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.5


class OzonConfigError(RuntimeError):
    pass


class OzonApiError(RuntimeError):
    pass


def normalize_text(value: Any) -> str:
    return str(value or '').strip().casefold()


def load_config(path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if not cfg_path.exists():
        raise OzonConfigError(f'Config file not found: {cfg_path}')
    return json.loads(cfg_path.read_text(encoding='utf-8-sig'))


def iter_enabled_stores(config: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for store in config.get('stores', []):
        if store.get('enabled', True):
            yield store


def get_store_identity(store: Dict[str, Any]) -> Dict[str, str]:
    return {
        'store_name': str(store.get('store_name', '')).strip(),
        'store_code': str(store.get('store_code', '')).strip(),
        'currency': str(store.get('currency', '')).strip(),
    }


def store_matches_filter(store: Dict[str, Any], store_filter: str) -> bool:
    selector = normalize_text(store_filter)
    if not selector:
        return True

    identity = get_store_identity(store)
    candidates = [normalize_text(identity['store_name']), normalize_text(identity['store_code'])]
    return any(selector == candidate or selector in candidate for candidate in candidates if candidate)


def select_stores(config: Dict[str, Any], store_filter: str = '') -> List[Dict[str, Any]]:
    selected = [store for store in iter_enabled_stores(config) if store_matches_filter(store, store_filter)]
    if selected:
        return selected

    if store_filter.strip():
        available = []
        for store in iter_enabled_stores(config):
            identity = get_store_identity(store)
            label = identity['store_name']
            if identity['store_code']:
                label = f"{label} ({identity['store_code']})" if label else identity['store_code']
            if label:
                available.append(label)
        available_text = ', '.join(available) if available else 'no enabled stores'
        raise OzonConfigError(f'Store filter did not match any enabled store: {store_filter}. Available: {available_text}')

    raise OzonConfigError('No enabled stores found in config')


def require_positive_int(value: int, *, field: str) -> int:
    if value <= 0:
        raise OzonConfigError(f'{field} must be greater than 0')
    return value


def require_non_negative_int(value: int, *, field: str) -> int:
    if value < 0:
        raise OzonConfigError(f'{field} must be greater than or equal to 0')
    return value


def summarize_store_credentials(store: Dict[str, Any]) -> Dict[str, Any]:
    identity = get_store_identity(store)
    seller = store.get('seller_api') or {}
    perf = store.get('performance_api') or {}
    return {
        **identity,
        'enabled': bool(store.get('enabled', True)),
        'has_seller_client_id': bool(str(seller.get('client_id', '')).strip()),
        'has_seller_api_key': bool(str(seller.get('api_key', '')).strip()),
        'has_perf_client_id': bool(str(perf.get('client_id', '')).strip()),
        'has_perf_client_secret': bool(str(perf.get('client_secret', '')).strip()),
    }


def inspect_config(path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    config = load_config(path)
    stores = [summarize_store_credentials(store) for store in config.get('stores', [])]
    return {
        'config_path': str(path or DEFAULT_CONFIG),
        'store_count': len(stores),
        'enabled_store_count': sum(1 for store in stores if store['enabled']),
        'seller_ready_count': sum(
            1 for store in stores if store['has_seller_client_id'] and store['has_seller_api_key']
        ),
        'performance_ready_count': sum(
            1 for store in stores if store['has_perf_client_id'] and store['has_perf_client_secret']
        ),
        'stores': stores,
    }


def list_store_identities(config: Optional[Dict[str, Any]] = None, *, include_disabled: bool = False) -> List[Dict[str, Any]]:
    active_config = config or load_config()
    stores = active_config.get('stores', []) if include_disabled else list(iter_enabled_stores(active_config))
    return [summarize_store_credentials(store) for store in stores]


def seller_headers(store: Dict[str, Any]) -> Dict[str, str]:
    seller = store.get('seller_api') or {}
    client_id = str(seller.get('client_id', '')).strip()
    api_key = str(seller.get('api_key', '')).strip()
    if not client_id or not api_key:
        raise OzonConfigError(f"Missing seller_api credentials for store: {store.get('store_name', '')}")
    return {
        'Client-Id': client_id,
        'Api-Key': api_key,
        'Content-Type': 'application/json',
    }


def perf_headers(token: str) -> Dict[str, str]:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }


def today_range(days: int = 7) -> Tuple[dt.date, dt.date]:
    require_positive_int(days, field='days')
    end = dt.date.today()
    start = end - dt.timedelta(days=days - 1)
    return start, end


def utc_day_range(days: int = 7) -> Tuple[str, str]:
    require_positive_int(days, field='days')
    end = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - dt.timedelta(days=days)
    return start.strftime('%Y-%m-%dT%H:%M:%SZ'), end.strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_csv_semicolon(text: str) -> List[Dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split(';')]
    rows: List[Dict[str, str]] = []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(';')]
        if len(parts) < len(header):
            parts += [''] * (len(header) - len(parts))
        rows.append(dict(zip(header, parts)))
    return rows


def ru_num(value: Any) -> float:
    s = str(value).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    if not s:
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {'raw': response.text[:1000]}


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Any] = None,
    json_body: Optional[Any] = None,
    data: Optional[Any] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    retry_statuses: Optional[Iterable[int]] = None,
) -> requests.Response:
    statuses = set(retry_statuses or {429, 500, 502, 503, 504})
    last_error: Exception | None = None
    response: requests.Response | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                data=data,
                timeout=timeout,
            )
            if response.status_code not in statuses or attempt >= retries:
                return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retries:
                break

        time.sleep(retry_delay * attempt)

    if response is not None:
        return response
    raise OzonApiError(f'Request failed after {retries} attempts: {method.upper()} {url}: {last_error}')


def request_json(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Any] = None,
    json_body: Optional[Any] = None,
    data: Optional[Any] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    expected_status: int = 200,
    error_context: str = 'API request failed',
) -> Any:
    response = request_with_retry(
        method,
        url,
        headers=headers,
        params=params,
        json_body=json_body,
        data=data,
        timeout=timeout,
        retries=retries,
    )
    if response.status_code != expected_status:
        raise OzonApiError(f'{error_context}: {response.status_code} {response.text[:300]}')
    return safe_json(response)


def request_csv(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Any] = None,
    json_body: Optional[Any] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    expected_status: int = 200,
    error_context: str = 'API request failed',
) -> str:
    response = request_with_retry(
        method,
        url,
        headers=headers,
        params=params,
        json_body=json_body,
        timeout=timeout,
        retries=retries,
    )
    if response.status_code != expected_status:
        raise OzonApiError(f'{error_context}: {response.status_code} {response.text[:300]}')
    return response.text


def print_json(payload: Dict[str, Any]) -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cli_error(exc: Exception) -> NoReturn:
    raise SystemExit(str(exc))


def run_store_pipeline(
    *,
    config: Dict[str, Any],
    store_filter: str,
    analyzer: Callable[..., Dict[str, Any]],
    analyzer_kwargs: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = select_stores(config, store_filter)
    results: List[Dict[str, Any]] = []
    kwargs = analyzer_kwargs or {}
    for store in selected:
        try:
            results.append(analyzer(store, **kwargs))
        except Exception as exc:
            results.append({
                **get_store_identity(store),
                'status': 'error',
                'error': str(exc),
            })
    return selected, results


def get_perf_token(store: Dict[str, Any], timeout: int = 30) -> str:
    perf = store.get('performance_api') or {}
    client_id = str(perf.get('client_id', '')).strip()
    client_secret = str(perf.get('client_secret', '')).strip()
    if not client_id or not client_secret:
        raise OzonConfigError(f"Missing performance_api credentials for store: {store.get('store_name', '')}")
    data = request_json(
        'POST',
        'https://api-performance.ozon.ru/api/client/token',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        json_body={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials',
        },
        timeout=timeout,
        error_context='Failed to get performance token',
    )
    token = data.get('access_token')
    if not token:
        raise OzonApiError('Performance token response did not include access_token')
    return token


def fetch_perf_campaigns(store: Dict[str, Any], timeout: int = 30) -> List[Dict[str, Any]]:
    token = get_perf_token(store, timeout=timeout)
    data = request_json(
        'GET',
        'https://api-performance.ozon.ru/api/client/campaign',
        headers=perf_headers(token),
        timeout=timeout,
        error_context='Failed to fetch performance campaigns',
    )
    return data.get('list', []) if isinstance(data, dict) else []


def fetch_finance_transactions(store: Dict[str, Any], days: int = 7, page_size: int = 1000, timeout: int = 60) -> List[Dict[str, Any]]:
    require_positive_int(days, field='days')
    require_positive_int(page_size, field='page_size')
    since, to = utc_day_range(days=days)
    body = {
        'filter': {
            'date': {'from': since, 'to': to},
            'transaction_type': 'all',
            'operation_type': [],
        },
        'page': 1,
        'page_size': page_size,
    }
    data = request_json(
        'POST',
        'https://api-seller.ozon.ru/v3/finance/transaction/list',
        headers=seller_headers(store),
        json_body=body,
        timeout=timeout,
        error_context='Failed to fetch finance transactions',
    )
    return data.get('result', {}).get('operations', []) if isinstance(data, dict) else []


def fetch_fbs_postings(
    store: Dict[str, Any],
    *,
    since: str,
    to: str,
    statuses: Optional[List[str]] = None,
    limit: int = 100,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    require_positive_int(limit, field='limit')
    status_values = [str(status).strip() for status in (statuses or []) if str(status).strip()]
    filter_body: Dict[str, Any] = {
        'since': since,
        'to': to,
    }
    if status_values:
        filter_body['status'] = status_values
    body: Dict[str, Any] = {
        'dir': 'DESC',
        'filter': filter_body,
        'limit': limit,
        'offset': 0,
        'with': {
            'analytics_data': True,
            'barcodes': False,
            'financial_data': False,
        },
    }
    data = request_json(
        'POST',
        'https://api-seller.ozon.ru/v3/posting/fbs/list',
        headers=seller_headers(store),
        json_body=body,
        timeout=timeout,
        error_context='Failed to fetch FBS postings',
    )
    result = data.get('result', {}) if isinstance(data, dict) else {}
    postings = result.get('postings', []) if isinstance(result, dict) else []
    return postings if isinstance(postings, list) else []


def fetch_fbs_unfulfilled_postings(store: Dict[str, Any], limit: int = 100, timeout: int = 60) -> List[Dict[str, Any]]:
    require_positive_int(limit, field='limit')
    body: Dict[str, Any] = {
        'dir': 'ASC',
        'filter': {},
        'limit': limit,
        'offset': 0,
        'with': {
            'analytics_data': True,
            'barcodes': False,
            'financial_data': False,
        },
    }
    data = request_json(
        'POST',
        'https://api-seller.ozon.ru/v3/posting/fbs/unfulfilled/list',
        headers=seller_headers(store),
        json_body=body,
        timeout=timeout,
        error_context='Failed to fetch unfulfilled FBS postings',
    )
    result = data.get('result', {}) if isinstance(data, dict) else {}
    postings = result.get('postings', []) if isinstance(result, dict) else []
    return postings if isinstance(postings, list) else []


def fetch_product_prices(store: Dict[str, Any], limit: int = 100, timeout: int = 60) -> List[Dict[str, Any]]:
    require_positive_int(limit, field='limit')
    body: Dict[str, Any] = {
        'cursor': '',
        'filter': {'visibility': 'ALL'},
        'limit': limit,
    }
    data = request_json(
        'POST',
        'https://api-seller.ozon.ru/v5/product/info/prices',
        headers=seller_headers(store),
        json_body=body,
        timeout=timeout,
        error_context='Failed to fetch product prices',
    )
    items = data.get('items', []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []
