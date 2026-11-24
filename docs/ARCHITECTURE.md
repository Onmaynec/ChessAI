# Chess AI v0.3.0 — архитектура (актуализация)

v0.3 добавляет к архитектуре v0.2:

- `chessai bridge`: C++ JSONL процесс с несколькими независимыми состояниями партий; команды `new`, `step`, `state`, `drop`, `quit`.
- `neural/selfplay.py`: пакетный вывод модели, on-policy rollout, PPO policy/value updates, тестовая arena, ведение checkpoints и JSONL.
- `dashboard/server.py`: локальный FastAPI, REST API и управление subprocess-тренировкой.
- `dashboard/ui/`: адаптивный полностью локальный UI, графики, просмотр партий и история запусков.
- `START_CHESS_AI.bat`: один Windows-скрипт для сборки, установки и запуска панели.

Подробно о математике: `docs/SELFPLAY_METHOD.md`. Настройки и мониторинг: `docs/TRAINING_STUDIO.md`.

---

## Сохранившаяся архитектура v0.2.0

# Архитектура Chess AI v0.2.0

## Реальные модули

```text
                  C++ Chess Core
                (unchanged v0.1.0)
                  /          \
      legal-json/apply      teacherdata
                  |          |
              agent.py  baseline depth 1-4
                  |          |
          inference model    JSONL
                  |          |
             legal mask    train.py
                  \          /
                     ChessNet
              19 planes -> Conv -> 2 ResBlocks
                 policy (4672), value (1)
```

### Формат данных

`chessai teacherdata COUNT DEPTH PATH [SEED]` экспортирует каждую независимую позицию отдельной строкой JSON:

```json
{"fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","best_move":"e2e4","score_cp":12,"teacher":"chessai_baseline_d2","sample_id":1,"legal_moves":["e2e3","e2e4"]}
```

Показанный JSON демонстрирует схему, **не является реальной записью**: список легальных ходов намеренно сокращён и дан только для объяснения полей. Обучение производится на реальных записях, созданных движком.

`score_cp` — centipawn-оценка со стороны игрока, которому ходить. Target value = `tanh(score_cp/600)` (эвристическая оценка, **не win rate**). Teacher выбирает shallow minimax; эта модель **не сильный шахматный интеллект**.

Кодирование и порядок policy-плоскостей указаны в `neural/encoding.py`; схема `planes19_actions73_v1` обязательно совпадает с обученным чекпойнтом. Дедупликация идёт по полной FEN; частично одинаковые позиции, отличающиеся счётчиком ходов, могут оказаться в разных выборках — это ограничение текущего разбиения, важно при будущей строгой оценке.

### Training

- CNN: 32 channels, 2 residual blocks в включённой модели; 111258 параметров.
- Softmax только над легальными ходами (train/inference), CE для policy.
- Value: MSE по эвристической цели, вес по умолчанию 0.25.
- AdamW + градиентный клиппинг; train/validation 90%/10%.
- Автоматическое определение CUDA через `torch.cuda.is_available()`.
- Минимальные Windows-команды из README; модель и dataset можно сгенерировать заново.

### Inference

`agent.py` обращается к C++ `legal-json` и `apply`, а не реализует второй конфликтующий шахматный движок. Это гарантирует, что выход — разрешённый ход. Протокол UCI предназначен для локального GUI/разрешённых bot-режимов; полноценный асинхронный UCI ещё не готов.

## Метрики

- Количество размеченных позиций, epochs, batch size и train/val loss.
- `policy_top1_legal` — совпадение с ходом слабого учителя после legal mask.
- `value_mae` — отклонение от heuristic value target.
- Не измерены: Elo, win-rate против уровня master, self-play games/s, GPU utilization на ПК пользователя.

## v0.3.0: цели

Перейти от имитации к обучению из игровых результатов: независимо собирать партии, учитывать исход (не объявлять игры по лимиту ничьими), хранить policy targets, replay buffer, конкуренцию с прошлыми checkpoint, фиксированный arena protocol и оценку Elo с доверительными интервалами. Потребуется уменьшить per-move subprocess overhead и пакетно вычислять policy/value.
