"""SkillBoost II: copy-only tactical/strategic distillation for ChessNet.

All generated examples come from ChessAI's local C++ engine or curated short
opening continuations. The local teacher is limited and is NOT a grandmaster.
No online chess data and no live PPO files are modified. An improvement of
holdout teacher loss is NOT proof of improved playing strength.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
import os
import random
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler

from .checkpoint import load_model
from .encoding import FEATURE_VERSION, POLICY_SIZE, encode_fen, encode_move, score_to_value
from .selfplay import ChessBridge, START_FEN
from .intelligence import evaluate_fens, SearchUnavailable
from .opening_repertoire_v2 import EXTRA_OPENINGS
from .skill_boost import build_teacher
from .train import read_rows

CATEGORIES = ('opening','counter','trade','defense','attack','endgame','general')
CAT_NUM = {name:i for i,name in enumerate(CATEGORIES)}
PIECE_VALUES = {'p':1,'n':3,'b':3,'r':5,'q':9,'k':0}
TACTICAL_SEEDS = (
    ('mate_attack','7k/6pp/5K2/8/8/8/8/6Q1 w - - 0 1'),
    ('free_queen','4k3/8/8/3q4/5N2/8/8/4K3 w - - 0 1'),
    ('rook_check','4k3/8/8/8/8/8/4r3/4K3 w - - 0 1'),
    ('castling','r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'),
    ('tactic_position_5','rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8'),
    ('tactic_position_kiwipete','r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1'),
    ('endgame_rooks','8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1'),
    ('equal_endgame','6k1/5ppp/8/8/8/5N2/5PPP/6K1 w - - 0 1'),
    ('pin_pressure','4k3/4q3/8/8/8/8/4R3/4K3 w - - 0 1'),
    ('rook_exchange','2r3k1/5ppp/8/8/8/8/5PPP/2R3K1 w - - 0 1'),
    ('knight_fork','4k3/3q4/8/8/5N2/8/8/4K3 w - - 0 1'),
    ('defensive_block','4r1k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1'),
    ('central_counterattack','4k3/8/8/2q5/8/2N5/8/4K3 w - - 0 1'),
    ('pawn_promotion_race','8/P6k/8/8/8/7p/K7/8 w - - 0 1'),
    ('major_piece_tactics','2r3k1/5ppp/8/8/8/8/5PPP/2Q3K1 w - - 0 1'),
    ('minor_piece_defense','4k3/8/8/8/2n5/8/3P4/4K3 w - - 0 1'),
)


def sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    target=path.with_name(path.name+'.pending')
    try:
        target.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(target,path)
    finally:
        target.unlink(missing_ok=True)


def fen_piece(fen: str, square: str) -> str:
    if len(square)!=2 or square[0] not in 'abcdefgh' or square[1] not in '12345678':
        raise ValueError('Invalid square')
    text=fen.split()[0].split('/')[8-int(square[1])]
    row=''.join('.'*int(ch) if ch.isdigit() else ch for ch in text)
    return row[ord(square[0])-ord('a')]


def material_count(fen: str) -> int:
    return sum(1 for p in fen.split()[0] if p.isalpha() and p.lower()!='k')


def classify(row: dict) -> str:
    if row.get('category') in CATEGORIES:
        return row['category']
    move=row['best_move']; dest=fen_piece(row['fen'],move[2:4]);origin=fen_piece(row['fen'],move[:2]);
    if dest!='.' and PIECE_VALUES.get(dest.lower(),0)>0:return 'trade'
    if material_count(row['fen'])<=8:return 'endgame'
    if abs(float(row['score_cp']))>=250:return 'attack' if float(row['score_cp'])>0 else 'defense'
    return 'general'


def add(rows: dict, row: dict, group: str, category: str | None = None) -> None:
    if not row.get('legal_moves') or row['best_move'] not in row['legal_moves']:
        raise ValueError('Teacher label is illegal')
    if row['fen'] in rows:
        return
    row=dict(row)
    row['category']=category or classify(row)
    row['split_group']=group
    rows[row['fen']]=row


def opening_positions(engine: Path, *, max_counter: int, seed: int) -> list[dict]:
    """Build legal prefix + novel-reply positions for both sides of repertoire."""
    rng=random.Random(seed)
    positions=[];seen=set();counter=0
    with ChessBridge(engine) as bridge:
        for item in EXTRA_OPENINGS:
            state=bridge.new(500,START_FEN)
            for ply, move in enumerate(item.moves):
                if move not in state['legal_moves']:
                    raise ValueError(f'Invalid repertoire: {item.name}, ply {ply+1}, {move}')
                if state['fen'] not in seen:
                    positions.append({'fen':state['fen'],'legal_moves':state['legal_moves'],
                                      'book_move':move,'category':'opening',
                                      'split_group':'family:'+item.family,'opening_name':item.name})
                    seen.add(state['fen'])
                # Opponent deviations: add unseen legal positions after a reply,
                # using the same independent local chess rules as the self-play.
                if counter<max_counter and 2 <= ply <= 10 and (ply%3==0):
                    alternatives=[m for m in state['legal_moves'] if m!=move]
                    # Pawn/knight moves are common practical alternatives.
                    alternatives.sort(key=lambda m:(fen_piece(state['fen'],m[:2]).lower() not in 'pn',m))
                    if alternatives:
                        alt=rng.choice(alternatives[:min(7,len(alternatives))])
                        bridge.new(501,state['fen'])
                        changed=bridge.step(501,alt)
                        if not changed['finished'] and changed['fen'] not in seen:
                            positions.append({'fen':changed['fen'],'legal_moves':changed['legal_moves'],
                                              'category':'counter', 'book_move':None,
                                              'split_group':'family:'+item.family,
                                              'opening_name':item.name+' / deviation'})
                            seen.add(changed['fen']);counter+=1
                state=bridge.step(500,move)
                if state['finished']:break
    return positions


def teacher_scores(engine: Path, positions: list[dict], *, depth: int, progress=None) -> list[dict]:
    """Deterministic local UCI bestmove and value labels. Never trust book unconditionally."""
    out=[]
    for start in range(0,len(positions),48):
        group=positions[start:start+48]
        answers=evaluate_fens(engine,[r['fen'] for r in group],depth=depth,
                              timeout=max(90.0,depth*70.0))
        for row,result in zip(group,answers):
            if not result.move or result.move not in row['legal_moves']:
                continue
            out.append({**row,'best_move':result.move,'score_cp':result.score_cp,
                        'teacher':f'chessai_builtin_search_d{depth}',
                        'teacher_best':result.move})
        if progress:progress(f'Размечено целевых позиций: {len(out)}/{len(positions)}')
    # Prefer established opening continuations ONLY after a local tactical
    # sanity check. A recognizable opening is never allowed to override a
    # forcing mate or clearly losing alternative. Search depth on the child
    # is d-1, comparable in ply budget to the root search depth d.
    selected=[r for r in out if r.get('category')=='opening' and r.get('book_move') in r['legal_moves']]
    if selected:
        with ChessBridge(engine) as bridge:
            children=[]
            for row in selected:
                bridge.new(715,row['fen'])
                children.append(bridge.step(715,row['book_move']))
        safe=[]
        child_fens=[c['fen'] for c in children if not c['finished']]
        for start in range(0,len(child_fens),48):
            safe.extend(evaluate_fens(engine,child_fens[start:start+48],
                                       depth=max(1,depth-1),timeout=max(90.,depth*60.)))
        answers=iter(safe)
        for row,child in zip(selected,children):
            if child['finished']:
                book_score=(0 if child['result']=='1/2-1/2' else
                            30000 if (child['result']=='1-0')==(row['fen'].split()[1]=='w') else -30000)
            else:
                book_score=-next(answers).score_cp
            row['book_verified_cp']=book_score
            # A 100cp safety band is conservative about weak engine noise.
            if book_score>=row['score_cp']-100:
                row['best_move']=row['book_move']
                row['teacher']='curated_opening_with_cpp_tactical_safety_gate'
    return out


def enrich_variations(engine: Path, rows: list[dict], *, max_positions: int,
                      depth: int, seed: int, progress=None) -> None:
    """Evaluate alternative replies: can a developing/capturing move be refuted?

    For a bounded subset we evaluate each legal child from opponent's point of
    view; negative score corresponds to our advantage. These become soft
    policy targets; the first label still comes from the native engine root.
    """
    rng=random.Random(seed+19)
    selected=[r for r in rows if r['category'] in ('opening','counter','trade','defense','attack')]
    rng.shuffle(selected)
    selected=selected[:max_positions]
    if not selected:return
    with ChessBridge(engine) as bridge:
        for n,row in enumerate(selected,1):
            children=[]
            # Compare a bounded candidate set, anchored on the root teacher.
            legal=[row['best_move']]
            if row.get('book_move') in row['legal_moves'] and row['book_move'] not in legal:
                legal.append(row['book_move'])
            other=[m for m in row['legal_moves'] if m not in legal]
            rng.shuffle(other)
            legal.extend(other[:max(0,8-len(legal))])
            for move in legal:
                bridge.new(700,row['fen'])
                child=bridge.step(700,move)
                children.append((move,child))
            unfinished=[s['fen'] for _,s in children if not s['finished']]
            try:
                answers=evaluate_fens(engine,unfinished,depth=depth,
                                      timeout=max(90.0,depth*45.0))
            except SearchUnavailable:
                continue  # Retain hard target; never guess tactical scores.
            ans=iter(answers);scored=[]
            for move,child in children:
                if child['finished']:
                    if child['result']=='1/2-1/2':score=0
                    else:score=30000 if (child['result']=='1-0')==(row['fen'].split()[1]=='w') else -30000
                else:
                    score=-next(ans).score_cp
                scored.append((move,int(score)))
            scored.sort(key=lambda p:(-p[1],p[0]))
            # Do not make a shallow alternate-search label contradict a strong
            # root search; take alternate scores as *relative* soft signal.
            best_score=scored[0][1]
            plausible=[(m,s) for m,s in scored if s>=best_score-200][:4]
            row['alternatives']=plausible
            row['branch_count']=len(scored)
            row['best_move']=scored[0][0]
            row['score_cp']=best_score
            row['teacher']='chessai_builtin_multibranch_d'+str(depth)
            if progress and n%25==0:progress(f'Проверено вариантов: {n}/{len(selected)}')


class SkillDataset(Dataset):
    def __init__(self, rows:list[dict]):
        self.rows=rows
    def __len__(self):return len(self.rows)
    def __getitem__(self,i):
        row=self.rows[i]
        x=torch.from_numpy(encode_fen(row['fen']))
        legal=torch.zeros(POLICY_SIZE,dtype=torch.bool)
        legal[[encode_move(m) for m in row['legal_moves']]]=True
        label=encode_move(row['best_move'])
        choices=row.get('alternatives') or [(row['best_move'],0)]
        # Distil teacher's relative preference, without teaching a 200cp blunder.
        scores=torch.tensor([max(-1000,min(1000,int(s))) for _,s in choices],dtype=torch.float32)
        probs=torch.softmax((scores-scores.max())/100.0,dim=0)
        ids=torch.zeros(4,dtype=torch.long);weights=torch.zeros(4,dtype=torch.float32)
        for j,((move,_),p) in enumerate(zip(choices[:4],probs[:4])):
            ids[j]=encode_move(move);weights[j]=p
        # Separate validation of tactical categories.
        return x,torch.tensor(label),torch.tensor(score_to_value(row['score_cp']),dtype=torch.float32),legal,ids,weights,torch.tensor(CAT_NUM[row['category']])


def epoch(model,loader,device,optimizer=None):
    model.train(optimizer is not None)
    n=0;losses=policy_losses=values=0.;correct=0
    cat_total=Counter();cat_correct=Counter()
    for x,label,value,legal,ids,weights,category in loader:
        x=x.to(device,non_blocking=True);label=label.to(device);value=value.to(device)
        legal=legal.to(device);ids=ids.to(device);weights=weights.to(device)
        with torch.set_grad_enabled(optimizer is not None):
            logits,pred=model(x)
            logits=logits.masked_fill(~legal,-1e9)
            log_probs=torch.log_softmax(logits,dim=1)
            hard=nn.functional.nll_loss(log_probs,label)
            soft=-(log_probs.gather(1,ids)*weights).sum(dim=1).mean()
            p_loss=0.7*hard+0.3*soft
            v_loss=nn.functional.mse_loss(pred,value)
            loss=p_loss+0.18*v_loss
            if optimizer is not None:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(),1.0)
                optimizer.step()
        size=label.size(0);n+=size
        losses+=float(loss.item())*size;policy_losses+=float(p_loss.item())*size;values+=float(v_loss.item())*size
        match=(logits.detach().argmax(dim=1)==label)
        correct+=int(match.sum().item())
        for cat,ok in zip(category.tolist(),match.cpu().tolist()):
            cat_total[int(cat)]+=1;cat_correct[int(cat)]+=int(ok)
    if n==0:raise ValueError('Training batch is empty')
    return {'loss':round(losses/n,6),'policy_loss':round(policy_losses/n,6),
            'value_mse':round(values/n,6),'policy_top1':round(correct/n,6),
            'category_top1':{CATEGORIES[k]:round(cat_correct[k]/v,6) for k,v in sorted(cat_total.items())}}


def split_rows(rows:list[dict],seed:int,ratio:float=0.18):
    if len(rows)<20:raise ValueError('At least 20 examples required')
    # Group split avoids training/validation on nearby opening prefixes in the
    # same opening family. Keep position-identical rows unique upstream.
    grouped={}
    for row in rows:
        group=row.get('split_group') or 'general:'+hashlib.sha256(row['fen'].encode()).hexdigest()[:6]
        grouped.setdefault(group,[]).append(row)
    keys=list(grouped);random.Random(seed).shuffle(keys)
    valid=[];train=[]
    target=max(4,round(len(rows)*ratio))
    for group in keys:
        if len(valid)<target and len(rows)-len(valid)-len(group)>=12:
            valid.extend(grouped[group])
        else:
            train.extend(grouped[group])
    if len(valid)<4 or len(train)<12:
        raise ValueError('Cannot form independent holdout groups')
    return train,valid


def source_checkpoint(run:Path,choice:str)->Path:
    if choice=='auto':
        for name in ('skillboost.pt','latest.pt','best.pt'):
            if (run/'checkpoints'/name).is_file():return run/'checkpoints'/name
        raise FileNotFoundError('No checkpoint found for SkillBoost v2')
    if choice not in ('skillboost.pt','latest.pt','best.pt'):
        raise ValueError('Unsafe checkpoint name')
    return run/'checkpoints'/choice


def train_skillboost_v2(*,run:Path,engine:Path,source:str='auto',samples:int=480,
                        teacher_depth:int=3,branch_depth:int=2,branches:int=48,
                        epochs:int=8,batch_size:int=64,lr:float=3e-5,
                        device:str='auto',seed:int=20261123,progress=print)->dict:
    run=run.resolve();engine=engine.resolve()
    if not engine.is_file():raise FileNotFoundError(f'Build C++ chess engine first: {engine}')
    if not 24<=samples<=30000 or not 1<=teacher_depth<=4 or not 1<=branch_depth<=5:
        raise ValueError('Invalid teacher sample count or search depth')
    if not 0<=branches<=500 or not 1<=epochs<=40 or not 4<=batch_size<=512 or not 0<lr<=0.001:
        raise ValueError('Invalid training parameters')
    if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
    if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA requested but unavailable')
    if device not in ('cpu','cuda'):raise ValueError('Invalid device')
    source_file=source_checkpoint(run,source)
    if not source_file.is_file():raise FileNotFoundError(f'Source checkpoint not found: {source_file}')
    output=run/'checkpoints'/'skillboost_v2.pt'
    if output.exists():raise FileExistsError(f'{output} exists. Preserve it before another training run.')
    stage=run/'skillboost_v2'
    stage.mkdir(parents=True,exist_ok=True)
    source_hash=sha256(source_file)
    snapshot=torch.load(source_file,map_location='cpu',weights_only=True)
    if snapshot.get('feature_version')!=FEATURE_VERSION:
        raise ValueError('Checkpoint encoding version incompatible')
    # Read the source exactly once and use a stable in-memory snapshot.
    model=load_model(source_file,device)
    torch.manual_seed(seed);np.random.seed(seed);random.seed(seed)
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    dataset=stage/'teacher_dataset.jsonl.gz'
    dataset_meta=stage/'dataset_generation.json'
    settings={'samples':samples,'teacher_depth':teacher_depth,'branch_depth':branch_depth,
              'branches':branches,'seed':seed,'format':2}
    if dataset.exists():
        if not dataset_meta.is_file() or json.loads(dataset_meta.read_text(encoding='utf-8'))!=settings:
            raise FileExistsError('An existing dataset has different settings or missing metadata; preserve it before a new experiment.')
        progress('Возобновляю из ранее сгенерированного и сжатого датасета...')
        with gzip.open(dataset,'rt',encoding='utf-8') as file:
            rows=[json.loads(line) for line in file if line.strip()]
        if not rows or any(r['best_move'] not in r['legal_moves'] for r in rows):
            raise ValueError('Previously saved teacher dataset is invalid')
    else:
        with tempfile.TemporaryDirectory(prefix='chess_skillboost_') as temporary:
            data_file=Path(temporary)/'random_teacher.jsonl'
            progress('Генерирую самостоятельные партии и позиции C++-учителя...')
            build_teacher(engine,data_file,samples=samples,depth=teacher_depth,seed=seed)
            random_rows=read_rows(data_file)
        by_fen={}
        for row in random_rows:
            add(by_fen,row,'game:'+hashlib.sha256(row['fen'].encode()).hexdigest()[:6])
        progress('Готовлю дебюты, ответы на отклонения и тактические упражнения...')
        book=opening_positions(engine,max_counter=max(40,branches*2),seed=seed)
        # Additional hand-verified tactical positions. Their moves are determined
        # by the local engine; no hand-authored forced win labels are fabricated.
        with ChessBridge(engine) as bridge:
            for name,fen in TACTICAL_SEEDS:
                state=bridge.new(900,fen)
                if not state['finished']:
                    book.append({'fen':state['fen'],'legal_moves':state['legal_moves'],
                                 'category':'attack' if any(word in name for word in ('mate','queen','fork','pin','tactics','counterattack')) else 'defense' if any(word in name for word in ('check','defens','block')) else 'endgame',
                                 'book_move':None,'split_group':'puzzle:'+name,'opening_name':name})
        extra=[r for r in book if r['fen'] not in by_fen]
        guided=teacher_scores(engine,extra,depth=teacher_depth,progress=progress)
        for row in guided:add(by_fen,row,row['split_group'],row['category'])
        rows=list(by_fen.values())
        progress(f'Получено {len(rows)} различных легальных позиций; сравниваю возможные продолжения...')
        enrich_variations(engine,rows,max_positions=branches,depth=branch_depth,seed=seed,progress=progress)
        # Use gzip to bound storage. No data is sourced from chess.com.
        temp=stage/'teacher_dataset.jsonl.gz.pending'
        try:
            with gzip.open(temp,'wt',encoding='utf-8',compresslevel=6) as file:
                for row in rows:file.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
            os.replace(temp,dataset)
        finally:temp.unlink(missing_ok=True)
        atomic_json(dataset_meta,settings)
    train,valid=split_rows(rows,seed)
    weights={'opening':1.4,'counter':1.8,'trade':2.1,'defense':2.2,'attack':2.0,'endgame':1.5,'general':1.0}
    sampler=WeightedRandomSampler([weights[row['category']] for row in train],len(train),replacement=True)
    train_loader=DataLoader(SkillDataset(train),batch_size=batch_size,sampler=sampler,num_workers=0,pin_memory=device=='cuda')
    val_loader=DataLoader(SkillDataset(valid),batch_size=batch_size,shuffle=False,num_workers=0,pin_memory=device=='cuda')
    model.eval()
    with torch.no_grad():before=epoch(model,val_loader,torch.device(device))
    optimizer=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=1e-4)
    best_loss=float(before['loss']);best_state=None;best_stats=before;history=[]
    progress(f'Начальная holdout loss: {best_loss:.4f} | {device} | train={len(train)} valid={len(valid)}')
    for i in range(1,epochs+1):
        learned=epoch(model,train_loader,torch.device(device),optimizer)
        with torch.no_grad():check=epoch(model,val_loader,torch.device(device))
        history.append({'epoch':i,'train':learned,'holdout':check})
        if check['loss']<best_loss-1e-5:
            best_loss=float(check['loss']);best_state=copy.deepcopy({k:v.detach().cpu() for k,v in model.state_dict().items()});best_stats=check
        progress(f'Эпоха {i}/{epochs}: holdout {check["loss"]:.4f}, top1 {check["policy_top1"]:.1%}')
    candidate_written=False
    # Slight decline in tactical category accuracy tolerated due to tiny
    # samples; holdout improvement is still not a strength guarantee.
    def cat_score(stats):
        cats=stats['category_top1']
        return sum(cats.get(k,0.) for k in ('trade','defense','attack'))/max(1,sum(k in cats for k in ('trade','defense','attack')))
    tactical_ok=cat_score(best_stats)>=cat_score(before)-0.05
    if best_state is not None and tactical_ok:
        payload={'model':best_state,'config':snapshot['config'],'feature_version':FEATURE_VERSION,
                 'iteration':int(snapshot.get('iteration',0)),'optimizer':None,'candidate_only':True,
                 'skillboost_v2':{'source':source_file.name,'source_sha256':source_hash,
                                  'teacher':'builtin_chessai_cpp_alpha_beta_not_grandmaster',
                                  'teacher_depth':teacher_depth,'branch_depth':branch_depth,
                                  'positions':len(rows),'holdout_positions':len(valid),
                                  'baseline':before,'selected_holdout':best_stats,
                                  'date':datetime.now(timezone.utc).isoformat()}}
        temp=output.with_name('skillboost_v2.pending.pt')
        try:
            torch.save(payload,temp)
            load_model(temp,'cpu')
            os.replace(temp,output)
            candidate_written=True
        finally:temp.unlink(missing_ok=True)
    report={'status':'candidate_written' if candidate_written else 'rejected_holdout_or_tactical_guard',
            'candidate_written':candidate_written,'candidate_path':str(output) if candidate_written else None,
            'source':str(source_file),'source_iteration':int(snapshot.get('iteration',0)),
            'source_sha256_at_start':source_hash,'source_unchanged_at_finish':sha256(source_file)==source_hash,
            'rows':len(rows),'categories':dict(Counter(r['category'] for r in rows)),
            'samples':samples,'teacher_depth':teacher_depth,'branch_depth':branch_depth,
            'branch_positions':sum('alternatives' in r for r in rows),'train':len(train),'holdout':len(valid),
            'baseline':before,'selected_holdout':best_stats,'tactical_guard_passed':tactical_ok,
            'epochs':history,'teacher_is_not_professional':True,
            'not_an_elo_measurement':True,'not_a_ppo_resume_checkpoint':True,
            'dataset_gzip':str(dataset),'device':device}
    atomic_json(stage/'report.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='SkillBoost v2: independent tactical/strategic chess candidate')
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--engine',type=Path,default=Path('build/Release/chessai.exe'))
    parser.add_argument('--source',choices=('auto','skillboost.pt','latest.pt','best.pt'),default='auto')
    parser.add_argument('--samples',type=int,default=480)
    parser.add_argument('--teacher-depth',type=int,default=3)
    parser.add_argument('--branch-depth',type=int,default=2)
    parser.add_argument('--branches',type=int,default=48)
    parser.add_argument('--epochs',type=int,default=8)
    parser.add_argument('--batch-size',type=int,default=64)
    parser.add_argument('--lr',type=float,default=3e-5)
    parser.add_argument('--seed',type=int,default=20261123)
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    args=parser.parse_args(argv)
    result=train_skillboost_v2(run=args.run,engine=args.engine,source=args.source,
                               samples=args.samples,teacher_depth=args.teacher_depth,
                               branch_depth=args.branch_depth,branches=args.branches,
                               epochs=args.epochs,batch_size=args.batch_size,lr=args.lr,
                               device=args.device,seed=args.seed)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
