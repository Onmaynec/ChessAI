"""Bounded, human-readable Vision status and analysis diagnostics.

All GUI widgets are updated only from Tk's main thread; worker messages are
JSON serialized and handed through the existing thread-safe queue. This module
contains no browser automation, neural writes or network requests.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

PREFIX = '@CHESSAI_ANALYSIS@'
MAX_LOG_BYTES = 2_000_000


def analysis_event(details: dict, *, move: str, fen: str, ply: int, value: float) -> str:
    payload = {'move':move, 'fen':fen, 'ply':ply, 'value':value,
               'details':details, 'when':datetime.now().astimezone().isoformat(timespec='seconds')}
    return PREFIX + json.dumps(payload, ensure_ascii=False, separators=(',',':'))


def read_event(message: str) -> dict | None:
    if not isinstance(message, str) or not message.startswith(PREFIX):
        return None
    parsed = json.loads(message[len(PREFIX):])
    if not isinstance(parsed,dict) or not isinstance(parsed.get('details'),dict):
        raise ValueError('Bad analysis event')
    return parsed


PIECE_VALUES = {'P':1,'N':3,'B':3,'R':5,'Q':9}


def position_summary(fen: str) -> str:
    """Readable material and side to move from trusted C++ FEN."""
    fields=fen.split()
    if len(fields)<2:
        return 'Неполный FEN'
    board=fields[0]
    white=sum(PIECE_VALUES.get(c,0) for c in board if c.isupper())
    black=sum(PIECE_VALUES.get(c.upper(),0) for c in board if c.islower())
    side='белые' if fields[1]=='w' else 'чёрные'
    if white+black<=18:
        phase='эндшпиль'
    elif len(fields)>5 and fields[5].isdigit() and int(fields[5])>=14:
        phase='миттельшпиль'
    else:
        phase='дебют / ранняя игра'
    return f'Очередь: {side} · Материал: белые {white}, чёрные {black} · Фаза: {phase}'


def formatted_analysis(event: dict) -> list[str]:
    d = event.get('details',{})
    res = [f"Ход № {event.get('ply',0)+1}: {event.get('move','?')}",
           position_summary(event.get('fen','')),
           f"FEN: {event.get('fen','?')}"]
    if d.get('mode')=='external_uci':
        res.extend([f"UCI: {d.get('engine')} · {d.get('profile')}",f"Оценка: {d.get('uci_score')} · глубина {d.get('search_depth')} · nodes {d.get('search_nodes')} · NPS {d.get('nps')}",f"PV: {' '.join(d.get('illustrative_line',[]))}",f"Время: {d.get('search_time_s')} с; перезапуски: {d.get('uci_restarts')}"])
        return res
    if d.get('mode') != 'neural_plus_cpp_search':
        res.append('ТАКТИЧЕСКИЙ ПОИСК НЕДОСТУПЕН — fallback нейросети')
        if d.get('reason'):res.append('Причина: '+str(d['reason'])[:230])
        return res
    cp = d.get('engine_cp')
    res.extend([
        f"Глубина: {d.get('search_depth','?')} полуходов (глубокий поиск: {'да' if d.get('deep_search') else 'нет'})",
        f"Время расчёта: {d.get('search_time_s','?')} с; проверено {d.get('evaluated_moves',0)} ходов; глубоко — {d.get('deep_evaluated_moves',0)}",
        f"Оценка движка: {cp:+d} cp" if isinstance(cp,int) else 'Оценка движка: нет',
        f"Оценка нейросети (value): {event.get('value',0):+.3f}; вероятность выбранного: {d.get('policy','?')}",
        f"Ожидаемый ответ противника: {d.get('expected_reply') or 'нет (конец партии)'}",
        ('Основная линия поиска: ' if d.get('line_kind')=='searched_pv' else 'Линия возможного продолжения: ') + (' '.join(d.get('illustrative_line',[])) or '?')])
    if d.get('search_nodes') is not None:
        res.append(f"Узлы: {d['search_nodes']} · Q: {d.get('search_qnodes')} · TT: {d.get('search_tt_hits')}")
    if d.get('opening_name'):
        res.append('Дебютная схема: '+d['opening_name'])
    if d.get('opening_plan'):
        res.append('План: '+d['opening_plan'])
    if d.get('repetition_penalty_cp'):
        res.append(f"Штраф за повторения: {d['repetition_penalty_cp']} cp")
    if d.get('motifs'):
        res.append('Мотивы: '+', '.join(d['motifs']))
    if d.get('possible_traps'):
        for trap in d['possible_traps']:
            res.append(f"Возможная ловушка: если соперник сыграет {trap['bait']}, "
                       f"локальный поиск оценивает ответ примерно в {trap['punishment_cp']:+d} cp")
    if d.get('deep_warning'):
        res.append('Внимание: углубление не завершено: '+d['deep_warning'][:180])
    res.append('Альтернативы (cp от текущей стороны, ответ соперника):')
    for c in d.get('candidates',[])[:8]:
        res.append(f"  {c['move']:<6} {c['cp']:+6d} cp  p={c['policy']:.3f}  ответ={c.get('expected_reply') or '-'}")
    res.append('Оценки приблизительные: используется собственный C++-движок, не Stockfish.')
    return res


def rotate_and_append(path: Path, message: str, *, cap: int = MAX_LOG_BYTES) -> None:
    """Keep a small diagnostic log; never write positions to PPO experience."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > cap:
        archived=path.with_suffix('.previous.log')
        path.replace(archived)
    with path.open('a',encoding='utf-8') as f:
        f.write(message.rstrip('\n')+'\n')


def rectangles_overlap(a: tuple[int,int,int,int], b: tuple[int,int,int,int]) -> bool:
    """Two rectangles (left, top, width, height), touching edges is safe."""
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    return ax<bx+bw and ax+aw>bx and ay<by+bh and ay+ah>by
