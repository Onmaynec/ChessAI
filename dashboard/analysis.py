"""Transparent experiment analytics: no fake Elo and no invented draw results."""
from __future__ import annotations
import math


def summarize(metrics: list[dict]) -> dict:
    total={'games':0,'plies':0,'finished':0,'draws':0,'unfinished':0,'samples':0,
           'arena_wins':0,'arena_draws':0,'arena_losses':0,'arena_unfinished':0}
    series=[]
    for row in metrics:
        results=row.get('results') or {}
        a=row.get('arena') or {}
        finished=sum(int(results.get(k) or 0) for k in ('white_wins','black_wins','draws'))
        total['games']+=int(row.get('games') or 0)
        total['plies']+=int(row.get('plies') or 0)
        total['finished']+=finished
        total['draws']+=int(results.get('draws') or 0)
        total['unfinished']+=int(results.get('unfinished') or 0)
        total['samples']+=int(row.get('samples') or 0)
        for key,col in [('wins','arena_wins'),('draws','arena_draws'),('losses','arena_losses'),('unfinished','arena_unfinished')]:
            total[col]+=int(a.get(key) or 0)
        series.append({'iteration':row.get('iteration'),
                       'finish_rate': round(100*finished/int(row['games']),2) if row.get('games') else None,
                       'games_per_s':row.get('games_per_s'),
                       'plies_per_s':row.get('plies_per_s'),
                       'value_mse':(row.get('train') or {}).get('value_mse'),
                       'policy_loss':(row.get('train') or {}).get('policy_loss'),
                       'entropy':(row.get('train') or {}).get('entropy'),
                       'approx_kl':(row.get('train') or {}).get('approx_kl'),
                       'clip_fraction':(row.get('train') or {}).get('clip_fraction'),
                       'repetition_draws':sum(int(n) for reason,n in (row.get('termination_reasons') or {}).items() if 'repetition' in reason),
                       'performance':row.get('performance')})
    arena_n=total['arena_wins']+total['arena_draws']+total['arena_losses']
    arena_score=(total['arena_wins']+.5*total['arena_draws'])/arena_n if arena_n else None
    # Past in-training arenas reuse deterministic openings; do not treat them
    # as independent observations or attach a misleading 95% confidence band.
    interval = None
    warnings=[]
    reason_counts = {}
    reason_iterations = 0
    revisits = 0
    kl_stops = 0
    recent_kl = None
    recent_clip = None
    recent_grad = None
    for row in metrics:
        counts=row.get('termination_reasons')
        if counts is not None:
            reason_iterations += 1
            for reason,count in counts.items():
                reason_counts[reason] = reason_counts.get(reason,0) + int(count)
            revisits += int(row.get('position_revisits') or 0)
        train=row.get('train') or {}
        if train.get('early_stopped_kl'):kl_stops += 1
        if train.get('approx_kl') is not None:recent_kl=train['approx_kl']
        if train.get('clip_fraction') is not None:recent_clip=train['clip_fraction']
        if train.get('grad_norm') is not None:recent_grad=train['grad_norm']
    known_reasons = sum(reason_counts.values())
    repetition_draws = sum(v for k,v in reason_counts.items() if 'repetition' in k)
    if known_reasons >= 20 and repetition_draws/known_reasons > .6:
        warnings.append({'level':'warning','text':f'Среди партий с известной причиной завершения {repetition_draws/known_reasons:.1%} закончились повторением позиции. Это диагностический сигнал, а не доказательство неправильной игры.'})
    if kl_stops >= 3:
        warnings.append({'level':'info','text':f'KL-gate остановил {kl_stops} PPO-обновлений раньше запланированного числа эпох. Проверь learning rate и clip; модель не обязана становиться сильнее от меньшего KL.'})
    if total['games'] and total['unfinished']/total['games']>.2:
        warnings.append({'level':'warning','text':'Более 20% партий оборваны лимитом полуходов; их результат не известен и они не дают целевой награды PPO.'})
    if arena_n<100:
        warnings.append({'level':'info','text':f'Завершено только {arena_n} проверочных партий. Для выводов о силе модели необходима более крупная независимая серия.'})
    if series:
        first=[x['value_mse'] for x in series[:min(5,len(series))] if x['value_mse'] is not None]
        last=[x['value_mse'] for x in series[-min(5,len(series)):] if x['value_mse'] is not None]
        if first and last and sum(last)/len(last)>sum(first)/len(first)*1.5:
            warnings.append({'level':'info','text':'Value MSE за последние итерации выше начальных. Это сигнал проверить стабильность, не прямая оценка шахматной силы.'})
    return {'totals':total,'arena':{'completed':arena_n,'score':round(arena_score,5) if arena_n else None,
                 'interval95_bounded':interval,'wins':total['arena_wins'],'draws':total['arena_draws'],
                 'losses':total['arena_losses'],'unfinished':total['arena_unfinished'],
                 'method':'Descriptive score only; historic training arenas used repeated deterministic trajectories, not an Elo estimate'},
            'completion_rate':round(total['finished']/total['games'],5) if total['games'] else None,
            'draw_rate_among_finished':round(total['draws']/total['finished'],5) if total['finished'] else None,
            'series':series,'warnings':warnings,
            'quality':{'reason_iterations':reason_iterations,'termination_reasons':reason_counts,
                       'position_revisits':revisits,'repetition_draws':repetition_draws,
                       'repetition_fraction':round(repetition_draws/known_reasons,4) if known_reasons else None,
                       'kl_early_stops':kl_stops,'last_approx_kl':recent_kl,
                       'last_clip_fraction':recent_clip,'last_grad_norm':recent_grad}}
