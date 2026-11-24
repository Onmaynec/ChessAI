"""Supervised tactical adapter: new checkpoint, never mutate the source."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
from .tactics import canonical
from .tactical_data import hash_file,output_dir

def load_rows(path):
    from benchmark.suite import load_suite
    forbidden=set()
    for suite in (Path(__file__).resolve().parents[1]/'benchmark').glob('suite_v*.json'):
        payload,_=load_suite(suite);forbidden.update(canonical(c['fen']) for c in payload['cases'])
    if not forbidden:raise ValueError('Benchmark exclusion set missing')
    rows={'train':[],'validation':[]};seen=set(forbidden);sources=set()
    for line in path.read_text(encoding='utf-8').splitlines():
        r=json.loads(line);k=canonical(r['fen'])
        if k in seen or r['source'] in sources:raise ValueError('Duplicate or benchmark overlap')
        if not r['accepted'] or not set(r['accepted'])<=set(r['legal']):raise ValueError('Invalid targets')
        seen.add(k);sources.add(r['source']);rows[r['split']].append(r)
    if min(map(len,rows.values()))<2:raise ValueError('Insufficient independent validation examples')
    return rows

def train(source,dataset,out,engine,epochs,batch,lr,device,seed):
    import copy
    import numpy as np
    import torch
    from neural.checkpoint import load_model
    from neural.encoding import encode_fen,encode_move,FEATURE_VERSION,POLICY_SIZE
    from neural.selfplay import ChessBridge
    from neural.agent import rank
    rows=load_rows(dataset);source_hash=hash_file(source);data_hash=hash_file(dataset)
    # Verify all legal move lists with the core, not just the JSON labels.
    with ChessBridge(engine) as bridge:
        for group in rows.values():
            for r in group:
                s=bridge.new(930010,r['fen'])
                if s['finished'] or set(s['legal_moves'])!=set(r['legal']):raise ValueError('Dataset legality mismatch')
    torch.manual_seed(seed);rng=random.Random(seed)
    dev=torch.device('cuda' if device=='auto' and torch.cuda.is_available() else 'cpu' if device=='auto' else device)
    model=load_model(source,dev);teacher=copy.deepcopy(model).eval()
    for p in teacher.parameters():p.requires_grad_(False)
    opt=torch.optim.AdamW(model.parameters(),lr=lr)
    def evaluate():
        model.eval();groups=defaultdict(lambda:[0,0])
        with torch.inference_mode():
            for r in rows['validation']:
                ordered,_=rank(model,r['fen'],r['legal'])
                hit=int(ordered[0][0] in r['accepted'])
                for k in ('all',r['category']):
                    groups[k][0]+=hit;groups[k][1]+=1
        return {k:{'correct':v[0],'total':v[1],'accuracy':v[0]/v[1]} for k,v in groups.items()}
    baseline=evaluate();best=baseline['all']['accuracy'];best_epoch=0
    history=[];candidate=out/'candidate.pt'
    for epoch in range(1,epochs+1):
        model.train()
        # Freeze BN running statistics on small specialised datasets.
        for layer in model.modules():
            if isinstance(layer,torch.nn.BatchNorm2d):layer.eval()
        items=list(rows['train']);rng.shuffle(items);losses=[]
        for start in range(0,len(items),batch):
            part=items[start:start+batch]
            x=torch.from_numpy(np.stack([encode_fen(r['fen']) for r in part])).to(dev)
            mask=torch.zeros((len(part),POLICY_SIZE),dtype=torch.bool,device=dev)
            target=torch.zeros((len(part),POLICY_SIZE),device=dev)
            for j,r in enumerate(part):
                legal=[encode_move(m) for m in r['legal']]
                ids=[encode_move(m) for m in r['accepted']]
                mask[j,legal]=True;target[j,ids]=1/len(ids)
            logits,value=model(x)
            with torch.no_grad():
                prior,old_value=teacher(x)
                prior=prior.masked_fill(~mask,-1e9).softmax(1)
            logp=logits.masked_fill(~mask,-1e9).log_softmax(1)
            loss=-(target*logp).sum(1).mean()-.15*(prior*logp).sum(1).mean()+.25*(value-old_value).square().mean()
            if not torch.isfinite(loss):raise RuntimeError('Nonfinite training loss')
            opt.zero_grad(set_to_none=True);loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
            losses.append(float(loss.detach().item()))
        metrics=evaluate()
        history.append({'epoch':epoch,'loss':sum(losses)/len(losses),'validation':metrics})
        print(f'[TRAIN] epoch {epoch}/{epochs}: {metrics["all"]}',flush=True)
        if metrics['all']['accuracy']>best:
            best=metrics['all']['accuracy'];best_epoch=epoch
            temp=candidate.with_suffix('.tmp')
            torch.save({'feature_version':FEATURE_VERSION,'config':model.config,
                        'model':{k:v.detach().cpu() for k,v in model.state_dict().items()},
                        'tactical_adapter':{'source_sha256':source_hash,'dataset_sha256':data_hash,'epoch':epoch}},temp)
            temp.replace(candidate)
    if hash_file(source)!=source_hash or hash_file(dataset)!=data_hash:
        candidate.unlink(missing_ok=True);raise RuntimeError('Source or dataset changed during experiment')
    report={'schema':'tactical_train_v1','source':str(source),'source_sha256':source_hash,'dataset_sha256':data_hash,
            'engine_sha256':hash_file(engine),'baseline':baseline,'epochs':history,'selected_epoch':best_epoch,
            'candidate':str(candidate) if best_epoch else None,'validation_accuracy':best,
            'warning':'Selection uses generated validation, not independent Elo/holdout; no automatic promotion or PPO resume.'}
    (out/'training_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Candidate saved for independent testing' if best_epoch else 'No improvement; original retained',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=8);p.add_argument('--batch',type=int,default=32)
    p.add_argument('--lr',type=float,default=3e-5);p.add_argument('--seed',type=int,default=9302026)
    p.add_argument('--device',choices=('auto','cpu','cuda'),default='auto');a=p.parse_args()
    if not all(p.is_file() for p in (a.source,a.dataset,a.engine)) or not 1<=a.epochs<=100 or not 1<=a.batch<=256 or not 0<a.lr<=.001:p.error('Invalid experiment configuration')
    train(a.source,a.dataset,output_dir(a.output),a.engine,a.epochs,a.batch,a.lr,a.device,a.seed)

if __name__=='__main__':main()
