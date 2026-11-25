"""Install pinned official binaries, without starting them or altering training."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,stat,tempfile,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'external_engines'/'v0935'
ASSETS=json.loads(Path(__file__).with_name('assets.json').read_text(encoding='utf-8'))

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def safe_extract(z,folder):
    seen=set();size=0
    for info in z.infolist():
        name=info.filename.replace('\\','/');parts=name.rstrip('/').split('/')
        if not parts or any(not p or p in ('.','..') or ':' in p or p.endswith(('.', ' ')) for p in parts):
            raise ValueError('Unsafe ZIP path: '+name)
        key=name.rstrip('/').casefold()
        if key in seen or stat.S_ISLNK(info.external_attr>>16):raise ValueError('Unsafe ZIP duplicate or symlink')
        seen.add(key);size+=info.file_size
        if size>4*1024**3:raise ValueError('ZIP expands beyond limit')
        target=folder.joinpath(*parts)
        if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with z.open(info) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)

def verify_install(folder,name):
    m=json.loads((folder/'installed.json').read_text(encoding='utf-8'))
    a=ASSETS[name]
    if m['archive_sha256']!=a['sha256'] or m['version']!=a['version']:raise ValueError('Installed version mismatch')
    for rel,h in m['files'].items():
        p=(folder/rel).resolve()
        if not p.is_relative_to(folder.resolve()) or not p.is_file() or digest(p)!=h:raise ValueError('Installed file mismatch: '+rel)
    return m

def install(name):
    a=ASSETS[name];DEST.mkdir(parents=True,exist_ok=True)
    folder=DEST/name
    if folder.exists():
        verify_install(folder,name);print('[INSTALL] Already verified:',name,flush=True);return
    # Reserve ample space for ZIP and extracted runtime/DLLs.
    if shutil.disk_usage(DEST).free<3*1024**3:raise RuntimeError('Need at least 3 GiB free disk space')
    with tempfile.TemporaryDirectory(prefix='.stage-',dir=DEST) as td:
        stage=Path(td);archive=stage/'release.zip';payload=stage/'payload';payload.mkdir()
        request=urllib.request.Request(a['url'],headers={'User-Agent':'ChessAI-external-core/0.9.3.5'})
        print('[DOWNLOAD]',name,a['size'], 'bytes',flush=True)
        count=0;h=hashlib.sha256();last=0
        with urllib.request.urlopen(request,timeout=90) as src,archive.open('xb') as dst:
            while True:
                block=src.read(1024*1024)
                if not block:break
                count+=len(block)
                if count>a['size']:raise ValueError('Release size exceeds pinned size')
                h.update(block);dst.write(block)
                if count-last>=32*1024**2:last=count;print(f'[DOWNLOAD] {count*100/a["size"]:.0f}%',flush=True)
        if count!=a['size'] or h.hexdigest()!=a['sha256']:raise ValueError('Official release size/SHA256 mismatch')
        with zipfile.ZipFile(archive) as z:safe_extract(z,payload)
        candidates=[p for p in payload.rglob('*.exe') if (p.name.lower()=='lc0.exe' if name=='lc0' else p.name.lower().startswith('stockfish'))]
        if len(candidates)!=1:raise ValueError(f'Unexpected executable layout: {candidates}')
        exe=candidates[0];weights=[]
        if name=='lc0':
            weights=sorted([p for p in payload.rglob('*') if p.is_file() and p.name.lower().endswith(('.pb.gz','.pb','.nn.gz'))],
                           key=lambda p:(-p.stat().st_size,str(p)))
            if not weights:raise ValueError('Official package contains no recognized network file')
        files={p.relative_to(payload).as_posix():digest(p) for p in payload.rglob('*') if p.is_file()}
        m={'schema':'external_install_v1','engine':name,'version':a['version'],'archive_sha256':a['sha256'],'url':a['url'],
           'exe':exe.relative_to(payload).as_posix(),'weights':weights[0].relative_to(payload).as_posix() if weights else None,'files':files}
        (payload/'installed.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
        # Rename into a new folder, never overwrite an existing installation.
        if folder.exists():raise FileExistsError(folder)
        payload.rename(folder)
        print('[INSTALL] Verified and installed:',folder,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--engine',choices=['all','stockfish','lc0'],default='all');a=p.parse_args()
    if os.name!='nt':p.error('These pinned releases are Windows binaries')
    for n in ASSETS if a.engine=='all' else (a.engine,):install(n)
    print('Installation complete. Engines were NOT started; finish Scaling before running the GPU lab.',flush=True)
if __name__=='__main__':main()
