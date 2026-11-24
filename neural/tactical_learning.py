"""Experiment-only persistence and deterministic stratification."""
from __future__ import annotations
from collections import defaultdict
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import random

def atomic_json(path, obj):
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

@contextmanager
def experiment_lock(folder):
    """OS lock released automatically after process termination."""
    with (folder/'experiment.lock').open('a+b') as f:
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            try:yield
            finally:
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:yield
            finally:fcntl.flock(f,fcntl.LOCK_UN)

def stratify(rows, validation_count, seed):
    """Exactly requested global size; preserve both splits per class where feasible."""
    groups=defaultdict(list)
    for row in rows:groups[row['category']].append(row)
    n=len(rows)
    if not 0<validation_count<n:raise ValueError('Invalid validation size')
    keys=sorted(groups)
    lower={k:int(len(groups[k])>=2) for k in keys}
    upper={k:max(0,len(groups[k])-1) for k in keys}
    if sum(lower.values())>validation_count:lower=dict.fromkeys(keys,0)
    if sum(upper.values())<validation_count:upper={k:len(groups[k]) for k in keys}
    quota={k:validation_count*len(groups[k])/n for k in keys}
    alloc={k:min(upper[k],max(lower[k],int(quota[k]))) for k in keys}
    while sum(alloc.values())<validation_count:
        k=max((k for k in keys if alloc[k]<upper[k]),key=lambda k:(quota[k]-alloc[k],k))
        alloc[k]+=1
    while sum(alloc.values())>validation_count:
        k=max((k for k in keys if alloc[k]>lower[k]),key=lambda k:(alloc[k]-quota[k],k))
        alloc[k]-=1
    rng=random.Random(seed);out=[]
    for k in keys:
        items=list(groups[k]);rng.shuffle(items)
        out.extend(dict(r,split='validation' if i<alloc[k] else 'train') for i,r in enumerate(items))
    rng.shuffle(out)
    return out

def move_metrics(ordered, accepted):
    """ordered: descending (legal UCI move, probability) pairs."""
    targets=set(accepted)
    rank=next((i for i,(m,_) in enumerate(ordered,1) if m in targets),None)
    if rank is None:raise ValueError('No valid target in ranking')
    mass=sum(p for m,p in ordered if m in targets)
    return {'top1':float(rank==1),'top3':float(rank<=3),'top5':float(rank<=5),
            'mrr':1/rank,'rank':rank,'target_mass':mass,'target_nll':-math.log(max(mass,1e-12))}

def aggregate(metrics):
    n=len(metrics)
    if not n:raise ValueError('Empty metric group')
    result={k:sum(m[k] for m in metrics)/n for k in metrics[0]}
    result.update(correct=int(sum(m['top1'] for m in metrics)),total=n,accuracy=result['top1'])
    return result

def hard_weight(metric, class_size, mean_size):
    """Bounded curriculum weight, computed from TRAIN examples only."""
    difficulty=1.0+1.5*(1.0-metric['target_mass'])+0.5*(1.0-metric['top1'])
    balance=math.sqrt(mean_size/max(1,class_size))
    return min(4.0,max(.5,difficulty*balance))

def selection_key(metric):
    return (metric['top1'],metric['mrr'],-metric['target_nll'])
