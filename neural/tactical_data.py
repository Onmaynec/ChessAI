"""Generate local teacher-labelled tactics, never copy benchmark solutions."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import os
from .tactical_learning import atomic_json, experiment_lock, stratify
from .tactics import board, canonical, describe, attacks, color, name, enemy

def hash_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def output_dir(path,resume=False):
    p=path.resolve()
    if any(x.lower() in ('runs','models','config','checkpoints','.venv','.venv-cuda') for x in p.parts):
        raise ValueError('Use a new experiment directory outside training data')
    p.mkdir(parents=True,exist_ok=resume)
    return p

def sparse_fen(rng,extra=False):
    """Random legal-looking KQK, KRK or KPK; bridge supplies final legality."""
    b=['.']*64
    k,e,p=rng.sample(range(64),3)
    if max(abs(k%8-e%8),abs(k//8-e//8))<=1:return None
    piece=rng.choice(('Q','Q','R','P'))
    if piece=='P' and p//8 not in (5,6):return None
    b[k]='K';b[e]='k';b[p]=piece
    if extra:
        for sq in rng.sample([i for i,x in enumerate(b) if x=='.'],rng.randint(2,5)):
            b[sq]=rng.choice('NBRQnbrq')
    if any(x!='.' and x.isupper() and e in attacks(b,i) for i,x in enumerate(b)):return None
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

def label(bridge,engine,state,depth,mastery=False):
    from neural.intelligence import evaluate_fens
    moves=children(bridge,state)
    side=state['fen'].split()[1]
    win='1-0' if side=='w' else '0-1'
    immediate=[m for m,s in moves.items() if s['finished'] and s['result']==win and s.get('reason')=='checkmate']
    if immediate and not mastery:
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
    if immediate:
        accepted=sorted(immediate);category='mate1'
    elif best>=29000:
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
    if mastery and category=='mate2_plus' and 'possible_sacrifice' in kinds:
        # Require an actual legal capture of the offered piece, not just attack geometry.
        if any(m[2:4]==chosen[2:4] for m in moves[chosen]['legal_moves']):category='mate_sacrifice'
    if category is None:
        category=next((k for k in ('promotion','check_evasion','pin_capture','fork','pin','discovered_attack') if k in kinds),None)
        if category is None:
            # Clear material capture; do not call this a proven tactic.
            b=board(state['fen'])
            from .tactics import square
            if enemy(b[square(chosen[2:4])],side):category='capture'
            else:return None
    return (accepted,category,best,tags,scores) if mastery else (accepted,category,best,tags)

def generate(engine,out,count,depth,seed,attempts,validation_count=None,resume=False,mastery=False):
    from benchmark.suite import load_suite
    validation_count=validation_count if validation_count is not None else max(2,round(count/6))
    suite_dir=Path(__file__).resolve().parents[1]/'benchmark'
    forbidden=set();suite_hashes={}
    for path in sorted(suite_dir.glob('suite_v*.json')):
        payload,sha=load_suite(path)
        suite_hashes[path.name]=sha
        forbidden.update(canonical(c['fen']) for c in payload['cases'])
    if not forbidden:raise ValueError('Benchmark exclusion set missing')
    config={'schema':'tactical_data_v3' if mastery else 'tactical_data_v2','seed':seed,'depth':depth,'count':count,
            'validation_count':validation_count,'engine_sha256':hash_file(engine),'suite_hashes':suite_hashes}
    with experiment_lock(out):
        return generate_locked(engine,out,config,attempts,forbidden,resume)

def generate_locked(engine,out,config,attempts,forbidden,resume):
    from neural.selfplay import ChessBridge
    from neural.agent import START_FEN
    from neural.intelligence import SearchUnavailable
    count=config['count'];depth=config['depth'];seed=config['seed']
    mastery=config['schema']=='tactical_data_v3'
    from .mastery import quotas,deficits,targeted_fen,validate_scores
    target=quotas(count) if mastery else None
    journal=out/'generation_state.json';pool=out/'pool.jsonl'
    if journal.exists():
        if not resume:raise ValueError('Experiment exists; use --resume')
        state=json.loads(journal.read_text(encoding='utf-8'))
        if state['config']!=config:raise ValueError('Resume configuration, engine or benchmark changed')
    else:
        if pool.exists():raise ValueError('Missing generation state')
        state={'config':config,'next_attempt':0,'teacher_failures':0}
        atomic_json(journal,state)
    rows=[];seen=set(forbidden);counts=Counter();sources=set()
    if pool.exists():
        # Only a torn final record may be removed after a process/power failure.
        with pool.open('r+b') as f:
            while True:
                pos=f.tell();line=f.readline()
                if not line:break
                if not line.endswith(b'\n'):
                    f.seek(pos);f.truncate();break
                row=json.loads(line);key=canonical(row['fen'])
                if key in seen or row['source'] in sources:raise ValueError('Pool duplicate or benchmark overlap')
                if mastery:validate_scores(row)
                seen.add(key);sources.add(row['source']);rows.append(row);counts[row['category']]+=1
    cursor=max(state['next_attempt'],max((int(r['source'].split(':')[-1])+1 for r in rows),default=0))
    failures=state['teacher_failures'];consecutive=0
    cap=max(6,count//4)
    print(f'[DATA] Resume cursor {cursor}; {len(rows)}/{count} positions; depth {depth}',flush=True)
    if len(rows)<count:
        with pool.open('ab') as f,ChessBridge(engine) as bridge:
            try:
                for i in range(cursor,attempts):
                    if len(rows)>=count:break
                    cursor=i
                    if i%25==0:
                        atomic_json(journal,{'config':config,'next_attempt':i,'teacher_failures':failures})
                        print(f'[DATA] attempt {i}/{attempts} | {len(rows)}/{count} | {dict(counts)}',flush=True)
                    # Per-attempt seed makes replays independent of interruption.
                    rng=random.Random(seed*1000003+i)
                    if mastery and i%4!=1:
                        remaining=deficits(counts,target)
                        keys=list(remaining);weights=[remaining[k]+.05 for k in keys]
                        focus=rng.choices(keys,weights=weights)[0]
                        fen=targeted_fen(rng,focus)
                        if not fen:cursor=i+1;continue
                        try:position=bridge.new(930001,fen)
                        except RuntimeError:
                            if bridge.proc.poll() is not None:raise
                            cursor=i+1;continue
                    elif not mastery and i%3!=1:
                        fen=sparse_fen(rng,extra=i%3==2)
                        if not fen:cursor=i+1;continue
                        try:position=bridge.new(930001,fen)
                        except RuntimeError:
                            if bridge.proc.poll() is not None:raise
                            cursor=i+1;continue
                    else:
                        position=bridge.new(930001,START_FEN)
                        for _ in range(rng.randint(10,75)):
                            if position['finished']:break
                            b=board(position['fen'])
                            from .tactics import square
                            moves=position['legal_moves']
                            weights=[4 if b[square(m[2:4])]!='.' else 1 for m in moves]
                            position=bridge.step(930001,rng.choices(moves,weights=weights)[0])
                    if position['finished']:cursor=i+1;continue
                    key=canonical(position['fen'])
                    if key in seen:cursor=i+1;continue
                    try:
                        # Cheap screening, then independently recompute all legal scores at target depth.
                        result=label(bridge,engine,position,min(2,depth))
                        if result and mastery:
                            result=label(bridge,engine,position,depth,mastery=True)
                        elif result and depth>2 and result[1]!='mate1':
                            result=label(bridge,engine,position,depth)
                        consecutive=0
                    except SearchUnavailable:
                        failures+=1;consecutive+=1;cursor=i+1
                        if consecutive>=10:raise RuntimeError('Ten consecutive teacher failures; reduce depth or inspect engine')
                        continue
                    if not result:cursor=i+1;continue
                    moves,category,cp,tags=result[:4]
                    if mastery:
                        # Strict category targets initially; explicit relaxed cap after 15 attempts per target row.
                        limit=target.get(category,0) if i<15*count else max(target.get(category,0),cap)
                    else:limit=cap
                    if counts[category]>=limit:cursor=i+1;continue
                    row={'fen':position['fen'],'accepted':moves,'legal':position['legal_moves'],
                         'category':category,'teacher_cp':cp,'evidence':tags,'source':f'generated:{seed}:{i}'}
                    if mastery:
                        row['move_scores']=result[4];validate_scores(row)
                    f.write((json.dumps(row)+'\n').encode('utf-8'));f.flush();os.fsync(f.fileno())
                    rows.append(row);seen.add(key);counts[category]+=1;cursor=i+1
                    if len(rows)%10==0 or len(rows)==count:
                        print(f'[DATA] {len(rows)}/{count} {category} | attempt {cursor}',flush=True)
            finally:
                atomic_json(journal,{'config':config,'next_attempt':cursor,'teacher_failures':failures})
    if hash_file(engine)!=config['engine_sha256']:raise RuntimeError('Engine changed during generation')
    if len(rows)!=count:
        print(f'[DATA] Incomplete pool {len(rows)}/{count}; rerun --resume with larger --attempts.',flush=True)
        raise RuntimeError('Requested dataset not complete; journal preserved')
    split_rows=stratify(rows,config['validation_count'],seed)
    path=out/'dataset.jsonl';tmp=path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8',newline='\n') as f:
        for r in split_rows:f.write(json.dumps(r)+'\n')
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    distribution={s:dict(Counter(r['category'] for r in split_rows if r['split']==s)) for s in ('train','validation')}
    meta={**config,'counts':dict(counts),'splits':dict(Counter(r['split'] for r in split_rows)),
          'category_splits':distribution,'missing_validation_categories':sorted(set(counts)-set(distribution['validation'])),
          'teacher_failures':failures,'excluded_signatures':len(forbidden),'complete':True,
          'dataset_sha256':hash_file(path)}
    if mastery:
        meta.update(target_quotas=target,quota_shortfalls=deficits(counts,target),
                    quota_relaxed=any(counts[k]>v for k,v in target.items()),score_schema='all_legal_cp_v1')
    atomic_json(out/'dataset_meta.json',meta)
    print('[DATA] Complete:',meta,flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--count',type=int,default=600);p.add_argument('--validation-count',type=int)
    p.add_argument('--depth',type=int,default=3);p.add_argument('--seed',type=int,default=9312026)
    p.add_argument('--attempts',type=int,default=30000);p.add_argument('--resume',action='store_true')
    p.add_argument('--mastery',action='store_true',help='Full teacher scores and targeted category quotas')
    a=p.parse_args()
    val=a.validation_count if a.validation_count is not None else max(2,round(a.count/6))
    if not a.engine.is_file() or not 10<=a.count<=20000 or not 2<=a.depth<=5 or not a.count<=a.attempts<=2000000 or not 2<=val<=a.count-2:p.error('Invalid engine or budget')
    generate(a.engine,output_dir(a.output,a.resume),a.count,a.depth,a.seed,a.attempts,val,a.resume,a.mastery)

if __name__=='__main__':main()
