"""Manual chess bot testing: legally valid moves, frozen inference snapshot,
independent self-play trainer remains under Training Studio's control.

This module never accesses chess.com or modifies training checkpoints.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neural.agent import START_FEN
from neural.intelligence import choose_move
from neural.checkpoint import load_model
from neural.selfplay import ChessBridge


def time_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def parse_board(fen: str) -> list[list[str]]:
    rows = fen.split()[0].split('/')
    if len(rows) != 8:
        raise ValueError('Invalid chess FEN')
    out: list[list[str]] = []
    for row in rows:
        a: list[str] = []
        for ch in row:
            if ch.isdigit():
                a.extend('.' for _ in range(int(ch)))
            elif ch in 'rnbqkpRNBQKP':
                a.append(ch)
            else:
                raise ValueError('Invalid chess piece')
        if len(a) != 8:
            raise ValueError('Invalid FEN row')
        out.append(a)
    return out


def to_coord(row: int, col: int) -> str:
    return 'abcdefgh'[col] + str(8 - row)


def safe_session_record(path: Path, data: dict[str, Any]) -> Path:
    """Persist test results separately; NEVER add them to PPO training datasets."""
    path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    destination = path / f'bot_test_{stamp}.json'
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return destination


def trainer_status(run_dir: Path) -> dict:
    """Read status only; dashboard owns starting/stopping training and checkpoints."""
    p = run_dir / 'run_state.json'
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {'status': 'unknown', 'iteration': None, 'device': 'unknown'}
    device = data.get('device_diagnostics') or {}
    return {'status': data.get('status', 'unknown'),
            'iteration': data.get('iteration', data.get('current_iteration')),
            'device': device.get('selected', 'unknown')}


class BotLabSession:
    """Manual relay of UCI moves. Inference is frozen per test game.

    Important: copying an opponent move from a non-human Chess.com bot game
    is a human action; code never controls, scrapes or logs into Chess.com.
    """
    def __init__(self, engine: Path, checkpoint: Path, color: str, *, device: str = 'cpu',
                 core=None, predict=None, initial_fen: str = START_FEN):
        if color not in ('white', 'black'):
            raise ValueError('AI color must be white or black')
        if not checkpoint.is_file():
            raise FileNotFoundError(f'Checkpoint not found: {checkpoint}')
        self.checkpoint = checkpoint.resolve()
        self.color = color
        self.device = device
        self.model = None
        self.predict = predict
        if predict is None:
            self.model = load_model(self.checkpoint, device=device)
        self.checkpoint_hash = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        self.engine = engine
        self.bridge = core if core is not None else ChessBridge(engine)
        self.own_bridge = core is None
        self.closed = False
        self.initial_fen = initial_fen
        self.state = self.bridge.new(444, initial_fen)
        self.history: list[str] = []
        self.history_fens: list[str] = [self.state['fen']]
        self.last_analysis: dict = {}
        self.pending: str | None = None
        self.started = time_utc()

    def ai_turn(self) -> bool:
        return (self.state['fen'].split()[1] == 'w') == (self.color == 'white')

    def propose(self) -> tuple[str, float]:
        if self.pending is not None:
            return self.pending, getattr(self, 'value', 0.0)
        if self.state['finished'] or not self.ai_turn():
            raise ValueError('Not the AI turn')
        if self.predict is not None:
            move, value = self.predict(self.state)
        else:
            move, value, self.last_analysis = choose_move(
                self.model, self.state, self.bridge, self.engine,
                history_moves=self.history, history_fens=self.history_fens, depth=4)
        if move not in self.state['legal_moves']:
            raise ValueError(f'AI proposed illegal move: {move}')
        self.pending, self.value = move, value
        return move, value

    def confirm_ai(self) -> str:
        if not self.pending or not self.ai_turn():
            raise ValueError('No proposed move to confirm')
        move = self.pending
        self.state = self.bridge.step(444, move)
        self.history.append(move)
        self.history_fens.append(self.state['fen'])
        self.pending = None
        return move

    def opponent_move(self, move: str) -> str:
        move = move.lower().strip()
        if self.state['finished'] or self.ai_turn() or self.pending:
            raise ValueError('Wait for the bot turn; first confirm the AI move')
        if move not in self.state['legal_moves']:
            raise ValueError(f'Illegal move: {move}; expected format e7e5 or a7a8q')
        self.state = self.bridge.step(444, move)
        self.history.append(move)
        self.history_fens.append(self.state['fen'])
        return move

    def report(self, opponent: str, result: str, notes: str = '') -> dict:
        if result not in ('win', 'draw', 'loss', 'unfinished'):
            raise ValueError('Invalid result')
        return {
            'source': 'manual_chesscom_computer_bot_test',
            'not_used_for_training': True,
            'ai_color': self.color,
            'opponent_label': opponent[:120],
            'result_for_ai': result,
            'checkpoint_file': self.checkpoint.name,
            'checkpoint_sha256': self.checkpoint_hash,
            'started_at': self.started,
            'completed_at': time_utc(),
            'plies': len(self.history),
            'uci_moves': list(self.history),
            'starting_fen': self.initial_fen,
            'board_result': self.state.get('result'),
            'end_reason': self.state.get('reason'),
            'notes': notes[:500],
        }

    def close(self):
        if not self.closed and self.own_bridge:
            self.bridge.__exit__(None, None, None)
        self.closed = True
