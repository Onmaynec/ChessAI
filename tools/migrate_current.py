"""Non-destructive migration from v0.3-v0.6 installations into v0.7.

Folder names are intentionally ignored. Prior source may have been renamed.
Only the training data under runs/ is copied, keeping the old tree untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def hash_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()


def preflight(source: Path, dest: Path, *, allow_interrupted:bool=False) -> dict:
    src, dst = source.resolve(), dest.resolve()
    if src==dst or src in dst.parents or dst in src.parents:
        raise ValueError('Source and destination must be separate non-nested folders')
    if (src/'runs').is_symlink() or (dst/'runs').is_symlink():
        raise ValueError('Symlink runs/ root not supported')
    if not (src/'neural'/'selfplay.py').is_file() or not (src/'runs').is_dir():
        raise ValueError('Old installation must contain neural/selfplay.py and runs/')
    if not (dst/'neural'/'selfplay.py').is_file() or (dst/'VERSION').read_text().strip() != '0.7.0':
        raise ValueError('Destination must be the extracted v0.7.0 installation')
    # Validate interpreter reuse before copying any potentially large file.
    candidate=src/'.venv-cuda'/'Scripts'/'python.exe'
    pointer=dst/'config'/'python_path.txt'
    if candidate.is_file() and pointer.exists() and pointer.read_text(encoding='utf-8').strip()!=str(candidate):
        raise ValueError('Conflicting CUDA Python interpreter configuration; nothing modified')
    transfer, existing, total = [],0,0
    for root, directories, filenames in os.walk(src/'runs',followlinks=False):
        for d in directories:
            if (Path(root)/d).is_symlink():
                raise ValueError('Symlink folders cannot be migrated')
        for name in sorted(filenames):
            old = Path(root)/name
            if old.is_symlink() or not old.is_file():
                raise ValueError('Unsafe source file: '+str(old))
            rel=old.relative_to(src)
            target=dst/rel
            if target.is_symlink() or any(p.is_symlink() for p in target.parents if dst==p or dst in p.parents):
                raise ValueError('Symlink target path: '+str(target))
            if target.exists():
                if not target.is_file() or hash_file(old)!=hash_file(target):
                    raise ValueError('Conflicting existing destination file; nothing modified: '+str(rel))
                existing+=1
            else:
                transfer.append((rel,old.stat().st_size,hash_file(old)))
                total += old.stat().st_size
    for run in (src/'runs').iterdir():
        if not run.is_dir():continue
        state=run/'run_state.json'
        ck=run/'checkpoints'/'latest.pt'
        if (run/'run_metadata.json').exists() and (not ck.is_file() or ck.stat().st_size<512):
            raise ValueError('Incomplete checkpoint: '+str(run.name))
        if state.exists() and json.loads(state.read_text(encoding='utf-8')).get('status')=='running' and not allow_interrupted:
            raise ValueError('Run still marked running. Stop training and retry; use --allow-interrupted ONLY if prior process is stopped.')
    return {'source':str(src),'destination':str(dst),'copy_count':len(transfer),
            'identical_count':existing,'bytes_to_copy':total,'transfer':transfer}


def migrate(source: Path, dest: Path, *, dry_run:bool=False, allow_interrupted:bool=False) -> dict:
    data=preflight(source,dest,allow_interrupted=allow_interrupted)
    if dry_run:return {k:v for k,v in data.items() if k!='transfer'}|{'dry_run':True}
    src,dst=source.resolve(),dest.resolve()
    done=[]
    try:
        for rel,size,checksum in data['transfer']:
            target=dst/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name(target.name+'.v07-copying')
            if temp.exists() or target.exists():
                raise ValueError('Destination changed; refusing overwrite: '+str(rel))
            try:
                shutil.copy2(src/rel,temp,follow_symlinks=False)
                if temp.stat().st_size != size or hash_file(temp)!=checksum:
                    raise OSError('SHA-256 verification failed: '+str(rel))
                os.rename(temp,target)
                done.append(target)
            finally:
                temp.unlink(missing_ok=True)
    except Exception:
        for path in reversed(done):path.unlink(missing_ok=True)
        raise
    # Reuse old CUDA environment in place. Virtualenvs are not copied (they
    # often occupy multiple GB and relocation breaks embedded interpreter paths).
    # The old directory MUST be retained as long as this pointer is used.
    cuda_python=src/'.venv-cuda'/'Scripts'/'python.exe'
    if cuda_python.is_file():
        config=dst/'config'
        config.mkdir(parents=True,exist_ok=True)
        pointer=config/'python_path.txt'
        if pointer.exists() and pointer.read_text(encoding='utf-8').strip()!=str(cuda_python):
            raise ValueError('Existing custom Python interpreter config differs; manual resolution required')
        if not pointer.exists():
            pointer.write_text(str(cuda_python)+'\n',encoding='utf-8')
    out={k:v for k,v in data.items() if k!='transfer'}
    out.update({'reused_cuda_python':str(cuda_python) if cuda_python.is_file() else None,
                'copied':len(done),'dry_run':False,
                'at':datetime.now(timezone.utc).isoformat(),
                'note':'Source installation and checkpoints were not modified.'})
    report_dir=dst/'migration_reports'
    report_dir.mkdir(exist_ok=True)
    (report_dir/('migrate_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'.json')).write_text(
        json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
    return out


def main():
    p=argparse.ArgumentParser(description='Verified v0.3-v0.6 -> v0.7 runs migration')
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--destination',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--allow-interrupted',action='store_true')
    a=p.parse_args()
    try:
        print(json.dumps(migrate(a.source,a.destination,dry_run=a.dry_run,
                                  allow_interrupted=a.allow_interrupted),ensure_ascii=False,indent=2))
    except Exception as e:
        p.exit(1,f'ERROR: {e}\n')

if __name__=='__main__':main()
