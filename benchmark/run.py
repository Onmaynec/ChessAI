"""Read-only Intelligence Benchmark. Local engine, no online play."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from .suite import load_suite, prepare_case, audit_experience, signature
from .stats import rating_report, percentile

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def write_json(path, value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temp.replace(path)

def discover(run, names):
    from neural.agent_profiles import ALIASES
    wanted=names or ALIASES
    if len(set(wanted))!=len(wanted) or any(n not in ALIASES for n in wanted):
        raise ValueError('Choose distinct supported agent filenames')
    found={n:run/'checkpoints'/n for n in wanted}
    return {n:p for n,p in found.items() if p.is_file()},[n for n,p in found.items() if not p.is_file()]

def timing(values):
    return {'count':len(values),'median_ms':percentile(values,.5),'p95_ms':percentile(values,.95),
            'mean_ms':sum(values)/len(values) if values else None}

def make_starts(bridge, count, seed, forbidden):
    from neural.openings import open_position
    from neural.agent import START_FEN
    starts=[];seen=set(forbidden)
    for ordinal in range(count*30):
        state,moves=open_position(bridge,910010,START_FEN,seed,ordinal,8)
        fen=state['fen'];key=signature(fen)
        if not state['finished'] and key not in seen:
            starts.append({'id':len(starts),'fen':fen,'moves':moves});seen.add(key)
        bridge.drop(910010)
        if len(starts)==count:return starts
    raise RuntimeError('Could not generate distinct opening starts')

def choose(model, state, bridge, engine, mode, depth, moves=None, fens=None):
    import torch
    from neural.agent import rank
    from neural.intelligence import choose_move
    dev=next(model.parameters()).device
    if dev.type=='cuda':torch.cuda.synchronize(dev)
    start=perf_counter()
    if mode=='policy':
        ranks,_=rank(model,state['fen'],state['legal_moves'])
        move=ranks[0][0];details={'mode':'policy','top3':[m for m,_ in ranks[:3]]}
    else:
        move,_,details=choose_move(model,state,bridge,engine,depth=depth,deep_depth=None,
                                   history_moves=moves,history_fens=fens,style='balanced',repertoire='standard')
    if dev.type=='cuda':torch.cuda.synchronize(dev)
    elapsed=(perf_counter()-start)*1000
    if move not in state['legal_moves']:raise RuntimeError('Agent selected illegal move')
    return move,details,elapsed

def match(bridge,engine,models,a,b,start,white,mode,depth,cap):
    state=bridge.new(910020,start['fen']);moves=[];fens=[state['fen']]
    fallback=0
    for _ in range(cap):
        if state['finished']:break
        actor=white if state['fen'].split()[1]=='w' else (b if white==a else a)
        move,detail,_=choose(models[actor],state,bridge,engine,mode,depth,moves,fens)
        fallback+=detail.get('mode')=='neural_fallback'
        state=bridge.step(910020,move);moves.append(move);fens.append(state['fen'])
    bridge.drop(910020)
    return {'a':a,'b':b,'opening':start['id'],'start_fen':start['fen'],'white':white,
            'result':state['result'] if state['finished'] else '*','reason':state['reason'] if state['finished'] else 'max_plies_unfinished',
            'moves':moves,'fallback_moves':fallback,'mode':mode,'plies':len(moves),'final_fen':state['fen']}

def category_report(rows):
    groups=defaultdict(list)
    for r in rows:
        if r['status']=='scored':groups[r['category']].append(r)
    return {k:{'correct':sum(r['correct'] for r in v),'total':len(v),'accuracy':sum(r['correct'] for r in v)/len(v)}
            for k,v in sorted(groups.items())}

def main(argv=None):
    p=argparse.ArgumentParser(description='Chess AI Intelligence Benchmark; no training')
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True,help='New report directory outside runs/models/config')
    p.add_argument('--agents',nargs='+')
    p.add_argument('--candidate',type=Path,help='Optional separate experimental checkpoint')
    p.add_argument('--suite',choices=['v1','v2','v3','v4'],default='v3')
    p.add_argument('--profile',choices=['quick','standard','full'],default='standard')
    p.add_argument('--pairs',type=int,default=None)
    p.add_argument('--max-plies',type=int,default=240)
    p.add_argument('--depth',type=int,default=2)
    p.add_argument('--device',choices=['auto','cpu','cuda'],default='auto')
    p.add_argument('--seed',type=int,default=9102026)
    p.add_argument('--skip-audit',action='store_true',help='Skip selected run overlap scan (report is explicitly unaudited)')
    p.add_argument('--audit-cache',type=Path,help='Optional content-addressed canonical audit cache outside runs')
    p.add_argument('--validate-suite',action='store_true',help='Validate library only; no checkpoint loading')
    a=p.parse_args(argv)
    if not a.engine.is_file():p.error('Build C++ engine first')
    pairs=a.pairs if a.pairs is not None else {'quick':2,'standard':6,'full':8}[a.profile]
    if not 1<=pairs<=50 or not 20<=a.max_plies<=800 or not 1<=a.depth<=3:p.error('Invalid budget')
    import torch
    from neural.checkpoint import load_model
    from neural.selfplay import ChessBridge
    device=torch.device('cuda' if a.device=='auto' and torch.cuda.is_available() else 'cpu' if a.device=='auto' else a.device)
    if device.type=='cuda' and not torch.cuda.is_available():p.error('CUDA unavailable')
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    payload,suite_hash=load_suite(Path(__file__).with_name('suite_'+a.suite+'.json'));cases=payload['cases']
    with ChessBridge(a.engine) as bridge:
        expected={}
        for case in cases:
            expected[case['id']]=prepare_case(bridge,case)
            print('Validated:',case['id'],expected[case['id']],flush=True)
        if a.validate_suite:return
    paths,missing=discover(a.run,a.agents)
    if a.candidate:
        if not a.candidate.is_file():p.error('Candidate not found')
        paths['experimental_candidate.pt']=a.candidate
    if not paths:p.error('No supported checkpoints found in run/checkpoints')
    # Separate namespace; never write into training directories or existing reports.
    out=a.output.resolve()
    if any(part.lower() in ('runs','models','config','checkpoints','.venv','.venv-cuda') for part in out.parts):
        p.error('Report directory must be outside training/config directories')
    out.mkdir(parents=True,exist_ok=False)
    print('[BENCHMARK] Hashing checkpoints...',flush=True)
    hashes={n:digest(path) for n,path in paths.items()}
    if a.skip_audit:
        print('[AUDIT] SKIPPED: diagnostic results only; training overlap unknown.',flush=True)
    else:
        print('[AUDIT] Scanning selected run experience (read-only)...',flush=True)
    try:
        if a.skip_audit:audit={'status':'not requested','overlapping_ids':[]}
        elif a.audit_cache:
            from .audit_cache import audit_cached
            audit=audit_cached(a.run,cases,a.audit_cache)
        else:audit=audit_experience(a.run,cases)
    except (KeyboardInterrupt,OSError,EOFError) as exc:
        write_json(out/'report.json',{'schema':'intelligence_benchmark_v1','status':'interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed','phase':'audit','suite_sha256':suite_hash,'audit':{'status':'incomplete'},'error':str(exc)})
        print('[AUDIT] Incomplete; no strength results produced. Restart in a new report directory.',flush=True)
        raise
    print('[BENCHMARK] Audit status:',audit['status'],flush=True)
    excluded=set(audit['overlapping_ids'])
    report={'schema':'intelligence_benchmark_v1','status':'running','created_at':datetime.now(timezone.utc).isoformat(),
            'suite':payload['version'],'suite_sha256':suite_hash,'engine_sha256':digest(a.engine),
            'checkpoints':hashes,'missing':missing,'audit':audit,'profile':a.profile,'pairs':pairs,
            'max_plies':a.max_plies,'depth':a.depth,'seed':a.seed,'device':str(device),
            'torch':str(torch.__version__),'platform':platform.platform(),'gpu':torch.cuda.get_device_name(device) if device.type=='cuda' else None,'agents':{},'tournaments':{}}
    write_json(out/'report.json',report)
    models={}
    try:
        # Only one model on GPU during individual tests. Tournament loads all
        # weights on CPU and transfers the active pair, bounded VRAM usage.
        for n,path in paths.items():
            print('Testing',n,flush=True)
            model=load_model(path,device)
            if digest(path)!=hashes[n]:raise RuntimeError('Checkpoint changed while loading: '+n)
            results={}
            with ChessBridge(a.engine) as bridge:
                # Warm-up outside measured runs.
                first=bridge.new(910030,cases[0]['fen'])
                choose(model,first,bridge,a.engine,'policy',a.depth)
                for mode in ('policy','hybrid'):
                    if device.type=='cuda':
                        torch.cuda.synchronize(device);torch.cuda.reset_peak_memory_stats(device)
                    rows=[];latency=[]
                    for case_index,case in enumerate(cases,1):
                        print(f'  [{mode}] {case_index}/{len(cases)} {case["id"]}',flush=True)
                        if case['id'] in excluded:
                            rows.append({'id':case['id'],'category':case['category'],'status':'overlap_excluded'});continue
                        state=bridge.new(910030,case['fen'])
                        move,detail,ms=choose(model,state,bridge,a.engine,mode,a.depth)
                        latency.append(ms)
                        rows.append({'id':case['id'],'category':case['category'],'side':state['fen'].split()[1],
                                     'status':'fallback' if detail.get('mode')=='neural_fallback' else 'scored',
                                     'move':move,'accepted':expected[case['id']],'v3_new':case.get('v3_new',False),'v4_new':case.get('v4_new',False),
                                     'correct':move in expected[case['id']],'latency_ms':ms,
                                     'actual_depth':detail.get('search_depth'), 'top3':detail.get('top3')})
                    cats=category_report(rows)
                    results[mode]={'cases':rows,'categories':cats,'timing':timing(latency),
                                   'white_categories':category_report([r for r in rows if r.get('side')=='w']),
                                   'black_categories':category_report([r for r in rows if r.get('side')=='b']),
                                   'top3_correct':sum(any(m in r.get('accepted',[]) for m in (r.get('top3') or [])) for r in rows if r['status']=='scored') if mode=='policy' else None,
                                   'fallbacks':sum(r['status']=='fallback' for r in rows),
                                   'peak_allocated_mib':torch.cuda.max_memory_allocated(device)/1048576 if device.type=='cuda' else None,
                                   'peak_reserved_mib':torch.cuda.max_memory_reserved(device)/1048576 if device.type=='cuda' else None,
                                   'strengths':[k for k in sorted(cats,key=lambda k:-cats[k]['accuracy']) if cats[k]['accuracy']>=.75][:3],
                                   'weaknesses':[k for k in sorted(cats,key=lambda k:cats[k]['accuracy']) if cats[k]['accuracy']<.75][:3]}
            report['agents'][n]=results
            report.setdefault('model_configs',{})[n]={'config':model.config,'parameters':sum(p.numel() for p in model.parameters())}
            models[n]=model.cpu()
            write_json(out/'report.json',report)
        with ChessBridge(a.engine) as bridge:
            starts=make_starts(bridge,pairs,a.seed,[signature(c['fen']) for c in cases])
            report['opening_starts']=starts
            modes=('policy','hybrid') if a.profile=='full' else ('policy',)
            for mode in modes:
                records=[]
                for a_name,b_name in combinations(models,2):
                    print('Match',mode,a_name,b_name,flush=True)
                    models[a_name].to(device);models[b_name].to(device)
                    try:
                        for start in starts:
                            for white in (a_name,b_name):
                                rec=match(bridge,a.engine,models,a_name,b_name,start,white,mode,a.depth,a.max_plies)
                                records.append(rec)
                                with (out/'games.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
                                print(' ',start['id'],white,rec['result'],len(rec['moves']),flush=True)
                    finally:
                        models[a_name].cpu();models[b_name].cpu()
                # Hybrid fallbacks invalidate the complete color pair for rating.
                invalid={(r['a'],r['b'],r['opening']) for r in records if r['fallback_moves']}
                rated=[r for r in records if (r['a'],r['b'],r['opening']) not in invalid]
                report['tournaments'][mode]={'rating':rating_report(list(models),rated,seed=a.seed),
                                              'games':len(records),'excluded_fallback_pairs':len(invalid)}
                write_json(out/'report.json',report)
        if digest(a.engine)!=report['engine_sha256']:raise RuntimeError('Engine changed during benchmark')
        if any(digest(path)!=hashes[n] for n,path in paths.items()):
            raise RuntimeError('Checkpoint changed during benchmark; results invalid. Stop training and rerun.')
        from neural.tactics import repetition_stats
        game_log=out/'games.jsonl'
        report['repetition_diagnostics']=repetition_stats(json.loads(line) for line in game_log.read_text(encoding='utf-8').splitlines()) if game_log.is_file() else repetition_stats([])
        report['games_sha256']=digest(game_log) if game_log.is_file() else None
        if game_log.is_file():
            games=[json.loads(l) for l in game_log.read_text(encoding='utf-8').splitlines()]
            report['unfinished_games']=[{k:g[k] for k in ('opening','white','mode','plies','final_fen','reason')} for g in games if g['result']=='*']
        report['status']='complete'
    except BaseException as exc:
        report['status']='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed'
        report['error']=str(exc);write_json(out/'report.json',report);raise
    write_json(out/'report.json',report)
    lines=['# Intelligence Benchmark v0.9.3.2','',f"Status: {report['status']} | device: {device} | suite: {suite_hash[:12]}",
           '', 'Internal ratings only. Curated motif targets are not certified optimal moves. Small groups are diagnostic.','']
    for n,results in report['agents'].items():
        lines.extend(['## '+n,'','| Mode | Category | Correct / scored |','|---|---|---|'])
        for mode,res in results.items():
            for cat,v in res['categories'].items():lines.append(f"| {mode} | {cat} | {v['correct']} / {v['total']} |")
        lines.append('')
        for mode,res in results.items():
            lines.append(f"- {mode}: median/p95 ms {res['timing']['median_ms']} / {res['timing']['p95_ms']}; peak allocated MiB {res['peak_allocated_mib']}; fallback {res['fallbacks']}.")
            lines.append(f"  Relative strongest categories: {', '.join(res['strengths'])}; weakest: {', '.join(res['weaknesses'])}.")
        lines.append('')
    for mode,tour in report['tournaments'].items():
        lines.extend(['## Tournament '+mode,'','| Agent | Rating | 95% CI | White score | Black score | Finished |','|---|---:|---|---:|---:|---:|'])
        for name,r in sorted(tour['rating']['agents'].items(),key=lambda x:x[1]['rating'] if x[1]['rating'] is not None else -1,reverse=True):
            lines.append(f"| {name} | {r['rating']} | {r['ci95']} | {r['colors']['white']['score']} | {r['colors']['black']['score']} | {r['overall']['completed']}/{r['overall']['played']} |")
        lines.extend(['',tour['rating']['caveat'],''])
    lines.extend(['## Repetition diagnostics','',str(report['repetition_diagnostics']),''])
    lines.extend(['## Integrity','',f"Missing agents: {', '.join(missing) or 'none'}",f"Overlap audit: {audit}",'Original checkpoint hashes unchanged.'])
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved:',out,flush=True)

if __name__=='__main__':main()
