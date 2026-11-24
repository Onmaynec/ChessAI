"""Regression tests for Windows state-file sharing violations (v0.4.1)."""
import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.server as dashboard
from neural.selfplay import atomic_json


class DashboardFileAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.addCleanup(dashboard.read_issues.clear)
        self.addCleanup(dashboard.last_json.clear)
        self.addCleanup(dashboard.last_jsonl.clear)
        self.addCleanup(dashboard.last_text.clear)

    def test_json_read_retries_a_transient_access_denial(self):
        target = self.root / 'run_state.json'
        target.write_text('{"iteration": 100, "status": "completed"}')
        original = Path.read_text
        counter = {'calls': 0}
        def read(p, *args, **kwargs):
            if p == target and counter['calls'] < 2:
                counter['calls'] += 1
                raise PermissionError(errno.EACCES, 'The file is temporarily locked')
            return original(p, *args, **kwargs)
        with patch.object(Path, 'read_text', read), patch.object(dashboard.time, 'sleep'):
            result = dashboard.json_file(target, {})
        self.assertEqual(result['iteration'], 100)
        self.assertEqual(counter['calls'], 2)
        self.assertEqual(dashboard.file_warnings(), [])

    def test_permanent_denial_does_not_break_endpoint_and_recovers(self):
        with patch.object(dashboard, 'RUNS', self.root):
            run = self.root / 'run_test'
            run.mkdir()
            (run / 'run_metadata.json').write_text('{"name":"Test run","created_at":"2026-11-23"}')
            state = run / 'run_state.json'
            state.write_text('{"status":"running","iteration":27}')
            client = TestClient(dashboard.app)
            first = client.get('/api/overview?run=run_test')
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()['state']['iteration'], 27)
            original = Path.read_text
            def denied(p, *args, **kwargs):
                if p == state:
                    raise PermissionError(errno.EACCES, 'Denied')
                return original(p, *args, **kwargs)
            with patch.object(Path, 'read_text', denied), patch.object(dashboard.time, 'sleep'):
                second = client.get('/api/overview?run=run_test')
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()['state']['iteration'], 27)  # stale but safe
            self.assertEqual(second.json()['file_warnings'][0]['file'], 'run_state.json')
            third = client.get('/api/overview?run=run_test')
            self.assertEqual(third.status_code, 200)
            self.assertFalse(third.json()['file_warnings'])

    def test_retries_jsonl_and_can_recover(self):
        path = self.root/'metrics.jsonl'
        path.write_text('{"iteration":1}\n{"iteration":2}\n')
        expected = dashboard.tail_jsonl(path, 5)
        original = Path.open
        def denied(p, *args, **kwargs):
            if p == path: raise PermissionError(errno.EACCES, 'Locked')
            return original(p, *args, **kwargs)
        with patch.object(Path, 'open', denied), patch.object(dashboard.time, 'sleep'):
            self.assertEqual(dashboard.tail_jsonl(path, 5), expected)
        self.assertEqual(dashboard.file_warnings()[0]['file'], 'metrics.jsonl')
        self.assertEqual(dashboard.tail_jsonl(path, 5), expected)
        self.assertFalse(dashboard.file_warnings())

    def test_atomic_json_retries_replace_and_keeps_valid_file(self):
        target = self.root/'run_state.json'
        target.write_text('{"iteration": 25}')
        original = __import__('os').replace
        calls = {'n':0}
        def busy_replace(src, dst):
            calls['n'] += 1
            if calls['n'] < 3:
                raise PermissionError(errno.EACCES, 'Locked')
            return original(src, dst)
        with patch('neural.selfplay.os.replace', side_effect=busy_replace), patch('neural.selfplay.time.sleep'):
            atomic_json(target, {'iteration': 26})
        self.assertEqual(calls['n'], 3)
        self.assertEqual(json.loads(target.read_text())['iteration'], 26)
        self.assertFalse((self.root/'run_state.json.tmp').exists())

if __name__ == '__main__':
    unittest.main()
