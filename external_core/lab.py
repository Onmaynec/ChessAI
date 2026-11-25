"""External engine local lab. No screen capture, browser or mouse operations."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from .uci import configured,PROFILES,START_FEN
from .local import Bridge
from .install import ROOT

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',choices=['stockfish','lc0'],default='stockfish')
    p.add_argument('--profile',choices=PROFILES,default='balanced')
    p.add_argument('--mode',choices=['check','analyse','play'],default='check')
    p.add_argument('--fen',default=START_FEN);p.add_argument('--weights',type=Path)
    p.add_argument('--movetime',type=int);p.add_argument('--multipv',type=int,default=1)
    p.add_argument('--human',choices=['white','black'],default='white')
    p.add_argument('--core',type=Path)
    a=p.parse_args()
    if not a.core:
        a.core=next((x for x in (ROOT/'build/Release/chessai.exe',ROOT/'build/chessai.exe') if x.is_file()),None)
    if not a.core:p.error('Local C++ engine missing')
    ms=a.movetime or PROFILES[a.profile][2]
    if not 50<=ms<=60000 or not 1<=a.multipv<=5:p.error('Invalid search budget')
    with Bridge(a.core) as bridge,configured(a.engine,a.profile,a.weights) as engine:
        state=bridge.new(a.fen);engine.new_game();moves=[]
        if state['finished']:p.error('Terminal position')
        print('Engine:',engine.name,'Profile:',a.profile,flush=True)
        if a.mode in ('check','analyse'):
            result=engine.analyse(a.fen,state['legal_moves'],movetime=ms if a.mode=='analyse' else 300,multipv=a.multipv)
            result['weights_sha256']=getattr(engine,'weights_sha256',None)
            result['fen']=state['fen'];result['status']='ok'
            print(json.dumps(result,indent=2),flush=True)
            out=ROOT/'external_engines'/'v0935'/'reports';out.mkdir(exist_ok=True)
            path=out/f'{a.mode}_{a.engine}_{time.time_ns()}.json';path.write_text(json.dumps(result,indent=2),encoding='utf-8')
            print('Report:',path)
            return
        while not state['finished']:
            print('FEN:',state['fen'],'\nLegal:', ' '.join(state['legal_moves']),flush=True)
            if (state['fen'].split()[1]=='w')==(a.human=='white'):
                m=input('Your UCI move (quit to exit): ').strip().lower()
                if m=='quit':return
                if m not in state['legal_moves']:print('Illegal move');continue
            else:
                r=engine.analyse(a.fen,state['legal_moves'],moves,ms,a.multipv);m=r['bestmove'];print(json.dumps(r,indent=2),flush=True)
            state=bridge.step(m);moves.append(m)
        print('Result:',state['result'],state.get('reason'),'Moves:',' '.join(moves),flush=True)
if __name__=='__main__':main()
