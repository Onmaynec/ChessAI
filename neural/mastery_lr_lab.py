"""Compare learning rates on one fixed dataset, same source and seed."""
from __future__ import annotations
import json
from pathlib import Path
from uuid import uuid4
from .tactical_data import hash_file,output_dir
from .tactical_learning import atomic_json,experiment_lock
from .tactical_train import train

def run_lab(experiment,engine):
    cfg=json.loads((experiment/'experiment.json').read_text(encoding='utf-8'))
    if cfg.get('schema')!='tactical_experiment_v3':raise ValueError('Use completed Mastery V3 dataset')
    source=Path(cfg['source']);dataset=experiment/'data'/'dataset.jsonl'
    meta=json.loads(dataset.with_name('dataset_meta.json').read_text(encoding='utf-8'))
    if meta.get('schema')!='tactical_data_v3' or not meta.get('complete') or meta.get('dataset_sha256')!=hash_file(dataset):
        raise ValueError('Incomplete V3 dataset')
    if hash_file(source)!=cfg['source_sha256'] or hash_file(engine)!=cfg['engine_sha256']:raise ValueError('Experiment source or engine changed')
    replay=experiment/'replay'/'replay.jsonl' if cfg.get('replay') else None
    if replay is not None and not replay.is_file():raise ValueError('Run original experiment to create replay snapshot first')
    out=output_dir(experiment/('lr_lab_'+uuid4().hex[:8]));print('LR Lab:',out,flush=True)
    records=[]
    with experiment_lock(out):
        for rate in (3e-5,1e-4,3e-4):
            dest=out/('lr_'+format(rate,'.0e'));dest.mkdir()
            train(source,dataset,dest,engine,cfg['epochs'],cfg['batch'],rate,'auto',cfg['seed'],cfg['patience'],False,replay)
            r=json.loads((dest/'training_report.json').read_text(encoding='utf-8'))
            records.append({'lr':rate,'candidate':r['candidate'],'selected_epoch':r['selected_epoch'],
                            'best_observed':r['best_observed_validation'],'selected':r['selected_validation'],
                            'optimizer_steps':r['optimizer_steps'],'report':str(dest/'training_report.json')})
            atomic_json(out/'lab_report.json',{'schema':'mastery_lr_lab_v1','results':records,
                        'warning':'Same validation used for selection; compare only chosen candidate on separate benchmark. No automatic promotion.'})
        print('LR Lab results:',out/'lab_report.json',flush=True)
