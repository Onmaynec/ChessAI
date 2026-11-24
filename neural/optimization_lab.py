"""Optimization lab: reuse a frozen Mastery dataset, no overwrite of old experiments."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from uuid import uuid4
from .tactical_data import output_dir,hash_file
from .tactical_learning import atomic_json,experiment_lock
from .tactical_optimization import settings
from .tactical_train import train

def run(experiment,engine,mode='single',source=None,epochs=60,min_epochs=20,batch=32,lr=.0003,replay_weight=.10,capacity='same',seed=9332026,resume=None):
    cfg=json.loads((experiment/'experiment.json').read_text(encoding='utf-8'))
    dataset=experiment/'data'/'dataset.jsonl'
    meta=json.loads(dataset.with_name('dataset_meta.json').read_text(encoding='utf-8'))
    if meta.get('schema')!='tactical_data_v3' or not meta.get('complete') or meta.get('dataset_sha256')!=hash_file(dataset):
        raise ValueError('Need complete V3 dataset')
    source=(source or Path(cfg['source'])).resolve()
    replay=experiment/'replay'/'replay.jsonl' if cfg.get('replay') else None
    if replay is not None and not replay.is_file():raise ValueError('Missing original replay snapshot')
    if mode=='replay' and replay is None:raise ValueError('Replay lab requires replay snapshot')
    if not 1<=min_epochs<=epochs<=60 or not 1<=batch<=256 or not 0<lr<=.001:raise ValueError('Invalid optimization budget')
    # Each variant starts from exactly the same source. Different batch sizes intentionally change steps.
    variants={'single':[(batch,replay_weight,capacity)],'batch':[(b,replay_weight,'same') for b in (16,32,64)],
              'replay':[(batch,w,'same') for w in (.05,.10,.20)],
              'capacity':[(batch,replay_weight,c) for c in ('same','light','standard','advanced')]}[mode]
    jobs=[{'batch':b,'settings':settings(min_epochs,w,c)} for b,w,c in variants]
    config={'schema':'optimization_lab_v1','experiment':str(experiment.resolve()),'source':str(source),
            'source_sha256':hash_file(source),'dataset_sha256':hash_file(dataset),'engine_sha256':hash_file(engine),
            'replay_sha256':hash_file(replay) if replay else None,'mode':mode,'epochs':epochs,'lr':lr,'seed':seed,'jobs':jobs}
    out=output_dir(resume,True) if resume else output_dir(Path('tactical_experiments')/('v0933_'+mode+'_'+uuid4().hex[:10]))
    print('[OPTIMIZATION] Directory:',out,flush=True)
    with experiment_lock(out):
        manifest=out/'lab_config.json'
        if manifest.exists():
            if json.loads(manifest.read_text(encoding='utf-8'))!=config:raise ValueError('Resume inputs/config changed')
        elif resume:raise ValueError('Missing lab configuration')
        else:atomic_json(manifest,config)
        results=[]
        for i,job in enumerate(jobs,1):
            dest=out/f'variant_{i:02d}';dest.mkdir(exist_ok=True)
            print(f'[OPTIMIZATION] {i}/{len(jobs)}: {job}',flush=True)
            train(source,dataset,dest,engine,epochs,job['batch'],lr,'auto',seed,8,True,replay,job['settings'])
            report=json.loads((dest/'training_report.json').read_text(encoding='utf-8'))
            results.append({'variant':i,**job,'candidate':report['candidate'],'selected_epoch':report['selected_epoch'],
                            'selected':report['selected_validation'],'best_observed':report['best_observed_validation'],
                            'parameters':report['parameters'],'model_config':report['model_config'],
                            'optimizer_steps':report['optimizer_steps'],'report':str(dest/'training_report.json')})
            atomic_json(out/'lab_report.json',{'schema':'optimization_lab_v1','config':config,'results':results,
                'complete':len(results)==len(jobs),'warning':'Selection uses existing validation; fresh holdout required. No automatic promotion.'})
        print('[OPTIMIZATION] Reports:',out/'lab_report.json',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--experiment',type=Path)
    p.add_argument('--mode',choices=['single','batch','replay','capacity'],default='single')
    p.add_argument('--source',type=Path);p.add_argument('--epochs',type=int,default=60);p.add_argument('--min-epochs',type=int,default=20)
    p.add_argument('--batch',type=int,default=32);p.add_argument('--lr',type=float,default=.0003)
    p.add_argument('--replay-weight',type=float,default=.10);p.add_argument('--capacity',choices=['same','light','standard','advanced'],default='same')
    p.add_argument('--seed',type=int,default=9332026);p.add_argument('--resume',type=Path);a=p.parse_args()
    if a.resume:
        cfg=json.loads((a.resume/'lab_config.json').read_text(encoding='utf-8'))
        j=cfg['jobs'][0];s=j['settings']
        run(Path(cfg['experiment']),a.engine,cfg['mode'],Path(cfg['source']),cfg['epochs'],s['min_epochs'],j['batch'],cfg['lr'],s['replay_weight'],s['capacity'],cfg['seed'],a.resume)
    else:
        if not a.experiment:p.error('--experiment required')
        run(a.experiment,a.engine,a.mode,a.source,a.epochs,a.min_epochs,a.batch,a.lr,a.replay_weight,a.capacity,a.seed)

if __name__=='__main__':main()
