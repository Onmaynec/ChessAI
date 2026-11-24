"""Freeze a separate evaluation-only V4 suite; no model predictions used."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
from collections import Counter
from neural.tactical_data import hash_file,label,output_dir
from neural.tactical_learning import atomic_json,experiment_lock
from neural.tactics import canonical,board,square

def build(engine,out,exclude,count=500,depth=4,seed=9339127,attempts=100000):
    from neural.selfplay import ChessBridge
    from neural.agent import START_FEN
    from neural.mastery import targeted_fen,quotas,validate_scores
    from neural.intelligence import SearchUnavailable
    from .suite import load_suite
    target_path=Path(__file__).with_name('suite_v4.json')
    if target_path.exists():raise ValueError('V4 already frozen; never regenerate to improve results')
    forbidden=set();hashes={}
    for p in sorted(Path(__file__).parent.glob('suite_v*.json')):
        payload,h=load_suite(p);hashes[str(p.resolve())]=h;forbidden.update(canonical(r['fen']) for r in payload['cases'])
    if not exclude:raise ValueError('Prior training/replay files required')
    for p in exclude:
        hashes[str(p.resolve())]=hash_file(p)
        with p.open(encoding='utf-8') as f:
            forbidden.update(canonical(json.loads(l)['fen']) for l in f if l.strip())
    cfg={'engine_sha256':hash_file(engine),'count':count,'depth':depth,'seed':seed,'excluded_hashes':hashes}
    with experiment_lock(out):
        journal=out/'holdout_state.json'
        if journal.exists():
            state=json.loads(journal.read_text(encoding='utf-8'))
            if state['config']!=cfg:raise ValueError('Holdout inputs changed')
        else:state={'config':cfg,'next_attempt':0,'cases':[],'failures':0}
        rows=state['cases'];seen=forbidden|{canonical(r['fen']) for r in rows}
        counts=Counter(r['category'] for r in rows);target=quotas(count);cursor=state['next_attempt'];failures=state['failures'];consecutive=0
        with ChessBridge(engine) as bridge:
            try:
                for i in range(cursor,attempts):
                    if len(rows)>=count:break
                    cursor=i
                    rng=random.Random(seed*1000003+i)
                    if i%2==0:
                        s=bridge.new(933101,START_FEN)
                        for _ in range(rng.randint(16,100)):
                            if s['finished']:break
                            b=board(s['fen']);moves=s['legal_moves']
                            s=bridge.step(933101,rng.choices(moves,weights=[3 if b[square(m[2:4])]!='.' else 1 for m in moves])[0])
                    else:
                        keys=list(target);cat=rng.choices(keys,weights=[max(0,target[k]-counts[k])+.1 for k in keys])[0]
                        fen=targeted_fen(rng,cat)
                        if not fen:cursor=i+1;continue
                        try:s=bridge.new(933101,fen)
                        except RuntimeError:
                            if bridge.proc.poll() is not None:raise
                            cursor=i+1;continue
                    if s['finished'] or canonical(s['fen']) in seen:cursor=i+1;continue
                    try:
                        quick=label(bridge,engine,s,2,mastery=True)
                        result=label(bridge,engine,s,depth,mastery=True) if quick else None
                        consecutive=0
                    except SearchUnavailable:
                        failures+=1;consecutive+=1;cursor=i+1
                        if consecutive>=10:raise RuntimeError('Teacher failed repeatedly')
                        continue
                    if not result:cursor=i+1;continue
                    accepted,cat,cp,tags,scores=result
                    # Require agreement between two search budgets; no certification of optimality.
                    if not set(accepted)&set(quick[0]) or cat!=quick[1]:cursor=i+1;continue
                    limit=max(target.get(cat,0),count//4) if i>=30*count else target.get(cat,0)
                    if counts[cat]>=limit:cursor=i+1;continue
                    row={'id':f'holdout_{len(rows):04d}','category':cat,'fen':s['fen'],'accepted':accepted,'v4_new':True,
                         'teacher_cp':cp,'move_scores':scores,'legal':s['legal_moves'],'origin':'trajectory' if i%2==0 else 'synthetic'}
                    validate_scores(row);rows.append(row);counts[cat]+=1;seen.add(canonical(s['fen']));cursor=i+1
                    atomic_json(journal,{'config':cfg,'next_attempt':cursor,'cases':rows,'failures':failures})
                    if len(rows)%10==0:print(f'[HOLDOUT] {len(rows)}/{count} | attempt {cursor}',flush=True)
            finally:atomic_json(journal,{'config':cfg,'next_attempt':cursor,'cases':rows,'failures':failures})
        if len(rows)!=count:raise RuntimeError('Incomplete holdout; resume with larger attempt limit')
        if hash_file(engine)!=cfg['engine_sha256'] or any(hash_file(Path(p))!=h for p,h in hashes.items()):raise RuntimeError('Holdout inputs changed')
        payload={'version':'benchmark_v4','purpose':'evaluation_only','provenance':'Frozen local search-labelled holdout; two-depth agreement, not proven optimality.',
                 'generation':cfg,'category_counts':dict(counts),'origins':dict(Counter(r['origin'] for r in rows)),'cases':rows}
        # Exclusive creation: never overwrite a frozen library, even across concurrent builders.
        raw=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8')
        tmp=out/'suite_v4.json';tmp.write_bytes(raw)
        import os
        # Hard-link a complete, fsynced temporary file on the same volume; fails if destination exists.
        import tempfile
        fd,staging=tempfile.mkstemp(prefix='.holdout_',suffix='.tmp',dir=target_path.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            os.link(staging,target_path)
        finally:Path(staging).unlink(missing_ok=True)
        print('[HOLDOUT] Frozen',target_path,hash_file(target_path),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--engine',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exclude',type=Path,nargs='+',required=True,help='All prior tactical datasets and replay JSONL')
    p.add_argument('--count',type=int,default=500);p.add_argument('--depth',type=int,default=4);p.add_argument('--seed',type=int,default=9339127)
    p.add_argument('--attempts',type=int,default=100000);p.add_argument('--resume',action='store_true');a=p.parse_args()
    if not 50<=a.count<=2000 or not 3<=a.depth<=5 or not a.count<=a.attempts<=2000000:p.error('Invalid budget')
    build(a.engine,output_dir(a.output,a.resume),a.exclude,a.count,a.depth,a.seed,a.attempts)
if __name__=='__main__':main()
