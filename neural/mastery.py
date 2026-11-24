"""Tactical Mastery targets and augmentation; pure helpers, no model mutation."""
from __future__ import annotations
import math
from collections import Counter
from .tactics import board, square, name, attacks, color

QUOTA_WEIGHTS={'mate1':15,'mate2_plus':15,'fork':15,'pin':5,'pin_capture':5,
               'discovered_attack':5,'mate_sacrifice':5,'capture':15,'check_evasion':15,'promotion':5}
EASY={'mate1','capture','check_evasion','promotion'}

def quotas(count):
    raw={k:count*v/100 for k,v in QUOTA_WEIGHTS.items()}
    result={k:int(v) for k,v in raw.items()}
    for k in sorted(raw,key=lambda k:(-(raw[k]-result[k]),k))[:count-sum(result.values())]:
        result[k]+=1
    return result

def deficits(counts,target):
    return {k:max(0,v-counts.get(k,0)) for k,v in target.items()}

def gap_cp(best,score):
    """Finite policy gap, preserving mate distance order and ordinary cp scale."""
    if best>=29000:
        return min(2000,80*(best-score)) if score>=29000 else 2000
    if best<=-29000:
        return min(2000,80*max(0,best-score))
    if score<=-29000:return 2000
    return min(2000,max(0,best-score))

def validate_scores(row):
    scores=row['move_scores']
    if set(scores)!=set(row['legal']) or not scores or any(type(v) is not int or abs(v)>30000 for v in scores.values()):
        raise ValueError('Teacher scores must cover every legal move')
    if max(scores.values())!=row['teacher_cp'] or not set(row['accepted'])<=set(scores):
        raise ValueError('Teacher best score or accepted move mismatch')
    if not any(scores[m]==row['teacher_cp'] for m in row['accepted']):
        raise ValueError('Best move missing from targets')

def soft_targets(row,temperature=120.,soft_fraction=.65):
    validate_scores(row)
    if not math.isfinite(temperature) or temperature<=0 or not 0<=soft_fraction<=1:
        raise ValueError('Invalid target temperature/mix')
    scores=row['move_scores'];best=max(scores.values())
    gaps={m:gap_cp(best,v) for m,v in scores.items()}
    exp={m:math.exp(-v/temperature) for m,v in gaps.items()};total=sum(exp.values())
    accepted=set(row['accepted'])
    policy={m:soft_fraction*exp[m]/total+(1-soft_fraction)*(m in accepted)/len(accepted) for m in scores}
    negative=[m for m,v in gaps.items() if v>=250 and m not in accepted]
    return policy,negative,math.tanh(best/600.)

def fen_from_board(b,turn='w',rights='-',ep='-',half='0',full='1'):
    ranks=[]
    for r in range(7,-1,-1):
        row='';empty=0
        for p in b[r*8:r*8+8]:
            if p=='.':empty+=1
            else:
                if empty:row+=str(empty);empty=0
                row+=p
        if empty:row+=str(empty)
        ranks.append(row)
    return '/'.join(ranks)+' '+turn+' '+rights+' '+ep+' '+half+' '+full

def transform_row(row,flip=True,mirror=False):
    """Rank+color reflection always; file reflection only without castling rights."""
    _,turn,rights,ep,half,full=row['fen'].split()
    if mirror and rights!='-':raise ValueError('Cannot mirror castling rights')
    def transform(s):return (7-s//8 if flip else s//8)*8+(7-s%8 if mirror else s%8)
    def move(m):return name(transform(square(m[:2])))+name(transform(square(m[2:4])))+m[4:]
    b=['.']*64
    for i,p in enumerate(board(row['fen'])):b[transform(i)]=p.swapcase() if flip else p
    if flip:
        turn='b' if turn=='w' else 'w'
        rights=''.join(c for c in 'KQkq' if c in rights.swapcase()) or '-'
    out=dict(row,fen=fen_from_board(b,turn,rights,name(transform(square(ep))) if ep!='-' else '-',half,full),
             legal=[move(m) for m in row['legal']],accepted=[move(m) for m in row['accepted']])
    if 'move_scores' in row:out['move_scores']={move(m):v for m,v in row['move_scores'].items()}
    if 'evidence' in row:out['evidence']=[dict(t,squares=[name(transform(square(s))) for s in t['squares']]) for t in row['evidence']]
    return out

def curriculum_indices(rows,epoch):
    """Easy examples first; all train examples by epoch 5."""
    if epoch>=5:return list(range(len(rows)))
    easy=[i for i,r in enumerate(rows) if r['category'] in EASY]
    hard=[i for i,r in enumerate(rows) if r['category'] not in EASY]
    hard.sort(key=lambda i:(len(rows[i]['legal']),rows[i]['source']))
    n=math.ceil(len(hard)*epoch/5)
    return easy+hard[:n] or list(range(len(rows)))

def eligible_candidate(current,baseline):
    return (current['top1']>baseline['top1'] and current['mrr']>=baseline['mrr']
            and current['top3']>=baseline['top3']-.02-1e-9
            and current['value_mse']<=baseline['value_mse']+.02+1e-9
            and current['target_nll']<=baseline['target_nll']+1e-9)

def motif_proposal(rng,category):
    """Geometry-biased proposals; only teacher/bridge can accept them."""
    from .tactics import KNIGHTS, DIRS
    def step(s,dx,dy,n=1):
        f=s%8+dx*n;r=s//8+dy*n
        return r*8+f if 0<=f<8 and 0<=r<8 else None
    b=['.']*64
    if category=='fork':
        dest=rng.randrange(64)
        neighbors=[t for dx,dy in KNIGHTS if (t:=step(dest,dx,dy)) is not None]
        if len(neighbors)<3:return None
        src,bk,victim=rng.sample(neighbors,3)
        b[src]='N';b[bk]='k';b[victim]=rng.choice('rq')
        if rng.random()<.5:
            free=[i for i,p in enumerate(b) if p=='.' and i!=dest]
            b[rng.choice(free)]=rng.choice('BRbn')
    elif category in ('pin','pin_capture','discovered_attack'):
        anchor=rng.randrange(64);dx,dy=rng.choice(DIRS)
        ray=[t for n in range(1,8) if (t:=step(anchor,dx,dy,n)) is not None]
        if len(ray)<3:return None
        i,j=sorted(rng.sample(range(len(ray)),2))
        between,target=ray[i],ray[j]
        slider='B' if dx and dy else 'R'
        if category=='discovered_attack':
            b[anchor]=slider;b[between]=rng.choice('NB');b[target]=rng.choice('rq')
            free=[k for k,p in enumerate(b) if p=='.' and k not in ray[:j+1]]
            if not free:return None
            bk=rng.choice(free);b[bk]='k'
        else:
            b[between]=rng.choice('rq');b[target]='k';bk=target
            if category=='pin_capture':
                b[anchor]=slider
            else:
                # Move the slider from an off-ray square into the pin.
                srcs=[k for k in range(64) if b[k]=='.' and k!=anchor and k not in ray]
                rng.shuffle(srcs)
                for src in srcs:
                    b[src]=slider
                    if anchor in attacks(b,src):break
                    b[src]='.'
                else:return None
    elif category=='mate_sacrifice':
        bk=62;b[bk]='k'
        for s in (53,54,55):b[s]='p'
        qfile=rng.randint(1,4);rfile=rng.randrange(qfile)
        qr=rng.randint(1,5);rr=rng.randrange(qr)
        b[qr*8+qfile]='Q';b[rr*8+qfile]='R';b[56+rfile]='r'
        if rng.random()<.5:
            free=[i for i,p in enumerate(b) if p=='.' and i%8!=qfile and i//8!=7]
            b[rng.choice(free)]=rng.choice('BNbn')
    else:return None
    free=[i for i,p in enumerate(b) if p=='.' and max(abs(i%8-bk%8),abs(i//8-bk//8))>1]
    if not free:return None
    wk=rng.choice(free);b[wk]='K'
    if any(p!='.' and p.isupper() and bk in attacks(b,i) for i,p in enumerate(b)):return None
    row={'fen':fen_from_board(b),'legal':[],'accepted':[]}
    return transform_row(row,flip=bool(rng.randrange(2)),mirror=bool(rng.randrange(2)))['fen']

def targeted_fen(rng,category):
    """Biased synthetic proposals, not pre-labelled chess puzzles."""
    if category in ('fork','pin','pin_capture','discovered_attack','mate_sacrifice') and rng.random()<.65:
        proposal=motif_proposal(rng,category)
        if proposal:return proposal
    b=['.']*64
    wk,bk=rng.sample(range(64),2)
    if max(abs(wk%8-bk%8),abs(wk//8-bk//8))<=1:return None
    b[wk]='K';b[bk]='k'
    def place(piece,allowed=None):
        free=[i for i,p in enumerate(b) if p=='.' and (allowed is None or i in allowed)]
        if not free:return False
        b[rng.choice(free)]=piece
        return True
    if category=='promotion':
        if not place('P',range(40,56)):return None
        if rng.random()<.4:place(rng.choice('nr'))
    elif category in ('mate1','mate2_plus'):
        place(rng.choice('QQR'))
        if rng.random()<.35:place(rng.choice('RB'))
    elif category=='fork':
        for p in ('N',rng.choice('rq'),rng.choice('rbq')):place(p)
        if rng.random()<.5:place(rng.choice('BRP'),range(8,56))
    elif category in ('pin','pin_capture','discovered_attack'):
        for p in (rng.choice('BRQ'),rng.choice('NB'),rng.choice('rq'),rng.choice('nb')):place(p)
    elif category=='mate_sacrifice':
        for p in ('Q','R',rng.choice('rbn')):place(p)
        if rng.random()<.5:place('B')
    else:
        for p in (rng.choice('NBRQ'),rng.choice('nbrq'),rng.choice('nbrq'),rng.choice('NBRQ')):place(p)
    # Opponent may not already be checked before the side-to-move acts.
    if any(p!='.' and p.isupper() and bk in attacks(b,i) for i,p in enumerate(b)):return None
    row={'fen':fen_from_board(b),'legal':[],'accepted':[]}
    return transform_row(row)['fen'] if rng.randrange(2) else row['fen']
