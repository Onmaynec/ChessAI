"""Bounded read-only archive snapshot for retention distillation, not PPO replay."""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
import random
from .tactics import canonical
from .tactical_data import hash_file
from .tactical_learning import atomic_json,experiment_lock

def snapshot(run,dataset,out,engine,limit=512,scan=30000,seed=9322026,family_holdout=False):
    from neural.storage import archived_segments
    from neural.selfplay import ChessBridge
    from benchmark.suite import load_suite
    if not 1<=limit<=5000 or not limit<=scan<=200000:raise ValueError('Invalid replay limits')
    out=out.resolve()
    if any(p.lower() in ('runs','models','checkpoints','config','.venv','.venv-cuda') for p in out.parts):
        raise ValueError('Replay output must be outside training data')
    out.mkdir(parents=True,exist_ok=True)
    with experiment_lock(out):
        path=out/'replay.jsonl';meta=out/'replay_meta.json'
        cfg={'schema':'retention_replay_v1','run':str(run.resolve()),'dataset_sha256':hash_file(dataset),
             'engine_sha256':hash_file(engine),'limit':limit,'scan':scan,'seed':seed}
        if family_holdout:cfg['family_holdout']='coarse_material_king_zones_v1'
        if meta.exists():
            m=json.loads(meta.read_text(encoding='utf-8'))
            if any(m.get(k)!=v for k,v in cfg.items()) or not path.is_file() or m.get('sha256')!=hash_file(path):
                raise ValueError('Replay snapshot mismatch')
            return path
        rows=[json.loads(l) for l in dataset.read_text(encoding='utf-8').splitlines()]
        forbidden={canonical(r['fen']) for r in rows}
        if family_holdout:
            from .scaling import family_id
            families={family_id(r['fen']) for r in rows if r['split']=='validation'}
        del rows
        for suite in sorted((Path(__file__).resolve().parents[1]/'benchmark').glob('suite_v*.json')):
            payload,_=load_suite(suite);forbidden.update(canonical(r['fen']) for r in payload['cases'])
        sources=[run/'experience.jsonl',*reversed(archived_segments(run,'experience.jsonl'))]
        seen=set(forbidden);selected=[];scanned=0;eligible=0;bad=0;read_sources=[]
        rng=random.Random(seed)
        for src in sources:
            if scanned>=scan:break
            if not src.is_file():continue
            print('[REPLAY] read',src.name,flush=True)
            before=src.stat();read_sources.append(str(src))
            opener=gzip.open if src.suffix=='.gz' else open
            with opener(src,'rt',encoding='utf-8') as f:
                for line in f:
                    scanned+=1
                    try:
                        row=json.loads(line);fen=row['fen'];moves=row['legal_moves']
                        if not moves or len(moves)!=len(set(moves)):raise ValueError('Bad move list')
                        key=canonical(fen)
                        if key not in seen and (not family_holdout or family_id(fen) not in families):
                            seen.add(key);eligible+=1
                            sample={'fen':fen,'legal':moves}
                            if len(selected)<limit:selected.append(sample)
                            else:
                                i=rng.randrange(eligible)
                                if i<limit:selected[i]=sample
                    except (ValueError,KeyError,TypeError,IndexError,AttributeError):bad+=1
                    if scanned>=scan:break
            after=src.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise RuntimeError('Experience changed while reading; stop PPO and retry')
        valid=[]
        with ChessBridge(engine) as bridge:
            for r in selected:
                try:s=bridge.new(932040,r['fen'])
                except RuntimeError:
                    if bridge.proc.poll() is not None:raise
                    bad+=1;continue
                if s['finished'] or set(s['legal_moves'])!=set(r['legal']):bad+=1;continue
                valid.append(r)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(''.join(json.dumps(r)+'\n' for r in valid),encoding='utf-8')
        tmp.replace(path)
        atomic_json(meta,{**cfg,'records_scanned':scanned,'eligible':eligible,'selected':len(valid),
                          'rejected':bad,'sources':read_sources,'sha256':hash_file(path),
                          'note':'Bounded newest-file-first sample; not historical overlap audit; distillation only'})
        print(f'[REPLAY] selected {len(valid)} of {scanned} scanned rows',flush=True)
        return path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--limit',type=int,default=512);p.add_argument('--scan',type=int,default=30000)
    a=p.parse_args();snapshot(a.run,a.dataset,a.output,a.engine,a.limit,a.scan)

if __name__=='__main__':main()
