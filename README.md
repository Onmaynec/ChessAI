<div align="center">

# Chess AI 🧠

[![Version](https://img.shields.io/badge/version-0.9.10-242424)](VERSION)
[![Platform](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows)](docs/README.md)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python)](requirements.txt)
[![PyTorch](https://img.shields.io/badge/PyTorch-CUDA%20%7C%20CPU-EE4C2C?logo=pytorch)](requirements.txt)
[![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus)](docs/ARCHITECTURE.md)

**Локальная шахматная исследовательская система: C++20 Chess Core, собственная policy/value сеть на PyTorch, PPO self-play и Training Studio.**

[Архитектура](docs/ARCHITECTURE.md) · [Обновление](docs/LOCAL_UPDATE.md) · [Сборка](docs/README.md) · [Требования](docs/COMPATIBILITY.md)

</div>

## Vision Bot 0.9.10 — Performance & Accessibility (Qt preview)

Индексация журнала, ограничение размера локального импорта, кэширование доски, масштаб текста и клавиатурная навигация. Только локальный preview. [Измерения и ограничения](docs/VISION_UI_PERFORMANCE_0910.md).

### 0.9.9 — Motion Design & Component Gallery (Qt preview)

Единые интервалы анимаций, типографика, интерактивные состояния, переключатели, семантические статусы и галерея компонентов. Настройка уменьшения движения сохраняется отдельно. Только локальный preview; рабочий GUI сохранён. [Документация](docs/VISION_UI_MOTION_099.md).

### 0.9.8 — Workspace & Overlay Reengineering (Qt preview)

Compact / Standard / Expanded, независимые окна метрик, доски, вариантов и журнала, сохранение положения и закрепления, общая модель просмотра. Только локальный preview; рабочий GUI сохранён. [Настройки и проверка](docs/VISION_UI_WORKSPACE_098.md).

### 0.9.7 — Advanced Chessboard & Analysis (Qt preview)

Шахматная доска с 12 оригинальными SVG-фигурами, ориентация, стрелка предложенного хода, кандидаты, оценочная шкала и история полученных позиций. Только локальный просмотр; рабочий CustomTkinter сохранён. [Документация и проверка](docs/VISION_UI_BOARD_097.md).

### 0.9.6 — Professional Desktop Interface (Qt preview)

Новая отдельная оболочка Qt Quick: обзор, анализ, журнал, настройки, общие компоненты и адаптивная компоновка. Пока только локальный просмотр; рабочий CustomTkinter сохранён. [Установка, режимы и проверка](docs/VISION_UI_QT_096.md).

### 0.9.5 — UI Architecture & QML Preparation

Независимый контроллер UI, модели состояния сессии и анализа, адаптер QObject для будущего Qt Quick. Действующий интерфейс CustomTkinter сохранён. Qt-зависимости опциональны. [Архитектура 0.9.5](docs/VISION_UI_ARCHITECTURE_095.md).

### 0.9.4 — UI Foundation

Тестовая версия редизайна: общая монохромная дизайн-система, адаптивные панели, компактный режим, журнал с поиском и экспортом. Вычислительное ядро и веса не изменены. Полная визуальная приёмка на Windows ещё не проведена. [Изменения и проверка](docs/VISION_UI_REENGINEERING.md).

> [!IMPORTANT]
> Обновление версии само по себе не делает модель сильнее. Силу проверяйте через **Holdout Evaluation**, а не по loss или загрузке GPU. Веса и кодировщик позиций (`planes19_actions73_v1`) совместимы с v0.6.0.

Ручной запуск из корня:

```powershell
.\.venv-cuda\Scripts\python.exe -m tools.compact_runs --run runs\run_20261123_072154_6a110b
.\.venv-cuda\Scripts\python.exe -m tools.compact_runs --run runs\run_20261123_072154_6a110b --apply
```

Если CUDA-Python остался в старой папке, используйте `.bat` — он сам найдёт выбранный интерпретатор. `--apply` не сработает, если `run_state` всё ещё помечен как running.

## CPU + GPU — непрерывное пакетирование ⚡

`rollout()` больше не ждёт завершения самой долгой партии всей волны: освободившиеся слоты сразу заполняются новыми партиями, а сеть оценивает позиции одновременно готовых игр одним inference batch.

- `--bridge-workers 2` по умолчанию — независимые C++ chess bridge процессы, параллельное выполнение ходов на CPU через пул потоков Python, без конкурентного чтения одного stdin pipe. Допустимые значения 1–8.
- `--parallel` задаёт число одновременных партий отдельно от `--batch-size` (размер минибатча PPO). Начните с 16 партий при `games-per-iteration=16` и замеряйте реальное время на своей машине.
- В `metrics.jsonl` появились поля `performance`: `opening_s`, `bridge_steps_s`, `neural_inference_s`, `ppo_s`, `arena_s`, `average_inference_batch`, `max_inference_batch`, `bridge_workers`, `concurrent_games`, `total_iteration_s`. Отображаются в панели диагностики.

Бенчмарки проводятся только на собственном ПК — никаких обещаний ускорения в X раз. Маленькая сеть и обмен CPU/GPU способны стать узким местом даже при 100% загрузке одного движка GPU.

## CUDA после обновления 🧩

Если в старой установке уже была `.venv-cuda` с `torch==2.15.0+cu134`, новой установке не нужно качать те же 2,2 ГБ повторно. `START_CHESS_AI.bat` использует указанный в `config/python_path.txt` абсолютный путь; Training Studio передаёт текущий `sys.executable` дочерним процессам. Если путь устарел — отредактируйте `config/python_path.txt` или поставьте окружение в новой папке.

Не копируйте `.venv-cuda` как обычную папку — virtualenv может содержать жёсткие пути.

## Качество обучения 🎯

PPO, весовые checkpoint и схема наград **не изменены** — это снижает риск незаметного сброса или смены обучающей задачи. `best.pt` остаётся отдельно от `latest.pt`, контролируемые проверочные матчи продолжают работать.

Оценку реальной силы проводите через Holdout Evaluation, а не по падению loss или высокой загрузке GPU.

## Обновление с 0.6.0 🔄

1. В старой Training Studio нажмите **Остановить после итерации**, дождитесь записи `latest.pt` и завершения Python процесса. Не закрывайте окно посреди записи checkpoint.
2. Сделайте независимую резервную копию `runs/` (или старой установки). Перед очисткой убедитесь, что `runs/<ID>/checkpoints/latest.pt` существует. Старую папку не удаляйте.
3. Распакуйте новый архив отдельно, в `ChessAI-v0.7.0`. Не поверх старой версии.
4. Запустите `UPGRADE_FROM_CURRENT.bat` и укажите полный путь к корню установленной v0.6.0, даже если он переименован. Установщик сначала проверяет файлы и конфликты, затем копирует сохранения с SHA-256. Старую папку не трогает.
5. Если старая папка содержит `.venv-cuda/Scripts/python.exe`, мигратор настроит `config/python_path.txt` на старую CUDA-среду без копирования Torch. Старая папка должна оставаться на месте, пока используется этот интерпретатор.
6. Запустите `scripts/VERIFY_PROGRESS_WINDOWS.bat` и убедитесь, что это номер последнего сохранённого checkpoint, а не ноль.
7. Запустите `START_CHESS_AI.bat`, проверьте `BUILD 0.7.0`, выберите старый эксперимент и сделайте 1–2 пробные итерации, затем повторите `VERIFY_PROGRESS_WINDOWS.bat`.

> [!WARNING]
> Не запускайте старую и новую Training Studio одновременно. Убедитесь, что предыдущий `python -m neural.selfplay` действительно остановлен. Не удаляйте старый проект до проверки новой версии и резервной копии.

Подробно: [историческая инструкция 0.7.0](docs/archive/UPGRADE_TO_0.7.md).

## Быстрый старт 🪟

1. Установите CMake, C++ Build Tools / Visual Studio, Python и зависимости из `requirements.txt`.
2. Для CPU можно использовать `.venv`; для NVIDIA нужен подходящий CUDA PyTorch.
3. Запустите `START_CHESS_AI.bat` и откройте `http://127.0.0.1:8765`.
4. Если порт занят старым процессом — закройте его перед запуском.

## Проверки 🩺

- `scripts/VERIFY_PROGRESS_WINDOWS.bat` — итерация, архитектура весов, оптимизатор и история метрик
- `scripts/BENCHMARK_HARDWARE_WINDOWS.bat` — замер скорости на вашей машине
- `scripts/AUDIT_COLOR_WINDOWS.bat`
- `scripts/EVALUATE_RUN_WINDOWS.bat` — Holdout Evaluation
- `scripts/CHECKPOINT_TOURNAMENT_WINDOWS.bat`
- `scripts/COMPACT_RUNS_WINDOWS.bat` — сжатие журналов для освобождения места

Для освобождения места введите ID эксперимента и подтвердите `YES`. Вы увидите размер до и после. Скрипт не удаляет веса, оптимизатор, checkpoint и историю метрик.

## Тесты 🧪

Python:

```bash
python -m unittest discover -s tests
```

C++:

```bash
cmake --build build --target test
ctest --test-dir build
```

Windows `.bat` и CUDA на физической RTX 3050 в тестовом контейнере не запускались.

## Честные ограничения ⚠️

- Ни одна модель не становится сильнее автоматически от обновления версии.
- Падение loss и высокая загрузка GPU не являются доказательством роста силы игры.
- Бенчмарки ускорения на другом железе не переносятся на вашу машину.
- Тесты Windows `.bat` и CUDA на физической RTX 3050 в тестовом контейнере не проводились.

## Лицензирование ⚖️

Проект предназначен для обучения и игры в разрешённых окружениях. Не используйте систему для скрытого управления человеческими аккаунтами на соревновательных шахматных сайтах.

## Автор 👤

**Kufik** (Onmaynec) · they/them · [@Onmaynec](https://github.com/Onmaynec)

---

**Chess AI 0.7.0** · Encoder: **planes19_actions73_v1** · Совместимость с 0.6.0

## Tactical Intelligence 0.9.3

`START_TACTICAL_TRAINER.bat` — локальный эксперимент генерации задач и тактического дообучения. [Методика](docs/guides/TACTICAL_INTELLIGENCE.md). Не заменяет исходные веса.

### Tactical Learning Overhaul 0.9.3.1

Профили Pilot/Standard/Full, возобновляемая генерация и обучение, стратификация, Top-k/MRR, hard-example weighting и scheduler. `START_TACTICAL_TRAINER.bat`.

### Tactical Mastery 0.9.3.2

Teacher score targets, curriculum, value/negative learning, legal symmetries, bounded retention replay, LR/anti-repetition labs and V3 promotion screening. `START_TACTICAL_TRAINER.bat`.

### Tactical Optimization 0.9.3.3

Optimization/Batch/Replay/Capacity labs, loss and gradient diagnostics, frozen local V4 builder, canonical audit cache and clean-set guard. Start `START_TACTICAL_TRAINER.bat` option 5.

### Neural Scaling & Generalization 0.9.3.4

Family-grouped datasets, initialized Advanced fine-tuning with separate retention teacher, protected categories, GPU lab, round robin and optional independent PGN/UCI evaluation. See [Scaling guide](docs/guides/NEURAL_SCALING.md). Start `START_TACTICAL_TRAINER.bat` option 11.
