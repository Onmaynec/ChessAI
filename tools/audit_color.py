"""Read-only color-perspective diagnostics for an existing checkpoint.

Comparing one network on a position and a color-flipped 180° position is an
invariance *test*, not a proof that its lack of invariance is a software bug.
"""
from __future__ import annotations
import argparse
from collections import deque
import json
import sys
from pathlib import Path
import numpy as np
import torch
from neural.checkpoint import load_model
from neural.encoding import encode_fen
from neural.quality import swap_colors_rotate_fen
from neural.selfplay import atomic_json,timestamp


def audit(model, fens: list[str], device) -> dict:
    if not fens:
        return {'positions':0,'note':'No saved positions in games.jsonl'}
    model.eval()
    all_orig=np.stack([encode_fen(f) for f in fens])
    all_mirror=np.stack([encode_fen(swap_colors_rotate_fen(f)) for f in fens])
    vals=[]
    with torch.inference_mode():
        for i in range(0,len(fens),64):
            orig=torch.from_numpy(all_orig[i:i+64]).to(device)
            swapped=torch.from_numpy(all_mirror[i:i+64]).to(device)
            va=model(orig)[1].cpu().numpy()
            vb=model(swapped)[1].cpu().numpy()
            vals.extend(zip(va.tolist(),vb.tolist()))
    err=[abs(a-b) for a,b in vals]
    signed=[a-b for a,b in vals]
    return {'positions':len(vals),'mean_abs_value_difference':round(float(np.mean(err)),6),
            'max_abs_value_difference':round(float(max(err)),6),
            'mean_signed_difference':round(float(np.mean(signed)),6),
            'note':'Diagnostic of color-rotation consistency; nonzero discrepancy is not, by itself, proof of an encoding error.'}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path)
    p.add_argument('--max-samples',type=int,default=128)
    p.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    a=p.parse_args(argv)
    if not 1<=a.max_samples<=10000:p.error('max-samples must be 1..10000')
    ck=a.checkpoint or a.run/'checkpoints/latest.pt'
    device='cuda' if a.device=='auto' and torch.cuda.is_available() else 'cpu' if a.device=='auto' else a.device
    if device=='cuda' and not torch.cuda.is_available():p.error('CUDA unavailable')
    net=load_model(ck,device)
    latest=deque(maxlen=a.max_samples)
    with (a.run/'games.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            try:
                row=json.loads(line)
            except json.JSONDecodeError:continue
            fens=row.get('fens') or []
            if fens:latest.append(fens[len(fens)//2])
    report={'version':'0.6.0','created_at':timestamp(),
            'checkpoint':str(ck.name),**audit(net,list(latest),device)}
    output=a.run/'diagnostics/color_audit.json'
    atomic_json(output,report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
