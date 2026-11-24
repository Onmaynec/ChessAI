# Chess AI 

Локальная шахматная исследовательская система: C++20 Chess Core, собственная policy/value сеть на PyTorch, PPO self-play и Training Studio.

**Совместимость:** веса и кодировщик позиций (`planes19_actions73_v1`) совместимы с v0.6.0. Обновление версии само по себе не делает модель сильнее — силу нужно проверять через Holdout Evaluation.

### Архивирование журналов

Завершённые `experience.jsonl`, `games.jsonl` и `arena_games.jsonl` теперь сжимаются без потерь в `runs/<ID>/archives/` (gzip). При распаковке проверяется SHA-256. Автоматическое сжатие выполняется раз в 5 итераций после записи checkpoint и метрик; отключается через `--archive-every 0`.

Для ручного сжатия без продолжения обучения используйте `scripts/COMPACT_RUNS_WINDOWS.bat` (или `python -m tools.compact_runs --run ... --apply` после остановки обучения). Checkpoint'ы, `metrics.jsonl`, `run_metadata.json` и `run_state.json` не сжимаются и не удаляются.

### CPU + GPU

`rollout()` больше не ждёт завершения самой долгой партии волны: освободившиеся слоты сразу заполняются новыми партиями, а сеть оценивает готовые позиции одним батчем. По умолчанию используется `--bridge-workers 2` (независимые C++ bridge-процессы) и `--parallel` для числа одновременных партий (отдельно от `--batch-size`).

В `metrics.jsonl` добавлены поля `performance`: `opening_s`, `bridge_steps_s`, `neural_inference_s`, `ppo_s`, `arena_s`, `average_inference_batch`, `max_inference_batch`, `bridge_workers`, `concurrent_games`, `total_iteration_s`. Ускорение зависит от железа; замеряйте на своей машине.

### CUDA

Если в старой установке уже есть `.venv-cuda`, новая версия может использовать её через `config/python_path.txt`, не скачивая Torch заново. Не копируйте `.venv-cuda` как обычную папку — virtualenv может содержать жёсткие пути.

### Качество обучения

PPO, checkpoint'ы и схема наград не изменены. `best.pt` по-прежнему отделён от `latest.pt`. Реальную силу модели оценивайте через Holdout Evaluation, а не по loss или загрузке GPU.

## Запуск

Windows: `START_CHESS_AI.bat` → `http://127.0.0.1:8765`. Требуются CMake, C++ Build Tools/Visual Studio, Python и зависимости из `requirements.txt`. Для CPU можно использовать `.venv`; для NVIDIA нужен CUDA PyTorch.

## Проверки

- `scripts/VERIFY_PROGRESS_WINDOWS.bat`
- `scripts/BENCHMARK_HARDWARE_WINDOWS.bat`
- `scripts/AUDIT_COLOR_WINDOWS.bat`
- `scripts/EVALUATE_RUN_WINDOWS.bat`
- `scripts/CHECKPOINT_TOURNAMENT_WINDOWS.bat`

## Тесты

Python: `unittest discover -s tests`. C++: CMake + CTest.

## Примечание

Система предназначена для обучения и игры в разрешённых окружениях. Не используйте её для скрытого управления человеческими аккаунтами на соревновательных шахматных сайтах.
