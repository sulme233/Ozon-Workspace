from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

import run_ozon


class RunOzonCliTests(unittest.TestCase):
    def test_smoke_commands_are_registered(self) -> None:
        self.assertEqual(run_ozon.PIPELINES['smoke'], 'scripts/smoke_test_interfaces.py')
        self.assertEqual(run_ozon.PIPELINES['api-smoke'], 'scripts/smoke_test_interfaces.py')

    def test_runtime_maintenance_commands_are_registered(self) -> None:
        self.assertEqual(run_ozon.PIPELINES['backup'], 'scripts/backup_runtime.py')
        self.assertEqual(run_ozon.PIPELINES['restore'], 'scripts/restore_runtime.py')

    def test_smoke_command_dispatches_to_pipeline(self) -> None:
        with patch('run_ozon.run_pipeline', return_value=0) as mock_run:
            with patch.object(sys, 'argv', ['run_ozon.py', 'smoke', '--days', '3']):
                code = run_ozon.main()
        self.assertEqual(code, 0)
        mock_run.assert_called_once_with('smoke', ['--days', '3'])

    def test_run_pipeline_adds_workspace_to_pythonpath_for_script_imports(self) -> None:
        with patch('run_ozon.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            code = run_ozon.run_pipeline('backup', ['--name', 'check'])

        self.assertEqual(code, 0)
        env = mock_run.call_args.kwargs['env']
        pythonpath_parts = str(env['PYTHONPATH']).split(os.pathsep)
        self.assertEqual(pythonpath_parts[0], str(run_ozon.WORKSPACE))
        self.assertIn('PYTHONIOENCODING', env)

    def test_api_smoke_alias_dispatches_to_pipeline(self) -> None:
        with patch('run_ozon.run_pipeline', return_value=0) as mock_run:
            with patch.object(sys, 'argv', ['run_ozon.py', 'api-smoke', '--startup-timeout', '5']):
                code = run_ozon.main()
        self.assertEqual(code, 0)
        mock_run.assert_called_once_with('api-smoke', ['--startup-timeout', '5'])

    def test_backup_command_dispatches_to_pipeline(self) -> None:
        with patch('run_ozon.run_pipeline', return_value=0) as mock_run:
            with patch.object(sys, 'argv', ['run_ozon.py', 'backup', '--name', 'pre-release']):
                code = run_ozon.main()
        self.assertEqual(code, 0)
        mock_run.assert_called_once_with('backup', ['--name', 'pre-release'])

    def test_restore_command_dispatches_to_pipeline(self) -> None:
        with patch('run_ozon.run_pipeline', return_value=0) as mock_run:
            with patch.object(sys, 'argv', ['run_ozon.py', 'restore', 'backups/example.zip', '--yes']):
                code = run_ozon.main()
        self.assertEqual(code, 0)
        mock_run.assert_called_once_with('restore', ['backups/example.zip', '--yes'])

    def test_project_status_handles_missing_config_safely(self) -> None:
        with patch('run_ozon.inspect_config', side_effect=RuntimeError('api_key=secret-value')):
            status = run_ozon.build_project_status()

        self.assertEqual(status['status'], 'needs_config')
        self.assertFalse(status['config']['ready'])
        self.assertEqual(status['config']['error'], 'RuntimeError')
        self.assertNotIn('secret-value', str(status))
        self.assertNotIn('api_key', str(status))
        self.assertIn('python scripts/validate.py', status['quality_gate']['default_command'])
        self.assertIn('python run_ozon.py backup', status['quality_gate']['pre_release_backup_command'])
        self.assertIn('secrets/', status['protected_runtime_paths'])
        self.assertTrue(any('gpt-5.5' in item for item in status['known_tooling_issues']))

    def test_project_status_command_prints_summary(self) -> None:
        fake_status = {'status': 'ready', 'project': 'Ozon 多店铺经营系统'}
        with patch('run_ozon.build_project_status', return_value=fake_status):
            with patch('run_ozon.print_json') as mock_print:
                with patch.object(sys, 'argv', ['run_ozon.py', 'project-status']):
                    code = run_ozon.main()

        self.assertEqual(code, 0)
        mock_print.assert_called_once_with(fake_status)

    def test_release_check_runs_validate_by_default(self) -> None:
        with patch('run_ozon.build_project_status', return_value={'status': 'ready'}):
            with patch('run_ozon.run_script', return_value=0) as mock_script:
                with patch('run_ozon.run_pipeline') as mock_pipeline:
                    with patch('run_ozon.print_json') as mock_print:
                        with patch.object(sys, 'argv', ['run_ozon.py', 'release-check']):
                            code = run_ozon.main()

        self.assertEqual(code, 0)
        mock_script.assert_called_once_with('scripts/validate.py', [])
        mock_pipeline.assert_not_called()
        mock_print.assert_called_once()
        self.assertEqual(mock_print.call_args.args[0]['status'], 'ok')

    def test_release_check_can_skip_validate_and_run_backup(self) -> None:
        with patch('run_ozon.build_project_status', return_value={'status': 'ready'}):
            with patch('run_ozon.run_script') as mock_script:
                with patch('run_ozon.run_pipeline', return_value=0) as mock_pipeline:
                    with patch('run_ozon.print_json'):
                        with patch.object(
                            sys,
                            'argv',
                            ['run_ozon.py', 'release-check', '--no-validate', '--backup', '--backup-name', 'ship', '--backup-dir', 'backups/test'],
                        ):
                            code = run_ozon.main()

        self.assertEqual(code, 0)
        mock_script.assert_not_called()
        mock_pipeline.assert_called_once_with('backup', ['--name', 'ship', '--backup-dir', 'backups/test'])

    def test_release_check_propagates_validation_failure(self) -> None:
        with patch('run_ozon.build_project_status', return_value={'status': 'ready'}):
            with patch('run_ozon.run_script', return_value=7):
                with patch('run_ozon.run_pipeline') as mock_pipeline:
                    with patch('run_ozon.print_json') as mock_print:
                        with patch.object(sys, 'argv', ['run_ozon.py', 'release-check']):
                            code = run_ozon.main()

        self.assertEqual(code, 7)
        mock_pipeline.assert_not_called()
        self.assertEqual(mock_print.call_args.args[0]['status'], 'failed')

    def test_release_check_can_run_local_api_smoke(self) -> None:
        with patch('run_ozon.build_project_status', return_value={'status': 'ready'}):
            with patch('run_ozon.run_script', return_value=0):
                with patch('run_ozon.run_pipeline', return_value=0) as mock_pipeline:
                    with patch('run_ozon.print_json'):
                        with patch.object(sys, 'argv', ['run_ozon.py', 'release-check', '--api-smoke']):
                            code = run_ozon.main()

        self.assertEqual(code, 0)
        mock_pipeline.assert_called_once_with('api-smoke', ['--skip-refresh', '--no-history'])


if __name__ == '__main__':
    unittest.main()
