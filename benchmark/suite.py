"""Versioned, authored diagnostic suite. Not a training dataset."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

SUITE_PATH=Path(__file__).with_name('suite_v1.json')

def signature(fen):
    return ' '.join(fen.split()[:4])

def load_suite(path=SUITE_PATH):
    raw=path.read_bytes()
    payload=json.loads(raw)
    if payload.get('purpose')!='evaluation_only':raise ValueError('Expected evaluation-only suite')
    cases=payload['cases']
    if not cases or len({r['id'] for r in cases})!=len(cases):raise ValueError('Duplicate/empty case IDs')
    if len({signature(r['fen']) for r in cases})!=len(cases):raise ValueError('Duplicate positions')
    return payload,hashlib.sha256(raw).hexdigest()

def prove_mate(bridge,state,attacker,remaining,cache):
    """Exhaustive AND/OR proof within a small ply cap, not heuristic score."""
    if state['finished']:return state['result']==('1-0' if attacker=='w' else '0-1')
    if remaining<=0:return False
    key=(state['fen'],remaining,attacker)
    if key in cache:return cache[key]
    turn=state['fen'].split()[1]
    def children():
        for move in state['legal_moves']:
            bridge.new(910002,state['fen'])
            yield bridge.step(910002,move)
    checks=(prove_mate(bridge,child,attacker,remaining-1,cache) for child in children())
    result=any(checks) if turn==attacker else all(checks)
    cache[key]=result
    return result

def prepare_case(bridge,case):
    state=bridge.new(910001,case['fen'])
    if state['finished']:raise ValueError('Terminal case: '+case['id'])
    legal=state['legal_moves'];expected=case.get('accepted',[])
    if not set(expected)<=set(legal):raise ValueError('Illegal accepted move: '+case['id'])
    if 'mate_plies' in case:
        attacker=state['fen'].split()[1];cache={};cap=case['mate_plies']
        proven=[]
        for move in legal:
            bridge.new(910002,state['fen'])
            child=bridge.step(910002,move)
            if prove_mate(bridge,child,attacker,cap-1,cache):proven.append(move)
        if not proven:raise ValueError('Mate proof failed: '+case['id'])
        if expected and not set(expected)<=set(proven):raise ValueError('Expected move not proven: '+case['id'])
        if case.get('exact') and cap>1:
            for move in legal:
                bridge.new(910002,state['fen'])
                if prove_mate(bridge,bridge.step(910002,move),attacker,cap-3,cache):
                    raise ValueError('Shorter mate exists: '+case['id'])
        expected=expected or proven
    if not expected:raise ValueError('Missing accepted moves: '+case['id'])
    return sorted(expected)

def audit_sources(sources, cases, progress=print, interval=2.0):
    """Read-only scan; report progress and malformed records explicitly."""
    import gzip
    import time
    targets={signature(r['fen']):r['id'] for r in cases}
    hits=set();count=0;bad=0;done=0;records=0
    sources=[p for p in sources if p.is_file()]
    sizes=[p.stat().st_size for p in sources]
    total=sum(sizes)
    progress(f'[AUDIT] {len(sources)} files; {total/1048576:.1f} MiB on disk. Full scan may be slow.')
    started=time.monotonic()
    for index,(path,size) in enumerate(zip(sources,sizes),1):
        progress(f'[AUDIT] File {index}/{len(sources)}: {path.name} ({size/1048576:.1f} MiB)')
        last=time.monotonic()
        with path.open('rb') as raw:
            stream=gzip.GzipFile(fileobj=raw) if path.suffix=='.gz' else raw
            try:
                for line in stream:
                    records+=1
                    if line.strip():
                        try:
                            row=json.loads(line)
                            fen=row.get('fen') if isinstance(row,dict) else None
                            if not isinstance(fen,str) or len(fen.split())<4:bad+=1
                            else:
                                count+=1
                                case=targets.get(signature(fen))
                                if case:hits.add(case)
                        except (ValueError,UnicodeError):bad+=1
                    if records%1024==0 and time.monotonic()-last>=interval:
                        percent=100*(done+min(size,raw.tell()))/max(1,total)
                        progress(f'[AUDIT] ~{percent:.1f}% disk bytes | {count:,} FEN | overlaps {len(hits)} | elapsed {time.monotonic()-started:.0f}s')
                        last=time.monotonic()
            finally:
                if stream is not raw:stream.close()
        done+=size
        progress(f'[AUDIT] Finished {index}/{len(sources)} | {count:,} FEN | overlaps {len(hits)}')
    status='partial: malformed records' if bad else 'scanned' if count else 'no readable experience'
    return {'status':status,'records_checked':count,'malformed_records':bad,'overlapping_ids':sorted(hits),
            'sources':[str(p) for p in sources],
            'scope':'selected run experience only; no proof of historical non-contamination'}

def audit_experience(run,cases):
    """Exact FEN signature scan of archived and current self-play experience."""
    from neural.storage import archived_segments
    sources=archived_segments(run,'experience.jsonl')+[run/'experience.jsonl']
    return audit_sources(sources,cases,progress=lambda msg:print(msg,flush=True))
