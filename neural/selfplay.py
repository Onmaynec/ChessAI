"""ChessAI v0.7 continuous GPU microbatch self-play + clipped PPO.

Chess positions, legality, checkmate and draws come exclusively from C++ bridge.
No visual game client, chess website automation or external model/API is involved.

Usage: python -m neural.selfplay --engine build/chessai --out runs/example --iterations 20
"""
from __future__ import annotations

import argparse
import errno
import json
import math
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

from .checkpoint import load_model
from .encoding import FEATURE_VERSION, POLICY_SIZE, encode_fen, encode_move
from .model import ChessNet
from .openings import open_position
from .quality import repeated_positions, reversible_move_candidates, reason_breakdown
from .league import load_league
from .storage import compact_run, iter_records, last_game_id, space_report

ROOT = Path(__file__).resolve().parents[1]
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt, delay in enumerate((0.03, 0.06, 0.12, 0.24, 0.4, None)):
        try:
            os.replace(tmp, path)
            return
        except OSError as error:
            retryable = error.errno in (errno.EACCES, errno.EPERM) or getattr(error, 'winerror', None) in (32, 33)
            if not retryable or delay is None:
                raise
            time.sleep(delay)


def append_json(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for text in f:
            if text.strip():
                try:
                    rows.append(json.loads(text))
                except json.JSONDecodeError:
                    pass  # A process can be interrupted while writing the final line.
    return rows


class ChessBridge:
    """One long-lived, small C++ process controls many chess positions."""

    def __init__(self, executable: Path):
        if not executable.is_file():
            raise FileNotFoundError(f"Chess engine not found: {executable}. Compile it first.")
        self.proc = subprocess.Popen([str(executable.resolve()), "bridge"], text=True,
                                     bufsize=1, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)

    def call(self, command: str) -> dict:
        if not self.proc.stdin or not self.proc.stdout or self.proc.poll() is not None:
            raise RuntimeError("Chess bridge has stopped")
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("Chess bridge did not return a state")
        result = json.loads(line)
        if "error" in result:
            raise RuntimeError(f"Chess bridge rejected command {command[:60]!r}")
        return result

    def new(self, game_id: int, fen: str = START_FEN) -> dict:
        # FEN is strictly validated in the C++ engine.
        if "\n" in fen or "\r" in fen:
            raise ValueError("FEN cannot contain a line break")
        return self.call(f"new {game_id} {fen}")

    def step(self, game_id: int, move: str) -> dict:
        return self.call(f"step {game_id} {move}")

    def drop(self, game_id: int) -> None:
        self.call(f"drop {game_id}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.proc.poll() is None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.write("quit\n")
                    self.proc.stdin.flush()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self.proc.stdin:
            self.proc.stdin.close()
        if self.proc.stdout:
            self.proc.stdout.close()


class BridgePool:
    """Several independent C++ chess bridges; GPU inference remains batched.

    Each game is assigned one bridge for its entire lifetime. Step requests for
    different bridges execute concurrently on CPU without sharing stdin pipes.
    """
    def __init__(self, executable: Path, workers: int = 1):
        if not 1 <= workers <= 8:
            raise ValueError('Bridge workers must be 1..8')
        self.executable, self.workers = executable, workers
        self.bridges: list[ChessBridge] = []
        self.pool = None
    def __enter__(self):
        try:
            for _ in range(self.workers):
                self.bridges.append(ChessBridge(self.executable).__enter__())
            self.pool = ThreadPoolExecutor(max_workers=self.workers)
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise
    def __exit__(self, *args):
        if self.pool:
            self.pool.shutdown(wait=True)
        for bridge in self.bridges:
            bridge.__exit__(*args)
    def _bridge(self, game_id: int) -> ChessBridge:
        return self.bridges[game_id % self.workers]
    def new(self, game_id: int, fen: str = START_FEN) -> dict:
        return self._bridge(game_id).new(game_id,fen)
    def step(self, game_id: int, move: str) -> dict:
        return self._bridge(game_id).step(game_id,move)
    def drop(self, game_id: int) -> None:
        self._bridge(game_id).drop(game_id)
    def step_many(self, actions: dict[int,str]) -> dict[int,dict]:
        if self.workers == 1:
            return {game_id:self.step(game_id,move) for game_id,move in actions.items()}
        groups: list[list[tuple[int,str]]] = [[] for _ in range(self.workers)]
        for game_id,move in actions.items():
            groups[game_id % self.workers].append((game_id,move))
        def perform(worker: int):
            bridge = self.bridges[worker]
            return {i:bridge.step(i,move) for i,move in groups[worker]}
        futures=[self.pool.submit(perform,i) for i in range(self.workers) if groups[i]]
        states = {}
        for future in futures:
            states.update(future.result())
        return states


@dataclass
class Game:
    id: int
    state: dict
    fens: list[str]
    moves: list[str] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    exploration_entropy: list[float] = field(default_factory=list)
    result: str = "*"
    reason: str = "ongoing"
    finished: bool = False
    seconds: float = 0.0
    mode: str = "selfplay"
    learning_color: str | None = None
    league_opponent_idx: int = 0

    def record(self, index: int, prob: float, entropy: float, value: float, action: str,
               on_policy: bool = True, discouraged: list[str] | None = None) -> None:
        if on_policy:
            self.experience.append({"fen": self.state["fen"],
                                "legal_moves": self.state["legal_moves"],
                                "move": action,
                                "old_logp": math.log(max(1e-30, prob)),
                                "old_value": value,
                                    "side": self.state["fen"].split()[1],
                                    "discouraged_moves": discouraged or []})
        self.exploration_entropy.append(entropy)
        self.moves.append(action)

    def finish(self, plies_cap: int, elapsed: float) -> None:
        self.result = self.state["result"]
        self.finished = bool(self.state["finished"])
        self.reason = self.state["reason"] if self.finished else "max_plies_unfinished"
        self.seconds = elapsed
        if not self.finished and len(self.moves) < plies_cap:
            raise RuntimeError("Game ended prematurely without terminal position")


def sample_moves(model: ChessNet, states: list[dict], device: torch.device,
                 temperature: float, stochastic: bool, *,
                 discouraged: list[list[str]] | None = None,
                 repetition_penalty: float = 0.0) -> list[tuple[str, float, float, float]]:
    if not states:
        return []
    x = torch.from_numpy(np.stack([encode_fen(s["fen"]) for s in states])).to(device)
    with torch.inference_mode():
        logits, values = model(x)
        # One device -> host transfer per batch, not 3 GPU synchronizations per
        # legal-move selection. Masking/softmax are on the small legal subsets.
        # This is particularly useful when many simultaneous boards share a GPU.
        batch = torch.cat((logits.float(),values.float().unsqueeze(1)),dim=1).cpu().numpy()
    sampled = []
    for i, state in enumerate(states):
        moves = state["legal_moves"]
        if not moves:
            raise RuntimeError("Terminal chess position given to action sampler")
        indexes = [encode_move(m) for m in moves]
        local = batch[i,indexes].astype(np.float64) / temperature
        if repetition_penalty and discouraged:
            avoid = set(discouraged[i])
            if avoid:
                local -= np.asarray([repetition_penalty if m in avoid else 0.0 for m in moves])
        local -= np.max(local)
        probs = np.exp(local)
        probs /= probs.sum()
        choice = int(np.random.choice(len(moves),p=probs)) if stochastic else int(probs.argmax())
        entropy = float(-(probs * np.log(np.maximum(probs,1e-30))).sum())
        sampled.append((moves[choice],float(probs[choice]),entropy,float(batch[i,-1])))
    return sampled


def rollout(model: ChessNet, engine: Path, *, games: int, parallel: int,
            max_plies: int, temperature: float, start_fen: str, device: torch.device,
            id_start: int, progress=None, opening_plies: int = 0, opening_seed: int = 0,
            opponent: ChessNet | None = None, league_fraction: float = 0.0,
            opponents: list[ChessNet] | None = None,
            repetition_penalty: float = 0.0, bridge_workers: int = 1,
            profile: dict | None = None) -> list[Game]:
    """Continuous microbatch self-play, with parallel CPU bridge workers.

    Refill a game slot as soon as it ends instead of waiting for the slowest
    game in a fixed wave. GPU receives all ready model positions as one batch.
    Only current-policy actions are retained as training experience.
    """
    if not 1 <= parallel <= 512 or not 1 <= bridge_workers <= 8:
        raise ValueError('Invalid parallel games or bridge workers')
    completed: list[Game] = []
    frozen_pool = opponents if opponents is not None else ([opponent] if opponent is not None else [])
    started = time.monotonic()
    spent_open = spent_bridge = spent_inference = 0.0
    batch_sizes: list[int] = []
    batches = 0
    with BridgePool(engine,bridge_workers) as bridge:
        active: dict[int,Game] = {}
        launched=0
        def start_next():
            nonlocal launched,spent_open
            if launched >= games:
                return
            identifier = id_start + launched
            t = time.monotonic()
            state,opening_moves=open_position(bridge,identifier,start_fen,opening_seed,identifier,opening_plies)
            spent_open += time.monotonic()-t
            game = Game(identifier,state,[state['fen']])
            game.opening_moves=opening_moves
            rng=random.Random(opening_seed+identifier*19)
            if frozen_pool and rng.random()<league_fraction:
                game.mode='league'
                game.learning_color='w' if identifier % 2 == 0 else 'b'
                game.league_opponent_idx=rng.randrange(len(frozen_pool))
            launched+=1
            if state['finished']:
                game.finish(max_plies,time.monotonic()-started)
                completed.append(game)
                bridge.drop(identifier)
                if progress:
                    progress(game)
            else:
                active[identifier]=game
        while launched < games and len(active)<parallel:
            start_next()
        while active:
            ready=list(active.values())
            current=[]
            frozen_by_index: dict[int,list[Game]]={}
            for game in ready:
                is_actor=game.mode!='league' or game.state['fen'].split()[1]==game.learning_color
                if is_actor:
                    current.append(game)
                else:
                    frozen_by_index.setdefault(game.league_opponent_idx,[]).append(game)
            actions_by_id={}
            discouraged_by_id={}
            groups=[(current,model,True)]+[(subset,frozen_pool[idx],False) for idx,subset in frozen_by_index.items()]
            for subset,actor,train_policy in groups:
                if not subset:
                    continue
                discouraged=[reversible_move_candidates(g.moves,g.state['legal_moves']) if
                             train_policy and repetition_penalty else [] for g in subset]
                t=time.monotonic()
                actions=sample_moves(actor,[g.state for g in subset],device,temperature,True,
                                     discouraged=discouraged,
                                     repetition_penalty=repetition_penalty if train_policy else 0)
                spent_inference+=time.monotonic()-t
                batches+=1
                batch_sizes.append(len(subset))
                for game,action,avoid in zip(subset,actions,discouraged):
                    actions_by_id[game.id]=action
                    discouraged_by_id[game.id]=avoid
            for game in ready:
                action,prob,ent,value=actions_by_id[game.id]
                on_policy=game.mode!='league' or game.state['fen'].split()[1]==game.learning_color
                game.record(encode_move(action),prob,ent,value,action,on_policy=on_policy,
                            discouraged=discouraged_by_id[game.id])
            t=time.monotonic()
            stepped=bridge.step_many({game.id:actions_by_id[game.id][0] for game in ready})
            spent_bridge+=time.monotonic()-t
            for game in ready:
                game.state=stepped[game.id]
                game.fens.append(game.state['fen'])
                if game.state['finished'] or len(game.moves)>=max_plies:
                    game.finish(max_plies,time.monotonic()-started)
                    completed.append(game)
                    bridge.drop(game.id)
                    del active[game.id]
                    if progress:
                        progress(game)
            while launched<games and len(active)<parallel:
                start_next()
    elapsed=time.monotonic()-started
    if profile is not None:
        profile.update({'elapsed_s':round(elapsed,4), 'opening_s':round(spent_open,4),
                        'bridge_steps_s':round(spent_bridge,4),
                        'neural_inference_s':round(spent_inference,4),
                        'other_s':round(max(0,elapsed-spent_open-spent_bridge-spent_inference),4),
                        'inference_batches':batches,
                        'average_inference_batch':round(sum(batch_sizes)/max(1,batches),2),
                        'max_inference_batch':max(batch_sizes,default=0),
                        'bridge_workers':bridge_workers,'concurrent_games':parallel,
                        'mode':'continuous_microbatch'})
    return completed


def returns_for(game: Game) -> list[dict]:
    # Unfinished games do NOT supply ground-truth game results or policy rewards.
    if not game.finished:
        return []
    winner = "w" if game.result == "1-0" else "b" if game.result == "0-1" else None
    result = []
    for row in game.experience:
        z = 0.0 if winner is None else 1.0 if row["side"] == winner else -1.0
        result.append({**row, "outcome_value": z})
    return result


def ppo_train(model: ChessNet, optimizer: torch.optim.Optimizer,
              experiences: list[dict], device: torch.device, *, temperature: float,
              epochs: int, batch_size: int, clip: float, value_weight: float,
              entropy_weight: float, target_kl: float = 0.035,
              repetition_penalty: float = 0.0, grad_clip: float = 1.0) -> dict:
    """On-policy clipped surrogate objective with a frozen rollout-value baseline.

    Previously collected samples may be archived for review, but they are NOT
    replayed in later policy updates without off-policy corrections.
    """
    if not experiences:
        return {"samples": 0, "updates": 0, "total_loss": None, "policy_loss": None,
                "value_mse": None, "entropy": None, "advantage_abs": None,
                "approx_kl": None, "clip_fraction": None, "early_stopped_kl": False}
    x = torch.from_numpy(np.stack([encode_fen(row["fen"]) for row in experiences]))
    n = len(experiences)
    masks = torch.zeros((n, POLICY_SIZE), dtype=torch.bool)
    selected = torch.tensor([encode_move(row["move"]) for row in experiences], dtype=torch.long)
    discouraged_indices = []
    for i, row in enumerate(experiences):
        masks[i, [encode_move(m) for m in row["legal_moves"]]] = True
        discouraged_indices.append([encode_move(m) for m in row.get("discouraged_moves",[])])
    assert masks[torch.arange(n), selected].all()
    old_logp = torch.tensor([row["old_logp"] for row in experiences], dtype=torch.float32)
    targets = torch.tensor([row["outcome_value"] for row in experiences], dtype=torch.float32)
    base_values = torch.tensor([row["old_value"] for row in experiences], dtype=torch.float32)
    adv = targets - base_values
    # Keep scale stable while preserving reward sign and its zero point.
    adv = adv / adv.std(unbiased=False).clamp_min(0.20)
    metrics = []
    stopped_for_kl = False
    model.train()
    for epoch in range(epochs):
        order = torch.randperm(n)
        for start in range(0, n, batch_size):
            ids = order[start:start + batch_size]
            X = x[ids].to(device)
            legal_mask = masks[ids].to(device)
            chosen = selected[ids].to(device)
            old = old_logp[ids].to(device)
            target = targets[ids].to(device)
            advantage = adv[ids].to(device)
            logits, value = model(X)
            scaled = (logits.float() / temperature).masked_fill(~legal_mask, -1e9)
            if repetition_penalty:
                for j, original_id in enumerate(ids.tolist()):
                    if discouraged_indices[original_id]:
                        scaled[j, discouraged_indices[original_id]] -= repetition_penalty
            log_probs = F.log_softmax(scaled, dim=1)
            action_logp = log_probs.gather(1, chosen.unsqueeze(1)).squeeze(1)
            log_ratio = action_logp - old
            ratio = torch.exp(log_ratio.clamp(-15,15))
            # Always nonnegative up to floating-point roundoff; unlike the
            # signed estimator, this is stable for zero-mean PPO updates.
            approx_kl = ((ratio - 1.0) - log_ratio).mean()
            clip_fraction = ((ratio-1.0).abs()>clip).float().mean()
            if target_kl > 0 and metrics and float(approx_kl.item()) > target_kl:
                stopped_for_kl = True
                break
            surrogate = torch.min(ratio * advantage,
                                  ratio.clamp(1.0-clip, 1.0+clip) * advantage)
            policy_loss = -surrogate.mean()
            value_loss = F.mse_loss(value, target)
            # 0 * (-1e9) is safe, but suppress irrelevant logits explicitly.
            probs = log_probs.exp()
            entropy = -(probs * log_probs).sum(dim=1).mean()
            loss = policy_loss + value_weight * value_loss - entropy_weight * entropy
            if not torch.isfinite(loss):
                raise FloatingPointError('Non-finite PPO loss; refusing to write corrupted weights')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            gradient_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            if not torch.isfinite(gradient_norm):
                optimizer.zero_grad(set_to_none=True)
                raise FloatingPointError('Non-finite gradient norm; refusing PPO optimizer update')
            optimizer.step()
            metrics.append((float(loss.item()), float(policy_loss.item()),
                            float(value_loss.item()), float(entropy.item()),
                            float(approx_kl.item()), float(clip_fraction.item()),
                            float(gradient_norm.item())))
        if stopped_for_kl:
            break
    model.eval()
    return {"samples": n, "updates": len(metrics),
            "total_loss": round(sum(x[0] for x in metrics)/len(metrics), 6) if metrics else None,
            "policy_loss": round(sum(x[1] for x in metrics)/len(metrics), 6) if metrics else None,
            "value_mse": round(sum(x[2] for x in metrics)/len(metrics), 6) if metrics else None,
            "entropy": round(sum(x[3] for x in metrics)/len(metrics), 6) if metrics else None,
            "advantage_abs": round(float(adv.abs().mean().item()), 6),
            "approx_kl": round(sum(x[4] for x in metrics)/len(metrics), 6) if metrics else None,
            "clip_fraction": round(sum(x[5] for x in metrics)/len(metrics), 6) if metrics else None,
            "grad_norm": round(sum(x[6] for x in metrics)/len(metrics), 6) if metrics else None,
            "early_stopped_kl":stopped_for_kl,"epochs_requested":epochs}


def evaluate(model: ChessNet, opponent: ChessNet | None, engine: Path,
             games: int, max_plies: int, device: torch.device,
             start_fen: str, id_start: int, *, opening_plies: int = 6,
             seed: int = 20261123) -> tuple[dict, list[dict]]:
    """Paired-color evaluation across independent reproducible opening *starts*.

    A pairing shares the identical position and exchanges the candidate's color.
    Distinct opening seeds address v0.4's repeated-trajectory failure. Truncated
    games remain excluded. This does not claim a calibrated Elo/confidence band.
    """
    if opponent is None or games <= 0:
        return {"completed": 0, "unfinished": 0, "wins": 0, "losses": 0,
                "draws": 0, "score": None, "played": 0,
                "opening_pairs": 0, "unique_sequences": 0}, []
    if games % 2:
        raise ValueError('Evaluation requires an even number of games for paired colors')
    wins = losses = draws = unfinished = 0
    reason_counts = {}
    records = []
    unique_starts: set[str] = set()
    unique_games: set[tuple[str, str, tuple[str,...]]] = set()
    pairs_complete = 0
    paired_scores = []
    color_stats = {'white': {'wins':0,'losses':0,'draws':0,'unfinished':0},
                   'black': {'wins':0,'losses':0,'draws':0,'unfinished':0}}
    with ChessBridge(engine) as bridge:
        for pair in range(games // 2):
            pair_results = []
            for member in range(2):
                ix = 2*pair+member
                gid = id_start + ix
                is_white = member == 0
                state, opening_moves = open_position(bridge, gid, start_fen,
                                                     seed, pair, opening_plies)
                initial = state['fen']
                unique_starts.add(initial)
                fens = [initial]
                moves = []
                while not state['finished'] and len(moves) < max_plies:
                    is_candidate = (state['fen'].split()[1] == 'w') == is_white
                    actor = model if is_candidate else opponent
                    action = sample_moves(actor, [state], device, 1.0, False)[0][0]
                    moves.append(action)
                    state = bridge.step(gid, action)
                    fens.append(state['fen'])
                color = 'white' if is_white else 'black'
                reason = state['reason'] if state['finished'] else 'max_plies_unfinished'
                reason_counts[reason] = reason_counts.get(reason,0) + 1
                if not state['finished']:
                    unfinished += 1
                    color_stats[color]['unfinished'] += 1
                    pair_results.append(None)
                elif state['result'] == '1/2-1/2':
                    draws += 1
                    color_stats[color]['draws'] += 1
                    pair_results.append(.5)
                elif (state['result'] == '1-0') == is_white:
                    wins += 1
                    color_stats[color]['wins'] += 1
                    pair_results.append(1.)
                else:
                    losses += 1
                    color_stats[color]['losses'] += 1
                    pair_results.append(0.)
                unique_games.add((initial,color,tuple(moves)))
                records.append({"game_id":gid, "kind":"arena", "pair_id":pair,
                                "opening_plies":opening_moves, "opening_seed":seed,
                                "start_fen":initial, "neural_color":color,
                                "result":state['result'] if state['finished'] else '*',
                                "reason":state['reason'] if state['finished'] else 'max_plies_unfinished',
                                "plies":len(moves), "moves":moves, "fens":fens})
                bridge.drop(gid)
            if None not in pair_results:
                pairs_complete += 1
                paired_scores.append(sum(pair_results)/2)
    completed = wins + draws + losses
    return {"completed":completed, "played":games, "unfinished":unfinished,
            "wins":wins, "losses":losses, "draws":draws,
            "score":round((wins+.5*draws)/completed,5) if completed else None,
            "opening_pairs":games//2,"completed_pairs":pairs_complete,
            "unique_opening_positions":len(unique_starts),
            "unique_sequences":len(unique_games),
            "color_stats":color_stats,
            "termination_reasons":reason_counts,
            "paired_score":round(sum(paired_scores)/len(paired_scores),5) if paired_scores else None,
            "method":"paired colors across seeded opening positions; not Elo"}, records



def recover_resume_files(out: Path, checkpoint: dict) -> dict:
    """Stream incomplete journal rows into gzip recovery; never load GB into RAM.

    Checkpoint/optimizer iteration is authoritative. Committed rows remain;
    incomplete rows are quarantined with a lossless compressed source backup.
    """
    from .storage import _archive_digest, digest, BUFFER
    import gzip
    committed=int(checkpoint.get('iteration',0))
    metrics_path=out/'metrics.jsonl'
    metrics=read_jsonl(metrics_path)
    if any(int(m['iteration'])>committed for m in metrics):
        raise ValueError('Metrics iteration is newer than model checkpoint')
    if committed and not any(int(m['iteration'])==committed for m in metrics):
        metric=checkpoint.get('metrics')
        if not metric or int(metric.get('iteration',-1))!=committed:
            raise ValueError('Checkpoint metric missing; cannot reconcile safely')
        append_json(metrics_path,metric)
    quarantined={}
    for filename in ('games.jsonl','experience.jsonl','arena_games.jsonl'):
        path=out/filename
        if not path.is_file():
            continue
        missing=0
        with path.open('rb') as f:
            for line in f:
                try:
                    if line.strip() and int(json.loads(line).get('iteration',0))>committed:
                        missing+=1
                except (ValueError,UnicodeDecodeError):
                    missing+=1
        if not missing:
            continue
        folder=out/'recovery'
        folder.mkdir(parents=True,exist_ok=True)
        stamp=timestamp().replace(':','-')
        source_hash=digest(path)
        backup=folder/f'{filename}.{stamp}.{source_hash[:12]}.full-original.gz'
        if backup.exists():
            raise FileExistsError(f'Refusing to overwrite recovery archive: {backup}')
        with path.open('rb') as inp, backup.open('xb') as out_backup:
            with gzip.GzipFile(filename='',mode='wb',fileobj=out_backup,compresslevel=6,mtime=0) as zipped:
                for chunk in iter(lambda:inp.read(BUFFER),b''):
                    zipped.write(chunk)
        if _archive_digest(backup)!=(source_hash,path.stat().st_size):
            backup.unlink(missing_ok=True)
            raise ValueError('Recovery backup checksum verification failed')
        discarded=folder/f'{filename}.{stamp}.uncommitted'
        temp=path.with_name(path.name+'.recovery.tmp')
        try:
            with path.open('rb') as inp, temp.open('xb') as kept, discarded.open('xb') as skipped:
                for line in inp:
                    try:
                        is_uncommitted=bool(line.strip()) and int(json.loads(line).get('iteration',0))>committed
                    except (ValueError,UnicodeDecodeError):
                        is_uncommitted=True
                    (skipped if is_uncommitted else kept).write(line)
            os.replace(temp,path)
            quarantined[filename]=missing
        finally:
            temp.unlink(missing_ok=True)
    return quarantined


def model_and_optimizer(args, device: torch.device, last: Path):
    checkpoint = None
    if args.resume and last.is_file():
        checkpoint = torch.load(last, map_location="cpu", weights_only=True)
        if checkpoint.get("feature_version") != FEATURE_VERSION:
            raise ValueError("Cannot resume: checkpoint encoder version does not match")
        model = ChessNet(**checkpoint["config"])
        model.load_state_dict(checkpoint["model"])
    elif args.bootstrap and args.bootstrap.is_file():
        model = load_model(args.bootstrap, "cpu")
    else:
        model = ChessNet(args.channels, args.blocks)
    model = model.to(device).eval()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    if checkpoint and "optimizer" in checkpoint:
        optimizer.load_state_dict(checkpoint["optimizer"])
    return model, optimizer, checkpoint


def run(args) -> None:
    if args.iterations < 1 or args.games_per_iteration < 1 or args.parallel < 1 or args.max_plies < 1:
        raise ValueError("iterations, games, parallel, max-plies must be positive")
    if args.temperature <= 0 or args.lr <= 0 or args.ppo_epochs < 1 or args.batch_size < 1:
        raise ValueError("temperature, lr, epochs and batch size must be positive")
    if not 0 <= args.repetition_penalty <= 2 or not 0 < args.target_kl <= 2 or not 0 < args.grad_clip <= 10:
        raise ValueError("Invalid repetition, KL or gradient controls")
    if not 1 <= args.bridge_workers <= 8 or not 0 <= args.archive_every <= 1000:
        raise ValueError('Invalid bridge workers or archive frequency')
    if not 1 <= args.league_pool_size <= 16:
        raise ValueError("Invalid league pool size")
    if not 0 <= args.league_fraction <= 1:
        raise ValueError('league-fraction must be 0..1')
    if not 0 <= args.opening_plies <= 16 or args.best_every < 0 or args.best_games < 0 or args.best_games % 2:
        raise ValueError('Invalid opening plies or best-model screening options')
    if args.games_per_iteration * args.max_plies > 80000:
        raise ValueError("Requested rollout is too large for a single 16 GB RAM batch; use fewer games or a smaller ply limit")
    if not 0.0 < args.clip < 1.0 or args.arena_games < 0 or args.arena_every < 1:
        raise ValueError("Invalid clip, arena-games or arena-every")
    if "\n" in args.start_fen or "\r" in args.start_fen:
        raise ValueError("Invalid start FEN")
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(min(6, max(1, torch.get_num_threads())))
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else
                          "cpu" if args.device == "auto" else args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable in this installed PyTorch")
    if not args.engine.is_file():
        raise FileNotFoundError(f"Build the C++ core first: {args.engine}")
    args.out.mkdir(parents=True, exist_ok=True)
    last = args.out / "checkpoints" / "latest.pt"
    model, optimizer, resumed = model_and_optimizer(args, device, last)
    metadata = args.out / "run_metadata.json"
    if args.resume and not resumed:
        raise ValueError("Resume requested but latest.pt is missing")
    if not args.resume and metadata.exists():
        raise ValueError("The output directory already has a run. Use --resume or a new directory")
    cfg = {"iterations": args.iterations, "games_per_iteration": args.games_per_iteration,
           "parallel": args.parallel, "max_plies": args.max_plies,
           "temperature": args.temperature, "ppo_epochs": args.ppo_epochs,
           "batch_size": args.batch_size, "lr": args.lr, "entropy_weight": args.entropy_weight,
           "value_weight": args.value_weight, "clip": args.clip, "arena_games": args.arena_games,
           "arena_every": args.arena_every, "seed": args.seed, "start_fen": args.start_fen,
           "device": args.device, "opening_plies":args.opening_plies,
           "best_every":args.best_every, "best_games":args.best_games,
           "league_fraction":args.league_fraction,
           "league_pool_size":args.league_pool_size,
           "repetition_penalty":args.repetition_penalty,
           "target_kl":args.target_kl, "grad_clip":args.grad_clip, "bridge_workers":args.bridge_workers,
           "archive_every":args.archive_every,
           "engine": str(args.engine.resolve()),
           "bootstrap": str(args.bootstrap.resolve()) if args.bootstrap else None,
           "reference": str(args.reference.resolve()) if args.reference else None}
    if resumed:
        prior = read_json(metadata)
        # Changing a policy distribution's temperature between resumption epochs is fine,
        # but changing model topology, engine path or start FEN can conceal discontinuities.
        if prior and prior["config"]["start_fen"] != args.start_fen:
            raise ValueError("Resume requires the same starting FEN")
        if prior:
            # Preserve the original experiment and record intentional parameter
            # changes after resumption, so the dashboard uses the new limit next time.
            changed = {key: [prior['config'].get(key), cfg[key]]
                       for key in ('max_plies','games_per_iteration','temperature','lr','opening_plies','best_every','best_games','league_fraction','league_pool_size','repetition_penalty','target_kl','grad_clip')
                       if prior['config'].get(key) != cfg[key]}
            if changed:
                prior.setdefault('config_changes', []).append({'at':timestamp(),
                    'from_checkpoint_iteration':int(resumed.get('iteration',0)),
                    'changes':changed})
                prior['config'].update({k:cfg[k] for k in changed})
                atomic_json(metadata,prior)
    else:
        atomic_json(metadata, {"version":"0.7.0", "name":args.out.name,
                               "created_at":timestamp(), "feature_version":FEATURE_VERSION,
                               "parameters":sum(p.numel() for p in model.parameters()),
                               "architecture":model.config, "config":cfg})
    with ChessBridge(args.engine) as check:
        check.new(0, args.start_fen)
    opponent = None
    if args.arena_games and args.reference and args.reference.is_file():
        opponent = load_model(args.reference, device)
        opponent.eval()
    if resumed:
        recovered = recover_resume_files(args.out, resumed)
        if recovered:
            print("Recovered incomplete iteration records:", recovered,flush=True)
    previous = read_jsonl(args.out / "metrics.jsonl")
    start_iteration = int(resumed.get("iteration", 0)) if resumed else 0
    target_iteration = start_iteration + args.iterations
    # Prefer the committed checkpoint's cumulative snapshot: it survives log
    # compression and avoids loading gigabytes of historical JSONL into RAM.
    committed_counters = (resumed or {}).get('metrics',{}).get('cumulative') if resumed and resumed.get('metrics') else None
    if committed_counters:
        counters = dict(committed_counters)
    else:
        counters = {"games":0,"finished":0,"unfinished":0,"white_wins":0,
                    "black_wins":0,"draws":0,"plies":0,
                    "samples":sum(int(row.get('samples',0)) for row in previous)}
        for g in iter_records(args.out,'games.jsonl') if resumed else []:
            counters['games']+=1
            counters['plies']+=int(g['plies'])
            if g['result']=='*': counters['unfinished']+=1
            else:
                counters['finished']+=1
                if g['result']=='1-0': counters['white_wins']+=1
                elif g['result']=='0-1': counters['black_wins']+=1
                else:counters['draws']+=1
    previous_state=read_json(args.out/'run_state.json',{}) or {}
    # Older experiments have no next_game_id; find it by a streaming pass, not
    # by keeping all moves/FENs in memory.
    next_id=(int(previous_state['next_game_id']) if resumed and
             previous_state.get('iteration')==start_iteration and
             previous_state.get('next_game_id') is not None else
             last_game_id(args.out)+1 if resumed else 0)
    if resumed and args.archive_every:
        # A previous gzip publication may have completed just before a crash.
        # Compact only AFTER recovery has removed uncommitted rows; this also
        # converts large legacy plaintext journals without discarding history.
        compact_run(args.out,committed=start_iteration,trusted_trainer=True)
    state = {"status":"running", "started_at":timestamp(), "updated_at":timestamp(),
             "iteration": start_iteration, "target_iteration":target_iteration,
             "iteration_games":0, "iteration_target":args.games_per_iteration,
             "device":str(device), "counters": counters,
             "note":"Model plays both colors; games at the ply limit are NOT treated as draws."}
    atomic_json(args.out / "run_state.json", state)
    # A user may request Stop before the first batch finishes. Save a valid
    # iteration-0 snapshot so the experiment remains resumable in this case.
    if not resumed and not last.is_file():
        last.parent.mkdir(parents=True, exist_ok=True)
        first = {"model":model.state_dict(), "optimizer":optimizer.state_dict(),
                 "config":model.config, "feature_version":FEATURE_VERSION,
                 "iteration":0, "metrics":None}
        tmp = last.with_name("latest.tmp.pt")
        torch.save(first,tmp)
        os.replace(tmp,last)
    from .model_guard import initialize_best, check_and_promote
    best_info = initialize_best(args.out, last, args.reference)
    league_entries = load_league(args.out,device,args.league_pool_size,model.config) if args.league_fraction else []
    state['league_opponents'] = [name for name,_ in league_entries]
    state['best_model'] = best_info
    state['device_diagnostics'] = {
        'requested':args.device, 'selected':str(device), 'torch_version':torch.__version__,
        'cuda_available':torch.cuda.is_available(),
        'cuda_device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'note':'CUDA availability depends on installed PyTorch build and drivers; performance depends on workload.'
    }
    atomic_json(args.out/'run_state.json',state)
    print(f"SELF-PLAY | {args.out} | device={device} | params={sum(p.numel() for p in model.parameters()):,}", flush=True)
    print("PPO uses fresh own-policy games only. No fabricated rating/Elo or outcome for truncated games.", flush=True)
    run_started = time.monotonic()
    try:
        for it in range(start_iteration + 1, target_iteration + 1):
            if (args.out / "stop_requested").exists():
                (args.out / "stop_requested").unlink()
                state["status"] = "stopped"
                break
            state.update({"iteration":it, "iteration_games":0, "iteration_target":args.games_per_iteration,
                          "phase":"selfplay", "updated_at":timestamp()})
            atomic_json(args.out / "run_state.json", state)
            iteration_start = time.monotonic()
            def on_game(game: Game):
                record = {"game_id":game.id, "iteration":it, "kind":"selfplay",
                          "result":game.result, "reason":game.reason,
                          "opening_moves":getattr(game,"opening_moves",[]),
                          "mode":game.mode, "learning_color":game.learning_color,
                          "league_opponent":(league_entries[game.league_opponent_idx][0] if game.mode == "league" else None),
                          "position_revisits":repeated_positions(game.fens),
                          "on_policy_positions":len(game.experience),
                          "plies":len(game.moves), "moves":game.moves, "fens":game.fens,
                          "entropy":round(float(np.mean(game.exploration_entropy)),4) if game.exploration_entropy else None,
                          "recorded_at":timestamp()}
                append_json(args.out / "games.jsonl", record)
                counters["games"] += 1
                counters["plies"] += len(game.moves)
                if game.finished:
                    counters["finished"] += 1
                    if game.result == "1-0": counters["white_wins"] += 1
                    elif game.result == "0-1": counters["black_wins"] += 1
                    else: counters["draws"] += 1
                else:
                    counters["unfinished"] += 1
                state.update({"iteration_games":state["iteration_games"]+1,
                              "updated_at":timestamp(), "counters":counters})
                atomic_json(args.out / "run_state.json", state)
            rollout_profile = {}
            games = rollout(model,args.engine,games=args.games_per_iteration, parallel=args.parallel,
                            max_plies=args.max_plies, temperature=args.temperature,
                            start_fen=args.start_fen,device=device,id_start=next_id, progress=on_game,
                            opening_plies=args.opening_plies, opening_seed=args.seed,
                            opponents=[net for _,net in league_entries],
                            league_fraction=args.league_fraction, repetition_penalty=args.repetition_penalty,
                            bridge_workers=args.bridge_workers, profile=rollout_profile)
            next_id += len(games)
            experiences = []
            for game in games:
                rows = returns_for(game)
                for row in rows:
                    append_json(args.out / "experience.jsonl", {"iteration":it, "game_id":game.id, **row})
                experiences.extend(rows)
            state.update({"phase":"optimization", "updated_at":timestamp()})
            atomic_json(args.out / "run_state.json", state)
            optimize_started=time.monotonic()
            training = ppo_train(model, optimizer, experiences, device,
                                 temperature=args.temperature, epochs=args.ppo_epochs,
                                 batch_size=args.batch_size, clip=args.clip,
                                 value_weight=args.value_weight,entropy_weight=args.entropy_weight,
                                 target_kl=args.target_kl, repetition_penalty=args.repetition_penalty,
                                 grad_clip=args.grad_clip)
            optimize_seconds=time.monotonic()-optimize_started
            counters["samples"] += training["samples"]
            arena_started=time.monotonic()
            arena = {"completed":0,"unfinished":0,"wins":0,"losses":0,"draws":0,
                     "score":None,"played":0}
            if opponent is not None and it % args.arena_every == 0:
                state.update({"phase":"arena", "updated_at":timestamp()})
                atomic_json(args.out / "run_state.json", state)
                arena, arena_records = evaluate(model,opponent,args.engine,args.arena_games,
                                                  args.max_plies,device,args.start_fen,
                                                  100000 + it*max(args.arena_games,1),
                                                  opening_plies=max(4,args.opening_plies),seed=args.seed+it)
                for record in arena_records:
                    record["iteration"] = it
                    append_json(args.out / "arena_games.jsonl",record)
            arena_seconds=time.monotonic()-arena_started
            seconds = time.monotonic()-iteration_start
            selfplay_plies = sum(len(g.moves) for g in games)
            results = {"white_wins":sum(g.result=="1-0" for g in games),
                       "black_wins":sum(g.result=="0-1" for g in games),
                       "draws":sum(g.result=="1/2-1/2" for g in games),
                       "unfinished":sum(not g.finished for g in games)}
            reasons = reason_breakdown(games)
            revisits = sum(repeated_positions(g.fens) for g in games)
            metric = {"iteration":it,"at":timestamp(),"elapsed_s":round(seconds,3),
                      "games":len(games),"plies":selfplay_plies,"games_per_s":round(len(games)/max(seconds,1e-6),4),
                      "plies_per_s":round(selfplay_plies/max(seconds,1e-6),2),
                      "results":results,"samples":training["samples"],
                      "termination_reasons":reasons,"position_revisits":revisits,
                      "league_opponents":[name for name,_ in league_entries],
                      "performance":{**rollout_profile,'ppo_s':round(optimize_seconds,4),
                                     'arena_s':round(arena_seconds,4),
                                     'total_iteration_s':round(seconds,4)},
                      "train":training, "arena":arena,"cumulative":dict(counters),
                      "rollout_entropy":round(float(np.mean([e for g in games for e in g.exploration_entropy])),4)
                                        if selfplay_plies else None}
            last.parent.mkdir(parents=True,exist_ok=True)
            checkpoint = {"model":model.state_dict(),"optimizer":optimizer.state_dict(),
                          "config":model.config,"feature_version":FEATURE_VERSION,
                          "iteration":it,"metrics":metric}
            tmp = last.with_name("latest.tmp.pt")
            torch.save(checkpoint,tmp)
            os.replace(tmp,last)
            if args.save_every > 0 and it % args.save_every == 0:
                archive_path = last.parent / f"iteration_{it:05}.pt"
                archive_temp = last.parent / f"iteration_{it:05}.tmp.pt"
                torch.save(checkpoint,archive_temp)
                os.replace(archive_temp,archive_path)
                if args.league_fraction:
                    league_entries = load_league(args.out,device,args.league_pool_size,model.config)
                    state['league_opponents'] = [name for name,_ in league_entries]
            if args.best_every and args.best_games >= 8 and it % args.best_every == 0:
                state.update({'phase':'best_screening','updated_at':timestamp()})
                atomic_json(args.out/'run_state.json', state)
                decision = check_and_promote(model,args.out,args.engine,last,device,
                          games=args.best_games,max_plies=args.max_plies,
                          seed=args.seed+it*97,opening_plies=args.opening_plies)
                metric['best_screening'] = {'decision':decision['decision'],
                                             'statistics':decision['statistics']}
                state['best_model'] = decision
                if decision['decision']['promote'] and args.league_fraction:
                    league_entries = load_league(args.out,device,args.league_pool_size,model.config)
                    state['league_opponents'] = [name for name,_ in league_entries]
            append_json(args.out / "metrics.jsonl",metric)
            state.update({"iteration":it, "phase":"ready", "updated_at":timestamp(),
                          "last_metrics":metric, "counters":counters, "next_game_id":next_id,
                          "elapsed_session_s":round(time.monotonic()-run_started,3)})
            atomic_json(args.out / "run_state.json",state)
            if args.archive_every and it % args.archive_every == 0:
                # Checkpoint AND metrics are committed before journaling is moved.
                # Never compress mid-iteration or alter weights/optimizer.
                summary=compact_run(args.out,committed=it,trusted_trainer=True)
                state['last_archive']=summary
                atomic_json(args.out/'run_state.json',state)
            print(f"iteration={it} games={len(games)} plies={selfplay_plies} complete={sum(g.finished for g in games)} "
                  f"samples={training['samples']} policy_loss={training['policy_loss']} "
                  f"value_mse={training['value_mse']} time_s={seconds:.1f}",flush=True)
        else:
            state["status"]="completed"
        state.update({"updated_at":timestamp(), "finished_at":timestamp(), "phase":"idle"})
    except BaseException as exc:
        state.update({"status":"failed", "error":str(exc), "updated_at":timestamp(),
                      "finished_at":timestamp(), "phase":"error"})
        atomic_json(args.out / "run_state.json",state)
        raise
    atomic_json(args.out / "run_state.json",state)
    print(f"RUN ENDED: {state['status']} | {args.out}",flush=True)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Neural self-play PPO training & live dashboard data")
    p.add_argument("--engine",type=Path,default=ROOT/("build/Release/chessai.exe" if sys.platform=="win32" else "build/chessai"))
    p.add_argument("--out",type=Path,default=ROOT/"runs"/"training")
    p.add_argument("--bootstrap",type=Path,default=ROOT/"models/neural_best.pt")
    p.add_argument("--reference",type=Path,default=ROOT/"models/neural_best.pt")
    p.add_argument("--resume",action="store_true")
    p.add_argument("--iterations",type=int,default=10,help="Additional iterations when resuming")
    p.add_argument("--games-per-iteration",type=int,default=8)
    p.add_argument("--parallel",type=int,default=4)
    p.add_argument("--max-plies",type=int,default=240)
    p.add_argument("--temperature",type=float,default=1.1)
    p.add_argument("--ppo-epochs",type=int,default=2)
    p.add_argument("--batch-size",type=int,default=64)
    p.add_argument("--bridge-workers",type=int,default=2,
                   help="Independent CPU C++ bridge processes; GPU inference stays microbatched")
    p.add_argument("--archive-every",type=int,default=5,
                   help="Losslessly gzip completed journals every N iterations; 0 disables")
    p.add_argument("--lr",type=float,default=0.0003)
    p.add_argument("--clip",type=float,default=0.2)
    p.add_argument("--value-weight",type=float,default=0.5)
    p.add_argument("--entropy-weight",type=float,default=0.005)
    p.add_argument("--arena-games",type=int,default=2)
    p.add_argument("--arena-every",type=int,default=2)
    p.add_argument("--device",choices=("auto","cpu","cuda"),default="auto")
    p.add_argument("--save-every",type=int,default=5)
    p.add_argument("--opening-plies",type=int,default=0,
                   help="Randomized legal opening moves before each training game; 0 preserves legacy behavior")
    p.add_argument("--league-fraction",type=float,default=0.25,
                   help="Fraction of league games, using historical frozen opponents")
    p.add_argument("--league-pool-size",type=int,default=4)
    p.add_argument("--repetition-penalty",type=float,default=0.12,
                   help="Small train-only logit penalty for an immediate same-color reversal; never alters game outcome")
    p.add_argument("--target-kl",type=float,default=0.035,
                   help="Maximum mean approximate KL per PPO minibatch")
    p.add_argument("--grad-clip",type=float,default=1.0)
    p.add_argument("--best-every",type=int,default=10,help="Screen best checkpoint every N iterations; 0 disables")
    p.add_argument("--best-games",type=int,default=16,help="Even paired screening games")
    p.add_argument("--channels",type=int,default=32)
    p.add_argument("--blocks",type=int,default=2)
    p.add_argument("--seed",type=int,default=20261123)
    p.add_argument("--start-fen",type=str,default=START_FEN)
    return p.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
