"""Seeded opening-suite / color-paired checkpoint comparison. No weight changes."""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from .checkpoint import load_model
from .selfplay import START_FEN, evaluate


def main(argv=None):
    p = argparse.ArgumentParser(description='Diverse paired-color checkpoint evaluation')
    p.add_argument('--engine',type=Path,default=Path('build/Release/chessai.exe' if sys.platform=='win32' else 'build/chessai'))
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--reference',type=Path,default=Path('models/neural_best.pt'))
    p.add_argument('--games',type=int,default=40)
    p.add_argument('--max-plies',type=int,default=400)
    p.add_argument('--start-fen',default=START_FEN)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    p.add_argument('--seed',type=int,default=20261123)
    p.add_argument('--opening-plies',type=int,default=8)
    p.add_argument('--suite',choices=('selection','holdout'),default='holdout',
                   help='Holdout uses a disjoint deterministic opening-seed namespace')
    args=p.parse_args(argv)
    if not 2 <= args.games <= 500 or args.games % 2:
        p.error('--games must be even and between 2 and 500')
    if not 20 <= args.max_plies <= 1500 or not 0 <= args.opening_plies <= 16:
        p.error('invalid plies limit')
    if args.checkpoint.resolve()==args.reference.resolve():
        p.error('Candidate and reference checkpoints must differ')
    if args.output.exists():
        p.error('Output exists; evaluation never overwrites previous reports')
    device = 'cuda' if args.device == 'auto' and torch.cuda.is_available() else ('cpu' if args.device=='auto' else args.device)
    if device == 'cuda' and not torch.cuda.is_available():
        p.error('PyTorch has no usable CUDA runtime')
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    candidate=load_model(args.checkpoint,device)
    reference=load_model(args.reference,device)
    stats, games=evaluate(candidate,reference,args.engine,args.games,args.max_plies,
                          torch.device(device),args.start_fen,500000,
                          opening_plies=args.opening_plies,seed=args.seed + (0x5a17beef if args.suite=='holdout' else 0))
    report={'version':'0.6.0','created_at':datetime.now(timezone.utc).isoformat(),
            'candidate':str(args.checkpoint.resolve()),'reference':str(args.reference.resolve()),
            'games_requested':args.games,'max_plies':args.max_plies,'start_fen':args.start_fen,
            'seed':args.seed,'effective_seed':args.seed + (0x5a17beef if args.suite=='holdout' else 0),
            'suite':args.suite,'opening_plies':args.opening_plies,'statistics':stats,
            'score_interval95_hoeffding':None,
            'caveat':'Holdout means distinct from the selection seed, not a guarantee of independent games. Not Elo. Each opening is played with both colors. Pairs and deterministic match trajectories are correlated; no calibrated confidence interval is claimed.',
            'games':games}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_suffix(args.output.suffix+'.tmp')
    try:
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,args.output)
    finally:
        temp.unlink(missing_ok=True)
    print(json.dumps({k:v for k,v in report.items() if k!='games'},indent=2,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
