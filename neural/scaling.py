"""Versioned scaling helpers. No changes to the inference checkpoint format."""
from __future__ import annotations
from collections import Counter,defaultdict
import math
import random
import hashlib
from .tactics import board,canonical

# Coarse material/king-zone family; deliberately NOT a claim of universal near-duplicate detection.
QUOTAS={'mate1':20,'mate2_plus':12,'fork':12,'capture':12,'check_evasion':20,
        'pin':5,'pin_capture':5,'discovered_attack':4,'mate_sacrifice':5,'promotion':5}

def quotas(count):
    q={k:count*v//100 for k,v in QUOTAS.items()}
    for k in sorted(q,key=lambda k:(-(count*QUOTAS[k]%100),k))[:count-sum(q.values())]:q[k]+=1
    return q

def family_id(fen):
    # Normalize the moving side to white; mirror king files to the nearer edge.
    b=list(board(fen));turn=fen.split()[1]
    if turn=='b':b=[p.swapcase() for rank in range(7,-1,-1) for p in b[rank*8:rank*8+8]]
    counts=tuple(b.count(p) for p in 'PNBRQpnbrq')
    def zone(piece,mirror):
        s=b.index(piece);f=s%8
        return (s//8//2,(7-f if mirror else f)//2)
    zones=min((zone('K',m),zone('k',m)) for m in (False,True))
    # Castling rights are deliberately omitted to group close variants together.
    return hashlib.sha256(repr((counts,zones)).encode()).hexdigest()[:24]

def family_split(rows,validation_count,seed):
    if not 2<=validation_count<=len(rows)-2:raise ValueError('Invalid validation count')
    grouped=defaultdict(list);total=Counter(r['category'] for r in rows)
    for r in rows:grouped[family_id(r['fen'])].append(r)
    groups=list(grouped.items());rng=random.Random(seed);rng.shuffle(groups)
    groups.sort(key=lambda x:-len(x[1]))
    # Greedy bounded group assignment toward per-category and total targets.
    target={k:v*validation_count/len(rows) for k,v in total.items()}
    current=Counter();n=0;chosen=set()
    def cost(c,size):
        return ((size-validation_count)/max(1,validation_count))**2*3+sum(
            ((c[k]-v)/max(1,v))**2 for k,v in target.items())/len(target)
    for key,group in groups:
        g=Counter(r['category'] for r in group)
        if n+len(group)<=math.ceil(validation_count*1.10) and cost(current+g,n+len(group))<cost(current,n):
            chosen.add(key);current.update(g);n+=len(group)
    # Keep a practical minimum size without breaking any family.
    if n<validation_count*.90:
        for key,group in reversed(groups):
            if key not in chosen and n+len(group)<=validation_count:
                chosen.add(key);n+=len(group)
                if n>=validation_count*.90:break
    if not validation_count*.90<=n<=validation_count*1.10 or not 2<=n<=len(rows)-2:
        raise ValueError('Family split cannot meet 90–110% validation budget; generate more diverse positions')
    out=[dict(r,family_id=key,split='validation' if key in chosen else 'train') for key,group in groups for r in group]
    rng.shuffle(out)
    return out

def verify_families(rows):
    seen={}
    for split,group in rows.items():
        for r in group:
            key=family_id(r['fen'])
            if r.get('family_id')!=key or seen.setdefault(key,split)!=split:
                raise ValueError('Family leakage or invalid family ID')
    return {s:len({r['family_id'] for r in g}) for s,g in rows.items()}

def indices(rows,metrics,epoch):
    """Adaptive train-only curriculum. Never permanently drops difficult examples."""
    if epoch>=6:return list(range(len(rows)))
    from .mastery import EASY
    easy=[i for i,r in enumerate(rows) if r['category'] in EASY]
    other=[i for i,r in enumerate(rows) if r['category'] not in EASY]
    # First introduce partially learned examples; later include all hard examples.
    other.sort(key=lambda i:(-metrics[i]['target_mass'],len(rows[i]['legal']),rows[i]['source']))
    return easy+other[:math.ceil(len(other)*epoch/6)] or list(range(len(rows)))

def weight(r,m,base):
    # Defending a check, elementary mates, and promotion cannot be sacrificed for attack accuracy.
    return min(5.,base*(1.35 if r['category'] in ('mate1','check_evasion','promotion') else 1.))

def guard_categories(current,baseline,tolerance=.05):
    for cat in ('mate1','check_evasion','promotion'):
        if cat not in current or cat not in baseline:return False
        if current[cat]['top1']<baseline[cat]['top1']-tolerance-1e-9:return False
    return True

def settings(reference,reference_sha256):
    return {'schema':'scaling_v1','reference':str(reference),'reference_sha256':reference_sha256,
            'weight_decay':.02,'head_dropout':.10,'distill_temperature':2.,
            'distill_weight':.15,'defense_tolerance':.05,'eval_train_limit':0}
