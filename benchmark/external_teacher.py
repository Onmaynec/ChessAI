"""Independent PGN evaluation with a user-supplied UCI teacher (e.g. Stockfish).
Requires optional python-chess. Never downloads engines or uses targets for training.
"""
from __future__ import annotations
import argparse,json,random
from pathlib import Path
from collections import Counter
from neural.tactical_data import hash_file,output_dir
from neural.tactical_learning import atomic_json
from neural.tactics import canonical

def freeze(pgn,out,count,seed,exclude):
    import chess.pgn
    from .suite import load_suite
    forbidden=set();hashes={}
    for p in sorted(Path(__file__).parent.glob('suite_v*.json')):
        data,h=load_suite(p);hashes[str(p.resolve())]=h;forbidden.update(canonical(r['fen']) for r in data['cases'])
    for p in exclude:
        hashes[str(p.resolve())]=hash_file(p)
        with p.open(encoding='utf-8') as f:
            forbidden.update(canonical(json.loads(l)['fen']) for l in f if l.strip())
    pgn_hash=hash_file(pgn);rng=random.Random(seed);seen=set(forbidden);rows=[];games=valid=0
    with pgn.open(encoding='utf-8-sig',errors='strict') as f:
        while True:
            game=chess.pgn.read_game(f)
            if game is None:break
            games+=1
            if game.errors or game.board().chess960 or game.board().uci_variant!='chess':continue
            positions=[]
            for ply,b in enumerate(game.mainline(),1):
                pos=b.board()
                if ply>=12 and pos.is_valid() and not pos.is_game_over() and len(list(pos.legal_moves))>=2:
                    positions.append(pos.fen(en_passant='fen'))
            rng.shuffle(positions)
            fen=next((x for x in positions if canonical(x) not in seen),None)
            if fen is None:continue
            seen.add(canonical(fen));valid+=1
            row={'id':f'pgn_game_{games:08d}','fen':fen}
            if len(rows)<count:rows.append(row)
            else:
                i=rng.randrange(valid)
                if i<count:rows[i]=row
            if games%1000==0:print('[EXTERNAL] PGN games scanned',games,flush=True)
    if len(rows)!=count:raise ValueError(f'Need {count} eligible games, got {len(rows)}')
    if hash_file(pgn)!=pgn_hash or any(hash_file(Path(p))!=h for p,h in hashes.items()):raise RuntimeError('Inputs changed')
    rows.sort(key=lambda r:r['id']);path=out/'external_positions.json'
    atomic_json(path,{'schema':'external_holdout_v1','purpose':'evaluation_only','pgn_sha256':pgn_hash,
                'excluded_hashes':hashes,'seed':seed,'games_scanned':games,'eligible_games':valid,'cases':rows})
    return path

def evaluate(positions,uci,models,out,nodes,run=None,audit_cache=None,device='auto',exclude=()):
    import chess
    import chess.engine
    import torch
    from neural.agent import rank
    from neural.checkpoint import load_model
    payload=json.loads(positions.read_text(encoding='utf-8'))
    if payload.get('schema')!='external_holdout_v1' or payload.get('purpose')!='evaluation_only':raise ValueError('Invalid frozen positions')
    cases=payload['cases']
    if not cases or len({r['id'] for r in cases})!=len(cases) or len({canonical(r['fen']) for r in cases})!=len(cases):raise ValueError('Invalid case IDs')
    hashes={n:hash_file(p) for n,p in models.items()};engine_hash=hash_file(uci);pos_hash=hash_file(positions)
    audit={'status':'not requested','overlapping_ids':[]}
    if run is not None:
        from .audit_cache import audit_cached
        audit=audit_cached(run,cases,audit_cache)
    from .suite import load_suite
    forbidden=set()
    for p in sorted(Path(__file__).parent.glob('suite_v*.json')):
        s,_=load_suite(p);forbidden.update(canonical(r['fen']) for r in s['cases'])
    for p in exclude:
        with p.open(encoding='utf-8') as f:forbidden.update(canonical(json.loads(l)['fen']) for l in f if l.strip())
    prior_overlap={r['id'] for r in cases if canonical(r['fen']) in forbidden}
    audit['known_training_or_suite_overlap']=sorted(prior_overlap)
    excluded=set(audit['overlapping_ids'])|prior_overlap;dev=torch.device('cuda' if device=='auto' and torch.cuda.is_available() else 'cpu' if device=='auto' else device)
    networks={n:load_model(p,dev) for n,p in models.items()}
    stats={n:[] for n in models};report={'schema':'external_teacher_v1','status':'running','positions_sha256':pos_hash,
        'engine_sha256':engine_hash,'models':hashes,'nodes_per_search':nodes,'audit':audit,'device':str(dev)}
    with chess.engine.SimpleEngine.popen_uci(str(uci.resolve()),timeout=60) as engine:
        options={k:v for k,v in {'Threads':1,'Hash':64}.items() if k in engine.options}
        engine.configure(options);report['teacher']=dict(engine.id);atomic_json(out/'report.json',report)
        # A unique game object per search triggers ucinewgame, reducing carry-over.
        def analyse(b,root=None):
            result=engine.analyse(b,chess.engine.Limit(nodes=nodes),game=object(),root_moves=root)
            score=result['score'].pov(b.turn)
            return {'move':result['pv'][0].uci(),'cp':score.score(mate_score=30000),'mate':score.mate(),
                    'depth':result.get('depth'),'nodes':result.get('nodes')}
        for i,c in enumerate(cases,1):
            if c['id'] in excluded:continue
            b=chess.Board(c['fen'])
            if not b.is_valid() or b.is_game_over():raise ValueError('Invalid external position')
            moves=[m.uci() for m in b.legal_moves]
            best=analyse(b);answers={best['move']:best};entry={'id':c['id'],'best':best,'models':{}}
            for n,model in networks.items():
                ordered,_=rank(model,c['fen'],moves);chosen=ordered[0][0]
                if chosen not in answers:answers[chosen]=analyse(b,[chess.Move.from_uci(chosen)])
                a=answers[chosen]
                if a['move']!=chosen:raise ValueError('Teacher ignored root move')
                # Fixed node budget estimates, not exact optimal regret.
                gap=max(0,best['cp']-a['cp']);m={'move':chosen,'top1':chosen==best['move'],'top3':best['move'] in [m for m,_ in ordered[:3]],
                    'regret_cp_capped':min(2000,gap),'within_100cp':gap<=100,'loses_mate':best['mate'] is not None and best['mate']>0 and not(a['mate'] is not None and a['mate']>0),
                    'teacher':a}
                stats[n].append(m);entry['models'][n]=m
            with (out/'positions.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(entry)+'\n')
            print(f'[EXTERNAL] {i}/{len(cases)}',flush=True)
    if hash_file(uci)!=engine_hash or hash_file(positions)!=pos_hash or any(hash_file(p)!=hashes[n] for n,p in models.items()):raise RuntimeError('Inputs changed')
    if not all(stats.values()):raise ValueError('No nonoverlapping cases')
    report.update(status='complete',results={n:{'count':len(rows),**{k:sum(r[k] for r in rows)/len(rows) for k in ('top1','top3','regret_cp_capped','within_100cp','loses_mate')}} for n,rows in stats.items()},
        journal_sha256=hash_file(out/'positions.jsonl'),warning='PGN provenance must be independent; finite-node UCI estimates, selected-run audit only; not a promotion certificate.')
    atomic_json(out/'report.json',report);print('[EXTERNAL] Complete',out,flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pgn',type=Path);p.add_argument('--positions',type=Path);p.add_argument('--uci',type=Path,required=True)
    p.add_argument('--agent',action='append',required=True,metavar='NAME=CHECKPOINT')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--count',type=int,default=500);p.add_argument('--nodes',type=int,default=50000)
    p.add_argument('--seed',type=int,default=9349011);p.add_argument('--exclude',type=Path,nargs='*',default=[])
    p.add_argument('--run',type=Path);p.add_argument('--audit-cache',type=Path)
    p.add_argument('--device',choices=['auto','cpu','cuda'],default='auto');a=p.parse_args()
    try:import chess.pgn,chess.engine
    except ImportError:p.error('Optional dependency missing: install python-chess in the selected environment')
    if bool(a.pgn)==bool(a.positions) or not 50<=a.count<=5000 or not 1000<=a.nodes<=1000000:p.error('Invalid inputs or budget')
    if bool(a.run)!=bool(a.audit_cache):p.error('--run and --audit-cache must be provided together')
    models={}
    for item in a.agent:
        n,sep,path=item.partition('=')
        if not sep or not n or n in models or not Path(path).is_file():p.error('Invalid agent')
        models[n]=Path(path)
    if len(models)>4:p.error('At most four agents')
    out=output_dir(a.output)
    exclude=sorted(set(Path('tactical_experiments').rglob('dataset.jsonl'))|set(Path('tactical_experiments').rglob('replay.jsonl'))|set(a.exclude))
    positions=a.positions or freeze(a.pgn,out,a.count,a.seed,exclude)
    evaluate(positions,a.uci,models,out,a.nodes,a.run,a.audit_cache,a.device,exclude)

if __name__=='__main__':main()
