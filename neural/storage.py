"""Lossless, bounded-memory journal archiving for Chess AI 0.7.

Archived JSONL is byte-for-byte recoverable from verified gzip segments. Never
remove checkpoints, metrics, optimizer state, or experimental metadata.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import deque
from pathlib import Path
from typing import Iterator

LOGS = ('experience.jsonl', 'games.jsonl', 'arena_games.jsonl')
BUFFER = 1024 * 1024
# Only short game-list tails are cached. Avoid decoding gigabytes of archived
# FEN histories on every 2.5-second dashboard refresh.
_tail_cache: dict[tuple[str,int,int,int],list[dict]] = {}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as file:
        for part in iter(lambda: file.read(BUFFER), b''):
            h.update(part)
    return h.hexdigest()


def archived_segments(run: Path, name: str) -> list[Path]:
    if name not in LOGS:
        raise ValueError('Unrecognized journal')
    return sorted((run / 'archives' / name.removesuffix('.jsonl')).glob('*.jsonl.gz'))


def _archive_digest(file: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with gzip.open(file, 'rb') as stream:
        for block in iter(lambda: stream.read(BUFFER), b''):
            h.update(block)
            size += len(block)
    return h.hexdigest(), size


def iter_records(run: Path, name: str) -> Iterator[dict]:
    """Iterate archived segments oldest-first, then the current append-only log."""
    if name not in LOGS:
        raise ValueError('Unrecognized journal')
    sources = archived_segments(run, name) + [run / name]
    for source in sources:
        if not source.is_file():
            continue
        opener = gzip.open if source.suffix == '.gz' else open
        with opener(source, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        # An interrupted append may have an incomplete tail; never
                        # silently discard a line when COMPACTING (see compact_one).
                        continue


def tail_records(run: Path, name: str, limit: int) -> list[dict]:
    """View the newest games across compressed history and live records."""
    if not 1 <= limit <= 100000:
        raise ValueError('Invalid tail size')
    buffer: deque[dict] = deque(maxlen=limit)
    sources = [run / name] + list(reversed(archived_segments(run, name)))
    for source in sources:
        if not source.is_file():
            continue
        stat=source.stat()
        signature=(str(source),limit,stat.st_mtime_ns,stat.st_size)
        if limit <= 100 and signature in _tail_cache:
            part=deque(_tail_cache[signature],maxlen=limit)
        else:
            part=deque(maxlen=limit)
            opener = gzip.open if source.suffix == '.gz' else open
            with opener(source, 'rt', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            part.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            if limit <= 100:
                if len(_tail_cache) >= 24:
                    _tail_cache.pop(next(iter(_tail_cache)))
                _tail_cache[signature] = list(part)
        # Insert earlier segment records before more recent ones.
        if part:
            buffer = deque(list(part) + list(buffer), maxlen=limit)
            if len(buffer) >= limit:
                break
    return list(buffer)


def find_game(run: Path, name: str, game_id: int) -> dict | None:
    # Newest segment first. IDs are unique across completed runs.
    for source in [run / name] + list(reversed(archived_segments(run, name))):
        if not source.is_file():
            continue
        opener = gzip.open if source.suffix == '.gz' else open
        with opener(source, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get('game_id') == game_id:
                        return row
    return None


def last_game_id(run: Path) -> int:
    # Used only to bootstrap legacy runs without a durable next_game_id.
    maximum = -1
    for row in iter_records(run, 'games.jsonl'):
        maximum = max(maximum, int(row.get('game_id', -1)))
    return maximum


def compact_one(run: Path, name: str, *, committed: int) -> dict:
    """Write -> verify -> publish gzip -> delete original; replayable after crash.

    It is only safe to call when no other writer is active, or between fully
    committed iterations from the one trainer that owns the output directory.
    """
    if name not in LOGS:
        raise ValueError('Unrecognized journal')
    source = run / name
    if not source.is_file() or source.stat().st_size == 0:
        return {'file': name, 'saved_bytes': 0, 'reason': 'nothing to compact'}
    raw_hash = digest(source)
    folder = run / 'archives' / name.removesuffix('.jsonl')
    folder.mkdir(parents=True, exist_ok=True)
    # A crash after archive publication but before unlink leaves BOTH copies.
    # Reconcile only if they contain precisely the same bytes.
    for old in archived_segments(run, name):
        if old.name.endswith(f'_{raw_hash}.jsonl.gz'):
            verified, length = _archive_digest(old)
            if verified != raw_hash or length != source.stat().st_size:
                raise ValueError('Archive verification failed; keeping original: ' + str(old))
            size_before = source.stat().st_size
            source.unlink()
            return {'file': name, 'saved_bytes': size_before,
                    'reason': 'reconciled interrupted archival', 'archive': str(old.relative_to(run))}
    count, max_iteration = 0, 0
    with source.open('rb') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (ValueError, UnicodeDecodeError) as ex:
                raise ValueError(f'Invalid record in {source}: cannot safely compact') from ex
            max_iteration = max(max_iteration, int(record.get('iteration', 0)))
            count += 1
    if max_iteration > committed:
        raise ValueError(f'{name} contains uncommitted iteration {max_iteration}, checkpoint is {committed}')
    next_seq = max((int(p.name.split('_',1)[0]) for p in archived_segments(run,name)), default=0) + 1
    final = folder / f'{next_seq:07d}_{raw_hash}.jsonl.gz'
    temp = folder / (final.name + '.tmp')
    if temp.exists() or final.exists():
        raise FileExistsError('Refusing to replace existing archive')
    try:
        with source.open('rb') as inp, temp.open('xb') as out:
            with gzip.GzipFile(filename='',mode='wb',compresslevel=6,fileobj=out,mtime=0) as zipped:
                for block in iter(lambda:inp.read(BUFFER),b''):
                    zipped.write(block)
            out.flush()
            os.fsync(out.fileno())
        verified, length = _archive_digest(temp)
        size_before = source.stat().st_size
        if verified != raw_hash or length != size_before:
            raise ValueError('Roundtrip SHA-256 mismatch; original left untouched')
        os.replace(temp,final)
        # The training process must not write to this file concurrently.
        if digest(source) != raw_hash:
            raise RuntimeError('Source changed during archiving; original left untouched')
        source.unlink()
    finally:
        temp.unlink(missing_ok=True)
    return {'file':name,'records':count,'max_iteration':max_iteration,
            'original_bytes':size_before,'archive_bytes':final.stat().st_size,
            'saved_bytes':size_before-final.stat().st_size,
            'sha256_original':raw_hash,'archive':str(final.relative_to(run))}


def compact_run(run: Path, *, committed: int, trusted_trainer: bool = False) -> dict:
    state_path = run / 'run_state.json'
    if not trusted_trainer and state_path.is_file():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('status') == 'running':
            raise ValueError('Training still marked running. Stop training cleanly before compacting.')
    ck = run / 'checkpoints' / 'latest.pt'
    if not ck.is_file() or ck.stat().st_size < 512:
        raise ValueError('A valid latest.pt must exist before archiving')
    # User-provided committed iteration should be extracted from checkpoint by
    # the caller; never trust run_state alone when handling a crashed session.
    results = [compact_one(run,name,committed=committed) for name in LOGS]
    return {'run':run.name,'files':results,'saved_bytes':sum(x['saved_bytes'] for x in results),
            'note':'All original log bytes are recoverable from SHA-256-verified gzip archives. Checkpoints untouched.'}


def space_report(run: Path) -> dict:
    original, archived, checkpoints, other = 0, 0, 0, 0
    for file in run.rglob('*'):
        if file.is_symlink():
            raise ValueError('Unsafe symlink in run: ' + str(file))
        if not file.is_file():
            continue
        value = file.stat().st_size
        if file.name in LOGS:
            original += value
        elif 'archives' in file.parts and file.name.endswith('.jsonl.gz'):
            archived += value
        elif 'checkpoints' in file.parts:
            checkpoints += value
        else:
            other += value
    return {'run':run.name,'journals_bytes':original,'archives_bytes':archived,
            'checkpoint_bytes':checkpoints,'other_bytes':other,
            'total_bytes':original+archived+checkpoints+other}
