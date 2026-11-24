"""ChessAI v0.7.1: optional supervised skill-boost on a COPY of current model.

The local C++ baseline supplies imperfect tactical targets; these are NOT
Stockfish/grandmaster labels. Current PPO run, latest.pt, optimizer, and best.pt
are read-only. Candidate is saved separately, with a clearly tagged new
optimizer; only a future independent evaluation can establish playing strength.

Command: python -m neural.skill_boost --run runs/<id> --engine build/Release/chessai.exe
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from .checkpoint import load_model
from .encoding import FEATURE_VERSION
from .train import PositionDataset, read_rows, run_epoch


def _json(path: Path, data: dict):
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp,path)


def build_teacher(engine: Path, path: Path, *, samples: int, depth: int, seed: int):
    if not 8 <= samples <= 200000:
        raise ValueError('samples must be 8..200000')
    if not 1 <= depth <= 4:
        raise ValueError('teacher depth must be 1..4')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        raise FileExistsError(f'Teacher dataset already exists: {path}; choose a new output path')
    # The C++ core validates all generated legal moves and writes locally.
    process = subprocess.run([str(engine.resolve()),'teacherdata',str(samples),str(depth),str(path),str(seed)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                             timeout=7200, check=False)
    if process.returncode:
        path.unlink(missing_ok=True)
        raise RuntimeError(f'Teacher generation failed: {process.stderr[-500:]}')
    return process.stdout.strip()


def tune(*, engine: Path, run: Path, samples: int = 1200, depth: int = 4,
         epochs: int = 6, batch_size: int = 64, lr: float = 5e-5,
         seed: int = 20261123, device: str = 'auto',
         source_name: str = 'latest.pt') -> dict:
    run = run.resolve()
    engine = engine.resolve()
    source = run/'checkpoints'/source_name
    candidate = run/'checkpoints'/'skillboost.pt'
    report_file = run/'skillboost_report.json'
    dataset = run/'skillboost_teacher.jsonl'
    if not source.is_file() or not engine.is_file():
        raise FileNotFoundError('Run checkpoint and compiled C++ engine are both required')
    if candidate.exists():
        raise FileExistsError('skillboost.pt already exists. Preserve/evaluate it before creating a new candidate.')
    if not 1 <= epochs <= 50 or not 1 <= batch_size <= 512 or not (0 < lr < 0.01):
        raise ValueError('Invalid epochs, batch size, or learning rate')
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA unavailable; choose --device cpu')
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    snapshot = torch.load(str(source), map_location='cpu', weights_only=True)
    if snapshot.get('feature_version') != FEATURE_VERSION:
        raise ValueError('Checkpoint encoding incompatible')
    model = load_model(source, device=device)
    if not dataset.exists():
        message = build_teacher(engine,dataset,samples=samples,depth=depth,seed=seed)
        print(message,flush=True)
    else:
        print(f'Reusing existing local teacher dataset: {dataset}',flush=True)
    rows = read_rows(dataset)
    if len(rows) < 16:
        raise ValueError('At least 16 distinct positions required for held-out validation')
    rng=random.Random(seed)
    rng.shuffle(rows)
    split = max(2,round(len(rows)*0.15))
    train_rows, valid_rows = rows[split:],rows[:split]
    train_loader=DataLoader(PositionDataset(train_rows),batch_size=batch_size,shuffle=True,
                            num_workers=0,pin_memory=(device=='cuda'))
    valid_loader=DataLoader(PositionDataset(valid_rows),batch_size=batch_size,shuffle=False,num_workers=0,
                            pin_memory=(device=='cuda'))
    optimizer = torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=0.0001)
    with torch.no_grad():
        baseline = run_epoch(model,valid_loader,torch.device(device),None,0.25)
    best = copy.deepcopy(model.state_dict())
    best_val=float(baseline['loss'])
    history=[]
    for epoch in range(1,epochs+1):
        train_stats=run_epoch(model,train_loader,torch.device(device),optimizer,0.25)
        with torch.no_grad():
            validation=run_epoch(model,valid_loader,torch.device(device),None,0.25)
        improved=float(validation['loss']) < best_val
        if improved:
            best_val=float(validation['loss'])
            best=copy.deepcopy(model.state_dict())
        history.append({'epoch':epoch,'train':train_stats,'validation':validation,'improved':improved})
        print(f'epoch {epoch}: validation loss {validation["loss"]:.4f}; '
              f'policy top1 {validation["policy_top1_legal"]:.1%}; improved={improved}',flush=True)
    if best_val >= float(baseline['loss']):
        return {'status':'rejected_no_holdout_improvement','candidate_written':False,
                'baseline':baseline,'best_validation_loss':best_val,
                'note':'Original checkpoint and optimizer not changed.'}
    model.load_state_dict(best)
    with torch.no_grad():
        validated = run_epoch(model,valid_loader,torch.device(device),None,0.25)
    metadata = {
        'model':{k:v.detach().cpu() for k,v in best.items()},
        'config':snapshot['config'],'feature_version':FEATURE_VERSION,
        'iteration':int(snapshot.get('iteration',0)),
        'optimizer':None, # Candidate is for testing, NOT for PPO --resume.
        'candidate_only':True,
        'skillboost':{'source_name':source_name,'source_sha256':before_hash,
                      'teacher':'chessai_builtin_baseline','teacher_depth':depth,
                      'positions':len(rows),'holdout_positions':len(valid_rows),
                      'baseline_validation':baseline,'candidate_validation':validated,
                      'date':datetime.now(timezone.utc).isoformat()}
    }
    tmp=candidate.with_name('skillboost.pending.pt')
    try:
        torch.save(metadata,tmp)
        # Confirm the model can be loaded before publishing it for Vision Bot.
        load_model(tmp,'cpu')
        os.replace(tmp,candidate)
    finally:
        tmp.unlink(missing_ok=True)
    report = {'status':'candidate_written_for_independent_testing',
              'source_sha256':before_hash,'source_iteration':metadata['iteration'],
              'candidate_path':str(candidate), 'candidate_written':True, 'baseline':baseline,
              'candidate_validation':validated,'history':history,
              'not_elo':True,'not_a_ppo_resume_checkpoint':True,
              'teacher_note':'Weak native C++ baseline targets, NOT expert games.',
              'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==before_hash}
    _json(report_file,report)
    if not report['source_unchanged']:
        # If selfplay advanced concurrently this is expected; never mutate it.
        report['note']='Live trainer checkpoint changed during candidate creation; original was read-only.'
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Fine-tune a separate candidate using a local weak chess teacher')
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--engine',type=Path,default=Path('build/Release/chessai.exe' if sys.platform=='win32' else 'build/chessai'))
    parser.add_argument('--samples',type=int,default=1200)
    parser.add_argument('--depth',type=int,default=4)
    parser.add_argument('--epochs',type=int,default=6)
    parser.add_argument('--batch-size',type=int,default=64)
    parser.add_argument('--lr',type=float,default=5e-5)
    parser.add_argument('--seed',type=int,default=20261123)
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--source',choices=('latest.pt','best.pt'),default='latest.pt')
    args=parser.parse_args(argv)
    result=tune(engine=args.engine,run=args.run,samples=args.samples,depth=args.depth,
                epochs=args.epochs,batch_size=args.batch_size,lr=args.lr,seed=args.seed,
                device=args.device,source_name=args.source)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
