"""Read-only promotion screening, never replaces a checkpoint."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
from .tactical_data import hash_file
from .tactical_learning import atomic_json

def paired_scores(games,source,candidate):
    groups={}
    for g in games:
        if g.get('mode')!='policy' or {g['a'],g['b']}!={source,candidate}:continue
        groups.setdefault(g['opening'],[]).append(g)
    scores=[]
    for rows in groups.values():
        if len(rows)!=2 or {g['white'] for g in rows}!={source,candidate} or rows[0].get('start_fen')!=rows[1].get('start_fen'):continue
        if any(g['result'] not in ('1-0','0-1','1/2-1/2') or g.get('fallback_moves',0) for g in rows):continue
        scores.append(sum(.5 if g['result']=='1/2-1/2' else float((g['result']=='1-0')==(g['white']==candidate)) for g in rows)/2)
    return scores

def confidence(scores,seed=932,replicates=2000):
    if len(scores)<20:return None
    rng=random.Random(seed);n=len(scores)
    samples=sorted(sum(rng.choices(scores,k=n))/n for _ in range(replicates))
    return [samples[int(.025*replicates)],samples[int(.975*replicates)-1]]

def examine(report,games,source,candidate='experimental_candidate.pt'):
    if report.get('status')!='complete' or set(report.get('agents',{}))!={source,candidate}:
        raise ValueError('Need complete two-model benchmark')
    a,b=[report['agents'][n] for n in (source,candidate)]
    from benchmark.suite import load_suite
    version=report.get('suite')
    if version not in ('benchmark_v3','benchmark_v4'):raise ValueError('Use V3 or V4 suite')
    payload,expected_hash=load_suite(Path(__file__).resolve().parents[1]/'benchmark'/('suite_'+version[-2:]+'.json'))
    all_ids={c['id'] for c in payload['cases']}
    fresh_flag='v4_new' if version=='benchmark_v4' else 'v3_new'
    fresh_ids={c['id'] for c in payload['cases'] if c.get(fresh_flag)}
    audit=report.get('audit',{});excluded=set(audit.get('overlapping_ids',[]));clean=all_ids-excluded;clean_fresh=fresh_ids-excluded
    def scored(agent,mode,new=False):
        return {r['id']:r for r in agent[mode]['cases'] if r['status']=='scored' and (not new or r['id'] in fresh_ids)}
    checks={}
    def comparable(mode,new=False):
        left,right=scored(a,mode,new),scored(b,mode,new)
        if not left or left.keys()!=right.keys():return None
        return {'source':sum(r['correct'] for r in left.values()),'candidate':sum(r['correct'] for r in right.values()),'total':len(left),
                'gained':[i for i in left if not left[i]['correct'] and right[i]['correct']],
                'lost':[i for i in left if left[i]['correct'] and not right[i]['correct']]}
    full=comparable('policy');fresh=comparable('policy',True);hybrid=comparable('hybrid')
    scores=paired_scores(games,source,candidate);ci=confidence(scores)
    score=sum(scores)/len(scores) if scores else None
    checks['suite_hash']=report.get('suite_sha256')==expected_hash
    checks['complete_cases']=bool(full and fresh and hybrid and excluded<=all_ids and len(clean)>=.9*len(all_ids) and len(clean_fresh)>=.85*len(fresh_ids) and all(set(scored(agent,m))==clean and set(scored(agent,m,True))==clean_fresh for agent in (a,b) for m in ('policy','hybrid')))
    checks['audited']=audit.get('status')=='scanned' and audit.get('malformed_records')==0 and audit.get('records_checked',0)>0
    checks['canonical_audit']=audit.get('signature_mode')=='canonical_v1'
    checks['policy_no_regression']=bool(full and full['candidate']>=full['source'])
    checks['new_cases_improved']=bool(fresh and fresh['candidate']>fresh['source'])
    checks['hybrid_no_regression']=bool(hybrid and hybrid['candidate']>=hybrid['source'])
    checks['no_fallbacks']=all(agent[m].get('fallbacks')==0 for agent in (a,b) for m in ('policy','hybrid'))
    checks['paired_strength']=bool(ci and score>=.55 and ci[0]>.5)
    return {'schema':'mastery_promotion_guard_v2','decision':'eligible_for_manual_review' if all(checks.values()) else 'retain_source',
            'checks':checks,'policy':full,'new_cases':fresh,'hybrid':hybrid,'excluded_ids':sorted(excluded),'clean_cases':len(clean),'suite_cases':len(all_ids),'completed_pairs':len(scores),
            'paired_candidate_score':score,'paired_bootstrap_ci95':ci,
            'warning':'Screening only; known suite, finite teacher and partial historical scope cannot prove absolute strength. No automatic promotion.'}

def run_guard(report_path,source,candidate_path,source_path,out):
    report=json.loads(report_path.read_text(encoding='utf-8'))
    expected=report.get('checkpoints',{})
    if expected.get(source)!=hash_file(source_path) or expected.get('experimental_candidate.pt')!=hash_file(candidate_path):
        raise ValueError('Checkpoint hashes do not match benchmark')
    game_path=report_path.with_name('games.jsonl')
    if report.get('games_sha256')!=hash_file(game_path):raise ValueError('Game journal hash mismatch')
    games=[json.loads(l) for l in game_path.read_text(encoding='utf-8').splitlines()]
    result=examine(report,games,source);result['report_sha256']=hash_file(report_path)
    atomic_json(out,result);print(result,flush=True);return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--report',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    a=p.parse_args();run_guard(a.report,a.source.name,a.candidate,a.source,a.report.with_name('promotion_guard.json'))

if __name__=='__main__':main()
