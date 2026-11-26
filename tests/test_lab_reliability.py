"""Isolated dashboard tests. No actual engine or trainer subprocess."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import dashboard.server as server


class ReliabilityTests(unittest.TestCase):
    def test_analysis_limit_keeps_totals(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'RUNS', Path(tmp)):
            run = Path(tmp) / 'test_run'
            run.mkdir()
            (run / 'metrics.jsonl').write_text(''.join(json.dumps({'iteration':i,'games':2})+'\n' for i in range(1,701)), encoding='utf-8')
            client = TestClient(server.app)
            full = client.get('/api/analysis?run=test_run').json()
            limited = client.get('/api/analysis?run=test_run&series_limit=600').json()
            self.assertEqual(len(full['series']),700)
            self.assertEqual(len(limited['series']),600)
            self.assertEqual(limited['series_total'],700)
            self.assertEqual(limited['series'][0]['iteration'],101)
            self.assertEqual(limited['totals'],full['totals'])

    def test_stop_wrong_run_cannot_write_marker(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server,'RUNS',Path(tmp)), patch.object(server,'process_status',return_value={'active':True,'run':'new_run'}):
            target=Path(tmp)/'new_run'
            target.mkdir()
            response=TestClient(server.app).post('/api/stop?run=old_run')
            self.assertEqual(response.status_code,409)
            self.assertFalse((target/'stop_requested').exists())

    def test_concurrent_launch_creates_one_process(self):
        proc=Mock()
        proc.poll.return_value=None
        with tempfile.TemporaryDirectory() as tmp, patch.object(server,'RUNS',Path(tmp)), patch.object(server,'active_proc',None), patch.object(server,'active_run',None), patch.object(server,'active_log',None):
            engine=Path(tmp)/'engine'
            engine.touch()
            barrier=threading.Barrier(2)
            def engine_lookup():
                barrier.wait(timeout=5)
                return engine
            def launch(name):
                try:
                    server.launch(name, {})
                    return 200
                except HTTPException as e:
                    return e.status_code
            with patch.object(server,'default_engine',side_effect=engine_lookup),patch.object(server.subprocess,'Popen',return_value=proc) as spawn:
                try:
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        self.assertEqual(sorted(executor.map(launch,['run_a','run_b'])),[200,409])
                    self.assertEqual(spawn.call_count,1)
                finally:
                    if server.active_log:
                        server.active_log.close()


if __name__ == '__main__':
    unittest.main()
