"""v0.7: disk safety, full replay compatibility, continuous batching, CPU workers."""
from __future__ import annotations
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from fastapi.testclient import TestClient
from neural.model import ChessNet
from neural.selfplay import START_FEN, rollout, parse_args, run
from neural.storage import (compact_run,compact_one,digest,iter_records,tail_records,
                            find_game,space_report,archived_segments,last_game_id)
from dashboard.server import app
from tools.verify_progress import verify_run

ROOT=Path(__file__).resolve().parents[1]
ENGINE=next((p for p in (ROOT/'build/Release/chessai.exe',ROOT/'build/chessai.exe',ROOT/'build/chessai') if p.exists()),None)


def make_run(root:Path,committed=3):
    run=root/'runs'/'run_v07'
    (run/'checkpoints').mkdir(parents=True)
    net=ChessNet(8,1)
    optimizer=torch.optim.AdamW(net.parameters())
    torch.save({'model':net.state_dict(),'optimizer':optimizer.state_dict(),
                'config':net.config,'feature_version':'planes19_actions73_v1',
                'iteration':committed,'metrics':{'iteration':committed}},
               run/'checkpoints/latest.pt')
    (run/'run_metadata.json').write_text(json.dumps({'feature_version':'planes19_actions73_v1',
                                        'config':{},'name':'run_v07'}),encoding='utf-8')
    (run/'run_state.json').write_text(json.dumps({'iteration':committed,'status':'completed'}),encoding='utf-8')
    for n in ('games.jsonl','arena_games.jsonl','experience.jsonl'):
        (run/n).write_text(''.join(json.dumps({'iteration':i,'game_id':i,'fens':[START_FEN],
                     'moves':['e2e4'],'note':'repeated strings '*20})+'\n' for i in range(1,committed+1)),encoding='utf-8')
    return run


class StorageTests(unittest.TestCase):
    def test_lossless_archive_replay_resume_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=make_run(Path(tmp))
            original={n:(run/n).read_bytes() for n in ('games.jsonl','arena_games.jsonl','experience.jsonl')}
            checkpoint_hash=digest(run/'checkpoints/latest.pt')
            report=compact_run(run,committed=3)
            self.assertGreater(report['saved_bytes'],0)
            self.assertEqual(digest(run/'checkpoints/latest.pt'),checkpoint_hash)
            for n,raw in original.items():
                archived=archived_segments(run,n)
                self.assertEqual(len(archived),1)
                self.assertEqual(gzip.decompress(archived[0].read_bytes()),raw)
                self.assertFalse((run/n).exists())
                self.assertEqual(len(list(iter_records(run,n))),3)
                self.assertEqual([x['game_id'] for x in tail_records(run,n,2)],[2,3])
            self.assertEqual(find_game(run,'games.jsonl',1)['game_id'],1)
            self.assertEqual(last_game_id(run),3)
            self.assertTrue(verify_run(run)['optimizer_restorable'])
            (run/'games.jsonl').write_text(json.dumps({'iteration':3,'game_id':4})+'\n')
            self.assertEqual([x['game_id'] for x in tail_records(run,'games.jsonl',2)],[3,4])
            self.assertEqual(next(x for x in compact_run(run,committed=3)['files'] if x['file']=='games.jsonl')['records'],1)
            self.assertEqual(len(archived_segments(run,'games.jsonl')),2)
            self.assertEqual([x['game_id'] for x in tail_records(run,'games.jsonl',4)],[1,2,3,4])

    def test_crash_reconciliation_and_invalid_rows_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=make_run(Path(tmp))
            original=(run/'games.jsonl').read_bytes()
            segment=(run/'archives'/'games');segment.mkdir(parents=True)
            filename=segment/f'0000001_{digest(run/"games.jsonl")}.jsonl.gz'
            with gzip.open(filename,'wb') as f:f.write(original)
            result=compact_one(run,'games.jsonl',committed=3)
            self.assertEqual(result['reason'],'reconciled interrupted archival')
            self.assertFalse((run/'games.jsonl').exists())
            (run/'games.jsonl').write_text('{broken\n')
            with self.assertRaisesRegex(ValueError,'Invalid record'):
                compact_one(run,'games.jsonl',committed=3)
            self.assertTrue((run/'games.jsonl').is_file())
            (run/'games.jsonl').write_text('{"iteration":4,"game_id":5}\n')
            with self.assertRaisesRegex(ValueError,'uncommitted'):
                compact_one(run,'games.jsonl',committed=3)
            self.assertTrue((run/'games.jsonl').is_file())

    def test_stream_recovery_preserves_full_original_and_uncommitted(self):
        from neural.selfplay import recover_resume_files
        with tempfile.TemporaryDirectory() as tmp:
            run=make_run(Path(tmp))
            raw=run/'experience.jsonl'
            raw.write_bytes(raw.read_bytes()+b'{"iteration":4,"game_id":6}\n')
            original=raw.read_bytes()
            ck=torch.load(run/'checkpoints/latest.pt',weights_only=True)
            result=recover_resume_files(run,ck)
            self.assertEqual(result['experience.jsonl'],1)
            self.assertEqual(len(list(iter_records(run,'experience.jsonl'))),3)
            backups=list((run/'recovery').glob('experience.jsonl.*.full-original.gz'))
            self.assertEqual(len(backups),1)
            self.assertEqual(gzip.decompress(backups[0].read_bytes()),original)
            self.assertTrue((run/'checkpoints/latest.pt').is_file())

    def test_migration_reuses_cuda_python_without_copying_torch(self):
        from tools.migrate_current import migrate
        with tempfile.TemporaryDirectory() as tmp:
            top=Path(tmp);old=top/'old';new=top/'new'
            for root,version in ((old,'0.6.0'),(new,'0.7.0')):
                (root/'neural').mkdir(parents=True)
                (root/'neural/selfplay.py').write_text('unchanged')
                (root/'VERSION').write_text(version)
                (root/'runs').mkdir()
            src=make_run(old)
            cuda=old/'.venv-cuda/Scripts/python.exe'
            cuda.parent.mkdir(parents=True)
            cuda.write_bytes(b'placeholder-executable')
            report=migrate(old,new)
            self.assertEqual(report['reused_cuda_python'],str(cuda.resolve()))
            self.assertEqual((new/'config/python_path.txt').read_text().strip(),str(cuda.resolve()))
            self.assertTrue((new/'runs/run_v07/checkpoints/latest.pt').is_file())
            self.assertTrue(cuda.is_file())

    def test_running_refuses_offline_compaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=make_run(Path(tmp))
            (run/'run_state.json').write_text('{"status":"running"}')
            with self.assertRaisesRegex(ValueError,'Stop training'):
                compact_run(run,committed=3)

    def test_archived_replay_works_through_api(self):
        from dashboard import server
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=make_run(root)
            compact_run(run,committed=3)
            with patch.object(server,'RUNS',root/'runs'):
                with TestClient(app) as client:
                    data=client.get('/api/storage/run_v07').json()
                    self.assertGreater(data['space']['archives_bytes'],0)
                    self.assertEqual(client.get('/api/games',params={'run':'run_v07'}).json()['games'][0]['game_id'],3)
                    self.assertEqual(client.get('/api/game/2',params={'run':'run_v07'}).json()['game_id'],2)


@unittest.skipIf(ENGINE is None,'C++ build needed')
class EngineTests(unittest.TestCase):
    def test_continuous_bridges_keep_games_valid(self):
        torch.set_num_threads(2)
        model=ChessNet(8,1).eval()
        profile={}
        games=rollout(model,ENGINE,games=7,parallel=3,bridge_workers=2,
                max_plies=25,temperature=1.0,start_fen=START_FEN,
                device=torch.device('cpu'),id_start=10000,profile=profile,
                opening_plies=2)
        self.assertEqual(len(games),7)
        self.assertEqual(len({g.id for g in games}),7)
        self.assertEqual(profile['bridge_workers'],2)
        self.assertGreater(profile['inference_batches'],0)
        for g in games:
            self.assertEqual(len(g.moves)+1,len(g.fens))

    def test_resume_after_archiving_preserves_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'run'
            flags=['--engine',str(ENGINE),'--out',str(path),'--iterations','1',
                   '--games-per-iteration','2','--parallel','2','--max-plies','32',
                   '--arena-games','0','--best-every','0','--save-every','1',
                   '--bridge-workers','2','--archive-every','1',
                   '--start-fen','8/8/8/8/8/2k5/8/K7 w - - 0 1']
            run(parse_args(flags))
            first=torch.load(path/'checkpoints/latest.pt',weights_only=True)
            self.assertEqual(first['iteration'],1)
            self.assertTrue(archived_segments(path,'games.jsonl'))
            run(parse_args(flags+['--resume']))
            later=torch.load(path/'checkpoints/latest.pt',weights_only=True)
            self.assertEqual(later['iteration'],2)
            self.assertIn('optimizer',later)
            self.assertEqual(len(list(iter_records(path,'games.jsonl'))),4)
            self.assertIn('performance',later['metrics'])
            self.assertEqual(len(list(iter_records(path,'arena_games.jsonl'))),0)
            self.assertTrue(verify_run(path)['optimizer_restorable'])

if __name__=='__main__':unittest.main()
