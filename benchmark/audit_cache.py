"""Suite-specific, content-addressed, resumable read-only overlap audit."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from neural.tactical_data import hash_file,output_dir
from neural.tactical_learning import atomic_json,experiment_lock
from neural.tactics import canonical

def audit_cached(run,cases,folder):
    from neural.storage import archived_segments
    from .suite import signature,audit_sources
    folder=output_dir(folder,True)
    # Exact and canonical signatures: include every case sharing a symmetry.
    targets={}
    for r in cases:targets.setdefault(canonical(r['fen']),[]).append(r['id'])
    key=hashlib.sha256(json.dumps(targets,sort_keys=True).encode()).hexdigest()
    sources=archived_segments(run,'experience.jsonl')+[run/'experience.jsonl']
    sources=[p for p in sources if p.is_file()]
    def identity(p):
        stat=p.stat()
        return (stat.st_size,stat.st_mtime_ns)
    manifest={str(p.resolve()):identity(p) for p in sources}
    count=bad=hits_cache=0;overlap=set()
    with experiment_lock(folder):
        for i,path in enumerate(sources,1):
            sha=hash_file(path)
            entry=folder/(key+'_'+sha+'.json')
            if entry.is_file():
                row=json.loads(entry.read_text(encoding='utf-8'))
                if row.get('schema')!='audit_cache_v1' or row.get('source_sha256')!=sha or row.get('target_sha256')!=key:
                    raise ValueError('Invalid audit cache entry')
                hits_cache+=1
            else:
                # Canonicalize only rows with matching material counts? Full canonical scan for correctness.
                import gzip
                from collections import Counter
                from neural.tactics import board
                def material(fen):
                    s=Counter(x.lower() for x in board(fen) if x!='.')
                    return tuple(sorted(s.items()))
                materials={material(r['fen']) for r in cases}
                n=b=0;found=set()
                opener=gzip.open if path.suffix=='.gz' else open
                with opener(path,'rt',encoding='utf-8') as f:
                    for line in f:
                        if not line.strip():continue
                        try:
                            obj=json.loads(line);fen=obj['fen']
                            if not isinstance(fen,str) or len(fen.split())<4:raise ValueError('bad FEN')
                            if material(fen) in materials:found.update(targets.get(canonical(fen),[]))
                            n+=1
                        except (ValueError,KeyError,TypeError,IndexError,AttributeError):b+=1
                row={'schema':'audit_cache_v1','source_sha256':sha,'target_sha256':key,'records_checked':n,'malformed_records':b,'overlapping_ids':sorted(found)}
                if identity(path)!=manifest[str(path.resolve())] or hash_file(path)!=sha:raise RuntimeError('Experience changed during audit')
                atomic_json(entry,row)
            if identity(path)!=manifest[str(path.resolve())]:raise RuntimeError('Experience changed during audit')
            if not set(row['overlapping_ids'])<=set(r['id'] for r in cases):raise ValueError('Invalid cache case IDs')
            count+=row['records_checked'];bad+=row['malformed_records'];overlap.update(row['overlapping_ids'])
            if i%25==0 or i==len(sources):print(f'[AUDIT] {i}/{len(sources)} files, cache hits {hits_cache}, {count:,} FEN, overlaps {len(overlap)}',flush=True)
        current=[p for p in archived_segments(run,'experience.jsonl')+[run/'experience.jsonl'] if p.is_file()]
        if {str(p.resolve()):identity(p) for p in current}!=manifest:raise RuntimeError('Run changed during audit; stop PPO and retry')
    return {'status':'partial: malformed records' if bad else 'scanned' if count else 'no readable experience',
            'records_checked':count,'malformed_records':bad,'overlapping_ids':sorted(overlap),'sources':[str(p) for p in sources],
            'cache_hits':hits_cache,'cache_misses':len(sources)-hits_cache,'signature_mode':'canonical_v1',
            'scope':'selected run only; content-addressed suite-specific local cache, not proof of historical independence'}
