"""Read-only interpretation of existing engine telemetry, never a second search."""
import re
import math

MOVE=re.compile(r'^[a-h][1-8][a-h][1-8][qrbn]?$')
PIECES={'P':1,'N':3,'B':3,'R':5,'Q':9}

def uci(value):
    return value if isinstance(value,str) and MOVE.fullmatch(value) and value[:2]!=value[2:4] else None

def line_moves(event):
    event=event or {}
    details=event.get('details',{})
    chosen=uci(event.get('move'))
    if not chosen:return []
    line=details.get('illustrative_line') or []
    if not isinstance(line,list) or not line or line[0]!=chosen:return [chosen]
    out=[]
    for move in line[:12]:
        if not uci(move):break
        out.append(move)
    return out or [chosen]

def arrows(event, alternatives=True):
    event=event or {}
    chosen=uci(event.get('move'))
    result=[]
    seen={chosen}
    if alternatives:
        for item in event.get('details',{}).get('candidates') or []:
            if not isinstance(item,dict):continue
            move=uci(item.get('move'))
            if move and move not in seen:
                result.append((move,'alternative'));seen.add(move)
            if len(result)>=3:break
    if chosen:result.append((chosen,'chosen'))
    return result

def square_xy(square, black=False):
    if not isinstance(square,str) or not re.fullmatch('[a-h][1-8]',square):
        raise ValueError('Invalid square')
    x=ord(square[0])-97;y=8-int(square[1])
    return (7-x,7-y) if black else (x,y)

def number(value,fmt='.3f'):
    if isinstance(value,(int,float)) and math.isfinite(value):return format(value,fmt)
    return '—'

def report_sections(event, en=False):
    """Title/body pairs, clearly separate measurements and hypotheses."""
    if not event:return [('Waiting for analysis' if en else 'Ожидание анализа','—')]
    d=event.get('details',{});fen=str(event.get('fen',''));fields=fen.split()
    board=fields[0] if fields else ''
    white=sum(PIECES.get(p,0) for p in board if p.isupper())
    black=sum(PIECES.get(p.upper(),0) for p in board if p.islower())
    turn=('White' if en else 'белые') if fields[1:2]==['w'] else ('Black' if en else 'чёрные') if fields[1:2]==['b'] else '—'
    mode=d.get('mode')
    chosen=uci(event.get('move')) or '—'
    cp=number(d.get('engine_cp'),'+.0f')
    sections=[
      ('Position' if en else 'Позиция',f'{turn} · '+('material' if en else 'материал')+f' W {white} / B {black}\n'+('Engine score, side to move: ' if en else 'Оценка стороны хода: ')+cp+' cp'),
      ('Decision' if en else 'Решение',f'{chosen}  ·  policy {number(d.get("policy"))}  ·  value {number(event.get("value"),"+.3f")}'),
      ('Search' if en else 'Расчёт',('Depth / time / checked moves: ' if en else 'Глубина / время / проверено ходов: ')+f'{d.get("search_depth","—")} / {d.get("search_time_s","—")} s / {d.get("evaluated_moves","—")}')
    ]
    if mode!='neural_plus_cpp_search':
        sections.append(('Fallback' if en else 'Резервный выбор',str(d.get('reason') or ('Tactical search unavailable.' if en else 'Тактический поиск недоступен.'))))
    else:
        plan=[str(d[k]) for k in ('opening_name','opening_plan') if d.get(k)]
        motifs=[str(m) for m in d.get('motifs') or []]
        sections.append(('Plan and motifs' if en else 'План и мотивы','\n'.join(plan+motifs) or ('No classified motifs.' if en else 'Мотивы не классифицированы.')))
        best=d.get('best_engine_cp');score=d.get('engine_cp')
        if isinstance(best,int) and isinstance(score,int):
            sections.append(('Trade-off' if en else 'Компромисс выбора',('Best searched score / chosen: ' if en else 'Лучший проверенный / выбранный: ')+f'{best:+d} / {score:+d} cp'))
        if d.get('deep_warning'):sections.append(('Search limitation' if en else 'Ограничение поиска',str(d['deep_warning'])))
        traps=[]
        for trap in d.get('possible_traps') or []:
            if isinstance(trap,dict) and uci(trap.get('bait')):
                traps.append(f'{trap["bait"]}: {number(trap.get("punishment_cp"),"+.0f")} cp')
        sections.append(('Possible traps (conditional)' if en else 'Возможные ловушки (условно)','\n'.join(traps) or ('None reported.' if en else 'Не обнаружены в отчёте.')))
    sections.append((('Searched principal variation' if en else 'Основная линия поиска') if d.get('line_kind')=='searched_pv' else ('Illustrative continuation' if en else 'Возможное продолжение'),' → '.join(line_moves(event)) or '—'))
    if d.get('search_nodes') is not None:
        sections.append(('Search counters' if en else 'Счётчики поиска',f"Nodes: {d['search_nodes']} · Q: {d.get('search_qnodes')} · TT: {d.get('search_tt_hits')}"))
    sections.append(('Opponent mistakes' if en else 'Ошибки соперника','Not classified: no comparable before/after opponent search.' if en else 'Не классифицированы: нет сопоставимых оценок до и после хода соперника.'))
    sections.append(('Interpretation' if en else 'Ограничения','Engine telemetry, not internal neural reasoning. Policy is not win probability; even a searched PV is conditional on the search budget.' if en else 'Пояснения из телеметрии, не внутренние мысли сети. Policy не вероятность победы; даже основная линия зависит от бюджета поиска.'))
    return sections

def geometry_parts(value):
    match=re.fullmatch(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)',str(value))
    return tuple(map(int,match.groups())) if match else None
