# Chess AI

Локальная исследовательская шахматная система: собственное ядро C++20, policy/value-сеть PyTorch, PPO self-play, Training Studio и экспериментальные агенты. Текущая интеграционная версия — **0.8.1 (Repository Foundation)**. Формат весов остаётся `planes19_actions73_v1`.

## Быстрый старт (Windows)

1. Установите Python 3.11+, CMake и Visual Studio C++ Build Tools. Для NVIDIA установите подходящий CUDA PyTorch в отдельное окружение.
2. Запустите `START_CHESS_AI.bat`: он использует выбранный Python, при необходимости собирает ядро и открывает Training Studio на http://127.0.0.1:8765.
3. Для нового обучения нужен локальный стартовый checkpoint `models/neural_best.pt`: веса не публикуются в Git. Его можно создать через `scripts/train_neural_windows.bat` (скрипт использует CPU-окружение .venv или установленный в нём CUDA PyTorch). Для существующего эксперимента используйте «Продолжить обучение».
4. Vision Bot — отдельный запуск `START_CHESS_VISION_BOT.bat`, дополнительные зависимости в `requirements-vision.txt`. Используйте только в разрешённых тестовых окружениях.

## Структура

| Каталог | Назначение |
| --- | --- |
| src/ | C++ Chess Core, CLI, UCI и JSONL bridge |
| neural/ | Кодирование, ChessNet, обучение, поиск, evaluation и специализации |
| dashboard/ | Локальная Training Studio и API |
| botlab/, visionbot/ | Отдельные интерфейсы экспериментов и анализа |
| scripts/ | Windows-команды сборки, тестов, обучения и диагностики |
| tools/ | Миграция, проверка checkpoint, архивирование |
| tests/ | Регрессионные тесты Python и C++ |
| docs/ | Актуальная документация, руководства и исторический архив |
| models/, runs/, config/ | Локальные веса, прогресс и настройки; в Git только явно предусмотренные метаданные/примеры |

## Документация

Начните с [индекса документации](docs/README.md), [архитектуры](docs/ARCHITECTURE.md), [обучения](docs/TRAINING_STUDIO.md) и [безопасного обновления](docs/LOCAL_UPDATE.md). История — [CHANGELOG](CHANGELOG.md).

## Проверки

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
python -m unittest discover -s tests
```

Windows: `scripts/VERIFY_PROGRESS_WINDOWS.bat` проверяет совместимость checkpoint и optimizer. `scripts/EVALUATE_RUN_WINDOWS.bat` и `scripts/CHECKPOINT_TOURNAMENT_WINDOWS.bat` помогают измерять силу. Не объявляйте Elo по loss или числу итераций.

## Данные

Не удаляйте и не переименовывайте `runs/`, не заменяйте `latest.pt` специализированной моделью. Перед обновлением остановите обучение после итерации и сделайте отдельную резервную копию. Не публикуйте локальные пути, калибровку, веса или журналы. Training Studio не предназначена для публичного доступа.

Автор: [Onmaynec](https://github.com/Onmaynec).
