"""Offline paired anti-repetition experiment; never modifies PPO or checkpoints."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
from .tactical_data import output_dir,hash_file
from .tactical_learning import atomic_json

def choose_local(model,state,bridge,engine,history,enabled):
    from neural.agent import rank
    from neural.intelligence import evaluate_fens,SearchUnavailable
    from benchmark.suite import signature
    ordered,_=rank(model,state['fen'],state['legal_moves'])
    best,prob=ordered[0]
    if not enabled or prob<=0:return best,False
    seen=Counter(signature(f) for f in history)
    bridge.new(932060,state['fen']);child=bridge.step(932060,best)
    if child['finished'] or seen[signature(child['fen'])]<1:return best,False
    alternatives=[]
    for m,p in ordered[1:5]:
        if p<prob*.15:continue
        bridge.new(932060,state['fen']);s=bridge.step(932060,m)
        if s['finished'] or seen[signature(s['fen'])]:continue
        alternatives.append((m,s))
    if not alternatives:return best,False
    try:
        vals=evaluate_fens(engine,[child['fen'],*[s['fen'] for _,s in alternatives]],depth=2)
    except SearchUnavailable:return best,False
    baseline=-vals[0].score_cp
    # Never discourage a move with a mate score or when teacher sees a disadvantage.
    # A shallow cp comparison is a heuristic, not a proof of drawing safety.
    if not 50<=baseline<29000:return best,False
    acceptable=[(m,-v.score_cp) for (m,_),v in zip(alternatives,vals[1:]) if -v.score_cp>=max(50,baseline-40)]
    return (acceptable[0][0],True) if acceptable else (best,False)

def run(source,engine,out,pairs=8,cap=240,seed=9322026,device='auto'):
    import torch
    from neural.checkpoint import load_model
    from neural.selfplay import ChessBridge
    from benchmark.run import make_starts
    from .tactics import repetition_stats
    from .mastery_guard import paired_scores,confidence
    h=hash_file(source);eh=hash_file(engine)
    dev=torch.device('cuda' if device=='auto' and torch.cuda.is_available() else 'cpu' if device=='auto' else device)
    model=load_model(source,dev)
    if hash_file(source)!=h:raise ValueError('Checkpoint changed')
    games=[]
    with ChessBridge(engine) as bridge:
        starts=make_starts(bridge,pairs,seed,[])
        for start in starts:
            for white in ('plain','guarded'):
                state=bridge.new(932050,start['fen']);history=[state['fen']];moves=[];changed=0
                for _ in range(cap):
                    if state['finished']:break
                    actor=white if state['fen'].split()[1]=='w' else ('plain' if white=='guarded' else 'guarded')
                    m,c=choose_local(model,state,bridge,engine,history,actor=='guarded')
                    changed+=c;state=bridge.step(932050,m);moves.append(m);history.append(state['fen'])
                bridge.drop(932050)
                g={'a':'plain','b':'guarded','opening':start['id'],'white':white,'mode':'policy','fallback_moves':0,
                   'result':state['result'] if state['finished'] else '*','reason':state['reason'] if state['finished'] else 'max_plies_unfinished',
                   'moves':moves,'interventions':changed}
                games.append(g)
                with (out/'games.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(g)+'\n')
                print('[REPETITION]',start['id'],white,g['reason'],changed,flush=True)
    if hash_file(source)!=h or hash_file(engine)!=eh:raise RuntimeError('Inputs changed during lab')
    scores=paired_scores(games,'plain','guarded')
    atomic_json(out/'report.json',{'schema':'repetition_lab_v1','source_sha256':h,'engine_sha256':eh,
        'pairs':pairs,'completed_pairs':len(scores),'guarded_score':sum(scores)/len(scores) if scores else None,
        'ci95':confidence(scores),'interventions':sum(g['interventions'] for g in games),
        'repetition_diagnostics':repetition_stats(games),
        'warning':'Local experimental policy only, no changes to rewards or production play. Shallow cp safeguard is not a guarantee.'})

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--pairs',type=int,default=8)
    p.add_argument('--max-plies',type=int,default=240);p.add_argument('--seed',type=int,default=9322026)
    p.add_argument('--device',choices=['auto','cpu','cuda'],default='auto')
    a=p.parse_args()
    if not 1<=a.pairs<=50 or not 20<=a.max_plies<=800:p.error('Invalid lab budget')
    run(a.source,a.engine,output_dir(a.output),a.pairs,a.max_plies,a.seed,a.device)

if __name__=='__main__':main()
