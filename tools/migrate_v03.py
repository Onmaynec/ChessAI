"""Non-destructive, verified, standard-library-only migration v0.3 -> v0.4.

Source is NEVER altered; preflight refuses active runs and conflicting destination
files. Each copied file is SHA-256 checked. Safe to retry an interrupted import.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = ('runs', 'models', 'output')


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def files_under(root: Path):
    for base in CATEGORIES:
        folder = root / base
        if folder.is_symlink():
            raise ValueError(f'Symlink category not supported: {folder}')
        if not folder.exists():
            continue
        if not folder.is_dir():
            raise ValueError(f'Expected directory: {folder}')
        for directory, subdirs, names in os.walk(folder, followlinks=False):
            for name in subdirs:
                if (Path(directory) / name).is_symlink():
                    raise ValueError('Symlink directory in migration source')
            for name in names:
                source = Path(directory) / name
                if source.is_symlink() or not source.is_file():
                    raise ValueError(f'Unsafe migration source file: {source}')
                yield source.relative_to(root)


def json_read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def preflight(source: Path, destination: Path, *, allow_interrupted: bool = False) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must be separate, non-nested folders')
    if not source.is_dir() or not (source/'neural'/'selfplay.py').is_file():
        raise ValueError('Source does not look like Chess AI v0.3')
    if (source/'VERSION').read_text(encoding='utf-8').strip() != '0.3.0':
        raise ValueError('Expected v0.3.0 as source')
    if not destination.is_dir() or (destination/'VERSION').read_text(encoding='utf-8').strip() != '0.4.0':
        raise ValueError('Destination must be an extracted v0.4.0 directory')
    details = []
    old_runs = source/'runs'
    if old_runs.exists():
        for run in sorted(old_runs.iterdir()):
            if not run.is_dir() or run.is_symlink():
                raise ValueError(f'Unsafe run directory: {run}')
            if not (run/'run_metadata.json').is_file():
                # Other arbitrary folders in runs aren't deleted; preserve their files.
                continue
            metadata = json_read(run/'run_metadata.json')
            state = json_read(run/'run_state.json') if (run/'run_state.json').exists() else {}
            checkpoint = run/'checkpoints'/'latest.pt'
            if not checkpoint.is_file() or checkpoint.stat().st_size < 512:
                raise ValueError(f'Run {run.name} lacks a complete latest.pt. Make a separate backup and investigate.')
            if state.get('status') == 'running' and not allow_interrupted:
                raise ValueError(f'Run {run.name} still marked running. Stop training from the old dashboard first. '
                                 f'If it already crashed and is definitely stopped, pass --allow-interrupted.')
            details.append({'run':run.name,'status':state.get('status','unknown'),
                            'iteration':state.get('iteration'),
                            'checkpoint_bytes':checkpoint.stat().st_size,
                            'source_version':metadata.get('version')})
    transfer = []
    identical = []
    bytes_total = 0
    conflicts = []
    for relative in files_under(source):
        src, dst = source/relative, destination/relative
        if dst.is_symlink():
            raise ValueError(f'Unsafe destination symlink: {dst}')
        if any(parent.is_symlink() for parent in dst.parents if parent == destination or destination in parent.parents):
            raise ValueError(f'Unsafe destination parent: {dst}')
        src_hash = digest(src)
        if dst.exists():
            if not dst.is_file():
                conflicts.append(str(relative))
            elif digest(dst) == src_hash:
                identical.append(str(relative))
            else:
                conflicts.append(str(relative))
        else:
            transfer.append((relative, src_hash, src.stat().st_size))
            bytes_total += src.stat().st_size
    if conflicts:
        raise ValueError('Destination contains different files with the same names. Nothing was modified. '
                         'Resolve collisions or use a fresh unpacked v0.4 folder:\n'+'\n'.join(conflicts[:15]))
    return {'runs':details,'files_to_copy':len(transfer), 'already_identical':len(identical),
            'bytes_to_copy':bytes_total,'transfer':transfer}


def migrate(source: Path, destination: Path, *, dry_run=False, allow_interrupted=False) -> dict:
    source, destination = source.resolve(), destination.resolve()
    report = preflight(source, destination, allow_interrupted=allow_interrupted)
    if dry_run:
        return {k:v for k,v in report.items() if k!='transfer'} | {'dry_run':True}
    copied = []
    try:
        for relative, expected_hash, size in report['transfer']:
            src, dst = source/relative, destination/relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                raise ValueError(f'Destination changed during migration: {dst}')
            tmp = dst.with_name(dst.name+'.migration-temp')
            if tmp.exists():
                raise ValueError(f'Temporary file exists: {tmp}; remove it manually before retrying')
            try:
                shutil.copy2(src, tmp, follow_symlinks=False)
                if tmp.stat().st_size != size or digest(tmp) != expected_hash:
                    raise OSError(f'File verification failed: {relative}')
                if dst.exists():
                    raise ValueError(f'Destination changed during migration: {dst}')
                os.rename(tmp, dst)
                copied.append(dst)
            finally:
                tmp.unlink(missing_ok=True)
    except Exception:
        # Rollback new files only; NEVER touch preexisting or source files.
        for dst in reversed(copied):
            dst.unlink(missing_ok=True)
        raise
    summary = {k:v for k,v in report.items() if k!='transfer'}
    summary.update({'dry_run':False,'copied':len(copied),
                    'source':str(source),'destination':str(destination),
                    'completed_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'note':'Source v0.3 was not altered; checkpoint weights and optimizer bytes are preserved.'})
    report_folder = destination/'migration_reports'
    report_folder.mkdir(exist_ok=True)
    name = 'migration_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'.json'
    (report_folder/name).write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description='Copy v0.3 training progress to v0.4 without modifying old installation')
    p.add_argument('--source',type=Path,required=True,help='Existing ChessAI-v0.3.0 root')
    p.add_argument('--destination',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--allow-interrupted',action='store_true',help='Only if previous trainer is definitely not running')
    args = p.parse_args(argv)
    try:
        outcome = migrate(args.source,args.destination,dry_run=args.dry_run,allow_interrupted=args.allow_interrupted)
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as error:
        print(f'[ERROR] {error}',file=sys.stderr)
        return 1
    print(json.dumps(outcome,indent=2,ensure_ascii=False))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
