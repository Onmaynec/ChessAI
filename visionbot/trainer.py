"""Use the existing local Training Studio API, never chess.com game data.

Starts the local 0.7 dashboard if absent, then resumes only the selected run.
Never overwrites checkpoints and never starts a second trainer for the same run.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib import request,error

ROOT=Path(__file__).resolve().parents[1]
URL='http://127.0.0.1:8765'


def read_health():
    with request.urlopen(URL+'/api/health',timeout=2) as response:
        return json.load(response)


def ensure_selfplay(run_id:str,engine:Path,iterations:int=500)->str:
    if not 1<=iterations<=100000:raise ValueError('Invalid iterations')
    run=ROOT/'runs'/run_id
    if not (run/'checkpoints'/'latest.pt').is_file():raise FileNotFoundError('Training checkpoint not found')
    proc=None
    try:health=read_health()
    except (OSError,TimeoutError,error.URLError,ValueError):
        logfile=ROOT/'vision_dashboard.log'
        with logfile.open('a',encoding='utf-8') as stream:
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            proc=subprocess.Popen([sys.executable,'-m','dashboard.server','--no-browser'],cwd=ROOT,
                                  stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,
                                  creationflags=flags)
        health=None
        for _ in range(35):
            time.sleep(.3)
            try:health=read_health();break
            except (OSError,TimeoutError,error.URLError,ValueError):
                if proc.poll() is not None:break
        if health is None:raise RuntimeError(f'Training Studio not responding: {logfile}')
    if str(health.get('version'))!='0.7.0':
        raise RuntimeError('Another Chess AI version occupies port 8765; no training was started')
    if Path(health.get('engine_path','')).resolve()!=engine.resolve():
        raise RuntimeError('Training Studio is running from another installation; no training was started')
    ps=health.get('process') or {}
    if ps.get('active'):
        if ps.get('run')==run_id:return 'Self-play already running on this run'
        raise RuntimeError('Another self-play run is active; will not start duplicate trainer')
    try:
        state=json.loads((run/'run_state.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):state={}
    if state.get('status')=='running':
        raise RuntimeError('Run state still says running; verify/recover trainer before starting another instance')
    data=json.dumps({'iterations':iterations}).encode('utf-8')
    req=request.Request(URL+'/api/resume/'+run_id,data=data,
                        headers={'Content-Type':'application/json'},method='POST')
    try:
        with request.urlopen(req,timeout=10) as response:res=json.load(response)
    except error.HTTPError as e:
        detail=e.read(400).decode('utf-8','replace')
        raise RuntimeError(f'Trainer rejected resume, HTTP {e.code}: {detail}') from e
    if not res.get('ok'):raise RuntimeError('Trainer did not confirm resume')
    return f'Self-play resumed for {iterations} iterations; independent from website games'
