"""Space-saving maintenance for completed Chess AI runs. Never discards records."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import torch
from neural.storage import compact_run, space_report


def main(argv=None):
    p=argparse.ArgumentParser(description='Lossless SHA-256 verified Chess AI log compression')
    p.add_argument('--run',type=Path,required=True,help='Path to one experiment folder')
    p.add_argument('--apply',action='store_true',help='Compress complete journals; default is dry-run')
    a=p.parse_args(argv)
    folder=a.run.resolve()
    if not folder.is_dir() or not (folder/'checkpoints/latest.pt').is_file():
        p.error('Experiment folder and checkpoints/latest.pt required')
    before=space_report(folder)
    result={'before':before,'mode':'dry-run'}
    if a.apply:
        checkpoint=torch.load(folder/'checkpoints/latest.pt',map_location='cpu',weights_only=True)
        result['compaction']=compact_run(folder,committed=int(checkpoint['iteration']))
        result['mode']='applied'
        result['after']=space_report(folder)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0
if __name__=='__main__':
    raise SystemExit(main())
