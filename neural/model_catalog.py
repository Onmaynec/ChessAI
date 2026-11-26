"""Shared, read-only model inventory. Stable path IDs, content revisions, no pickle loads."""
from __future__ import annotations
import argparse,hashlib,json,re
from datetime import datetime,timezone
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALIASES={
    'latest.pt':('ChessNet Core','Рабочая модель PPO','active',None),
    'best.pt':('ChessNet Champion','Сохранённая лучшая модель PPO','retained',None),
    'skillboost_v2.pt':('ChessNet SkillBoost II','Тактика, дебюты и защита','specialist',None),
    'aggressive.pt':('ChessNet Aggressive','Атакующая специализация','specialist',None),
    'defender.pt':('ChessNet Defender','Защитная специализация','specialist',None),
    'phantom.pt':('ChessNet Phantom X23','Дебютная специализация','specialist',None),
    'lasttest.pt':('ChessNet Previous Test','Старая тестовая копия','archive',None),
    'skillboost.pt':('ChessNet SkillBoost I','Предыдущая специализация','archive',None),
}
VERSIONS={'tactical_train_v2':('Tactical Learning','0.9.3.1'),
          'tactical_train_v3':('Tactical Mastery','0.9.3.2'),
          'tactical_train_v4':('Tactical Optimization','0.9.3.3'),
          'tactical_train_v5':('Neural Scaling','0.9.3.4')}
SIZES={(32,2):'Classic',(64,6):'Light',(96,10):'Standard',(128,15):'Advanced'}
ENGINES={'stockfish':('Stockfish 19','Stockfish','NNUE / CPU'),
         'lc0':('Leela Chess Zero','Leela Chess Zero','MCTS / CUDA')}

def read_json(p):
    try:
        data=json.loads(p.read_text(encoding='utf-8-sig'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

@lru_cache(maxsize=512)
def _hashed(path,size,mtime,ctime):
    p=Path(path);h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    st=p.stat()
    if (st.st_size,st.st_mtime_ns,st.st_ctime_ns)!=(size,mtime,ctime):raise OSError('File changed while reading')
    return h.hexdigest()

def file_info(p):
    st=p.stat()
    try:h=_hashed(str(p.resolve()),st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    except OSError:h=None
    return {'sha256':h,'revision':'r-'+h[:10] if h else 'revision pending',
            'bytes':st.st_size,'modified':datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat()}

def arch_label(a):
    if not isinstance(a,dict):return 'Не подтверждена',None
    c,b=a.get('channels'),a.get('blocks')
    if type(c) is not int or type(b) is not int or c<=0 or b<=0:return 'Не подтверждена',None
    return f'{c}×{b} CNN',SIZES.get((c,b),'Custom')

def run_label(run,metadata=None):
    m=metadata if isinstance(metadata,dict) else read_json(run/'run_metadata.json')
    arch,size=arch_label(m.get('architecture'))
    stamp=str(m.get('created_at') or '')
    match=re.search(r'run_(\d{8})_(\d{6})',run.name)
    if not stamp and match:stamp=match[1][:4]+'-'+match[1][4:6]+'-'+match[1][6:]+' '+match[2][:2]+':'+match[2][2:4]
    stamp=stamp[:16].replace('T',' ') or 'дата неизвестна'
    custom=str(m.get('name') or '')
    title=custom if custom and custom!=run.name and not custom.startswith('run_') else 'ChessNet '+(size or 'Core')+' · PPO'
    return f'{title} · {stamp} · {run.name[-6:]}'

def _entry(root,p,name,role,status,version=None,architecture='Не подтверждена',source=None,**extra):
    info=file_info(p)
    return {'id':p.relative_to(root).as_posix(),'path':p.relative_to(root).as_posix(),'name':name,
            'role':role,'status':status,'version':version,'architecture':architecture,'source':source,
            **info,**extra,'label':name+' · '+((f'v{version} · ') if version else '')+info['revision']}

def inventory(root=ROOT,run=None):
    root=Path(root).resolve();rows=[]
    runs=sorted((root/'runs').glob('*')) if run is None else [Path(run).resolve()]
    for r in runs:
        if not r.is_dir() or not r.is_relative_to(root/'runs'):continue
        m=read_json(r/'run_metadata.json');architecture,size=arch_label(m.get('architecture'))
        for p in sorted((r/'checkpoints').glob('*.pt')):
            if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(root):continue
            name,role,status,version=ALIASES.get(p.name,('ChessNet Historical','Исторический файл, происхождение не подтверждено','archive',None))
            # Run architecture is evidence for PPO slots only; specialist may differ.
            a=architecture if p.name in ('latest.pt','best.pt','lasttest.pt') else 'Не подтверждена'
            try:rows.append(_entry(root,p,name,role,status,version,a,run_label(r,m),run_id=r.name,
                                  trainer_version=m.get('version') if p.name in ('latest.pt','best.pt','lasttest.pt') else None,
                                  selectable=p.name in ALIASES and status!='archive'))
            except OSError:continue
    experiments=root/'tactical_experiments'
    if experiments.is_dir():
        for p in sorted(experiments.rglob('candidate.pt')):
            if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(root):continue
            report=read_json(p.with_name('training_report.json'))
            complete=report.get('status')=='complete' and bool(report.get('candidate')) and bool(report.get('selected_epoch'))
            stage,version=VERSIONS.get(report.get('schema'),('Unverified Candidate',None))
            architecture,size=arch_label(report.get('model_config'))
            name='ChessNet '+((size+' ') if size else '')+stage
            try:
                rows.append(_entry(root,p,name,'Экспериментальный кандидат — не заменяет PPO',
                    'candidate' if complete else 'archive',version,architecture,p.parent.relative_to(root).as_posix(),
                    selected_epoch=report.get('selected_epoch'),parameters=report.get('parameters'),
                    validation_top1=(report.get('selected_validation') or {}).get('top1') if isinstance(report.get('selected_validation'),dict) else None,
                    selectable=complete))
            except OSError:continue
    for key,(label,name,architecture) in ENGINES.items():
        p=root/'external_engines'/'v0935'/key/'installed.json';m=read_json(p)
        if m.get('engine')!=key or not m.get('version'):continue
        exe=p.parent/str(m.get('exe',''))
        if not exe.is_file() or not exe.resolve().is_relative_to(p.parent.resolve()):continue
        try:
            row=_entry(root,p,name,'Внешний готовый движок','external',str(m['version']),architecture,'Official release manifest',selectable=True,external=label)
            row['archive_sha256']=m.get('archive_sha256');row['weights']=m.get('weights')
            rows.append(row)
        except OSError:continue
    # Byte-identical checkpoints only, never infer equal weights from names.
    order={'active':0,'retained':1,'specialist':2,'candidate':3,'external':4,'archive':5}
    rows.sort(key=lambda x:(order[x['status']],x['name'],x['id']))
    seen={}
    for row in rows:
        h=row['sha256']
        if h and row['status']!='external':
            if h in seen:
                row.update(status='duplicate',duplicate_of=seen[h],selectable=False)
            else:seen[h]=row['id']
        if not h:row['selectable']=False
    return rows

def vision_entries(run,root=ROOT):
    rows=inventory(root,run)
    result=[]
    for row in rows:
        if not row['selectable']:continue
        key=row.get('external') or (Path(row['id']).name if row.get('run_id') else row['id'])
        result.append(dict(row,key=key))
    return result

def model_label(key,entries):
    return next((r['label'] for r in entries if r['key']==key),str(key))

def main():
    p=argparse.ArgumentParser(description='Read-only inventory; no deletion')
    p.add_argument('--output',type=Path,default=ROOT/'model_inventory.json');a=p.parse_args()
    target=a.output.resolve()
    if target.exists():p.error('Output already exists; choose a new path')
    if not target.parent.is_dir():p.error('Output parent missing')
    rows=inventory()
    with target.open('x',encoding='utf-8') as f:json.dump({'schema':'model_catalog_v1','models':rows},f,ensure_ascii=False,indent=2)
    print('Inventory:',target,'| visible:',sum(r['selectable'] for r in rows),'| hidden:',sum(not r['selectable'] for r in rows))
if __name__=='__main__':main()
