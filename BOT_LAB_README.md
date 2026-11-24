# Chess AI Bot Lab — manual Chess.com computer-bot challenge

**Purpose:** test your own already-trained ChessAI model against **Chess.com's computer bots**. This add-on does **not** log in to Chess.com, observe your screen, access undocumented endpoints, click chess.com moves, access other users' games, or provide live assistance against humans. All moves are manually mirrored by the user. It is not approved/endorsed by Chess.com.

## Hotfix: `The system cannot find the path specified` / `Python not configured`

This universal-launch hotfix fixes ambiguous launcher errors. The launcher can be started from the installed project root **or** the extracted addon folder after installation; the installer remembers the project path.

1. Run `INSTALL_BOT_LAB.bat` from this addon folder and choose the `ChessAI-v0.7.0` folder containing `neural`, `scripts`, `runs`, and `START_CHESS_AI.bat`. Type `YES`. Running this installer again safely replaces **only the Bot Lab addon files**, not any training data.
2. Run `ChessAI-v0.7.0\START_CHESSCOM_BOT_LAB.bat` from the installed project.
3. If the new launcher asks for Python, paste the path to your **existing** CUDA environment, e.g. `C:\Users\...\ChessAI-v0.6.0\.venv-cuda\Scripts\python.exe`. The launcher validates it and writes `config/python_path.txt` in UTF-8 (no BOM), so you do not need to re-enter it. It does not copy CUDA packages.
4. If the trained checkpoint is missing, migrate the `runs` folder separately; this addon does not perform migrations.

The launcher checks prerequisites and displays separate errors for incorrect installation directory, missing Python, missing C++ engine, missing checkpoint, and missing dependencies. It never modifies trained weights, optimizer or progress.

## Installation on Windows

1. Unpack this ZIP to a separate folder and run `INSTALL_BOT_LAB.bat`. Enter the absolute path to your current **ChessAI-v0.7.0 project root** (the directory containing `neural/`, `runs/`, `scripts/`). Type `YES`. The installer only adds Bot Lab files and never modifies `runs/`, `models/`, `.venv` or `neural/`.
2. Check that `runs/run_20261123_072154_6a110b/checkpoints/latest.pt` exists and C++ `build/Release/chessai.exe` has been compiled. Your CUDA/CPU Python environment used for Training Studio is reused.
3. Open `START_CHESSCOM_BOT_LAB.bat`. Click **New game**. The network is loaded and **frozen for that single test game**.
4. Click **Open Chess.com → Play Bots**, choose **Play Bots / Play Computer**, a computer opponent and the same color that your model uses. **Never do this in human rated/unrated live games.**
5. When it is **AI's turn**, Bot Lab shows a UCI move (`e2e4`). **You** execute that move on Chess.com, then click **Confirm AI move**.
6. When the Chess.com computer moves, enter its move in UCI format (`e7e5`) or click from/to on the local board. Bot Lab's C++ engine validates all moves. If promotion happens, append `q`, `r`, `b`, or `n`.
7. Repeat. Choose win/draw/loss and save the test report into `runs/<run>/botlab_sessions/`. These are *test-only records* and are **never used as training samples**.

## Simultaneous learning

Open `START_CHESS_AI.bat` in another window and click **Start / resume self-play in background** in Bot Lab (it calls the documented local Training Studio endpoint only after you confirm). Alternatively choose your original run `run_20261123_072154_6a110b` in Training Studio and use **Continue training**. The existing v0.7.0 self-play trainer independently plays thousands of **local simulated games** and updates `latest.pt` / optimizer after iterations. The Bot Lab reads `run_state.json` every 5 seconds. To ensure correct comparisons, it **does not reload the checkpoint mid-game**. Click **New game** to load the latest checkpoint for your next test. If the trainer is already running, don't start a second trainer targeting the same run.

This does **not** train on Chess.com game moves. Chess.com's User Agreement requires prior written authorization for AI/model-training use of its site content. If permission is granted, a separate expressly authorized training pipeline could be considered.

## Important limitations

- Test is **manual**, not fully automatic. Chess.com Public API is read-only and doesn't allow move submission; browser automation is not included.
- The Chess.com Fair Play exception applies to games **against Chess.com computers/bots**, not human opponents.
- CPU inference in Bot Lab is deliberate; it leaves GPU resources for simultaneous self-play. Model snapshots are read-only.
- Keep a backup of `runs`. `botlab_sessions/` grows slowly, one small file per recorded test; it is not PPO experience.
- If checkpoint does not appear, migrate/copy `runs` into this v0.7.0 installation before launching. Do not rename `runs` or overwrite old weights.

Official references (verified November 23, 2026):
- https://www.chess.com/legal/fair-play
- https://www.chess.com/legal/user-agreement
- https://support.chess.com/en/articles/8614091-how-can-i-play-against-the-chess-com-bots
- https://support.chess.com/en/articles/9650547-what-is-the-pubapi-and-how-do-i-use-it

## Universal launcher hotfix (November 23, 2026)

If the installer reports success but the launcher says it is "outside an installed project", you probably started the launcher from the extracted addon folder. This release supports **both** launch locations:

- Run `INSTALL_BOT_LAB.bat` once against the real project root. The installer copies files and stores a `BOT_LAB_INSTALL_ROOT.txt` pointer beside the extracted addon launcher.
- Run `START_CHESSCOM_BOT_LAB.bat` either from the `ChessAI-v0.7.0` root or from the extracted addon directory. If the pointer is absent, the launcher asks for the project root once.
- If the CUDA Python is missing in the new project, paste the path of the existing v0.6.0 `.venv-cuda\Scripts\python.exe`.
- No run, optimizer, checkpoint, or model file is modified by installation or launcher setup.

PowerShell direct launch using the confirmed project root:

```powershell
$root = 'C:\Users\Мамлеев Роман\Downloads\ChessAI_v0.7.0_Training_Performance_Intelligence\ChessAI-v0.7.0'
& "$root\START_CHESSCOM_BOT_LAB.bat"
```
