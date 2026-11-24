"""Interactive local tactical experiment launcher with saved configuration."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .tactical_learning import atomic_json,experiment_lock
from .tactical_data import generate,output_dir,hash_file
from .tactical_train import train

PROFILES={
    '1':{'count':600,'validation_count':100,'depth':3,'epochs':20,'batch':64,'lr':.0001,'attempts':30000},
    '2':{'count':2400,'validation_count':400,'depth':3,'epochs':25,'batch':64,'lr':.0001,'attempts':120000},
    '3':{'count':6000,'validation_count':1000,'depth':3,'epochs':30,'batch':64,'lr':.0001,'attempts':300000},
}
DEFAULT_SOURCE=Path('runs/run_20261123_072154_6a110b/checkpoints/latest.pt')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True)
    a=p.parse_args();engine=a.engine.resolve()
    if not engine.is_file():p.error('C++ engine missing')
    print('Stop PPO training and Vision Studio before starting.')
    print('1. New tactical experiment\n2. Resume existing v0.9.3.1 experiment')
    mode=input('Action [1]: ').strip() or '1'
    if mode=='2':
        raw=input('Experiment directory (contains experiment.json): ').strip().strip('"')
        if not raw:p.error('Experiment directory required')
        out=Path(raw).resolve()
        if not (out/'experiment.json').is_file():p.error('Experiment configuration not found')
        cfg=json.loads((out/'experiment.json').read_text(encoding='utf-8'))
        if cfg.get('schema')!='tactical_experiment_v2':p.error('Not a v0.9.3.1 experiment')
        source=Path(cfg['source'])
        if not source.is_file() or hash_file(source)!=cfg['source_sha256'] or hash_file(engine)!=cfg['engine_sha256']:
            p.error('Source checkpoint or engine changed; cannot resume safely')
        attempts=input(f"Total generation attempt limit [{cfg['attempts']}]: ").strip()
        if attempts:
            try:cfg['attempts']=int(attempts)
            except ValueError:p.error('Invalid attempt limit')
            if not cfg['count']<=cfg['attempts']<=2000000:p.error('Invalid attempt limit')
    elif mode=='1':
        source=Path(input(f'Source checkpoint [{DEFAULT_SOURCE}]: ').strip().strip('"') or DEFAULT_SOURCE).resolve()
        if not source.is_file():p.error('Source checkpoint missing')
        print('1. Pilot: 500 train + 100 validation, 20 epochs')
        print('2. Standard: 2000 train + 400 validation, 25 epochs')
        print('3. Full: 5000 train + 1000 validation, 30 epochs (very expensive generation)')
        profile=input('Profile [1]: ').strip() or '1'
        if profile not in PROFILES:p.error('Invalid profile')
        cfg=dict(PROFILES[profile])
        lr=input('Learning rate [0.0001] (0.00003 / 0.0001 / 0.0003): ').strip()
        depth=input('Teacher depth [3] (3 / 4 / 5): ').strip()
        try:
            if lr:cfg['lr']=float(lr)
            if depth:cfg['depth']=int(depth)
        except ValueError:p.error('Invalid learning rate/depth')
        if not 3e-5<=cfg['lr']<=3e-4 or not 3<=cfg['depth']<=5:p.error('Invalid learning rate/depth')
        cfg.update(schema='tactical_experiment_v2',source=str(source),source_sha256=hash_file(source),
                   engine_sha256=hash_file(engine),seed=9312026,patience=6)
        out=output_dir(Path('tactical_experiments')/('v0931_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:6]))
    else:p.error('Invalid action')
    print('Experiment:',out,flush=True)
    # Separate root lock prevents concurrent orchestration of the same experiment.
    with experiment_lock(out):
        atomic_json(out/'experiment.json',cfg)
        data=out/'data';data.mkdir(exist_ok=True)
        meta_path=data/'dataset_meta.json'
        if meta_path.is_file():
            meta=json.loads(meta_path.read_text(encoding='utf-8'))
            if meta.get('complete') and (data/'dataset.jsonl').is_file() and hash_file(data/'dataset.jsonl')==meta.get('dataset_sha256'):
                for key in ('count','validation_count','depth','seed','engine_sha256'):
                    if meta.get(key)!=cfg[key]:raise ValueError('Completed dataset configuration mismatch')
                print('[DATA] Reusing complete dataset',flush=True)
            else:generate(engine,data,cfg['count'],cfg['depth'],cfg['seed'],cfg['attempts'],cfg['validation_count'],True)
        else:generate(engine,data,cfg['count'],cfg['depth'],cfg['seed'],cfg['attempts'],cfg['validation_count'],True)
        if hash_file(source)!=cfg['source_sha256']:raise RuntimeError('Original checkpoint changed; stop training before resuming')
        dest=out/'train';dest.mkdir(exist_ok=True)
        train(source,data/'dataset.jsonl',dest,engine,cfg['epochs'],cfg['batch'],cfg['lr'],'auto',cfg['seed'],cfg['patience'],True)
        print('Reports:',dest/'training_report.json',flush=True)
        if (dest/'candidate.pt').is_file():
            print('Candidate is experimental. Compare using benchmark.run --candidate; do not replace latest.pt.',flush=True)

if __name__=='__main__':main()
