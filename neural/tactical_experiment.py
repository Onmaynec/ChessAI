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
from .mastery_replay import snapshot

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
    print('1. New Tactical Mastery experiment\n2. Resume existing experiment\n3. Learning Rate Lab (existing V3 dataset)\n4. Anti-Repetition Lab (local test)\n5. Tactical Optimization (reuse V3 dataset)\n6. Batch Lab\n7. Replay Lab\n8. Capacity Lab\n9. Resume Optimization Lab\n10. Build frozen V4 holdout\n11. Neural Scaling (new dataset + training)\n12. Resume Neural Scaling\n13. GPU Performance Lab')
    mode=input('Action [1]: ').strip() or '1'
    if mode in ('5','6','7','8','9'):
        from .optimization_lab import run as optimize_run,main as optimize_main
        raw=input('Existing experiment directory (lab directory for resume): ').strip().strip('"')
        if not raw:p.error('Directory required')
        if mode=='9':optimize_main_args=['--engine',str(engine),'--resume',raw]
        else:
            optimize_main_args=['--engine',str(engine),'--experiment',raw,'--mode',{'5':'single','6':'batch','7':'replay','8':'capacity'}[mode]]
            source=input('Alternative source checkpoint (Enter = original experiment source): ').strip().strip('"')
            if source:optimize_main_args+=['--source',source]
        import sys
        previous=sys.argv;sys.argv=[previous[0],*optimize_main_args]
        try:optimize_main()
        finally:sys.argv=previous
        return
    if mode in ('11','12'):
        from .scaling_experiment import DEFAULT_SOURCE as ADVANCED,new_config,run,PROFILES
        if mode=='12':
            raw=input('Scaling experiment directory: ').strip().strip('"')
            if not raw:p.error('Directory required')
            out=output_dir(Path(raw),True)
            cfg=json.loads((out/'scaling_config.json').read_text(encoding='utf-8'))
        else:
            source=Path(input(f'Initial checkpoint [{ADVANCED}]: ').strip().strip('"') or ADVANCED)
            reference=Path(input(f'Retention reference [{DEFAULT_SOURCE}]: ').strip().strip('"') or DEFAULT_SOURCE)
            print('1. Pilot: ~5000 train / 1000 validation\n2. Standard: ~20000 / 4000\n3. Full: ~50000 / 10000')
            profile={'1':'pilot','2':'standard','3':'full'}.get(input('Profile [1]: ').strip() or '1')
            if not profile:p.error('Invalid profile')
            cfg=new_config(engine,source,reference,profile,9342026)
            out=output_dir(Path('tactical_experiments')/('v0934_'+profile+'_'+uuid4().hex[:10]))
        limit=min(2000000,60*cfg['count']);raw=input(f'Total attempt budget [{limit}]: ').strip()
        run(engine,out,cfg,int(raw) if raw else limit);return
    if mode=='13':
        from .scaling_experiment import DEFAULT_SOURCE as ADVANCED
        from .scaling_gpu import run
        source=Path(input(f'Checkpoint [{ADVANCED}]: ').strip().strip('"') or ADVANCED)
        run(source,output_dir(Path('tactical_experiments')/('gpu_'+uuid4().hex[:10])));return
    if mode=='10':
        from benchmark.build_holdout import build
        paths=sorted(set(Path('tactical_experiments').rglob('dataset.jsonl'))|set(Path('tactical_experiments').rglob('replay.jsonl')))
        if not paths:p.error('No prior datasets found; use builder CLI with explicit --exclude')
        print('Excluding',len(paths),'prior datasets/replay files; add external datasets via CLI.')
        raw=input('New holdout [Enter] or existing holdout working directory: ').strip().strip('"')
        out=output_dir(Path(raw),True) if raw else output_dir(Path('tactical_experiments')/('holdout_'+uuid4().hex[:10]))
        print('Holdout working directory:',out,flush=True)
        build(engine,out,paths);return
    if mode=='4':
        from .mastery_repetition_lab import run
        source=Path(input(f'Source checkpoint [{DEFAULT_SOURCE}]: ').strip().strip('"') or DEFAULT_SOURCE).resolve()
        if not source.is_file():p.error('Source checkpoint missing')
        pairs=input('Opening pairs [8]: ').strip() or '8'
        if not pairs.isdigit() or not 1<=int(pairs)<=50:p.error('Invalid pairs')
        out=output_dir(Path('tactical_experiments')/('repetition_'+uuid4().hex[:10]))
        print('Experiment:',out,flush=True);run(source,engine,out,int(pairs));return
    if mode=='3':
        from .mastery_lr_lab import run_lab
        raw=input('Existing Tactical Mastery experiment directory: ').strip().strip('"')
        if not raw:p.error('Experiment directory required')
        run_lab(Path(raw).resolve(),engine);return
    if mode=='2':
        raw=input('Experiment directory (contains experiment.json): ').strip().strip('"')
        if not raw:p.error('Experiment directory required')
        out=Path(raw).resolve()
        if not (out/'experiment.json').is_file():p.error('Experiment configuration not found')
        cfg=json.loads((out/'experiment.json').read_text(encoding='utf-8'))
        if cfg.get('schema') not in ('tactical_experiment_v2','tactical_experiment_v3'):p.error('Unsupported experiment schema')
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
        use_replay=source.parent.name=='checkpoints' and (input('Retention replay from source run? [Y/n]: ').strip().lower()!='n')
        cfg.update(schema='tactical_experiment_v3',source=str(source),source_sha256=hash_file(source),
                   engine_sha256=hash_file(engine),seed=9322026,patience=6,replay=use_replay)
        out=output_dir(Path('tactical_experiments')/('v0932_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:6]))
    else:p.error('Invalid action')
    print('Experiment:',out,flush=True)
    # Separate root lock prevents concurrent orchestration of the same experiment.
    with experiment_lock(out):
        atomic_json(out/'experiment.json',cfg)
        mastery=cfg['schema']=='tactical_experiment_v3'
        data=out/'data';data.mkdir(exist_ok=True)
        meta_path=data/'dataset_meta.json'
        if meta_path.is_file():
            meta=json.loads(meta_path.read_text(encoding='utf-8'))
            if meta.get('complete') and (data/'dataset.jsonl').is_file() and hash_file(data/'dataset.jsonl')==meta.get('dataset_sha256'):
                if meta.get('schema')!=('tactical_data_v3' if mastery else 'tactical_data_v2'):raise ValueError('Dataset version mismatch')
                for key in ('count','validation_count','depth','seed','engine_sha256'):
                    if meta.get(key)!=cfg[key]:raise ValueError('Completed dataset configuration mismatch')
                print('[DATA] Reusing complete dataset',flush=True)
            else:generate(engine,data,cfg['count'],cfg['depth'],cfg['seed'],cfg['attempts'],cfg['validation_count'],True,mastery)
        else:generate(engine,data,cfg['count'],cfg['depth'],cfg['seed'],cfg['attempts'],cfg['validation_count'],True,mastery)
        if hash_file(source)!=cfg['source_sha256']:raise RuntimeError('Original checkpoint changed; stop training before resuming')
        replay=snapshot(source.parent.parent,data/'dataset.jsonl',out/'replay',engine,seed=cfg['seed']) if mastery and cfg.get('replay') else None
        dest=out/'train';dest.mkdir(exist_ok=True)
        train(source,data/'dataset.jsonl',dest,engine,cfg['epochs'],cfg['batch'],cfg['lr'],'auto',cfg['seed'],cfg['patience'],True,replay)
        print('Reports:',dest/'training_report.json',flush=True)
        if (dest/'candidate.pt').is_file():
            print('Candidate is experimental; do not replace latest.pt.',flush=True)
            from neural.agent_profiles import ALIASES
            if source.parent.name=='checkpoints' and source.name in ALIASES:
                print('1. Diagnostic comparison (6 pairs, no archive audit)\n2. Extended screening (32 pairs, canonical cached audit)\n3. Skip comparison')
                compare=input('Comparison [1]: ').strip() or '1'
                if compare in ('1','2'):
                    from benchmark.run import main as benchmark_main
                    if hash_file(source)!=cfg['source_sha256']:raise RuntimeError('Source changed before comparison')
                    from .mastery_guard import run_guard
                    comparison=out/('comparison_'+uuid4().hex[:6])
                    args=['--run',str(source.parent.parent),'--engine',str(engine),'--agents',source.name,
                          '--candidate',str(dest/'candidate.pt'),'--output',str(comparison),
                          '--profile','standard','--suite','v3','--seed','9332026','--pairs','6' if compare=='1' else '32','--max-plies','240' if compare=='1' else '480']
                    if compare=='1':args.append('--skip-audit')
                    else:args+=['--audit-cache','benchmark_reports/audit_cache']
                    benchmark_main(args)
                    run_guard(comparison/'report.json',source.name,dest/'candidate.pt',source,comparison/'promotion_guard.json')
            else:print('For a non-standard source path use benchmark.run manually.',flush=True)

if __name__=='__main__':main()
