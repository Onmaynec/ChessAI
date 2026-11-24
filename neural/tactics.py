"""Geometric tactical evidence; legality is supplied by the C++ bridge."""
from __future__ import annotations

VALUES={'p':100,'n':320,'b':335,'r':500,'q':900,'k':20000}
DIRS=((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))
KNIGHTS=((1,2),(2,1),(-1,2),(-2,1),(1,-2),(2,-1),(-1,-2),(-2,-1))

def board(fen):
    rows=fen.split()[0].split('/')
    return tuple(c for row in reversed(rows) for c in ''.join('.'*int(x) if x.isdigit() else x for x in row))

def square(s):return (int(s[1])-1)*8+ord(s[0])-97
def name(s):return chr(97+s%8)+str(1+s//8)
def color(p):return 'w' if p.isupper() else 'b'
def enemy(p,side):return p!='.' and color(p)!=side

def attacks(b,s):
    p=b[s]
    if p=='.':return set()
    k=p.lower();f=s%8;r=s//8;out=set()
    if k=='p':steps=((-1,1),(1,1)) if p.isupper() else ((-1,-1),(1,-1))
    elif k=='n':steps=KNIGHTS
    elif k=='k':steps=DIRS
    else:steps=DIRS[:4] if k=='r' else DIRS[4:] if k=='b' else DIRS
    for dx,dy in steps:
        x,y=f+dx,r+dy
        while 0<=x<8 and 0<=y<8:
            t=y*8+x;out.add(t)
            if k in 'pnk' or b[t]!='.':break
            x+=dx;y+=dy
    return out

def pins(b,side):
    """Absolute pins to king; returns (attacker, pinned, king) squares."""
    out=set()
    for s,p in enumerate(b):
        if p=='.' or color(p)!=side or p.lower() not in 'brq':continue
        dirs=DIRS[:4] if p.lower()=='r' else DIRS[4:] if p.lower()=='b' else DIRS
        for dx,dy in dirs:
            x,y=s%8+dx,s//8+dy;victim=None
            while 0<=x<8 and 0<=y<8:
                t=y*8+x;q=b[t]
                if q!='.':
                    if not enemy(q,side):break
                    if victim is None:
                        if q.lower()=='k':break
                        victim=t
                    else:
                        if q.lower()=='k':out.add((s,victim,t))
                        break
                x+=dx;y+=dy
    return out

def describe(before,move,after,score_cp=None):
    """Candidate geometry, not proof that the tactic wins material."""
    b,a=board(before),board(after);side=before.split()[1];src,dst=square(move[:2]),square(move[2:4])
    tags=[];targets=[s for s in attacks(a,dst) if enemy(a[s],side) and VALUES[a[s].lower()]>=320]
    if len(targets)>=2:
        tags.append({'kind':'fork','squares':[name(dst),*map(name,sorted(targets))]})
    if any(v==dst for _,v,_ in pins(b,'b' if side=='w' else 'w')):
        tags.append({'kind':'pinned_piece_move','squares':[name(src),name(dst)]})
    if any(v==dst for _,v,_ in pins(b,side)) and enemy(b[dst],side):
        tags.append({'kind':'pin_capture','squares':[name(src),name(dst)]})
    for pin in sorted(pins(a,side)-pins(b,side)):
        tags.append({'kind':'pin','squares':list(map(name,pin))})
    for s,p in enumerate(a):
        if s==dst or p=='.' or color(p)!=side or p.lower() not in 'brq' or p!=b[s]:continue
        newly=attacks(a,s)-attacks(b,s)
        for t in sorted(newly):
            if enemy(a[t],side) and VALUES[a[t].lower()]>=500:
                tags.append({'kind':'discovered_attack','squares':[name(s),name(t)]})
    if len(move)==5:tags.append({'kind':'promotion','squares':[move[:2],move[2:4]]})
    king=next((i for i,p in enumerate(b) if p==('K' if side=='w' else 'k')),None)
    if king is not None and any(enemy(p,side) and king in attacks(b,i) for i,p in enumerate(b)):
        tags.append({'kind':'check_evasion','squares':[move[:2],move[2:4]]})
    if score_cp is not None and score_cp>=29000:
        tags.append({'kind':'search_mate','squares':[move[:2],move[2:4]]})
        if VALUES.get(b[src].lower(),0)>=500 and any(enemy(p,side) and dst in attacks(a,i) for i,p in enumerate(a)):
            tags.append({'kind':'possible_sacrifice','squares':[move[:2],move[2:4]]})
    return tags

def canonical(fen):
    """Group exact FEN, color/rank reflection and file reflection (no clocks)."""
    b=board(fen);_,turn,rights,ep,*_=fen.split()
    keys=[]
    for flip in (False,True):
        for mirror in (False,True):
            # File reflection of positions with castling rights is not a legal chess symmetry.
            if mirror and rights!='-':continue
            def transform(s):
                return (7-s//8 if flip else s//8)*8+(7-s%8 if mirror else s%8)
            a=['.']*64
            for i,p in enumerate(b):a[transform(i)]=p.swapcase() if flip else p
            t=('b' if turn=='w' else 'w') if flip else turn
            r=''.join(sorted(rights.swapcase() if flip else rights))
            e=name(transform(square(ep))) if ep!='-' else '-'
            keys.append(''.join(a)+' '+t+' '+r+' '+e)
    return min(keys)

def repetition_stats(records):
    from collections import Counter
    reasons=Counter(str(r.get('reason','unknown')) for r in records)
    return {'games':sum(reasons.values()),'reasons':dict(reasons),
            'repetitions':sum(n for k,n in reasons.items() if 'repetition' in k.lower() or 'threefold' in k.lower())}
