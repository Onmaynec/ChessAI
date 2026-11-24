"""Conservative best-model *screening*; never overwrites latest.pt.

The promotion gate is a screening heuristic, NOT proof of Elo improvement.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import torch

from .checkpoint import load_model
from .selfplay import atomic_json, evaluate, read_json, timestamp


def initialize_best(run: Path, latest: Path, reference: Path | None) -> dict:
    best = run / 'checkpoints' / 'best.pt'
    info_path = run / 'best_status.json'
    if best.is_file():
        return read_json(info_path, {'status':'existing', 'note':'Existing best preserved'})
    source = latest
    origin = 'latest_checkpoint_unverified'
    if reference and reference.is_file():
        try:
            a = load_model(latest)
            b = load_model(reference)
            if a.config == b.config:
                source, origin = reference, 'frozen_v02_reference'
        except (RuntimeError, ValueError, KeyError, OSError):
            pass
    best.parent.mkdir(parents=True, exist_ok=True)
    temp = best.with_name('best.initializing.pt')
    try:
        shutil.copy2(source, temp)
        os.replace(temp, best)
    finally:
        temp.unlink(missing_ok=True)
    info = {'status':'initialized', 'origin':origin, 'updated_at':timestamp(),
            'note':'Initial retained model; it has not yet won a statistically decisive match.'}
    atomic_json(info_path, info)
    return info


def screening(stats: dict, *, threshold: float = .60) -> dict:
    """Demand diverse, color-balanced, sufficiently completed matches."""
    completed = stats['completed']
    pairs = stats.get('opening_pairs', 0)
    ok = (pairs >= 4 and stats.get('completed_pairs', 0) >= max(4, int(pairs * .75))
          and stats.get('unique_opening_positions', 0) >= 3
          and completed >= 8 and stats['score'] is not None
          and stats['score'] >= threshold)
    return {'promote': bool(ok), 'threshold':threshold,
            'note':'Screening threshold only; not statistically certified stronger or an Elo estimate.'}


def check_and_promote(model, run: Path, engine: Path, latest: Path, device: torch.device,
                      *, games: int, max_plies: int, seed: int, opening_plies: int) -> dict:
    best_path = run/'checkpoints'/'best.pt'
    if not best_path.is_file():
        raise FileNotFoundError('Best checkpoint must be initialized first')
    best_model = load_model(best_path, device)
    stats, records = evaluate(model, best_model, engine, games, max_plies, device,
                              'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
                              700000, opening_plies=max(4,opening_plies), seed=seed)
    decision = screening(stats)
    holdout_stats = None
    if decision['promote']:
        holdout_stats, _ = evaluate(model, best_model, engine, games, max_plies, device,
                                    'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
                                    705000,opening_plies=max(4,opening_plies),
                                    seed=seed+0x5a17beef)
        validation=screening(holdout_stats)
        decision['holdout_promote']=validation['promote']
        decision['promote']=decision['promote'] and validation['promote']
        decision['note']='Selection and disjoint-seed holdout both passed heuristic screening; not certified stronger.'
    info = {'at':timestamp(), 'candidate_iteration':int(torch.load(latest,map_location='cpu',weights_only=True)['iteration']),
            'opponent':'best.pt', 'statistics':stats, 'holdout_statistics':holdout_stats, 'decision':decision,
            'note':'latest.pt remains the resumable training checkpoint whether promoted or not.'}
    if decision['promote']:
        temp = best_path.with_name('best.promoting.pt')
        try:
            shutil.copy2(latest,temp)
            os.replace(temp,best_path)
        finally:
            temp.unlink(missing_ok=True)
        info['best_iteration'] = info['candidate_iteration']
    else:
        old = read_json(run/'best_status.json', {})
        info['best_iteration'] = old.get('best_iteration', 0)
    atomic_json(run/'best_status.json',info)
    with (run/'best_history.jsonl').open('a',encoding='utf-8') as f:
        import json
        f.write(json.dumps(info,ensure_ascii=False)+'\n')
    return info
