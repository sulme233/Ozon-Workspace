from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from ozon_lib import inspect_config, list_store_identities, load_config, print_json


WORKSPACE = Path(__file__).resolve().parent
PIPELINES = {
    'ads': 'run_ozon_ads_pipeline.py',
    'sales': 'run_ozon_sales_pipeline.py',
    'orders': 'run_ozon_orders_pipeline.py',
    'pricing': 'run_ozon_pricing_pipeline.py',
    'sku-risk': 'run_ozon_sku_risk_pipeline.py',
    'logistics': 'run_ozon_logistics_pipeline.py',
    'daily': 'run_ozon_daily_pipeline.py',
    'dashboard': 'run_ozon_dashboard.py',
    'refresh': 'run_ozon_dashboard.py',
}


def configure_stdio() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Unified Ozon workspace CLI')
    parser.add_argument(
        'command',
        nargs='?',
        default='daily',
        help='Pipeline name, check-config, or list-stores',
    )
    parser.add_argument('command_args', nargs=argparse.REMAINDER, help='Arguments for the selected command')
    return parser


def run_pipeline(pipeline: str, pipeline_args: list[str]) -> int:
    script_path = WORKSPACE / PIPELINES[pipeline]
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    cmd = [sys.executable, str(script_path), *pipeline_args]
    return subprocess.run(cmd, cwd=str(WORKSPACE), env=env).returncode


def handle_list_stores(command_args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='run_ozon.py list-stores', description='Show configured stores')
    parser.add_argument('--all', action='store_true', help='Include disabled stores')
    args = parser.parse_args(command_args)
    print_json({'stores': list_store_identities(load_config(), include_disabled=bool(args.all))})
    return 0


def handle_check_config(command_args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='run_ozon.py check-config', description='Inspect config readiness')
    parser.parse_args(command_args)
    print_json(inspect_config())
    return 0


def main() -> int:
    configure_stdio()
    args = build_parser().parse_args()
    command = args.command

    if command == 'check-config':
        return handle_check_config(args.command_args)
    if command == 'list-stores':
        return handle_list_stores(args.command_args)
    if command == 'run':
        if not args.command_args:
            raise SystemExit('run requires a pipeline name')
        pipeline = args.command_args[0]
        pipeline_args = args.command_args[1:]
        if pipeline not in PIPELINES:
            raise SystemExit(f'Unknown pipeline: {pipeline}')
        return run_pipeline(pipeline, pipeline_args)
    if command not in PIPELINES:
        raise SystemExit(f'Unknown command: {command}')
    return run_pipeline(command, args.command_args)


if __name__ == '__main__':
    raise SystemExit(main())
