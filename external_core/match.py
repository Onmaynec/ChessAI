"""Local-only multi-engine game runner. No screen capture or external input injection."""
from __future__ import annotations
import json,queue,threading,time
from contextlib import ExitStack
from pathlib import Path
from .uci import configured,PROFILES,START_FEN,ProtocolError
from .local import Bridge
from .install import ROOT,DEST,digest

ENGINES=('Human','Stockfish 19','Leela Chess Zero','ChessNet Policy','ChessNet Hybrid')

def installed(name):
    return (DEST/name/'installed.json').is_file()

def checkpoints():
    paths=set((ROOT/'runs').glob('*/checkpoints/*.pt'))
    paths.update((ROOT/'tactical_experiments').rglob('candidate.pt'))
    return sorted(str(p.relative_to(ROOT)) for p in paths if p.is_file())

def write_report(path,report):
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.flush()
    tmp.replace(path)

class Player:
    def __init__(self,spec,core,stack):
        self.spec=spec;self.core=core;self.stack=stack
        self.kind=spec['kind'];self.engine=None;self.model=None;self.bridge=None
        self.ms=PROFILES[spec['profile']][2]
        self.identity={'kind':self.kind,'profile':spec['profile'],'budget_ms':self.ms}
        if self.kind in ('Stockfish 19','Leela Chess Zero'):
            self.key='stockfish' if self.kind=='Stockfish 19' else 'lc0'
            self.open_uci()
        elif self.kind.startswith('ChessNet'):
            import torch
            from neural.checkpoint import load_model
            path=Path(spec['checkpoint']).resolve()
            self.identity.update(checkpoint=str(path),sha256=digest(path))
            device='cuda' if spec['device']=='cuda' else 'cpu'
            if device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable for ChessNet')
            self.model=load_model(path,device)
            if digest(path)!=self.identity['sha256']:raise RuntimeError('Checkpoint changed while loading')
            self.identity.update(device=device,model_config=self.model.config)
            if self.kind=='ChessNet Hybrid':
                from neural.selfplay import ChessBridge
                self.bridge=stack.enter_context(ChessBridge(core))
        elif self.kind!='Human':raise ValueError('Unknown player')

    def open_uci(self):
        e=self.stack.enter_context(configured(self.key,self.spec['profile'],self.spec.get('weights') or None))
        e.new_game();self.engine=e
        manifest=json.loads((DEST/self.key/'installed.json').read_text(encoding='utf-8'))
        self.identity.update(engine=e.name,weights_sha256=getattr(e,'weights_sha256',None),archive_sha256=manifest['archive_sha256'])

    def move(self,state,initial,moves,fens,stop):
        if self.engine is not None:
            try:
                return self.engine.analyse(initial,state['legal_moves'],moves,self.ms,self.spec['multipv'])
            except (ProtocolError,OSError):
                if stop.is_set():raise
                self.engine.close()
                self.open_uci()
                r=self.engine.analyse(initial,state['legal_moves'],moves,self.ms,self.spec['multipv'])
                r['recovered']=True;return r
        start=time.perf_counter()
        from neural.agent import rank
        if self.kind=='ChessNet Hybrid':
            from neural.intelligence import choose_move
            m,_,detail=choose_move(self.model,state,self.bridge,self.core,depth=2,deep_depth=None,
                history_moves=moves,history_fens=fens,style='balanced',repertoire='standard')
            return {'bestmove':m,'engine':self.kind,'elapsed_ms':(time.perf_counter()-start)*1000,
                    'detail':detail,'lines':[]}
        ranked,value=rank(self.model,state['fen'],state['legal_moves'])
        return {'bestmove':ranked[0][0],'engine':self.kind,'value':value,
                'top3':ranked[:3],'elapsed_ms':(time.perf_counter()-start)*1000,'lines':[]}

def play(core,specs,initial,cap,commands,events,stop):
    out=DEST/'matches';out.mkdir(parents=True,exist_ok=True)
    path=out/f'match_{time.time_ns()}.json'
    report={'schema':'local_multi_engine_v1','status':'running','start_fen':initial,
            'players':specs,'moves':[],'result':'*','reason':'initializing','max_plies':cap}
    try:
        write_report(path,report)
        with ExitStack() as stack:
            bridge=stack.enter_context(Bridge(core))
            state=bridge.new(initial);initial=state['fen'];report['start_fen']=initial
            players={s:Player(specs[s],core,stack) for s in ('w','b')}
            report['identities']={s:p.identity for s,p in players.items()}
            moves=[];fens=[initial]
            while not state['finished'] and len(moves)<cap and not stop.is_set():
                side=state['fen'].split()[1];p=players[side]
                events.put(('state',state,p.kind=='Human',p.kind))
                if p.kind=='Human':
                    while not stop.is_set():
                        try:m=commands.get(timeout=.1)
                        except queue.Empty:continue
                        if m in state['legal_moves']:break
                        events.put(('notice','Illegal move'))
                    if stop.is_set():break
                    result={'bestmove':m,'engine':'Human'}
                else:
                    result=p.move(state,initial,moves,fens,stop)
                    if stop.is_set():break
                    m=result['bestmove']
                if m not in state['legal_moves']:raise RuntimeError('Illegal engine move: '+m)
                state=bridge.step(m);moves.append(m);fens.append(state['fen'])
                report['moves'].append({'ply':len(moves),'side':side,'uci':m,'analysis':result,
                                        'fen':state['fen']})
                report['final_fen']=state['fen'];write_report(path,report)
                events.put(('move',state,side,m,result))
            report.update(status='complete' if state['finished'] else 'stopped' if stop.is_set() else 'incomplete',
                          result=state['result'] if state['finished'] else '*',
                          reason=state.get('reason') if state['finished'] else 'stopped' if stop.is_set() else 'max_plies_unfinished',
                          final_fen=state['fen'])
            events.put(('state',state,False,''))
    except Exception as exc:
        report.update(status='failed',reason=str(exc))
        events.put(('notice',str(exc)))
    finally:
        try:write_report(path,report)
        finally:events.put(('done',report['status'],report['result'],report['reason'],str(path)))
