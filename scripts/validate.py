from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]

PYTHON_COMPILE_TARGETS = [
    'run_ozon.py',
    'run_ozon_dashboard.py',
    'ozon_lib.py',
    'ozon_db.py',
    'ozon_api_catalog.py',
    'dashboard_auth.py',
    'dashboard_jobs.py',
    'dashboard_probe.py',
    'dashboard_store_config.py',
    'run_ozon_ads_pipeline.py',
    'run_ozon_daily_pipeline.py',
    'run_ozon_logistics_pipeline.py',
    'run_ozon_orders_pipeline.py',
    'run_ozon_pricing_pipeline.py',
    'run_ozon_sales_pipeline.py',
    'run_ozon_sku_risk_pipeline.py',
    'scripts/backup_runtime.py',
    'scripts/manage_admin.py',
    'scripts/restore_runtime.py',
    'scripts/smoke_test_interfaces.py',
    'scripts/validate.py',
]

def dashboard_js_targets() -> list[str]:
    return sorted(str(path.relative_to(WORKSPACE)) for path in (WORKSPACE / 'dashboard').glob('*.js'))


def run_step(name: str, command: list[str]) -> int:
    print(f'==> {name}')
    result = subprocess.run(command, cwd=str(WORKSPACE))
    if result.returncode != 0:
        print(f'FAILED: {name}', file=sys.stderr)
    return int(result.returncode)


def main() -> int:
    steps: list[tuple[str, list[str]]] = [
        ('unit tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']),
        ('python compile', [sys.executable, '-m', 'py_compile', *PYTHON_COMPILE_TARGETS]),
    ]

    if shutil.which('node'):
        steps.extend((f'js syntax: {target}', ['node', '--check', target]) for target in dashboard_js_targets())
    else:
        print('SKIP: node not found, JavaScript syntax checks were not run')

    for name, command in steps:
        code = run_step(name, command)
        if code != 0:
            return code

    print('OK: validation passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
