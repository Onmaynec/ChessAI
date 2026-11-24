"""Paired color statistics and internal ratings; no training imports."""
from __future__ import annotations
from collections import defaultdict
import math
import random

def score(result, white):
    if result == '*': return None
    if result == '1/2-1/2': return .5
    if result not in ('1-0','0-1'): raise ValueError('Unknown result')
    return float((result == '1-0') == white)

def percentile(values, p):
    if not values:return None
    v=sorted(values);i=(len(v)-1)*p
    lo=int(i);hi=min(lo+1,len(v)-1)
    return v[lo]+(i-lo)*(v[hi]-v[lo])

def summary(values):
    values=list(values)
    done=[v for v in values if v is not None]
    return dict(played=len(values), completed=len(done), unfinished=len(values)-len(done),
                wins=done.count(1.),draws=done.count(.5),losses=done.count(0.),
                score=sum(done)/len(done) if done else None)

def paired_rows(records):
    groups=defaultdict(list)
    for r in records:groups[(r['a'],r['b'],r['opening'])].append(r)
    rows=[]
    for (a,b,opening), games in groups.items():
        if len(games)!=2 or {g['white'] for g in games}!={a,b}:continue
        if len({g['start_fen'] for g in games})!=1:continue
        values=[score(g['result'],g['white']==a) for g in games]
        if None not in values:rows.append((a,b,opening,sum(values)/2))
    return rows

def fit_ratings(names, rows):
    """Regularized fractional-score Bradley-Terry; mean fixed to 1500."""
    if len(names)<2 or not rows:return None
    neighbors={n:set() for n in names};edges=defaultdict(lambda:[0.,0])
    for a,b,_,v in rows:
        neighbors[a].add(b);neighbors[b].add(a)
        edges[a,b][0]+=v;edges[a,b][1]+=1
    seen={names[0]};todo=list(seen)
    while todo:
        for n in neighbors[todo.pop()]-seen:seen.add(n);todo.append(n)
    if len(seen)!=len(names):return None
    ratings={n:0. for n in names}
    counts={n:sum(k for (a,b),(_,k) in edges.items() if n in (a,b)) for n in names}
    step=1./max(counts.values())
    for _ in range(300):
        grad={n:-.25*ratings[n] for n in names}
        for (a,b),(total,count) in edges.items():
            p=1./(1.+math.exp(max(-50.,min(50.,ratings[b]-ratings[a]))))
            delta=total-count*p
            grad[a]+=delta;grad[b]-=delta
        if max(abs(x) for x in grad.values())<1e-7:break
        for n in names:ratings[n]+=step*grad[n]
    mean=sum(ratings.values())/len(names)
    return {n:1500+400/math.log(10)*(v-mean) for n,v in ratings.items()}

def rating_report(names, records, seed=9191, bootstrap=300):
    rows=paired_rows(records)
    fit=fit_ratings(names,rows)
    groups=defaultdict(list)
    for row in rows:groups[row[2]].append(row)
    keys=sorted(groups)
    samples=defaultdict(list)
    rng=random.Random(seed)
    if fit and len(keys)>=5:
        for _ in range(bootstrap):
            draw=[r for k in rng.choices(keys,k=len(keys)) for r in groups[k]]
            other=fit_ratings(names,draw)
            if other:
                for n,v in other.items():samples[n].append(v)
    reports={}
    for n in names:
        vals=[score(g['result'],g['white']==n) for g in records if n in (g['a'],g['b'])]
        colors={c:summary(score(g['result'],g['white']==n) for g in records
                          if n in (g['a'],g['b']) and (g['white']==n)==(c=='white')) for c in ('white','black')}
        sample=samples[n]
        ci=[round(percentile(sample,p),1) for p in (.025,.975)] if len(sample)>=max(50,int(bootstrap*.8)) else None
        reports[n]={'overall':summary(vals),'colors':colors,'rating':round(fit[n],1) if fit else None,
                    'ci95':ci,'completed_pairs':sum(n in (a,b) for a,b,_,_ in rows)}
    return {'agents':reports,'complete_pairs':len(rows),'opening_blocks':len(keys),
            'bootstrap_valid':len(samples[names[0]]) if names else 0,
            'method':'regularized Bradley-Terry, mean 1500; paired opening-block bootstrap; conditional on completed pairs',
            'caveat':'Internal rating only; small samples, unfinished games, repeated or related starts can bias estimates. No CI with fewer than five opening blocks.'}
