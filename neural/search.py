"""Policy-guided, limited-width neural minimax search (not a Stockfish clone).

Every position/move/terminal result comes from the C++ bridge. Only candidate
prior probabilities and leaf values are estimated by our trained ChessNet.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import torch

from .agent import START_FEN
from .checkpoint import load_model
from .encoding import encode_fen, encode_move
from .selfplay import ChessBridge


def terminal_value(state: dict) -> float | None:
    if not state['finished']:
        return None
    if state['result'] == '1/2-1/2':
        return 0.0
    winner = 'w' if state['result'] == '1-0' else 'b'
    return 1.0 if state['fen'].split()[1] == winner else -1.0


@torch.inference_mode()
def priors_and_value(model, state: dict, device) -> tuple[list[tuple[str, float]],float]:
    legal = state['legal_moves']
    if not legal:
        return [], float(terminal_value(state) or 0)
    x = torch.from_numpy(encode_fen(state['fen'])).unsqueeze(0).to(device)
    logits, values = model(x)
    indices = [encode_move(m) for m in legal]
    probabilities = logits[0, indices].float().softmax(dim=0).cpu().tolist()
    return sorted(zip(legal,probabilities),key=lambda v:(-v[1],v[0])),float(values[0].item())


def analyze(model, engine: Path, fen: str = START_FEN, *, depth=2, width=8,
            device: torch.device | str='cpu') -> dict:
    if depth not in (1,2,3) or not 1 <= width <= 32:
        raise ValueError('depth must be 1..3, width must be 1..32')
    model.eval()
    count = 0
    bridge_id = 42
    with ChessBridge(engine) as bridge:
        root = bridge.new(bridge_id,fen)
        root_prior, current_value = priors_and_value(model,root,device)
        if not root_prior:
            return {'best_move':None,'state':root,'candidates':[], 'depth':depth,
                    'width':width,'leaf_evaluations':0}
        # Always consider every legal root action; width limits branching below root.
        # This prevents an immediate mate from being dropped by a weak policy.
        def visit(state: dict, remaining: int) -> float:
            nonlocal count
            tv = terminal_value(state)
            if tv is not None:
                return tv
            ordered, value = priors_and_value(model,state,device)
            count += 1
            if remaining == 0:
                return value
            best = -math.inf
            for move,_ in ordered[:width]:
                branch = bridge.new(bridge_id,state['fen'])
                branch = bridge.step(bridge_id,move)
                score = -visit(branch,remaining-1)
                best = max(best,score)
                if best >= 1.0:  # a guaranteed win needs no more branching
                    break
            return best
        ranked = []
        for move,prior in root_prior:
            bridge.new(bridge_id,root['fen'])
            child = bridge.step(bridge_id,move)
            score = -visit(child,depth-1)
            ranked.append({'move':move,'prior':round(prior,6),'value':round(score,6),
                           'terminal':child['result'] if child['finished'] else None})
    ranked.sort(key=lambda x:(-x['value'],-x['prior'],x['move']))
    return {'best_move':ranked[0]['move'],'root_value':round(current_value,6),
            'candidates':ranked,'depth':depth,'width':width,'leaf_evaluations':count}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Policy-guided neural lookahead')
    parser.add_argument('--engine',type=Path,default=Path('build/Release/chessai.exe' if sys.platform=='win32' else 'build/chessai'))
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--fen',default=START_FEN)
    parser.add_argument('--depth',type=int,choices=(1,2,3),default=2)
    parser.add_argument('--width',type=int,default=8)
    parser.add_argument('--device',choices=('cpu','cuda'),default='cpu')
    args=parser.parse_args(argv)
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    model=load_model(args.checkpoint,args.device)
    result=analyze(model,args.engine,args.fen,depth=args.depth,width=args.width,device=args.device)
    print(f'Best move: {result["best_move"] or "none"}; evaluations: {result["leaf_evaluations"]}')
    for entry in result['candidates'][:12]:
        print(f'{entry["move"]}  score={entry["value"]:+.4f} prior={entry["prior"]:.1%}  {entry["terminal"] or ""}')

if __name__=='__main__':
    main()
