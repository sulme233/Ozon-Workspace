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
    'smoke': 'scripts/smoke_test_interfaces.py',
    'api-smoke': 'scripts/smoke_test_interfaces.py',
    'backup': 'scripts/backup_runtime.py',
    'restore': 'scripts/restore_runtime.py',
}


def configure_stdio() -> None:
    stdout_reconfigure = getattr(sys.stdout, 'reconfigure', None)
    if callable(stdout_reconfigure):
        stdout_reconfigure(encoding='utf-8')
    stderr_reconfigure = getattr(sys.stderr, 'reconfigure', None)
    if callable(stderr_reconfigure):
        stderr_reconfigure(encoding='utf-8')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Unified Ozon workspace CLI')
    parser.add_argument(
        'command',
        nargs='?',
        default='daily',
        help='Pipeline name, maintenance command, check-config, project-status, or list-stores',
    )
    parser.add_argument('command_args', nargs=argparse.REMAINDER, help='Arguments for the selected command')
    return parser


def run_pipeline(pipeline: str, pipeline_args: list[str]) -> int:
    script_path = WORKSPACE / PIPELINES[pipeline]
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    existing_pythonpath = str(env.get('PYTHONPATH') or '').strip()
    env['PYTHONPATH'] = str(WORKSPACE) if not existing_pythonpath else f'{WORKSPACE}{os.pathsep}{existing_pythonpath}'
    cmd = [sys.executable, str(script_path), *pipeline_args]
    return subprocess.run(cmd, cwd=str(WORKSPACE), env=env).returncode


def run_script(script: str, script_args: list[str]) -> int:
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    existing_pythonpath = str(env.get('PYTHONPATH') or '').strip()
    env['PYTHONPATH'] = str(WORKSPACE) if not existing_pythonpath else f'{WORKSPACE}{os.pathsep}{existing_pythonpath}'
    cmd = [sys.executable, str(WORKSPACE / script), *script_args]
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


def build_project_status() -> dict:
    plan_path = WORKSPACE / 'docs' / 'OZON_PROJECT_PLAN.md'
    validate_path = WORKSPACE / 'scripts' / 'validate.py'
    env_example_path = WORKSPACE / '.env.example'
    docker_compose_path = WORKSPACE / 'docker-compose.yml'

    try:
        config_status = inspect_config()
        config_ready = True
        config_error = ''
    except Exception as exc:
        config_status = {
            'config_path': str(WORKSPACE / 'secrets' / 'ozon_accounts.json'),
            'store_count': 0,
            'enabled_store_count': 0,
            'seller_ready_count': 0,
            'performance_ready_count': 0,
        }
        config_ready = False
        config_error = exc.__class__.__name__

    return {
        'status': 'ready' if config_ready else 'needs_config',
        'project': 'Ozon 多店铺经营系统',
        'plan': {
            'path': str(plan_path.relative_to(WORKSPACE)),
            'exists': plan_path.exists(),
        },
        'config': {
            'ready': config_ready,
            'error': config_error,
            'path': config_status.get('config_path', ''),
            'store_count': config_status.get('store_count', 0),
            'enabled_store_count': config_status.get('enabled_store_count', 0),
            'seller_ready_count': config_status.get('seller_ready_count', 0),
            'performance_ready_count': config_status.get('performance_ready_count', 0),
        },
        'quality_gate': {
            'validate_script_exists': validate_path.exists(),
            'default_command': 'python scripts/validate.py',
            'api_smoke_command': 'python run_ozon.py api-smoke --skip-refresh --no-history',
            'full_smoke_command': 'python run_ozon.py smoke --days 2 --max-workers 1 --no-history',
            'pre_release_backup_command': 'python run_ozon.py backup --name pre-release',
        },
        'deployment': {
            'env_example_exists': env_example_path.exists(),
            'docker_compose_exists': docker_compose_path.exists(),
            'deploy_doc': 'docs/DEPLOY.md',
        },
        'protected_runtime_paths': [
            'secrets/',
            'dashboard/data/*.db',
            'dashboard/data/history/',
            'deploy/data/',
            'deploy/secrets/',
            'deploy/*.env',
            'backups/',
        ],
        'known_tooling_issues': [
            'Background agent model config has been updated to Cherry-plus/gpt-5.5; restart the OpenCode session if a running process still uses cached model routing.',
            'Repository search helpers depend on rg; install ripgrep or keep using targeted file reads in this shell.',
        ],
    }


def handle_project_status(command_args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='run_ozon.py project-status', description='Show safe project readiness summary')
    parser.parse_args(command_args)
    print_json(build_project_status())
    return 0


def handle_release_check(command_args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='run_ozon.py release-check', description='Run local pre-release readiness checks')
    parser.add_argument('--no-validate', action='store_true', help='Skip scripts/validate.py')
    parser.add_argument('--backup', action='store_true', help='Create a runtime backup after validation passes')
    parser.add_argument('--backup-name', type=str, default='pre-release', help='Backup name prefix when --backup is used')
    parser.add_argument('--backup-dir', type=str, default='', help='Optional backup output directory')
    parser.add_argument('--api-smoke', action='store_true', help='Run local dashboard API smoke without refresh/history')
    args = parser.parse_args(command_args)

    steps: list[dict[str, object]] = []
    status = build_project_status()
    steps.append({'name': 'project-status', 'status': status.get('status', 'unknown'), 'code': 0})

    if not args.no_validate:
        code = run_script('scripts/validate.py', [])
        steps.append({'name': 'validate', 'code': code})
        if code != 0:
            print_json({'status': 'failed', 'steps': steps})
            return code

    if args.backup:
        backup_args = ['--name', args.backup_name]
        if args.backup_dir:
            backup_args.extend(['--backup-dir', args.backup_dir])
        code = run_pipeline('backup', backup_args)
        steps.append({'name': 'backup', 'code': code})
        if code != 0:
            print_json({'status': 'failed', 'steps': steps})
            return code

    if args.api_smoke:
        code = run_pipeline('api-smoke', ['--skip-refresh', '--no-history'])
        steps.append({'name': 'api-smoke', 'code': code})
        if code != 0:
            print_json({'status': 'failed', 'steps': steps})
            return code

    print_json({'status': 'ok', 'steps': steps})
    return 0


def main() -> int:
    configure_stdio()
    args = build_parser().parse_args()
    command = args.command

    if command == 'check-config':
        return handle_check_config(args.command_args)
    if command == 'project-status':
        return handle_project_status(args.command_args)
    if command == 'release-check':
        return handle_release_check(args.command_args)
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
