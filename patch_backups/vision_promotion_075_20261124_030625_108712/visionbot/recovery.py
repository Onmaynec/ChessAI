"""Crash-safe local Vision game journal and conservative board reconciliation.

Only the local verified C++ history is authoritative. Screen captures confirm
occupancy and piece ownership; they cannot independently recover FEN metadata.
No online/game data are added to training. No browser/API access is used here.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from botlab.session import parse_board
from neural.agent import START_FEN


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    with tmp.open('wb') as out:
        out.write(content)
        out.flush()
        os.fsync(out.fileno())
    for delay in (0.03, 0.06, 0.12, 0.25, 0.4, None):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class RecoveryError(RuntimeError):
    pass


class RecoveryStore:
    """At most one active local computer-bot game per color per run."""

    def __init__(self, run_dir: Path, color: str):
        if color not in ('white', 'black'):
            raise ValueError('Unsupported board orientation')
        self.dir = Path(run_dir) / 'vision_recovery'
        self.color = color
        self.path = self.dir / f'active_{color}.json'
        self.photo = self.dir / f'initial_{color}.png'
        self.model_path = self.dir / f'frozen_{color}.pt'
        self.data = None

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise RecoveryError(f'Журнал восстановления повреждён: {exc}') from exc
        if data.get('version') != 1 or data.get('color') != self.color:
            raise RecoveryError('Неизвестная версия журнала или другая сторона игры')
        if not isinstance(data.get('moves'), list) or not isinstance(data.get('fen'), str):
            raise RecoveryError('В журнале отсутствует FEN или история ходов')
        for move in data['moves']:
            if not isinstance(move, str) or len(move) not in (4, 5):
                raise RecoveryError('Неверный формат сохранённых ходов')
        if not self.photo.is_file() or _sha(self.photo) != data.get('photo_sha256'):
            raise RecoveryError('Не найден или повреждён снимок начальной доски')
        if not self.model_path.is_file() or _sha(self.model_path) != data.get('model_sha256'):
            raise RecoveryError('Не найден или повреждён зафиксированный checkpoint партии')
        self.data = data
        return data

    def _save(self):
        self.data['updated_at'] = _utc()
        _atomic(self.path, json.dumps(self.data, ensure_ascii=False, indent=2).encode('utf-8'))

    def archive(self) -> None:
        """Explicit new-game action; keep old journal (no destructive reset)."""
        if not self.exists():
            return
        data = self.load()
        dest = self.dir / 'archive' / data['session_id']
        if dest.exists():
            raise RecoveryError('Архив с таким номером партии уже существует')
        dest.mkdir(parents=True)
        # Copy first, verify before removing the live journal. A failed archive
        # should leave the only recoverable match intact.
        sources = (self.photo, self.model_path, self.path)
        for source in sources:
            copy = dest / source.name
            shutil.copy2(source, copy)
            if _sha(copy) != _sha(source):
                raise RecoveryError(f'Ошибка копирования архива: {source.name}')
        # Commit archive only after all three files are safely present.
        self.path.unlink()
        for source in (self.photo, self.model_path):
            source.unlink(missing_ok=True)
        self.data = None

    def create(self, checkpoint: Path, first_frame: np.ndarray, rect, *, initial_fen: str = START_FEN) -> dict:
        if self.exists():
            raise RecoveryError('Уже есть незавершённая партия. Выбери «Продолжить» либо новую партию с архивированием.')
        self.dir.mkdir(parents=True, exist_ok=True)
        ok, png = cv2.imencode('.png', first_frame)
        if not ok:
            raise RecoveryError('Не удалось сохранить калибровку доски')
        _atomic(self.photo, png.tobytes())
        # Snapshot protects the current match if Training Studio rewrites latest.pt.
        tmp = self.model_path.with_name(self.model_path.name + '.new')
        shutil.copyfile(checkpoint, tmp)
        os.replace(tmp, self.model_path)
        self.data = {
            'version': 1, 'session_id': uuid.uuid4().hex,
            'created_at': _utc(), 'updated_at': _utc(), 'status': 'active',
            'color': self.color, 'rect': list(rect),
            'original_checkpoint': Path(checkpoint).name,
            'model_sha256': _sha(self.model_path), 'photo_sha256': _sha(self.photo),
            'initial_fen': initial_fen, 'fen': initial_fen, 'moves': [], 'pending': None,
        }
        self._save()
        return self.data

    def first_image(self) -> np.ndarray:
        self.load()
        frame = cv2.imread(str(self.photo), cv2.IMREAD_COLOR)
        if frame is None:
            raise RecoveryError('Не получилось прочитать сохранённую калибровку')
        return frame

    def intent(self, move: str, fen: str) -> None:
        """Write-ahead intent BEFORE the first physical mouse click."""
        if self.data is None:
            raise RecoveryError('Журнал не загружен')
        if self.data['fen'] != fen:
            raise RecoveryError('Позиция намерения не совпадает с журналом')
        self.data['pending'] = move
        self._save()

    def commit(self, sess) -> None:
        """Persist a fully verified C++ ply, never an unconfirmed click."""
        if self.data is None:
            raise RecoveryError('Журнал не загружен')
        if not sess.history[:len(self.data['moves'])] == self.data['moves']:
            raise RecoveryError('История C++ расходится с журналом')
        if len(sess.history) < len(self.data['moves']):
            raise RecoveryError('История C++ стала короче сохранённой')
        self.data['moves'] = list(sess.history)
        self.data['fen'] = sess.state['fen']
        self.data['pending'] = None
        if sess.state.get('finished'):
            self.data['status'] = 'finished'
        self._save()

    def mark_rect(self, rect) -> None:
        if self.data is not None:
            self.data['rect'] = list(rect)
            self._save()


def replay_session(sess, data: dict) -> None:
    """Legally replay journal with C++ so castling/ep/turn/move counters survive."""
    if sess.state['fen'] != data.get('initial_fen', START_FEN):
        raise RecoveryError('C++-сессия запущена не из сохранённой позиции')
    for m in data['moves']:
        if m not in sess.state['legal_moves']:
            raise RecoveryError(f'История содержит нелегальный ход: {m}')
        if sess.ai_turn():
            sess.pending = m
            sess.confirm_ai()
        else:
            sess.opponent_move(m)
    if sess.state['fen'] != data['fen']:
        raise RecoveryError('Сохранённый FEN не совпадает с пересчитанным C++')


def _board_agrees(observation, fen: str) -> bool:
    """Strictly compare all 64 occupied cells and nonzero color evidence."""
    board = parse_board(fen)
    occ = getattr(observation, 'occupied', None)
    if occ is None or np.asarray(occ).shape != (8, 8):
        return False
    if not np.array_equal(np.asarray(occ, dtype=bool),
                          np.asarray([[p != '.' for p in row] for row in board], dtype=bool)):
        return False
    sides = getattr(observation, 'sides', None)
    if sides is not None:
        for row in range(8):
            for col in range(8):
                p = board[row][col]
                observed = sides[row][col]
                if observed not in (-1, 0, 1):
                    return False
                if p != '.' and observed != 0 and observed != (1 if p.isupper() else -1):
                    return False
    return True


def _recovery_candidates(sess, pending: str | None):
    """Journal state plus at most 2 plies (pending own and quick reply)."""
    initial = sess.state
    yield (), initial['fen']
    bridge = getattr(sess, 'bridge', None)
    if bridge is None:
        return
    shadow = 448  # ordinary session 444; tactical search and preview differ
    try:
        if pending:
            if not sess.ai_turn() or pending not in initial['legal_moves']:
                raise RecoveryError('Сохранённое намерение стало нелегальным')
            after = bridge.new(shadow, initial['fen'])
            after = bridge.step(shadow, pending)
            yield (pending,), after['fen']
            for reply in after.get('legal_moves', []):
                bridge.new(shadow, after['fen'])
                follow = bridge.step(shadow, reply)
                yield (pending, reply), follow['fen']
        elif not sess.ai_turn():
            for reply in initial['legal_moves']:
                bridge.new(shadow, initial['fen'])
                after = bridge.step(shadow, reply)
                yield (reply,), after['fen']
    finally:
        try:
            bridge.drop(shadow)
        except (OSError, RuntimeError):
            pass


def recover_moves(sess, store: RecoveryStore, observation) -> list[str]:
    """Validate screenshot; advance only one *unambiguous* legal continuation."""
    if store.data is None:
        raise RecoveryError('Журнал не загружен')
    candidates = list(_recovery_candidates(sess, store.data['pending']))
    matches = [(moves, fen) for moves, fen in candidates if _board_agrees(observation, fen)]
    # Multiple legal lines with indistinguishable occupancy/color must stop.
    if len(matches) != 1:
        raise RecoveryError(
            f'Неоднозначная позиция: {len(matches)} подходящих продолжений из '
            f'{len(candidates)}. Автоклики запрещены. Проверь область доски и тему.')
    moves, _fen = matches[0]
    for move in moves:
        if sess.ai_turn():
            if move != store.data.get('pending'):
                raise RecoveryError('Неизвестный ход ИИ после сбоя')
            sess.pending = move
            sess.confirm_ai()
        else:
            sess.opponent_move(move)
        store.commit(sess)
    if not moves and store.data.get('pending'):
        # No click was confirmed. Clear intent; main loop may safely decide
        # again, but caller should clear selected-square highlights first.
        store.data['pending'] = None
        store._save()
    return list(moves)
