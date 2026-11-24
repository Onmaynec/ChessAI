# Chess AI v0.3.0 — фактический отчёт о тестировании

**Дата:** 23 ноября 2026 года. **Среда:** Linux, Python 3.13, PyTorch 2.10 CPU, g++/CMake, Chromium headless. Это не Windows и не RTX 3050.

| Проверка | Результат |
|---|---|
| Сборка C++20 Release + `ctest` | PASS |
| Persistent JSONL bridge: new/step/state/drop | PASS |
| Реальный Fool's Mate: 1.f3 e5 2.g4 Qh4# | PASS, `0-1/checkmate` |
| Параллельные партии с изолированными досками | PASS |
| Отклонение нелегального хода | PASS |
| Свежие self-play партии модели, собственный выбор легальных ходов | PASS |
| Policy PPO / Value MSE обновляют реальные веса | PASS |
| `result='*'` не даёт ложного reward | PASS |
| Endgame test: 2 итерации, 4 партии/итерация | PASS |
| Результаты endgame-прогона | 8 завершённых ничьих, 216 обучающих позиций |
| Сохранение и восстановление `latest.pt` | PASS |
| REST overview/status/games/CSV, валидация запросов | PASS |
| Веб-UI, открытие партии и все 64 клетки | PASS (Chromium) |
| Веб-UI, переключение ходов и обновление графиков | PASS (Chromium) |
| Мобильная адаптивность, viewport 390px | PASS, горизонтального скролла страницы нет |
| Реальная сборка Windows MSVC, CUDA/RTX 3050 | НЕ ПРОВЕРЯЛОСЬ |

### Репродукция из проекта

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
python -m unittest discover -s tests -p test_neural.py -v
python -m unittest discover -s tests -p test_selfplay.py -v
python -m neural.selfplay --engine build/chessai --out runs/my_qa --iterations 2 --games-per-iteration 4 --parallel 4 --max-plies 120 --arena-games 0 --start-fen '6k1/8/8/8/8/5K2/8/Q7 w - - 0 1'
```

### Что нельзя заключить из этих тестов

- Прототип способен обучаться по результатам завершённых партий, но это **не является доказательством увеличения Elo**.
- Value MSE улучшился на конкретном тестовом батче с 0.0945 до 0.0333 между двумя итерациями; величины нельзя считать измерением точности на фиксированной независимой выборке.
- Отдельный короткий запуск из стандартной стартовой позиции показал 2 партии без завершённого исхода при cap=100 (0 training samples). При cap=240 в другом тесте из 4 партий закончилась 1, получено 178 обучающих позиций. Это демонстрирует необходимость правильного cap и полноценного benchmarking.
- Прямые GPU-бенчмарки на пользовательском оборудовании отсутствуют.
