"""Generate local teacher-labelled tactics, never copy benchmark solutions."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from .tactics import board, canonical, describe, attacks, color, name, enemy

def hash_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def output_dir(path):
    p=path.resolve()
    if any(x.lower() in ('runs','models','config','checkpoints','.venv','.venv-cuda') for x in p.parts):
        raise ValueError('Use a new experiment directory outside training data')
    p.mkdir(parents=True,exist_ok=False)
    return p

def sparse_fen(rng):
    """Random legal-looking KQK, KRK or KPK; bridge supplies final legality."""
    b=['.']*64
    k,e,p=rng.sample(range(64),3)
    if max(abs(k%8-e%8),abs(k//8-e//8))<=1:return None
    piece=rng.choice(('Q','Q','R','P'))
    if piece=='P' and p//8 not in (5,6):return None
    b[k]='K';b[e]='k';b[p]=piece
    if e in attacks(b,p):return None
    if rng.randrange(2):
        b=[x.swapcase() for x in b[::-1]];turn='b'
    else:turn='w'
    ranks=[]
    for r in range(7,-1,-1):
        row='';empty=0
        for q in b[r*8:r*8+8]:
            if q=='.':empty+=1
            else:
                if empty:row+=str(empty);empty=0
                row+=q
        if empty:row+=str(empty)
        ranks.append(row)
    return '/'.join(ranks)+' '+turn+' - - 0 1'

def children(bridge,state):
    out={}
    for m in state['legal_moves']:
        bridge.new(930002,state['fen'])
        out[m]=bridge.step(930002,m)
    return out

def label(bridge,engine,state,depth):
    from neural.intelligence import evaluate_fens
    moves=children(bridge,state)
    side=state['fen'].split()[1]
    win='1-0' if side=='w' else '0-1'
    immediate=[m for m,s in moves.items() if s['finished'] and s['result']==win and s.get('reason')=='checkmate']
    if immediate:
        return immediate,'mate1',29999,describe(state['fen'],immediate[0],moves[immediate[0]]['fen'],29999)
    live=[(m,s) for m,s in moves.items() if not s['finished']]
    scores={}
    for m,s in moves.items():
        if s['finished']:scores[m]=29999 if s['result']==win else 0 if s['result']=='1/2-1/2' else -29999
    for (m,_),answer in zip(live,evaluate_fens(engine,[s['fen'] for _,s in live],depth=depth)):
        v=-answer.score_cp
        scores[m]=v-1 if v>=29000 else v+1 if v<=-29000 else v
    if not scores:return None
    best=max(scores.values());chosen=max(scores,key=scores.get)
    if best>=29000:
        accepted=sorted(m for m,v in scores.items() if v==best)
        category='mate2_plus'
    else:
        accepted=sorted(m for m,v in scores.items() if v>=best-35)
        others=[v for m,v in scores.items() if m not in accepted]
        # Require a clear tactical alternative, not arbitrary positional preference.
        if not others or best-max(others)<100 or best<=-29000:return None
        category=None
    tags=describe(state['fen'],chosen,moves[chosen]['fen'],best)
    kinds={t['kind'] for t in tags}
    if category is None:
        category=next((k for k in ('promotion','check_evasion','pin_capture','fork','pin','discovered_attack') if k in kinds),None)
        if category is None:
            # Clear material capture; do not call this a proven tactic.
            b=board(state['fen'])
            from .tactics import square
            if enemy(b[square(chosen[2:4])],side):category='capture'
            else:return None
    return accepted,category,best,tags

def generate(engine,out,count,depth,seed,attempts):
    from neural.selfplay import ChessBridge
    from neural.agent import START_FEN
    from neural.intelligence import SearchUnavailable
    from benchmark.suite import load_suite
    suite_dir=Path(__file__).resolve().parents[1]/'benchmark'
    forbidden=set()
    for path in sorted(suite_dir.glob('suite_v*.json')):
        payload,_=load_suite(path)
        forbidden.update(canonical(c['fen']) for c in payload['cases'])
    if not forbidden:raise ValueError('Benchmark exclusion set missing')
    rng=random.Random(seed);seen=set(forbidden);counts=Counter();splits=Counter();failures=0
    cap=max(6,count//5)
    target={'train':max(1,int(count*.8)),'validation':count-max(1,int(count*.8))}
    with (out/'dataset.jsonl').open('x',encoding='utf-8') as f,ChessBridge(engine) as bridge:
        for i in range(attempts):
            if all(splits[k]>=v for k,v in target.items()):break
            split='validation' if i%5==0 else 'train'
            if splits[split]>=target[split]:continue
            # Each example has its own independently generated trajectory.
            if i%2==0:
                fen=sparse_fen(rng)
                if not fen:continue
                try:state=bridge.new(930001,fen)
                except RuntimeError:continue
            else:
                state=bridge.new(930001,START_FEN)
                for _ in range(rng.randint(12,65)):
                    if state['finished']:break
                    b=board(state['fen'])
                    from .tactics import square
                    legal=state['legal_moves']
                    weights=[4 if b[square(m[2:4])]!='.' else 1 for m in legal]
                    state=bridge.step(930001,rng.choices(legal,weights=weights)[0])
            if state['finished']:continue
            key=canonical(state['fen'])
            if key in seen:continue
            seen.add(key)
            try:result=label(bridge,engine,state,depth)
            except SearchUnavailable:
                failures+=1
                if failures>=10:raise RuntimeError('Ten teacher failures; verify engine version and depth')
                continue
            if not result:continue
            moves,category,cp,tags=result
            if counts[category]>=cap:continue
            row={'fen':state['fen'],'accepted':moves,'legal':state['legal_moves'],'category':category,
                 'split':split,'teacher_cp':cp,'evidence':tags,'source':f'generated:{seed}:{i}'}
            f.write(json.dumps(row)+'\n');f.flush()
            counts[category]+=1;splits[split]+=1
            print(f'[DATA] {sum(splits.values())}/{count} {split} {category} (attempt {i+1}/{attempts})',flush=True)
    meta={'schema':'tactical_data_v1','seed':seed,'depth':depth,'engine_sha256':hash_file(engine),
          'counts':dict(counts),'splits':dict(splits),'teacher_failures':failures,'excluded_signatures':len(forbidden),
          'complete':all(splits[k]>=v for k,v in target.items()),'dataset_sha256':hash_file(out/'dataset.jsonl')}
    (out/'dataset_meta.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(meta,flush=True)
    if min(splits['train'],splits['validation'])<2:raise RuntimeError('Insufficient dataset; increase attempts')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--count',type=int,default=160);p.add_argument('--depth',type=int,default=2)
    p.add_argument('--seed',type=int,default=9302026);p.add_argument('--attempts',type=int,default=2400)
    a=p.parse_args()
    if not a.engine.is_file() or not 10<=a.count<=10000 or not 1<=a.depth<=4 or not a.count<=a.attempts<=100000:p.error('Invalid engine or budget')
    generate(a.engine,output_dir(a.output),a.count,a.depth,a.seed,a.attempts)

if __name__=='__main__':main()
