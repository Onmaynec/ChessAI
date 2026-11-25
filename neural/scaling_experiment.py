"""Resumable large-data scaling experiment. Original checkpoint and PPO remain read-only."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from uuid import uuid4
from .tactical_data import generate,hash_file,output_dir
from .tactical_learning import atomic_json,experiment_lock
from .tactical_optimization import settings as opt_settings
from .scaling import settings,verify_families
from .mastery_replay import snapshot
from .tactical_train import train,load_rows

PROFILES={
    'pilot':{'count':6000,'validation_count':1000,'epochs':24,'min_epochs':10,'batch':32,'depth':3,'replay_limit':2048,'scan':100000},
    'standard':{'count':24000,'validation_count':4000,'epochs':20,'min_epochs':8,'batch':32,'depth':3,'replay_limit':4096,'scan':200000},
    'full':{'count':60000,'validation_count':10000,'epochs':16,'min_epochs':8,'batch':32,'depth':3,'replay_limit':5000,'scan':200000},
}
ROOT=Path('tactical_experiments')
DEFAULT_SOURCE=ROOT/'v0933_capacity_aefae56959'/'variant_04'/'candidate.pt'
DEFAULT_REFERENCE=Path('runs/run_20261123_072154_6a110b/checkpoints/latest.pt')

def prior_files(root):
    # Do not include the new experiment itself; capture explicit snapshot before creation.
    return sorted(set(root.rglob('dataset.jsonl'))|set(root.rglob('replay.jsonl')))

def new_config(engine,source,reference,profile,seed,extra=()):
    from benchmark.suite import load_suite
    source,reference,engine=(p.resolve() for p in (source,reference,engine))
    if not all(p.is_file() for p in (source,reference,engine)):raise ValueError('Missing input')
    if reference.parent.name!='checkpoints':raise ValueError('Reference must be a frozen run checkpoint for replay')
    suites=Path(__file__).resolve().parents[1]/'benchmark'
    hashes={p.name:load_suite(p)[1] for p in sorted(suites.glob('suite_v*.json'))}
    if 'suite_v4.json' not in hashes:raise ValueError('Frozen V4 required')
    prior=sorted({p.resolve() for p in [*prior_files(ROOT),*extra]})
    if not prior:raise ValueError('Previous datasets/replay required')
    return {'schema':'scaling_experiment_v1','profile':profile,**PROFILES[profile],
            'source':str(source),'source_sha256':hash_file(source),'reference':str(reference),
            'reference_sha256':hash_file(reference),'engine_sha256':hash_file(engine),
            'suite_hashes':hashes,'excluded_hashes':{str(p):hash_file(p) for p in prior},
            'seed':seed,'lr':.0001,'patience':6}

def verify_inputs(cfg,engine):
    from benchmark.suite import load_suite
    if cfg.get('schema')!='scaling_experiment_v1':raise ValueError('Wrong experiment schema')
    if hash_file(engine)!=cfg['engine_sha256']:raise ValueError('Engine changed')
    for k in ('source','reference'):
        if hash_file(Path(cfg[k]))!=cfg[k+'_sha256']:raise ValueError(k+' changed')
    for p,h in cfg['excluded_hashes'].items():
        if hash_file(Path(p))!=h:raise ValueError('Previous dataset changed: '+p)
    suites=Path(__file__).resolve().parents[1]/'benchmark'
    if {p.name:load_suite(p)[1] for p in sorted(suites.glob('suite_v*.json'))}!=cfg['suite_hashes']:
        raise ValueError('Frozen suite set changed; resume with original libraries')

def run(engine,out,cfg,attempts):
    if not cfg['count']<=attempts<=2000000:raise ValueError('Invalid attempt budget')
    with experiment_lock(out):
        manifest=out/'scaling_config.json'
        if manifest.exists():
            if json.loads(manifest.read_text(encoding='utf-8'))!=cfg:raise ValueError('Resume config changed')
        else:atomic_json(manifest,cfg)
        verify_inputs(cfg,engine)
        data=out/'data';data.mkdir(exist_ok=True)
        path=data/'dataset.jsonl';meta=data/'dataset_meta.json'
        print('[SCALING] Experiment:',out,flush=True)
        if meta.is_file():
            m=json.loads(meta.read_text(encoding='utf-8'))
            if not m.get('complete') or not path.is_file() or hash_file(path)!=m.get('dataset_sha256'):
                raise ValueError('Completed dataset metadata mismatch')
            for k in ('count','validation_count','depth','seed','engine_sha256','suite_hashes','excluded_hashes'):
                if m.get(k)!=cfg[k]:raise ValueError('Dataset config mismatch: '+k)
            if m.get('scaling')!='family_v1':raise ValueError('Wrong dataset schema')
        else:
            generate(engine,data,cfg['count'],cfg['depth'],cfg['seed'],attempts,cfg['validation_count'],True,True,True,
                     [Path(p) for p in cfg['excluded_hashes']])
            m=json.loads(meta.read_text(encoding='utf-8'))
        rows=load_rows(path)
        families=verify_families(rows)
        required={'mate1','check_evasion','promotion'}
        if any(not required<={r['category'] for r in group} for group in rows.values()):
            raise ValueError('Protected category missing from a split')
        del rows
        verify_inputs(cfg,engine)
        reference=Path(cfg['reference'])
        replay=snapshot(reference.parent.parent,path,out/'replay',engine,limit=cfg['replay_limit'],scan=cfg['scan'],
                        seed=cfg['seed'],family_holdout=True)
        rm=json.loads(replay.with_name('replay_meta.json').read_text(encoding='utf-8'))
        if rm['selected']<128:raise ValueError('Insufficient retention positions after family exclusion')
        dest=out/'train';dest.mkdir(exist_ok=True)
        train(Path(cfg['source']),path,dest,engine,cfg['epochs'],cfg['batch'],cfg['lr'],'auto',cfg['seed'],cfg['patience'],True,replay,
              opt_settings(cfg['min_epochs'],.20,'same',.45,.30),settings(reference,cfg['reference_sha256']))
        verify_inputs(cfg,engine)
        report=json.loads((dest/'training_report.json').read_text(encoding='utf-8'))
        atomic_json(out/'scaling_report.json',{'schema':'scaling_report_v1','config':cfg,'dataset':m,'families':families,
                    'replay':rm,'selected_epoch':report['selected_epoch'],'selected':report['selected_validation'],
                    'candidate':report['candidate'],'candidate_sha256':hash_file(Path(report['candidate'])) if report['candidate'] else None,
                    'baseline':report['baseline']['all'],'optimizer_steps':report['optimizer_steps'],
                    'warning':'Family grouping is heuristic, V4 is now a known diagnostic set. No automatic promotion.'})
        print('[SCALING] Complete:',out/'scaling_report.json',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--reference',type=Path,default=DEFAULT_REFERENCE)
    p.add_argument('--profile',choices=PROFILES,default='pilot')
    p.add_argument('--seed',type=int,default=9342026)
    p.add_argument('--exclude',type=Path,nargs='*',default=[])
    p.add_argument('--output',type=Path);p.add_argument('--resume',type=Path)
    p.add_argument('--attempts',type=int)
    a=p.parse_args();engine=a.engine.resolve()
    if a.resume:
        out=output_dir(a.resume,True);cfg=json.loads((out/'scaling_config.json').read_text(encoding='utf-8'))
    else:
        cfg=new_config(engine,a.source,a.reference,a.profile,a.seed,a.exclude)
        out=output_dir(a.output or ROOT/('v0934_'+a.profile+'_'+uuid4().hex[:10]))
    run(engine,out,cfg,a.attempts or min(2000000,60*cfg['count']))

if __name__=='__main__':main()
