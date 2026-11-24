"""Opt-in Phantom-X23 policy fine-tuning into a NEW checkpoint.

Independent of PPO. Local study examples only; no downloaded games, no
human-opponent data. Book prefix matching is separately available without
training. Holdout agreement does not establish increased chess strength.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn.functional as F

from .checkpoint import load_model
from .encoding import FEATURE_VERSION, encode_fen, encode_move
from .phantom_opening import white_examples


def file_hash(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def source_checkpoint(run: Path, name: str='auto')->Path:
    root=run/'checkpoints'
    if name=='auto':
        for x in ('aggressive.pt','skillboost_v2.pt','skillboost.pt','latest.pt'):
            if (root/x).is_file():return root/x
        raise FileNotFoundError('No base checkpoint: expected Aggressive / SkillBoost II / Latest')
    if name not in ('aggressive.pt','skillboost_v2.pt','skillboost.pt','latest.pt','lasttest.pt','best.pt'):
        raise ValueError('Unsupported checkpoint selection')
    path=root/name
    if not path.is_file():raise FileNotFoundError(path)
    return path


def _general_positions(run:Path, exclude:set[str], limit:int=64)->list[dict]:
    """Local pre-existing SkillBoost teacher rows; only an anti-forgetting anchor."""
    sources=[run/'skillboost_v2'/'teacher_dataset.jsonl.gz',run/'skillboost_teacher.jsonl']
    rows=[]
    for path in sources:
        if not path.is_file():continue
        reader=gzip.open if path.suffix=='.gz' else open
        with reader(path,'rt',encoding='utf-8') as stream:
            for line in stream:
                try:row=json.loads(line)
                except (ValueError,TypeError):continue
                if row.get('fen') in exclude or not row.get('legal_moves'):continue
                rows.append({'fen':row['fen'],'legal_moves':row['legal_moves']})
                if len(rows)>=limit:break
        if rows:break
    return rows


def _prepare(rows,device):
    data=[]
    for r in rows:
        ids=torch.tensor([encode_move(move) for move in r['legal_moves']],dtype=torch.long,device=device)
        x=torch.from_numpy(encode_fen(r['fen'])).unsqueeze(0).to(device)
        target=encode_move(r['best_move']) if 'best_move' in r else None
        data.append((x,ids,target))
    return data


def _measure(model,data):
    model.eval(); n=0;hits=0;total=0.0
    with torch.inference_mode():
        for x,ids,target in data:
            logits,_=model(x)
            allowed=logits[0,ids].float()
            idx=(ids==target).nonzero(as_tuple=True)[0]
            assert idx.numel()==1
            total+=float(F.cross_entropy(allowed[None,:],idx))
            hits+=int(ids[int(torch.argmax(allowed))].item()==target)
            n+=1
    return {'positions':n,'policy_top1':round(hits/max(1,n),4),'nll':round(total/max(1,n),5)}


def train_phantom(run:Path,engine:Path,*,source='auto',epochs=9,lr=1e-5,
                  device='auto',seed=20261124):
    run=Path(run).resolve();engine=Path(engine).resolve()
    if not engine.is_file():raise FileNotFoundError('C++ engine missing: '+str(engine))
    if not 1<=epochs<=40 or not 0<lr<=5e-4:raise ValueError('Training parameters out of range')
    destination=run/'checkpoints'/'phantom.pt'
    if destination.exists():raise FileExistsError('phantom.pt already exists: keeping it unchanged')
    origin=source_checkpoint(run,source)
    before_sha=file_hash(origin)
    payload=torch.load(origin,map_location='cpu',weights_only=True)
    if payload.get('feature_version')!=FEATURE_VERSION:raise ValueError('Incompatible checkpoint encoding')
    dev=('cuda' if torch.cuda.is_available() else 'cpu') if device=='auto' else device
    if dev=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA is not installed')
    torch.manual_seed(seed);random.seed(seed)
    torch.set_num_threads(min(6,torch.get_num_threads()))
    rows=white_examples(engine)
    if len(rows)<20:raise ValueError('Not enough distinct validated white positions')
    random.Random(seed).shuffle(rows)
    # Position holdout is correlated along the same four game lines: evaluation
    # reflects repertoire agreement, NOT generalization or playing strength.
    validation=rows[::5]
    training=[row for i,row in enumerate(rows) if i%5]
    train_data=_prepare(training,dev)
    valid_data=_prepare(validation,dev)
    anchors=_general_positions(run,{r['fen'] for r in rows})
    anchor_data=_prepare(anchors,dev)
    model=load_model(origin,dev)
    reference=load_model(origin,dev)
    for p in reference.parameters():p.requires_grad_(False)
    initial=_measure(model,valid_data)
    optimizer=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=1e-5)
    best_loss=initial['nll'];best_state=None;best_stats=initial
    history=[]
    for epoch in range(1,epochs+1):
        model.train()
        epoch_rows=list(train_data)
        random.Random(seed+epoch).shuffle(epoch_rows)
        avg_loss=0.0
        for i,(x,ids,target) in enumerate(epoch_rows):
            logits,_=model(x)
            candidate=logits[0,ids].float()
            index=(ids==target).nonzero(as_tuple=True)[0]
            imitation=F.cross_entropy(candidate[None,:],index)
            with torch.inference_mode():
                ref_logits,_=reference(x)
            # Conservative soft teacher regularization on legal moves.
            old=F.softmax(ref_logits[0,ids].float(),dim=0)
            distill=F.kl_div(F.log_softmax(candidate,dim=0),old,reduction='sum')
            loss=imitation+0.20*distill
            if anchor_data:
                ax,aids,_=anchor_data[i%len(anchor_data)]
                now,_=model(ax)
                with torch.inference_mode():base,_=reference(ax)
                q=F.softmax(base[0,aids].float(),dim=0)
                loss=loss+0.35*F.kl_div(F.log_softmax(now[0,aids].float(),dim=0),q,reduction='sum')
            optimizer.zero_grad(set_to_none=True)
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
            optimizer.step()
            avg_loss+=float(loss.detach().item())
        stats=_measure(model,valid_data)
        history.append({'epoch':epoch,'train_loss':round(avg_loss/len(epoch_rows),5),**stats})
        print(f'Phantom epoch {epoch}/{epochs}: holdout NLL {stats["nll"]:.4f} top1={stats["policy_top1"]:.1%}',flush=True)
        if stats['nll']<best_loss-0.00001:
            best_loss=stats['nll'];best_stats=stats
            best_state=copy.deepcopy({k:v.detach().cpu() for k,v in model.state_dict().items()})
    if file_hash(origin)!=before_sha:raise RuntimeError('Source checkpoint changed during training: refusing publication')
    report={'status':'rejected_no_holdout_improvement','source':origin.name,'source_sha256':before_sha,
            'created_at':datetime.now(timezone.utc).isoformat(),'training_positions':len(training),
            'validation_positions':len(validation),'anti_forgetting_positions':len(anchors),
            'initial':initial,'best':best_stats,'epochs':history,'target':'phantom.pt',
            'note':'Local PGN-derived correlated examples; holdout NLL is not an Elo/strength metric.',
            'ppo_checkpoint_and_optimizer_unchanged':True}
    if best_state is not None:
        final={'model':best_state,'config':payload['config'],'feature_version':FEATURE_VERSION,
               'iteration':int(payload.get('iteration',0)), 'optimizer':None,
               'candidate_only':True,'opening_specialization':'Phantom-X23','training':report}
        tmp=destination.with_suffix('.pending.pt')
        destination.parent.mkdir(parents=True,exist_ok=True)
        try:
            torch.save(final,tmp)
            load_model(tmp,'cpu')
            if destination.exists():raise FileExistsError(destination)
            os.replace(tmp,destination)
        finally:tmp.unlink(missing_ok=True)
        report['status']='candidate_created_not_strength_verified'
        report['checkpoint']=str(destination)
    folder=run/'agent_training';folder.mkdir(parents=True,exist_ok=True)
    out=folder/'phantom_report.json';tmp=out.with_suffix('.pending.json')
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,out)
    print(json.dumps({'status':report['status'],'checkpoint':report.get('checkpoint'),
                      'initial':initial,'best':best_stats},ensure_ascii=False),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description='Create independent Phantom-X23 candidate checkpoint')
    p.add_argument('--run',required=True,type=Path);p.add_argument('--engine',required=True,type=Path)
    p.add_argument('--source',default='auto',choices=['auto','aggressive.pt','skillboost_v2.pt','skillboost.pt','latest.pt','lasttest.pt','best.pt'])
    p.add_argument('--epochs',default=9,type=int);p.add_argument('--lr',default=1e-5,type=float)
    p.add_argument('--device',default='auto',choices=['auto','cpu','cuda'])
    a=p.parse_args()
    train_phantom(a.run,a.engine,source=a.source,epochs=a.epochs,lr=a.lr,device=a.device)

if __name__=='__main__':main()
