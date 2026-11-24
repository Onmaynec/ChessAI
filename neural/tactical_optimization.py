"""Opt-in optimization experiment; never touches PPO state."""
from __future__ import annotations
import math

CAPACITY={'same':None,'light':(64,6),'standard':(96,10),'advanced':(128,15)}

def settings(min_epochs=20,replay_weight=.10,capacity='same',negative_weight=.40,value_weight=.25):
    if type(min_epochs) is not int or not 1<=min_epochs<=60 or capacity not in CAPACITY:
        raise ValueError('Invalid optimization budget or capacity')
    if not all(math.isfinite(x) and 0<=x<=1 for x in (replay_weight,negative_weight,value_weight)):
        raise ValueError('Invalid loss weights')
    return {'min_epochs':min_epochs,'replay_weight':replay_weight,'capacity':capacity,
            'negative_weight':negative_weight,'value_weight':value_weight,'warmup_epochs':5,
            'temperature':90.,'soft_fraction':.45,'value_lr_ratio':.5,'gradient_sample_interval':25}

def optimizer_groups(model,lr,cfg):
    return [{'params':list(model.stem.parameters())+list(model.body.parameters()),'lr':lr,'name':'backbone'},
            {'params':model.policy.parameters(),'lr':lr,'name':'policy'},
            {'params':model.value.parameters(),'lr':lr*cfg['value_lr_ratio'],'name':'value'}]

def components(logp,target,accepted,negative,value,values,prior,old_value,weights,cfg,scale=1.):
    import torch
    # Accepted mass is a marginal likelihood; no arbitrary preference among accepted answers.
    def mean(x):return (x*weights).sum()/weights.sum()
    mass=(logp.exp()*accepted).sum(1)
    bad=(logp.exp()*negative).sum(1)
    terms={'policy_ce':mean(-(target*logp).sum(1)),
           'accepted_nll':mean(-mass.clamp_min(1e-8).log()),
           'negative_nll':mean(-(1-bad).clamp_min(1e-6).log()),
           'policy_retention':mean(-(prior*logp).sum(1)),
           'value_teacher':mean((value-values).square()),
           'value_retention':mean((value-old_value).square())}
    policy=terms['policy_ce']+.35*terms['accepted_nll']+cfg['negative_weight']*terms['negative_nll']+.10*terms['policy_retention']
    val=scale*cfg['value_weight']*terms['value_teacher']+.15*terms['value_retention']
    return policy,val,terms

def gradient_diagnostics(policy,value,model):
    import torch
    shared=list(model.stem.parameters())+list(model.body.parameters())
    pg=torch.autograd.grad(policy,shared,retain_graph=True,allow_unused=True)
    vg=torch.autograd.grad(value,shared,retain_graph=True,allow_unused=True)
    def norm(gs):return sum(float(g.detach().square().sum()) for g in gs if g is not None)**.5
    p,v=norm(pg),norm(vg)
    dot=sum(float((a.detach()*b.detach()).sum()) for a,b in zip(pg,vg) if a is not None and b is not None)
    return {'policy_backbone_norm':p,'value_backbone_norm':v,'cosine':max(-1.,min(1.,dot/(p*v))) if p*v>0 else 0.}

def schedule_allowed(epoch,cfg):
    return epoch>cfg['warmup_epochs']

def stop_allowed(epoch,cfg):
    return epoch>=cfg['min_epochs']

def selection(metric):
    return (metric['top1'],metric['mrr'],-metric['negative_mass'],-metric['target_nll'])

def candidate_ok(metric,base):
    from .mastery import eligible_candidate
    return eligible_candidate(metric,base) and metric['negative_mass']<=base['negative_mass']+.005 and metric['teacher_regret_cp']<=base['teacher_regret_cp']+1e-9
