# Реальные тесты — v0.2.0

Среда тестирования: Linux container, CMake/GCC, Python 3.13, PyTorch 2.10 CPU. Сборка Windows и CUDA-ускорение **не проверены**. Эти показатели не являются замером ПК пользователя.

| Проверка | Результат |
|---|---|
| C++ Chess Core regression (`ctest`) | PASS |
| Python feature/move encoding tests | PASS |
| CNN policy 4672 + value 1, legal masking | PASS |
| C++ legal-json -> Python neural.agent | PASS |
| C++ teacherdata depth 2, 4000 samples | 4000 rows, ~3.85 s |
| Supervised PyTorch, 8 epochs, 3600/400 train/val | ~19.03 s CPU |
| Лучший `policy_top1_legal` | 41.5% (epoch 7) |
| Лучшая validation loss | 2.2667 (epoch 7) |
| Neural UCI `uci`, `isready`, `position`, `go` | PASS в отдельном smoke test |

Последняя эпоха #8 имела `policy_top1_legal` 39.5%; файл `neural_best.pt` выбран **по validation loss**, а не по точности последней эпохи. Результат 41.5% не отражает шанс победы в шахматной партии.

Все прежние эталонные результаты perft сохраняются. См. историю v0.1.0 в git/архиве предыдущего релиза.
