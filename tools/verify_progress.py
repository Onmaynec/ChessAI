"""Check all saved runs and checkpoint/PPO optimizer compatibility (requires torch)."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import torch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neural.encoding import FEATURE_VERSION
from neural.model import ChessNet


def verify_run(folder: Path):
    last = folder/'checkpoints'/'latest.pt'
    if not last.exists():
        raise ValueError('latest.pt missing')
    ck = torch.load(last,map_location='cpu',weights_only=True)
    for field in ('model','optimizer','config','feature_version','iteration'):
        if field not in ck:
            raise ValueError(f'{field} missing from checkpoint')
    if ck['feature_version'] != FEATURE_VERSION:
        raise ValueError(f'encoding mismatch: {ck["feature_version"]!r} != {FEATURE_VERSION!r}')
    model=ChessNet(**ck['config'])
    model.load_state_dict(ck['model'], strict=True)
    opt=torch.optim.AdamW(model.parameters())
    opt.load_state_dict(ck['optimizer'])
    metadata=json.loads((folder/'run_metadata.json').read_text(encoding='utf-8'))
    if metadata.get('feature_version') != ck['feature_version']:
        raise ValueError('run metadata/weights feature_version mismatch')
    metrics=[]
    f=folder/'metrics.jsonl'
    if f.exists():
        for line in f.read_text(encoding='utf-8').splitlines():
            if line.strip():
                try:
                    metrics.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    latest_metric=max((m['iteration'] for m in metrics),default=0)
    if latest_metric > ck['iteration']:
        raise ValueError('metrics newer than checkpoint; inspect manually')
    return {'run':folder.name,'checkpoint_iteration':ck['iteration'],
            'metrics_iteration':latest_metric,'checkpoint_size':last.stat().st_size,
            'optimizer_restorable':True,'architecture':ck['config'],
            'note':'Resume starts from checkpoint_iteration; partial in-flight work is reconciled.'}


def main(argv=None):
    p=argparse.ArgumentParser(description='Validate migrated Chess AI training progress')
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--run',help='Optional specific run ID')
    args=p.parse_args(argv)
    runs=args.root/'runs'
    folders=[runs/args.run] if args.run else sorted(x for x in runs.iterdir() if x.is_dir() and (x/'run_metadata.json').is_file()) if runs.exists() else []
    bad=0
    for path in folders:
        try:
            print('[OK] '+json.dumps(verify_run(path),ensure_ascii=False))
        except Exception as error:
            print(f'[FAIL] {path.name}: {error}',file=sys.stderr)
            bad+=1
    return 1 if bad else 0

if __name__=='__main__':
    raise SystemExit(main())
