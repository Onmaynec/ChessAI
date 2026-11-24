"""Historical checkpoint screening against the same frozen reference/opening suite.

No weights are changed. Scores are diagnostic, NOT calibrated Elo and the
highest observed score may have selection bias from trying many checkpoints.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from .checkpoint import load_model
from .selfplay import START_FEN, evaluate


HISTORICAL = re.compile(r'^iteration_(\d{5})\.pt$')


def checkpoints_for(run: Path, last: int=8) -> list[tuple[int,Path]]:
    folder=run/'checkpoints'
    items=[]
    for path in folder.glob('iteration_*.pt'):
        match=HISTORICAL.fullmatch(path.name)
        if match and path.is_file():
            items.append((int(match.group(1)),path))
    items.sort(key=lambda v:v[0])
    latest=folder/'latest.pt'
    if latest.is_file():
        ck=torch.load(latest,map_location='cpu',weights_only=True)
        iteration=int(ck['iteration'])
        items=[v for v in items if v[0]!=iteration]
        items.append((iteration,latest))
    items.sort(key=lambda v:v[0])
    return items[-last:]


def main(argv=None):
    p=argparse.ArgumentParser(description='Tournament of historical checkpoints; read-only weights')
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--engine',type=Path,default=Path('build/Release/chessai.exe' if sys.platform=='win32' else 'build/chessai'))
    p.add_argument('--reference',type=Path,default=Path('models/neural_best.pt'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--last',type=int,default=8)
    p.add_argument('--games',type=int,default=20)
    p.add_argument('--max-plies',type=int,default=400)
    p.add_argument('--opening-plies',type=int,default=8)
    p.add_argument('--seed',type=int,default=20261123)
    p.add_argument('--device',choices=['cpu','cuda','auto'],default='auto')
    a=p.parse_args(argv)
    if not 1<=a.last<=200 or a.games<4 or a.games>500 or a.games%2 or not 20<=a.max_plies<=1500 or not 0<=a.opening_plies<=16:
        p.error('Invalid tournament options')
    if a.output.exists():
        p.error('Output report already exists')
    device='cuda' if a.device=='auto' and torch.cuda.is_available() else ('cpu' if a.device=='auto' else a.device)
    if device=='cuda' and not torch.cuda.is_available():p.error('CUDA unavailable')
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    reference=load_model(a.reference,device)
    pool=checkpoints_for(a.run,a.last)
    if not pool:p.error('No checkpoints found')
    rows=[]
    for i,(iteration,path) in enumerate(pool,1):
        model=load_model(path,device)
        stats,_=evaluate(model,reference,a.engine,a.games,a.max_plies,torch.device(device),START_FEN,
                         800000,opening_plies=a.opening_plies,seed=a.seed)
        rows.append({'iteration':iteration,'filename':path.name,'statistics':stats})
        print(f'[{i}/{len(pool)}] iteration={iteration} score={stats["score"]} '
              f'unique={stats["unique_sequences"]}/{a.games}',flush=True)
    ranked=sorted(rows,key=lambda row:(row['statistics']['score'] is not None,
                          row['statistics']['score'] or -1),reverse=True)
    result={'version':'0.6.0','created_at':datetime.now(timezone.utc).isoformat(),
            'run':a.run.name,'reference':str(a.reference),'seed':a.seed,'suite':'selection',
            'games_per_candidate':a.games,'opening_plies':a.opening_plies,
            'candidates':rows,
            'ranking':[{'iteration':x['iteration'],'score':x['statistics']['score'],
                        'completed':x['statistics']['completed'],
                        'unique_sequences':x['statistics']['unique_sequences']}
                       for x in ranked],
            'caveat':'Descriptive screening, not Elo. Ranking multiple checkpoints on the same small suite has selection bias. Do not auto-promote without fresh holdout checks.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    temp=a.output.with_suffix('.json.tmp')
    try:
        temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,a.output)
    finally:temp.unlink(missing_ok=True)
    print('Saved:',a.output,flush=True)

if __name__=='__main__':main()
