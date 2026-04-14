from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

import run_ozon


class RunOzonCliTests(unittest.TestCase):
    def test_smoke_commands_are_registered(self) -> None:
        self.assertEqual(run_ozon.PIPELINES['smoke'], 'scripts/smoke_test_interfaces.py')
        self.assertEqual(run_ozon.PIPELINES['api-smoke'], 'scripts/smoke_test_interfaces.py')

    def test_smoke_command_dispatches_to_pipeline(self) -> None:
        with patch('run_ozon.run_pipeline', return_value=0) as mock_run:
            with patch.object(sys, 'argv', ['run_ozon.py', 'smoke', '--days', '3']):
                code = run_ozon.main()
        self.assertEqual(code, 0)
        mock_run.assert_called_once_with('smoke', ['--days', '3'])

    def test_api_smoke_alias_dispatches_to_pipeline(self) -> None:
        with patch('run_ozon.run_pipeline', return_value=0) as mock_run:
            with patch.object(sys, 'argv', ['run_ozon.py', 'api-smoke', '--startup-timeout', '5']):
                code = run_ozon.main()
        self.assertEqual(code, 0)
        mock_run.assert_called_once_with('api-smoke', ['--startup-timeout', '5'])


if __name__ == '__main__':
    unittest.main()
