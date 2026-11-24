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

def audit_experience(run,cases):
    """Exact FEN signature scan of archived and current self-play experience.
    Does not certify external data, unknown historical runs or symmetry overlap.
    """
    from neural.storage import iter_records, archived_segments
    targets={signature(r['fen']):r['id'] for r in cases}
    hits=set();count=0
    sources=archived_segments(run,'experience.jsonl')+[run/'experience.jsonl']
    for row in iter_records(run,'experience.jsonl'):
        fen=row.get('fen')
        if not isinstance(fen,str):continue
        count+=1
        case=targets.get(signature(fen))
        if case:hits.add(case)
    return {'status':'scanned' if count else 'no readable experience','records_checked':count,'overlapping_ids':sorted(hits),
            'sources':[str(p) for p in sources if p.is_file()],
            'scope':'selected run experience only; no proof of historical non-contamination'}
