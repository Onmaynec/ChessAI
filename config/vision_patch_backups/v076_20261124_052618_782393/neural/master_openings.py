"""Curated high-level opening patterns used in master-level chess.

These are *illustrative theory lines*, NOT copied GM game archives and do not
mean ChessAI has learned from or imitates any named player's recorded games.
Moves are only suggested for an exact legal opening prefix and can be vetoed
by deep tactics if refuted. No API or third-party copyrighted data used.
"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class ClassicalLine:
    name: str
    strategic_plan: str
    moves: tuple[str, ...]


def line(name:str, plan:str, *moves:str) -> ClassicalLine:
    return ClassicalLine(name,plan,moves)

LINES = (
    line('Испанская партия: берлинская защита', 'Упорная защита, борьба за e4 и эндшпиль',
         'e2e4','e7e5','g1f3','b8c6','f1b5','g8f6','e1g1','f6e4','d2d4','e4d6','b5c6','d7c6'),
    line('Испанская партия: атака Маршалла', 'Динамическая компенсация и активность фигур',
         'e2e4','e7e5','g1f3','b8c6','f1b5','a7a6','b5a4','g8f6','e1g1','f8e7','f1e1','b7b5','a4b3','e8g8','c2c3','d7d5'),
    line('Итальянская партия: джокко пианиссимо', 'Развитие, контроль центра и профилактика',
         'e2e4','e7e5','g1f3','b8c6','f1c4','f8c5','d2d3','g8f6','c2c3','d7d6','e1g1','e8g8'),
    line('Каталонское начало: открытый вариант', 'Давление слона g2 на длинной диагонали',
         'd2d4','g8f6','c2c4','e7e6','g2g3','d7d5','f1g2','d5c4','g1f3'),
    line('Каталонское начало: закрытый вариант', 'Долговременное позиционное давление',
         'd2d4','g8f6','c2c4','e7e6','g2g3','d7d5','f1g2','f8e7','g1f3','e8g8','e1g1'),
    line('Полуславянская: мерaнский вариант', 'Подрыв центра пешками и развитие с темпом',
         'd2d4','d7d5','c2c4','c7c6','g1f3','g8f6','b1c3','e7e6','e2e3','b8d7','f1d3','d5c4','d3c4','b7b5'),
    line('Сицилианская: английская атака', 'Разносторонняя борьба за инициативу',
         'e2e4','c7c5','g1f3','d7d6','d2d4','c5d4','f3d4','g8f6','b1c3','a7a6','c1e3','e7e5','d4b3','c8e6','f2f3'),
    line('Сицилианская: классическая схема', 'Контроль центральных полей и игра фигур',
         'e2e4','c7c5','g1f3','b8c6','d2d4','c5d4','f3d4','g8f6','b1c3','d7d6','c1g5'),
    line('Защита Грюнфельда: разменный вариант', 'Фигурное давление на белый пешечный центр',
         'd2d4','g8f6','c2c4','g7g6','b1c3','d7d5','c4d5','f6d5','e2e4','d5c3','b2c3','f8g7'),
    line('Староиндийская: Мар-дель-Плата', 'Пешечные штурмы на разных флангах',
         'd2d4','g8f6','c2c4','g7g6','b1c3','f8g7','e2e4','d7d6','g1f3','e8g8','f1e2','e7e5','e1g1','b8c6','d4d5','c6e7'),
    line('Каро-Канн: продвинутая система', 'Устойчивое развитие и давление на d4',
         'e2e4','c7c6','d2d4','d7d5','e4e5','c8f5','g1f3','e7e6','f1e2','c6c5','e1g1','b8c6'),
    line('Английское начало: обратная сицилианская', 'Пространство в центре и фианкетто',
         'c2c4','e7e5','b1c3','g8f6','g2g3','d7d5','c4d5','f6d5','f1g2'),
    line('Ферзевый гамбит: позиционная система', 'Давление на ферзевом фланге',
         'd2d4','d7d5','c2c4','e7e6','b1c3','g8f6','c1g5','f8e7','e2e3','e8g8','g1f3','b8d7','a1c1','c7c6','f1d3'),
    line('Защита Нимцовича: система Рубинштейна', 'Связка коня, контроль центра и активные пешечные размены',
         'd2d4','g8f6','c2c4','e7e6','b1c3','f8b4','e2e3','e8g8','f1d3','d7d5','g1f3','c7c5'),
    line('Французская защита: Винавер', 'Давление на центр и пешечные слабости',
         'e2e4','e7e6','d2d4','d7d5','b1c3','f8b4','e4e5','c7c5','a2a3','b4c3','b2c3'),
    line('Скандинавская: современный вариант', 'Развитие с темпом и активные фигуры',
         'e2e4','d7d5','e4d5','g8f6','d2d4','f6d5','g1f3','g7g6'),
)


def response(history: list[str] | tuple[str,...], legal_moves:list[str]) -> tuple[str,str,str] | None:
    prefix=tuple(history)
    allowed=set(legal_moves)
    for item in LINES:
        if len(prefix)<len(item.moves) and item.moves[:len(prefix)]==prefix:
            following=item.moves[len(prefix)]
            if following in allowed:
                return following,item.name,item.strategic_plan
    return None
