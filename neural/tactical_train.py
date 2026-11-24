"""Supervised tactical adapter: new checkpoint, never mutate the source."""
from __future__ import annotations
import argparse
from collections import defaultdict, Counter
import json
from pathlib import Path
import random
from .tactics import canonical
from .tactical_data import hash_file,output_dir
from .tactical_learning import atomic_json, experiment_lock, move_metrics, aggregate, hard_weight, selection_key
from .mastery import soft_targets,validate_scores,transform_row,curriculum_indices,eligible_candidate

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
        if not r['accepted'] or len(set(r['accepted']))!=len(r['accepted']) or len(set(r['legal']))!=len(r['legal']) or not set(r['accepted'])<=set(r['legal']):raise ValueError('Invalid targets')
        seen.add(k);sources.add(r['source']);rows[r['split']].append(r)
    if min(map(len,rows.values()))<2:raise ValueError('Insufficient independent validation examples')
    return rows

def train(source,dataset,out,engine,epochs,batch,lr,device,seed,patience=6,resume=False,replay=None):
    with experiment_lock(out):
        return train_locked(source,dataset,out,engine,epochs,batch,lr,device,seed,patience,resume,replay)

def train_locked(source,dataset,out,engine,epochs,batch,lr,device,seed,patience,resume,replay=None):
    import copy
    import math
    import numpy as np
    import torch
    from neural.checkpoint import load_model
    from neural.encoding import encode_fen,encode_move,FEATURE_VERSION,POLICY_SIZE
    from neural.selfplay import ChessBridge
    source_hash=hash_file(source);data_hash=hash_file(dataset);engine_hash=hash_file(engine)
    meta=json.loads(dataset.with_name('dataset_meta.json').read_text(encoding='utf-8'))
    if meta.get('schema') not in ('tactical_data_v1','tactical_data_v2','tactical_data_v3') or not meta.get('complete') or meta.get('dataset_sha256')!=data_hash or meta.get('engine_sha256')!=engine_hash:
        raise ValueError('Incomplete dataset or dataset/engine metadata mismatch')
    rows=load_rows(dataset)
    mastery=meta['schema']=='tactical_data_v3'
    replay_rows=[];replay_hash=None
    if replay is not None:
        if not mastery:raise ValueError('Replay requires v3 dataset')
        replay_hash=hash_file(replay)
        replay_meta=json.loads(replay.with_name('replay_meta.json').read_text(encoding='utf-8'))
        if replay_meta.get('sha256')!=replay_hash or replay_meta.get('dataset_sha256')!=data_hash or replay_meta.get('engine_sha256')!=engine_hash:
            raise ValueError('Replay metadata mismatch')
        replay_rows=[json.loads(l) for l in replay.read_text(encoding='utf-8').splitlines()]
        forbidden={canonical(r['fen']) for group in rows.values() for r in group}
        from benchmark.suite import load_suite
        for path in (Path(__file__).resolve().parents[1]/'benchmark').glob('suite_v*.json'):
            payload,_=load_suite(path);forbidden.update(canonical(r['fen']) for r in payload['cases'])
        for r in replay_rows:
            key=canonical(r['fen'])
            if key in forbidden:raise ValueError('Replay overlap or duplicate')
            forbidden.add(key)
    augmented=[]
    if mastery:
        for group in rows.values():
            for r in group:validate_scores(r)
        # One legal symmetry per original training example; alternate by epoch.
        augmented=[transform_row(r,flip=True,mirror=r['fen'].split()[2]=='-') for r in rows['train']]
    # Check source and data before each resume; never trust a partial training state.
    dev=torch.device('cuda' if device=='auto' and torch.cuda.is_available() else 'cpu' if device=='auto' else device)
    config={'schema':'tactical_train_v2','source_sha256':source_hash,'dataset_sha256':data_hash,
            'engine_sha256':engine_hash,'epochs':epochs,'batch':batch,'lr':lr,'seed':seed,
            'patience':patience,'device':str(dev)}
    if mastery:config.update(schema='tactical_train_v3',replay_sha256=replay_hash,objective='soft_policy_value_negative_curriculum_v1')
    print('[TRAIN] Validating legal moves...',flush=True)
    with ChessBridge(engine) as bridge:
        for group in [*rows.values(),augmented,replay_rows]:
            for i,r in enumerate(group):
                s=bridge.new(930010,r['fen'])
                if s['finished'] or set(s['legal_moves'])!=set(r['legal']):raise ValueError('Dataset legality mismatch')
                if (i+1)%500==0:print(f'[TRAIN] validated {i+1}/{len(group)}',flush=True)
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    torch.manual_seed(seed)
    model=load_model(source,dev)
    if hash_file(source)!=source_hash:raise RuntimeError('Source changed while loading')
    teacher=copy.deepcopy(model).eval()
    for p in teacher.parameters():p.requires_grad_(False)
    opt=torch.optim.AdamW(model.parameters(),lr=lr)
    scheduler=torch.optim.lr_scheduler.ReduceLROnPlateau(opt,mode='max',factor=.5,patience=2,min_lr=lr*.05)
    # Encode positions once; only batch tensors are sent to the accelerator.
    data=dict(rows)
    if augmented:data['augmented']=augmented
    if replay_rows:data['replay']=replay_rows
    encoded={k:torch.from_numpy(np.stack([encode_fen(r['fen']) for r in group])) for k,group in data.items()}
    legal_ids={k:[[encode_move(m) for m in r['legal']] for r in group] for k,group in data.items()}
    target_ids={k:[[encode_move(m) for m in r.get('accepted',[])] for r in group] for k,group in data.items()}
    targets={k:[soft_targets(r) for r in group] for k,group in data.items() if k!='replay'} if mastery else {}
    def batch_data(split,indices):
        x=encoded[split][indices].to(dev)
        mask=torch.zeros((len(indices),POLICY_SIZE),dtype=torch.bool,device=dev)
        target=torch.zeros_like(mask,dtype=torch.float32)
        negative=torch.zeros_like(mask)
        values=torch.zeros(len(indices),device=dev)
        for j,i in enumerate(indices):
            mask[j,legal_ids[split][i]]=True
            if split=='replay':continue
            if mastery:
                policy,bad,v=targets[split][i]
                target[j,legal_ids[split][i]]=torch.tensor([policy[m] for m in data[split][i]['legal']],device=dev)
                negative[j,[encode_move(m) for m in bad]]=True
                values[j]=v
            else:
                ids=target_ids[split][i];target[j,ids]=1/len(ids)
        return x,mask,target,negative,values
    def evaluate(split,network=model):
        network.eval();groups=defaultdict(list);individual=[]
        with torch.inference_mode():
            for start in range(0,len(rows[split]),batch):
                idx=list(range(start,min(start+batch,len(rows[split]))))
                x,mask,_,negative,values=batch_data(split,idx)
                logits,pred=network(x)
                if not torch.isfinite(logits).all() or not torch.isfinite(pred).all():raise RuntimeError('Nonfinite network output')
                probs=logits.masked_fill(~mask,-1e9).softmax(1)
                neg_mass=(probs*negative).sum(1).cpu().tolist()
                errors=(pred-values).square().cpu().tolist()
                probs=probs.cpu()
                for j,i in enumerate(idx):
                    r=rows[split][i]
                    ordered=sorted(zip(r['legal'],probs[j,legal_ids[split][i]].tolist()),key=lambda v:-v[1])
                    m=move_metrics(ordered,r['accepted'])
                    if mastery:
                        from .mastery import gap_cp
                        m.update(value_mse=errors[j],negative_mass=neg_mass[j],
                                 teacher_regret_cp=gap_cp(r['teacher_cp'],r['move_scores'][ordered[0][0]]))
                    individual.append(m)
                    groups['all'].append(m);groups[r['category']].append(m)
        return {k:aggregate(v) for k,v in groups.items()},individual
    recovery=out/'training_state.pt';candidate=out/'candidate.pt'
    def save_state(obj):
        tmp=recovery.with_suffix('.tmp');torch.save(obj,tmp);tmp.replace(recovery)
    if recovery.exists():
        if not resume:raise ValueError('Training state exists; use --resume')
        saved=torch.load(recovery,map_location='cpu',weights_only=True)
        if saved['config']!=config:raise ValueError('Resume training configuration or input hash changed')
        model.load_state_dict(saved['model']);opt.load_state_dict(saved['optimizer']);scheduler.load_state_dict(saved['scheduler'])
        torch.set_rng_state(saved['torch_rng'])
        if dev.type=='cuda':torch.cuda.set_rng_state(saved['cuda_rng'],dev)
        baseline=saved['baseline'];history=saved['history'];best=saved['best'];best_epoch=saved['best_epoch']
        best_model=saved['best_model'];stale=saved['stale'];steps=saved['steps'];start_epoch=saved['epoch']+1
        eligible_best=saved.get('eligible_best')
        print(f'[TRAIN] Resume epoch {start_epoch}; steps {steps}',flush=True)
    else:
        if candidate.exists():raise ValueError('Candidate exists without recovery state')
        baseline,_=evaluate('validation');best=baseline['all'];best_epoch=0;best_model=None
        history=[];stale=0;steps=0;start_epoch=1;eligible_best=None
    def report(status):
        return {'schema':'tactical_train_v2','status':status,'source':str(source),**config,
                'baseline':baseline,'epochs':history,'selected_epoch':best_epoch,
                'candidate':str(candidate) if status=='complete' and best_epoch and candidate.exists() else None,
                'validation_accuracy':eligible_best['top1'] if mastery and eligible_best else baseline['all']['top1'] if mastery else best['top1'],
                'best_observed_validation':best,'selected_validation':eligible_best if mastery else best,
                'retention_replay_rows':len(replay_rows),'optimizer_steps':steps,
                'warning':'Validation selection, not independent holdout; no automatic promotion or PPO resume.'}
    counts=Counter(r['category'] for r in rows['train'])
    mean_size=len(rows['train'])/len(counts)
    if stale>=patience:start_epoch=epochs+1
    for epoch in range(start_epoch,epochs+1):
        # Mine errors ONLY on training examples; all rows remain in each epoch.
        train_before,individual=evaluate('train')
        weights=[hard_weight(m,counts[r['category']],mean_size) for r,m in zip(rows['train'],individual)]
        model.train()
        for layer in model.modules():
            if isinstance(layer,torch.nn.BatchNorm2d):layer.eval()
        indices=curriculum_indices(rows['train'],epoch) if mastery else list(range(len(weights)))
        rng=random.Random(seed*1000003+epoch);rng.shuffle(indices)
        split='augmented' if mastery and epoch%2==0 else 'train'
        losses=[];grad_norms=[]
        for start in range(0,len(indices),batch):
            part=indices[start:start+batch]
            x,mask,target,negative,values=batch_data(split,part)
            logits,value=model(x)
            with torch.no_grad():
                prior,old_value=teacher(x)
                prior=prior.masked_fill(~mask,-1e9).softmax(1)
            logp=logits.masked_fill(~mask,-1e9).log_softmax(1)
            # Multi-target policy CE and original model regularizers.
            per=-(target*logp).sum(1)-.10*(prior*logp).sum(1)+.25*(value-old_value).square()
            if mastery:
                per=per+.35*(value-values).square()+.20*(logp.exp()*negative).sum(1)
            w=torch.tensor([weights[i] for i in part],device=dev)
            loss=(per*w).sum()/w.sum()
            if replay_rows:
                ri=rng.sample(range(len(replay_rows)),min(len(replay_rows),max(1,len(part)//4)))
                rx,rm,_,_,_=batch_data('replay',ri)
                rp,rv=model(rx)
                with torch.no_grad():
                    op,ov=teacher(rx);op=op.masked_fill(~rm,-1e9).softmax(1)
                replay_loss=-(op*rp.masked_fill(~rm,-1e9).log_softmax(1)).sum(1).mean()+.25*(rv-ov).square().mean()
                loss=loss+.20*replay_loss
            if not torch.isfinite(loss):raise RuntimeError('Nonfinite training loss')
            opt.zero_grad(set_to_none=True);loss.backward()
            norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.0,error_if_nonfinite=True)
            opt.step();steps+=1;losses.append(float(loss.detach().item()));grad_norms.append(float(norm.item()))
            if (start//batch+1)%25==0:print(f'[TRAIN] epoch {epoch} batch {start//batch+1}/{math.ceil(len(indices)/batch)} steps {steps}',flush=True)
        metrics,_=evaluate('validation')
        train_after,_=evaluate('train')
        current=metrics['all']
        # Smooth metrics govern scheduling; candidate requires strictly better top-1.
        lr_used=opt.param_groups[0]['lr']
        scheduler.step(current['mrr'])
        if selection_key(current)>selection_key(best):
            best=current;stale=0
            if not mastery and current['top1']>baseline['all']['top1']:
                best_epoch=epoch;best_model={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
        else:stale+=1
        if mastery and eligible_candidate(current,baseline['all']) and (eligible_best is None or selection_key(current)>selection_key(eligible_best)):
            eligible_best=current;best_epoch=epoch;best_model={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
        if mastery and epoch<5:stale=0
        history.append({'epoch':epoch,'loss':sum(losses)/len(losses),'validation':metrics,
                        'train_before':train_before,'train_after':train_after,'lr':lr_used,'next_lr':opt.param_groups[0]['lr'],
                        'steps':steps,'curriculum_examples':len(indices),'augmented_epoch':split=='augmented','mean_grad_norm':sum(grad_norms)/len(grad_norms)})
        save_state({'config':config,'epoch':epoch,'model':model.state_dict(),'optimizer':opt.state_dict(),
                    'scheduler':scheduler.state_dict(),'baseline':baseline,'history':history,'best':best,
                    'best_epoch':best_epoch,'best_model':best_model,'eligible_best':eligible_best,'stale':stale,'steps':steps,
                    'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state(dev) if dev.type=='cuda' else None})
        atomic_json(out/'training_report.json',report('running'))
        print(f'[TRAIN] {epoch}/{epochs} | top1 {current["top1"]:.3f} | top3 {current["top3"]:.3f} | MRR {current["mrr"]:.3f} | mass {current["target_mass"]:.3f} | lr {lr_used:g}',flush=True)
        if stale>=patience:
            print('[TRAIN] Early stopping',flush=True);break
    if hash_file(source)!=source_hash or hash_file(dataset)!=data_hash or hash_file(engine)!=engine_hash or (replay is not None and hash_file(replay)!=replay_hash):
        raise RuntimeError('Source, engine, dataset or replay changed during experiment')
    if best_epoch:
        tmp=candidate.with_suffix('.tmp')
        torch.save({'feature_version':FEATURE_VERSION,'config':model.config,'model':best_model,
                    'candidate_only':True,'optimizer':None,
                    'tactical_adapter':{'source_sha256':source_hash,'dataset_sha256':data_hash,'epoch':best_epoch}},tmp)
        tmp.replace(candidate)
    atomic_json(out/'training_report.json',report('complete'))
    print('Candidate saved for independent testing' if best_epoch else 'No eligible candidate; source retained',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=30);p.add_argument('--batch',type=int,default=64)
    p.add_argument('--lr',type=float,default=1e-4);p.add_argument('--seed',type=int,default=9312026)
    p.add_argument('--patience',type=int,default=6);p.add_argument('--resume',action='store_true');p.add_argument('--replay',type=Path)
    p.add_argument('--device',choices=('auto','cpu','cuda'),default='auto');a=p.parse_args()
    if not all(p.is_file() for p in (a.source,a.dataset,a.engine)) or not 1<=a.epochs<=100 or not 1<=a.batch<=256 or not 0<a.lr<=.001 or not 1<=a.patience<=100:p.error('Invalid experiment configuration')
    train(a.source,a.dataset,output_dir(a.output,a.resume),a.engine,a.epochs,a.batch,a.lr,a.device,a.seed,a.patience,a.resume,a.replay)

if __name__=='__main__':main()
