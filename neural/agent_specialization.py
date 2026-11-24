"""Style-specific checkpoint distillation from Latest + SkillBoost I + II.

Does not average unrelated weights, change PPO state or ingest online games.
Holdout loss is a *teacher agreement* metric, NOT proof of chess strength.
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

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from .agent_profiles import get_profile, resolve_source_checkpoints
from .checkpoint import load_model
from .encoding import FEATURE_VERSION, POLICY_SIZE, encode_fen, encode_move
from .skill_boost_v2 import CATEGORIES, opening_positions, TACTICAL_SEEDS, teacher_scores, split_rows
from .selfplay import ChessBridge


def checksum(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_rows(run: Path, engine: Path, max_rows: int, depth: int, seed: int) -> tuple[list[dict],str]:
    """Reuse local skillboost II teacher dataset, or create a small local set."""
    candidates=[run/'skillboost_v2'/'teacher_dataset.jsonl.gz',run/'skillboost_teacher.jsonl']
    rows=[]; origin=''
    for path in candidates:
        if path.is_file():
            opener=gzip.open if path.suffix=='.gz' else open
            with opener(path,'rt',encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        row=json.loads(line)
                        if row.get('best_move') in row.get('legal_moves',[]):
                            rows.append(row)
            if rows:
                origin=str(path)
                break
    # Make category coverage explicit even with small/missing v2 dataset.
    groups={row.get('category') for row in rows}
    if len(rows)<40 or any(c not in groups for c in ('attack','defense','opening')):
        seed_rows=opening_positions(engine,max_counter=70,seed=seed)
        with ChessBridge(engine) as bridge:
            for name, fen in TACTICAL_SEEDS:
                state=bridge.new(890,fen)
                if state.get('finished'):continue
                category=('attack' if any(k in name for k in ('mate','queen','fork','pin','tactics','counterattack'))
                          else 'defense' if any(k in name for k in ('check','defens','block')) else 'endgame')
                seed_rows.append({'fen':state['fen'],'legal_moves':state['legal_moves'],
                                  'category':category,'book_move':None,'split_group':'seed:'+name})
        seen={r['fen'] for r in rows}
        new=[r for r in seed_rows if r['fen'] not in seen]
        rows.extend(teacher_scores(engine,new,depth=depth))
        origin=(origin+' + local engine positions').strip()
    rng=random.Random(seed)
    # Keep a stable and reproducible subset; avoid large memory consumption.
    rng.shuffle(rows)
    by_fen={}
    for row in rows:
        if row.get('best_move') in row.get('legal_moves',[]) and row['fen'] not in by_fen:
            row=dict(row)
            row['category']=row.get('category') if row.get('category') in CATEGORIES else 'general'
            by_fen[row['fen']]=row
        if len(by_fen)>=max_rows:break
    selected=list(by_fen.values())
    if len(selected)<24:raise ValueError('Need >=24 valid teacher positions; train SkillBoost II or check C++ engine')
    return selected,origin


def validate_sources(paths:dict[str,Path]):
    cfg=None
    for name,path in paths.items():
        payload=torch.load(path,map_location='cpu',weights_only=True)
        if payload.get('feature_version')!=FEATURE_VERSION:raise ValueError(f'Incompatible encoding: {name}')
        if cfg is None:cfg=payload['config']
        if payload['config']!=cfg:raise ValueError('Different model architectures: distillation requires shared policy/action encoding')
    return cfg


class DistillDataset(Dataset):
    def __init__(self,rows,soft_targets):
        self.rows=rows;self.soft_targets=soft_targets
    def __len__(self):return len(self.rows)
    def __getitem__(self,i):
        row=self.rows[i]
        x=torch.from_numpy(encode_fen(row['fen']))
        ids=[encode_move(m) for m in row['legal_moves']]
        # The teacher target is sparse: keep only legal move probabilities.
        mask=torch.zeros(POLICY_SIZE,dtype=torch.bool);mask[ids]=True
        probs=torch.zeros(POLICY_SIZE,dtype=torch.float32)
        probs[ids]=self.soft_targets[i]
        return x,mask,probs,torch.tensor(encode_move(row['best_move']),dtype=torch.long)


def ensemble_targets(rows,paths,*,device='cpu'):
    # All three existing networks contribute explicitly. Do not average weights.
    weights={'latest':0.20,'skillboost':0.30,'skillboost_v2':0.50}
    results=[torch.zeros(len(r['legal_moves']),dtype=torch.float32) for r in rows]
    from .encoding import encode_fen
    for name,source in paths.items():
        model=load_model(source,device)
        with torch.inference_mode():
            for i,row in enumerate(rows):
                x=torch.from_numpy(encode_fen(row['fen'])).unsqueeze(0).to(device)
                logits,_=model(x)
                indices=[encode_move(m) for m in row['legal_moves']]
                results[i]+=weights[name]*torch.softmax(logits[0,indices].float(),dim=0).cpu()
        del model
    # Safety anchor: a verified local C++ teacher move always keeps a share.
    for i,row in enumerate(rows):
        good=row['legal_moves'].index(row['best_move'])
        one=torch.zeros_like(results[i]);one[good]=1
        results[i]=(0.55*results[i]+0.45*one).clamp_min(1e-8)
        results[i]/=results[i].sum()
    return results


def evaluate(model, loader, device):
    model.eval();total=0.;correct=0;n=0;anchor=0
    with torch.inference_mode():
        for x,mask,soft,label in loader:
            x=x.to(device);mask=mask.to(device);soft=soft.to(device);label=label.to(device)
            logits,_=model(x)
            lp=torch.log_softmax(logits.float().masked_fill(~mask,-1e9),dim=1)
            loss=-(lp*soft).sum(1).mean()
            total+=float(loss.item())*x.shape[0]
            correct+=int((lp.argmax(1)==label).sum().item());n+=x.shape[0]
    return {'loss':total/max(1,n),'teacher_top1':correct/max(1,n),'rows':n}


def train_agent(*,run:Path,engine:Path,profile:str,base:str='auto',epochs:int=5,max_rows:int=950,
                teacher_depth:int=3,batch_size:int=64,lr:float=2e-5,device:str='auto',seed:int=20261124):
    run=run.resolve();engine=engine.resolve()
    settings=get_profile(profile)
    if not engine.is_file():raise FileNotFoundError('C++ engine missing: '+str(engine))
    if not 1<=epochs<=30 or not 24<=max_rows<=15000 or not 1<=teacher_depth<=4 or not 8<=batch_size<=512 or not 0<lr<=1e-3:
        raise ValueError('Training arguments out of safe range')
    output=run/'checkpoints'/settings.filename
    if output.exists():raise FileExistsError(f'{output} already exists; never overwrite agents silently')
    sources=resolve_source_checkpoints(run,base)
    config=validate_sources(sources)
    source_hashes={name:checksum(file) for name,file in sources.items()}
    device=('cuda' if torch.cuda.is_available() else 'cpu') if device=='auto' else device
    if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA unavailable')
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    torch.set_num_threads(min(6,torch.get_num_threads()))
    rows,origin=source_rows(run,engine,max_rows,teacher_depth,seed)
    # Stable holdout split by opening family/puzzle group where available.
    training, validation=split_rows(rows,seed)
    target_by_fen={r['fen']:t for r,t in zip(rows,ensemble_targets(rows,sources,device=device))}
    train_ds=DistillDataset(training,[target_by_fen[r['fen']] for r in training])
    val_ds=DistillDataset(validation,[target_by_fen[r['fen']] for r in validation])
    sample_weights=[settings.category_weights.get(r['category'],1.0) for r in training]
    sampler=WeightedRandomSampler(sample_weights,len(training),replacement=True)
    loader=DataLoader(train_ds,batch_size=batch_size,sampler=sampler,num_workers=0)
    valid_loader=DataLoader(val_ds,batch_size=batch_size,shuffle=False,num_workers=0)
    model=load_model(sources['skillboost_v2'],device)
    before=evaluate(model,valid_loader,device)
    best_loss=before['loss'];best_weights=None;best_report=None
    optim=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=1e-4)
    report_epochs=[]
    for epoch in range(1,epochs+1):
        model.train();loss_sum=0.; seen=0
        for x,mask,soft,hard in loader:
            x=x.to(device);mask=mask.to(device);soft=soft.to(device);hard=hard.to(device)
            logits,_=model(x)
            lp=torch.log_softmax(logits.float().masked_fill(~mask,-1e9),dim=1)
            # Teacher mixture + C++-anchored tactical hard label.
            loss=0.8*(-(lp*soft).sum(1).mean())+0.2*nn.functional.nll_loss(lp,hard)
            optim.zero_grad(set_to_none=True);loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),1.0);optim.step()
            loss_sum+=float(loss.item())*x.shape[0];seen+=x.shape[0]
        check=evaluate(model,valid_loader,device)
        report_epochs.append({'epoch':epoch,'train_loss':loss_sum/max(1,seen),'holdout':check})
        print(f'{profile} epoch {epoch}/{epochs}: train={loss_sum/max(1,seen):.4f}; holdout={check["loss"]:.4f}',flush=True)
        if check['loss']<best_loss-1e-5:
            best_loss=check['loss'];best_weights=copy.deepcopy({k:v.detach().cpu() for k,v in model.state_dict().items()});best_report=check
    result={'profile':profile,'sources':{k:{'file':p.name,'sha256':source_hashes[k]} for k,p in sources.items()},
            'initial':before,'best':best_report,'epochs':report_epochs,'dataset_source':origin,
            'positions':len(rows),'training_positions':len(training),'validation_positions':len(validation),
            'teacher_note':'Three checkpoint policies + locally validated C++ targets. NOT grandmaster data or verified Elo.',
            'source_checkpoints_unchanged':all(checksum(file)==source_hashes[name] for name,file in sources.items()),
            'created_at':datetime.now(timezone.utc).isoformat()}
    stage=run/'agent_training';stage.mkdir(parents=True,exist_ok=True)
    result['status']='rejected_no_holdout_improvement'
    if best_weights is not None and result['source_checkpoints_unchanged']:
        v2=torch.load(sources['skillboost_v2'],map_location='cpu',weights_only=True)
        payload={'model':best_weights,'config':config,'feature_version':FEATURE_VERSION,
                 'iteration':int(v2.get('iteration',0)),'optimizer':None,'candidate_only':True,
                 'agent_profile':profile,'agent_training':result}
        tmp=output.with_suffix('.pending.pt')
        try:
            torch.save(payload,tmp)
            load_model(tmp,'cpu')
            os.replace(tmp,output)
        finally:tmp.unlink(missing_ok=True)
        result['status']='candidate_saved_not_yet_strength_verified'
        result['checkpoint']=str(output)
    if not result['source_checkpoints_unchanged']:
        result['status']='rejected_source_changed_during_training'
    # Report is separate from PPO metrics, and does not overwrite old versions.
    report=stage/f'{profile}_report.json'
    pending=report.with_suffix('.pending')
    try:
        pending.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(pending,report)
    finally:pending.unlink(missing_ok=True)
    print(json.dumps({'status':result['status'],'checkpoint':result.get('checkpoint'),'holdout':result['best']},ensure_ascii=False),flush=True)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description='Train distinct aggressive/defender agents without changing PPO checkpoints')
    p.add_argument('--run',required=True,type=Path)
    p.add_argument('--engine',required=True,type=Path)
    p.add_argument('--profile',required=True,choices=('aggressive','defender'))
    p.add_argument('--base',default='auto')
    p.add_argument('--epochs',type=int,default=5);p.add_argument('--max-rows',type=int,default=950)
    p.add_argument('--teacher-depth',type=int,default=3);p.add_argument('--batch-size',type=int,default=64)
    p.add_argument('--lr',type=float,default=2e-5);p.add_argument('--device',default='auto',choices=('auto','cpu','cuda'))
    p.add_argument('--seed',type=int,default=20261124)
    args=p.parse_args(argv)
    train_agent(run=args.run,engine=args.engine,profile=args.profile,base=args.base,epochs=args.epochs,
                max_rows=args.max_rows,teacher_depth=args.teacher_depth,batch_size=args.batch_size,
                lr=args.lr,device=args.device,seed=args.seed)

if __name__=='__main__':main()
