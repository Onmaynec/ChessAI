"""Local Chess AI dashboard. Serves only on 127.0.0.1 by default.

Start: python -m dashboard.server
Backend uses local experiment files and a user-controlled trainer subprocess.
"""
from __future__ import annotations

import argparse
import csv
import errno
from .analysis import summarize
from neural.storage import tail_records, find_game, space_report
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
UI = Path(__file__).resolve().parent / "ui"
RUN_ID = re.compile(r"^[a-zA-Z0-9_-]{1,70}$")
proc_lock = threading.RLock()
training_mutation_lock = threading.Lock()
active_proc: subprocess.Popen | None = None
active_run: str | None = None
active_log = None
active_eval: subprocess.Popen | None = None
active_eval_log = None
active_eval_run: str | None = None
active_eval_output: str | None = None
active_agent_proc: subprocess.Popen | None = None
active_agent_profile: str | None = None
active_agent_run: str | None = None
active_agent_log = None
app = FastAPI(title="Chess AI · Training Studio", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=UI), name="static")


def safe_run(run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise HTTPException(400, "Invalid run identifier")
    root = RUNS / run_id
    if not root.is_dir():
        raise HTTPException(404, "Run not found")
    return root


# Windows can briefly deny access when the trainer atomically replaces state
# files while a dashboard request is reading them. Retry short lock races and
# preserve the last successfully read data instead of returning HTTP 500.
READ_RETRY_DELAYS = (0.025, 0.05, 0.10, 0.20, 0.30)
read_issues: dict[str, str] = {}
last_json: dict[str, Any] = {}
last_jsonl: dict[str, list[dict]] = {}
last_text: dict[str, list[str]] = {}


def _read_with_retry(path: Path, reader, fallback):
    identity = str(path)
    for attempt in range(len(READ_RETRY_DELAYS) + 1):
        try:
            value = reader()
            read_issues.pop(identity, None)
            return value
        except FileNotFoundError:
            read_issues.pop(identity, None)
            return fallback()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return fallback()
        except OSError as error:
            # EACCES / EPERM and Windows sharing violations (32/33) are
            # generally transient. Do not mask unrelated filesystem errors.
            transient = error.errno in (errno.EACCES, errno.EPERM) or getattr(error, 'winerror', None) in (32, 33)
            if not transient:
                raise
            if attempt < len(READ_RETRY_DELAYS):
                time.sleep(READ_RETRY_DELAYS[attempt])
                continue
            read_issues[identity] = f"Temporarily unable to read {path.name}: {type(error).__name__}"
            return fallback()
    return fallback()  # defensive, normally unreachable


def json_file(path: Path, default: Any = None):
    identity = str(path)
    def reader():
        value = json.loads(path.read_text(encoding='utf-8'))
        last_json[identity] = value
        return value
    return _read_with_retry(path, reader, lambda: last_json.get(identity, default))


def tail_jsonl(path: Path, limit: int) -> list[dict]:
    identity = str(path)
    def reader():
        lines = deque(maxlen=limit)
        with path.open(encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.strip():
                    lines.append(line)
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # An interrupted append may leave a partial line.
        last_jsonl[identity] = records
        return records
    return _read_with_retry(path, reader, lambda: last_jsonl.get(identity, [])[-limit:])


def tail_text(path: Path, limit: int = 22) -> list[str]:
    identity = str(path)
    def reader():
        with path.open(encoding='utf-8', errors='replace') as f:
            value = [s.rstrip('\n') for s in deque(f, maxlen=limit)]
        last_text[identity] = value
        return value
    return _read_with_retry(path, reader, lambda: last_text.get(identity, [])[-limit:])


def file_warnings() -> list[dict[str, str]]:
    # Only expose filenames, not absolute local Windows paths, in the UI.
    return [{'file': Path(k).name, 'message': v} for k, v in sorted(read_issues.items())]


def sessions() -> list[dict]:
    RUNS.mkdir(parents=True, exist_ok=True)
    out = []
    for path in RUNS.iterdir():
        if not path.is_dir() or not RUN_ID.fullmatch(path.name):
            continue
        metadata = json_file(path / "run_metadata.json", {})
        state = json_file(path / "run_state.json", {})
        if not metadata:
            continue
        out.append({"id": path.name, "name":metadata.get("name",path.name),
                    "created_at": metadata.get("created_at"),
                    "status": state.get("status", "unknown"),
                    "iteration":state.get("iteration",0),
                    "games":state.get("counters",{}).get("games",0),
                    "architecture":metadata.get("architecture",{}),
                    "parameters":metadata.get("parameters")})
    return sorted(out, key=lambda x:x["created_at"] or "", reverse=True)


def process_status():
    global active_proc, active_log
    with proc_lock:
        if active_proc is None:
            return {"active":False, "run":active_run, "return_code":None}
        rc = active_proc.poll()
        if rc is not None:
            if active_log:
                active_log.close()
                active_log = None
            active_proc = None
        return {"active":rc is None, "run":active_run, "return_code":rc}


def default_engine() -> Path:
    candidates = [ROOT/"build/Release/chessai.exe", ROOT/"build/chessai.exe", ROOT/"build/chessai"]
    return next((p for p in candidates if p.is_file()), candidates[0] if os.name == "nt" else candidates[-1])


class TrainingConfig(BaseModel):
    iterations: int = Field(10, ge=1, le=100000)
    games_per_iteration: int = Field(8, ge=1, le=512)
    parallel: int = Field(4, ge=1, le=64)
    batch_size: int = Field(64,ge=1,le=2048)
    max_plies: int = Field(240, ge=8, le=1500)
    temperature: float = Field(1.1, ge=0.2, le=3.0)
    arena_games: int = Field(2, ge=0, le=40)
    ppo_epochs: int = Field(2, ge=1, le=12)
    lr: float = Field(0.0003, gt=0, le=0.02)
    opening_plies: int = Field(6, ge=0, le=16)
    best_every: int = Field(10, ge=0, le=10000)
    best_games: int = Field(16, ge=8, le=100)
    league_fraction: float = Field(0.25, ge=0, le=1)
    league_pool_size: int = Field(4, ge=1, le=16)
    repetition_penalty: float = Field(0.12, ge=0, le=2)
    target_kl: float = Field(0.035, gt=0, le=2)
    grad_clip: float = Field(1.0, gt=0, le=10)
    bridge_workers: int = Field(2,ge=1,le=8)
    archive_every: int = Field(5,ge=0,le=1000)


class ResumeConfig(BaseModel):
    iterations: int = Field(10, ge=1, le=100000)
    parallel: int | None = Field(None,ge=1,le=64)
    batch_size: int | None = Field(None,ge=1,le=2048)
    max_plies: int | None = Field(None, ge=8, le=1500)
    opening_plies: int | None = Field(None, ge=0, le=16)
    repetition_penalty: float | None = Field(None, ge=0, le=2)
    league_pool_size: int | None = Field(None, ge=1, le=16)
    target_kl: float | None = Field(None, gt=0, le=2)
    bridge_workers: int | None = Field(None,ge=1,le=8)
    archive_every: int | None = Field(None,ge=0,le=1000)


def launch(run_id: str, cfg: dict, resume: bool = False):
    global active_proc, active_run, active_log
    status = process_status()
    if status["active"]:
        raise HTTPException(409, f"Training already running: {status['run']}")
    engine = default_engine()
    if not engine.is_file():
        raise HTTPException(409, "Chess engine not compiled. Run scripts/build_windows.bat first")
    path = RUNS / run_id
    path.mkdir(parents=True,exist_ok=True)
    cmd = [sys.executable, "-m", "neural.selfplay", "--engine", str(engine.resolve()),
           "--out", str(path.resolve())]
    fields = {"iterations":"iterations", "games_per_iteration":"games-per-iteration",
              "parallel":"parallel", "max_plies":"max-plies", "temperature":"temperature",
              "arena_games":"arena-games", "ppo_epochs":"ppo-epochs", "lr":"lr",
              "arena_every":"arena-every", "batch_size":"batch-size",
              "seed":"seed", "start_fen":"start-fen", "clip":"clip",
              "entropy_weight":"entropy-weight", "value_weight":"value-weight",
              "device":"device", "opening_plies":"opening-plies",
              "best_every":"best-every", "best_games":"best-games",
              "league_fraction":"league-fraction", "league_pool_size":"league-pool-size",
              "repetition_penalty":"repetition-penalty", "target_kl":"target-kl",
              "grad_clip":"grad-clip", "bridge_workers":"bridge-workers",
              "archive_every":"archive-every"}
    for key, flag in fields.items():
        if key in cfg:
            cmd.extend(["--" + flag, str(cfg[key])])
    if resume:
        cmd.append("--resume")
    with training_mutation_lock, proc_lock:
        status = process_status()
        if status['active']:
            raise HTTPException(409, f"Training already running: {status['run']}")
        if resume:
            (path / 'stop_requested').unlink(missing_ok=True)
        log = (path / 'console.log').open('a', encoding='utf-8')
        try:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except BaseException:
            log.close()
            raise
        active_log, active_proc, active_run = log, proc, run_id
    return {"ok":True, "run":run_id}



class AgentTrainingConfig(BaseModel):
    epochs: int = Field(5, ge=1, le=30)
    max_rows: int = Field(950, ge=24, le=15000)
    teacher_depth: int = Field(3, ge=1, le=4)
    batch_size: int = Field(64, ge=8, le=512)
    lr: float = Field(0.00002, gt=0, le=0.001)


def agent_process_status() -> dict:
    global active_agent_proc, active_agent_log
    with proc_lock:
        if active_agent_proc is None:
            return {'active':False,'run':active_agent_run,'profile':active_agent_profile}
        rc=active_agent_proc.poll()
        if rc is not None:
            if active_agent_log is not None:
                active_agent_log.close();active_agent_log=None
            active_agent_proc=None
        return {'active':rc is None,'run':active_agent_run,
                'profile':active_agent_profile,'return_code':rc}


def training_health(run_dir: Path) -> dict:
    """Early warnings are descriptive, NOT an Elo estimate."""
    series=tail_jsonl(run_dir/'metrics.jsonl',100)[-100:]
    if not series:return {'iterations':0,'warnings':['Нет метрик PPO.']}
    finished=sum(max(0,int(r.get('games',0))-int(r.get('results',{}).get('unfinished',0))) for r in series)
    draws=sum(int(r.get('results',{}).get('draws',0)) for r in series)
    valid=[r for r in series if isinstance(r.get('quality'),dict) or isinstance(r.get('ppo_quality'),dict)]
    stops=sum(bool((r.get('quality') or r.get('ppo_quality') or {}).get('kl_early_stop')) for r in valid)
    # Prefer top-level keys when present in newer metrics schema.
    observed=[r for r in series if 'kl_early_stop' in r]
    if observed:
        valid=observed
        stops=sum(bool(r.get('kl_early_stop')) for r in observed)
    arena=[float(r['arena']['score']) for r in series if isinstance(r.get('arena'),dict) and r['arena'].get('completed',0)>0 and r['arena'].get('score') is not None]
    warnings=[]
    if finished and draws/finished > 0.75:
        warnings.append('Большая доля ничьих: проверьте повторения и качество разнообразия дебютов.')
    if valid and stops/len(valid)>0.6:
        warnings.append('PPO часто обрывается по KL: проверьте learning rate и target KL, не меняйте их одновременно.')
    if arena and len(arena)>=12 and sum(arena[-min(12,len(arena)):])/min(12,len(arena)) < 0.48:
        warnings.append('Недостаточно доказательств улучшения относительно эталона; выполните независимый evaluation.')
    return {'iterations':len(series),'completed_games':finished,'draw_share':round(draws/max(1,finished),4),
            'kl_early_stop_share':round(stops/len(valid),4) if valid else None,
            'arena_score_mean':round(sum(arena)/len(arena),4) if arena else None,
            'arena_samples':len(arena),'warnings':warnings,
            'note':'PPO diagnostics are descriptive; evaluate Elo with independent paired games.'}


@app.get('/api/agents/{run_id}')
def agents_status(run_id: str):
    path=safe_run(run_id)
    from neural.agent_profiles import resolve_source_checkpoints
    checkpoints=path/'checkpoints'
    files=['latest.pt','lasttest.pt','skillboost.pt','skillboost_v2.pt','aggressive.pt','defender.pt','phantom.pt']
    reports={}
    for style in ('aggressive','defender','phantom'):
        reports[style]=json_file(path/'agent_training'/f'{style}_report.json',{})
    return {'models':{f:(checkpoints/f).is_file() for f in files},'reports':reports,
            'process':agent_process_status(),'log':tail_text(path/'agent_training'/'console.log',16),
            'health':training_health(path),
            'note':'Independent candidates; Phantom is trained from local illustrative PGN, not verified Elo.'}


@app.post('/api/agents/{run_id}/train/{profile}')
def agents_train(run_id: str, profile: str, config: AgentTrainingConfig):
    global active_agent_proc, active_agent_log, active_agent_run, active_agent_profile
    if profile not in ('aggressive','defender','phantom'):raise HTTPException(400,'Unknown agent profile')
    path=safe_run(run_id)
    if agent_process_status()['active']:raise HTTPException(409,'An agent specialization job is already running')
    if process_status()['active']:raise HTTPException(409,'Stop PPO training after an iteration before GPU-intensive agent specialization')
    if (path/'checkpoints'/f'{profile}.pt').exists():raise HTTPException(409,'Agent already exists: existing checkpoint is preserved')
    if profile=='phantom':
        from neural.phantom_trainer import source_checkpoint
        try:source_checkpoint(path)
        except FileNotFoundError as exc:raise HTTPException(409,str(exc)) from exc
    else:
        from neural.agent_profiles import resolve_source_checkpoints
        try:resolve_source_checkpoints(path)
        except FileNotFoundError as exc:raise HTTPException(409,str(exc)) from exc
    engine=default_engine()
    if not engine.is_file():raise HTTPException(409,'C++ chess engine is missing')
    folder=path/'agent_training';folder.mkdir(parents=True,exist_ok=True)
    if profile=='phantom':
        cmd=[sys.executable,'-m','neural.phantom_trainer','--run',str(path.resolve()),
             '--engine',str(engine.resolve()),'--epochs',str(config.epochs),
             '--lr',str(min(config.lr,0.0005))]
    else:
        cmd=[sys.executable,'-m','neural.agent_specialization','--run',str(path.resolve()),
             '--engine',str(engine.resolve()),'--profile',profile,
             '--epochs',str(config.epochs),'--max-rows',str(config.max_rows),
             '--teacher-depth',str(config.teacher_depth),'--batch-size',str(config.batch_size),
             '--lr',str(config.lr)]
    with proc_lock:
        active_agent_log=(folder/'console.log').open('a',encoding='utf-8')
        active_agent_proc=subprocess.Popen(cmd,cwd=ROOT,stdout=active_agent_log,
                                           stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        active_agent_run=run_id;active_agent_profile=profile
    return {'ok':True,'run':run_id,'profile':profile,'note':'Candidate appears only if holdout gate passes'}


@app.post('/api/agents/{run_id}/stop')
def agents_stop(run_id: str):
    safe_run(run_id)
    status=agent_process_status()
    if not status['active'] or status['run']!=run_id:raise HTTPException(409,'No agent job running for this run')
    with proc_lock:
        active_agent_proc.terminate()
    return {'ok':True,'note':'Terminating candidate job; existing checkpoints are not overwritten'}


@app.get("/")
def index():
    return FileResponse(UI / "index.html", headers={"Cache-Control":"no-store"})


@app.get("/api/health")
def health():
    return {"engine_ready":default_engine().is_file(),
            "engine_path":str(default_engine()),
            "python":sys.version.split()[0],
            "runs":len(sessions()), "process":process_status(),
            "local_only":True, "file_warnings":file_warnings(),
            "version":(ROOT/'VERSION').read_text(encoding='utf-8').strip(),
            "evaluation":evaluation_status()}


@app.get("/api/overview")
def overview(run: str | None = None):
    runs = sessions()
    selected = run or (runs[0]["id"] if runs else None)
    if selected is None:
        return {"runs":runs, "selected":None, "process":process_status(),
                "metadata":None, "state":None, "metrics":[], "games":[], "arena_games":[], "log":[],
                "file_warnings":file_warnings(), "evaluation":evaluation_status()}
    path = safe_run(selected)
    response = {"runs":runs, "selected":selected, "process":process_status(),
                "metadata":json_file(path/"run_metadata.json",{}),
                "state":json_file(path/"run_state.json",{}),
                "metrics":tail_jsonl(path/"metrics.jsonl",600),
                "games":list(reversed(tail_records(path,"games.jsonl",30))),
                "arena_games":list(reversed(tail_records(path,"arena_games.jsonl",20))),
                "log":tail_text(path/"console.log")}
    response["file_warnings"] = file_warnings()
    response["evaluation"] = evaluation_status()
    response["best"] = json_file(path/"best_status.json",{})
    return response


@app.get("/api/games")
def games(run: str, kind: str = "selfplay", result: str = "all", limit: int=50):
    path = safe_run(run)
    if kind not in ("selfplay", "arena") or result not in ("all","1-0","0-1","1/2-1/2","*"):
        raise HTTPException(400, "Invalid filter")
    fname = "games.jsonl" if kind == "selfplay" else "arena_games.jsonl"
    if limit < 1 or limit > 300:
        raise HTTPException(400, "Invalid limit")
    values = tail_records(path,fname, 5000)
    if result != "all":
        values = [g for g in values if g.get("result")==result]
    return {"games":list(reversed(values[-limit:])), "view":"latest_5000", "kind":kind}


@app.get("/api/game/{game_id}")
def game(game_id: int, run: str, kind: str = "selfplay"):
    path = safe_run(run)
    if kind not in ("selfplay", "arena"):
        raise HTTPException(400,"Invalid kind")
    filename = "games.jsonl" if kind == "selfplay" else "arena_games.jsonl"
    found = find_game(path,filename,game_id)
    if found is not None:
        return found
    raise HTTPException(404,"Game not found")

@app.get('/api/storage/{run_id}')
def storage_status(run_id: str):
    path=safe_run(run_id)
    return {'space':space_report(path), 'process':process_status(),
            'note':'Archived history is lossless. Model and optimizer checkpoints remain unmodified.'}


@app.post('/api/storage/{run_id}/compact')
def compact_storage(run_id: str):
    # Only when all training processes are stopped. Strictly preserve the
    # checkpoint iteration boundary, even after interrupted process failures.
    with training_mutation_lock:
        path=safe_run(run_id)
        if process_status()['active']:
            raise HTTPException(409,'Stop training before compacting')
        state=json_file(path/'run_state.json',{}) or {}
        if state.get('status')=='running':
            raise HTTPException(409,'Run marked running. Verify trainer stopped; use offline tool after recovery.')
        from neural.storage import compact_run
        import torch
        checkpoint=torch.load(path/'checkpoints/latest.pt',map_location='cpu',weights_only=True)
        result=compact_run(path,committed=int(checkpoint['iteration']))
        return {'result':result,'space':space_report(path)}


@app.post("/api/start")
def start(config:TrainingConfig):
    value = config.model_dump()
    if value['best_games'] % 2:
        raise HTTPException(422, 'Best screening requires an even number of games')
    if value["games_per_iteration"] * value["max_plies"] > 80000:
        raise HTTPException(422, "Batch is too large for 16 GB RAM: reduce games or max plies")
    dt = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{dt}_{os.urandom(3).hex()}"
    return launch(run_id,value)


@app.post("/api/stop")
def stop(run: str | None = None):
    with proc_lock:
        status = process_status()
        if not status["active"] or not status["run"]:
            raise HTTPException(409, "No running training to stop")
        if run is not None and run != status["run"]:
            raise HTTPException(409, "Active experiment changed; refresh before stopping")
        path = safe_run(status["run"])
        (path / "stop_requested").write_text("Finish the current iteration, then stop.\n",encoding="utf-8")
        return {"ok":True, "message":"Stop requested: finish current iteration before exiting"}


@app.post("/api/resume/{run_id}")
def resume(run_id:str, config:ResumeConfig):
    path = safe_run(run_id)
    meta = json_file(path / "run_metadata.json")
    if not meta or not (path/"checkpoints"/"latest.pt").is_file():
        raise HTTPException(409,"Cannot resume: no complete checkpoint")
    cfg = meta["config"].copy()
    cfg["iterations"] = config.iterations
    if config.max_plies is not None:
        cfg["max_plies"] = config.max_plies
    if config.opening_plies is not None:
        cfg['opening_plies'] = config.opening_plies
    for key in ('repetition_penalty','league_pool_size','target_kl','bridge_workers','archive_every','parallel','batch_size'):
        value=getattr(config,key)
        if value is not None:cfg[key]=value
    if cfg["games_per_iteration"] * cfg["max_plies"] > 80000:
        raise HTTPException(422, "Batch is too large for 16 GB RAM")
    return launch(run_id,cfg,True)


@app.get('/api/analysis')
def analysis(run: str, series_limit: int | None = Query(None, ge=1, le=100000)):
    path=safe_run(run)
    metrics=tail_jsonl(path/'metrics.jsonl',100000)
    result=summarize(metrics)
    result['series_total']=len(result['series'])
    if isinstance(series_limit, int):
        result['series']=result['series'][-series_limit:]
    last=path/'checkpoints'/'latest.pt'
    result['checkpoint']={'exists':last.is_file(),
        'size_bytes':last.stat().st_size if last.is_file() else None,
        'state_iteration':json_file(path/'run_state.json',{}).get('iteration'),
        'note':'For full model + optimizer verification run scripts/VERIFY_PROGRESS_WINDOWS.bat'}
    evaluated=path/'evaluations'
    reports=[]
    if evaluated.is_dir():
        for file in sorted(evaluated.glob('eval_*.json'),reverse=True)[:12]:
            data=json_file(file)
            if isinstance(data,dict):
                stats = dict(data.get('statistics') or {})
                # Legacy v0.4 reports had no diversity field: derive it from
                # their actual saved trajectories rather than inventing a count.
                if 'unique_sequences' not in stats and isinstance(data.get('games'),list):
                    stats['unique_sequences']=len({(g.get('fens',[''])[0],
                         g.get('neural_color'),tuple(g.get('moves',[]))) for g in data['games'] if g.get('fens')})
                    stats['unique_opening_positions']=len({g.get('fens',[''])[0] for g in data['games'] if g.get('fens')})
                reports.append({'filename':file.name,'created_at':data.get('created_at'),
                                 'statistics':stats,
                                'interval':data.get('score_interval95_hoeffding'),
                                'seed':data.get('seed'),'opening_plies':data.get('opening_plies'),
                                'max_plies':data.get('max_plies'),'games_requested':data.get('games_requested'),
                                'suite':data.get('suite','legacy'),
                                'candidate':Path(data.get('candidate','')).name,
                                'reference':Path(data.get('reference','')).name})
    # Historical checkpoint rankings have a different schema; never confuse
    # them with single-match reports.
    tournaments=[]
    if evaluated.is_dir():
        for file in sorted(list(evaluated.glob('tournament_v05_*.json')) + list(evaluated.glob('tournament_v06_*.json')),reverse=True)[:5]:
            data=json_file(file,{})
            if isinstance(data,dict):
                tournaments.append({'filename':file.name,'created_at':data.get('created_at'),
                    'ranking':data.get('ranking',[]),'caveat':data.get('caveat','')})
    result['tournaments']=tournaments
    result['evaluations']=reports
    result['best']=json_file(path/'best_status.json',{})
    result['best_history']=tail_jsonl(path/'best_history.jsonl',100)
    result['device_diagnostics']=json_file(path/'run_state.json',{}).get('device_diagnostics',{})
    result['color_audit']=json_file(path/'diagnostics/color_audit.json',{})
    result['hardware_benchmark']=json_file(ROOT/'diagnostics/hardware_benchmark.json',{})
    result['evaluation_process']=evaluation_status()
    return result

class EvaluationConfig(BaseModel):
    games: int = Field(40, ge=8, le=500)
    max_plies: int = Field(400, ge=20, le=1500)
    opening_plies: int = Field(8, ge=0, le=16)
    seed: int = Field(20261123, ge=0, le=2147483647)
    opponent: str = Field('baseline', pattern='^(baseline|best)$')
    suite: str = Field('holdout', pattern='^(selection|holdout)$')


def evaluation_status():
    global active_eval, active_eval_log
    with proc_lock:
        if active_eval is None:
            return {'active':False,'run':active_eval_run,'output':active_eval_output,'return_code':None}
        code=active_eval.poll()
        if code is not None:
            if active_eval_log:
                active_eval_log.close()
                active_eval_log=None
            active_eval=None
        return {'active':code is None,'run':active_eval_run,
                'output':active_eval_output,'return_code':code}


@app.post('/api/evaluation/{run_id}')
def begin_evaluation(run_id: str, config: EvaluationConfig):
    global active_eval, active_eval_log, active_eval_run, active_eval_output
    run = safe_run(run_id)
    if config.games % 2:
        raise HTTPException(422, 'Use an even number of games for paired colors')
    if process_status()['active']:
        raise HTTPException(409,'Stop training before independent evaluation')
    if evaluation_status()['active']:
        raise HTTPException(409,'An evaluation is already running')
    engine=default_engine()
    if not engine.is_file():
        raise HTTPException(409,'Chess engine not built')
    checkpoint=run/'checkpoints'/'latest.pt'
    baseline=run/'checkpoints'/'best.pt' if config.opponent=='best' else ROOT/'models'/'neural_best.pt'
    if not checkpoint.is_file() or not baseline.is_file():
        raise HTTPException(409,'Checkpoint missing. Resume/initialize run or select baseline.')
    out=run/'evaluations'
    out.mkdir(parents=True,exist_ok=True)
    filename=f'eval_v06_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_{os.urandom(4).hex()}.json'
    target=out/filename
    command=[sys.executable,'-m','neural.evaluation','--engine',str(engine),
             '--checkpoint',str(checkpoint),'--reference',str(baseline),
             '--games',str(config.games),'--max-plies',str(config.max_plies),
             '--opening-plies',str(config.opening_plies),'--seed',str(config.seed),
             '--suite',config.suite,
             '--output',str(target)]
    with proc_lock:
        active_eval_log=(out/'evaluation.log').open('a',encoding='utf-8')
        try:
            active_eval=subprocess.Popen(command,cwd=ROOT,stdout=active_eval_log,
                                         stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        except Exception:
            active_eval_log.close()
            active_eval_log=None
            raise
        active_eval_run=run_id
        active_eval_output=filename
    return {'ok':True,'run':run_id,'filename':filename}


@app.post('/api/agents/{run_id}/evaluate/{profile}')
def evaluate_agent(run_id: str, profile: str):
    """Read-only, paired-color evaluation against previous SkillBoost II.

    This tests checkpoint strength without the Vision tactical search layer.
    """
    global active_eval, active_eval_log, active_eval_run, active_eval_output
    if profile not in ('aggressive','defender'):
        raise HTTPException(400,'Unknown profile')
    run=safe_run(run_id)
    if process_status()['active'] or agent_process_status()['active']:
        raise HTTPException(409,'Stop ongoing training before evaluation')
    if evaluation_status()['active']:
        raise HTTPException(409,'Another evaluation is already running')
    source=run/'checkpoints'/f'{profile}.pt'
    reference=run/'checkpoints'/'skillboost_v2.pt'
    engine=default_engine()
    if not source.is_file() or not reference.is_file() or not engine.is_file():
        raise HTTPException(409,'Specialized model, SkillBoost II or C++ chess engine missing')
    output=run/'evaluations';output.mkdir(parents=True,exist_ok=True)
    name=f'eval_agent_{profile}_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_{os.urandom(3).hex()}.json'
    command=[sys.executable,'-m','neural.evaluation','--engine',str(engine.resolve()),
             '--checkpoint',str(source.resolve()),'--reference',str(reference.resolve()),
             '--games','40','--max-plies','400','--opening-plies','8',
             '--suite','holdout','--output',str(output/name)]
    with proc_lock:
        active_eval_log=(output/'evaluation.log').open('a',encoding='utf-8')
        try:
            active_eval=subprocess.Popen(command,cwd=ROOT,stdout=active_eval_log,
                                         stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        except Exception:
            active_eval_log.close();active_eval_log=None
            raise
        active_eval_run=run_id;active_eval_output=name
    return {'ok':True,'filename':name,'caveat':'40 paired games is only an initial diagnostic, not Elo or proof of superiority'}


class TournamentConfig(BaseModel):
    games: int = Field(20, ge=4, le=500)
    last: int = Field(8, ge=1, le=200)
    max_plies: int = Field(400, ge=20, le=1500)
    opening_plies: int = Field(8, ge=0, le=16)


@app.post('/api/tournament/{run_id}')
def begin_tournament(run_id: str, config: TournamentConfig):
    global active_eval, active_eval_log, active_eval_run, active_eval_output
    run=safe_run(run_id)
    if config.games % 2:
        raise HTTPException(422,'Use an even number of games')
    if process_status()['active'] or evaluation_status()['active']:
        raise HTTPException(409,'Stop active training/evaluation first')
    if not (run/'checkpoints'/'latest.pt').is_file() or not default_engine().is_file():
        raise HTTPException(409,'Checkpoint or chess core missing')
    folder=run/'evaluations'
    folder.mkdir(parents=True,exist_ok=True)
    name=f'tournament_v06_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_{os.urandom(4).hex()}.json'
    command=[sys.executable,'-m','neural.tournament','--run',str(run),
             '--engine',str(default_engine()),'--output',str(folder/name),
             '--last',str(config.last),'--games',str(config.games),
             '--max-plies',str(config.max_plies),'--opening-plies',str(config.opening_plies)]
    with proc_lock:
        active_eval_log=(folder/'evaluation.log').open('a',encoding='utf-8')
        try:
            active_eval=subprocess.Popen(command,cwd=ROOT,stdout=active_eval_log,
                                         stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        except Exception:
            active_eval_log.close();active_eval_log=None
            raise
        active_eval_run=run_id
        active_eval_output=name
    return {'ok':True,'run':run_id,'filename':name}


@app.get('/api/evaluations/{run_id}')
def evaluations(run_id: str):
    run=safe_run(run_id)
    reports=[]
    for path in sorted((run/'evaluations').glob('*.json'),reverse=True)[:50] if (run/'evaluations').is_dir() else []:
        report=json_file(path,{})
        if not isinstance(report,dict):continue
        reports.append({'file':path.name,'created_at':report.get('created_at'),
                        'statistics':report.get('statistics'),
                        'opening_plies':report.get('opening_plies'),
                        'seed':report.get('seed')})
    return {'reports':reports,'process':evaluation_status()}


@app.get("/api/export/metrics.csv")
def metrics_csv(run: str):
    path = safe_run(run)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["iteration","timestamp","games","plies","games_per_s","plies_per_s",
                     "finished","draws","unfinished","samples","policy_loss","value_mse",
                     "entropy","arena_score","arena_completed",
                     "approx_kl","clip_fraction","kl_early_stop","repetition_draws","position_revisits"])
    for r in tail_jsonl(path/"metrics.jsonl",100000):
        t = r.get("train",{})
        a = r.get("arena",{})
        results = r.get("results",{})
        writer.writerow([r.get("iteration"),r.get("at"),r.get("games"),r.get("plies"),
                         r.get("games_per_s"),r.get("plies_per_s"),
                         results.get("white_wins",0)+results.get("black_wins",0)+results.get("draws",0),
                         results.get("draws"),results.get("unfinished"),r.get("samples"),
                         t.get("policy_loss"),t.get("value_mse"),t.get("entropy"),
                         a.get("score"),a.get("completed"),t.get("approx_kl"),t.get("clip_fraction"),
                         t.get("early_stopped_kl"),sum(v for k,v in (r.get("termination_reasons") or {}).items() if "repetition" in k),
                         r.get("position_revisits")])
    return Response(output.getvalue(),media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{run}_metrics.csv"'})


def main():
    p=argparse.ArgumentParser(description="ChessAI self-play training dashboard")
    p.add_argument("--host", default="127.0.0.1",help="Keep localhost unless remote access is configured securely")
    p.add_argument("--port",type=int,default=8765)
    p.add_argument("--no-browser",action="store_true")
    args=p.parse_args()
    # Do not open stale v0.3/v0.4 dashboard if port is still occupied.
    import socket
    with socket.socket() as sock:
        if sock.connect_ex((args.host,args.port)) == 0:
            raise SystemExit(f'Port {args.port} is already occupied. Close the old Chess AI server or use --port 8766.')
    if not args.no_browser:
        threading.Timer(1.5, lambda:webbrowser.open(f"http://{args.host}:{args.port}")).start()
    print(f"ChessAI Training Studio: http://{args.host}:{args.port}",flush=True)
    uvicorn.run(app,host=args.host,port=args.port,log_level="warning")


if __name__=="__main__":
    main()
