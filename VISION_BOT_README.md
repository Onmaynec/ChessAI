# Chess AI v0.7.0 — Vision Computer Bot (experimental)

This is a desktop *computer-vision prototype*, **not** an official Chess.com integration. Chess.com's Fair Play exception for games against its computer bots does not grant permission for all forms of automated website access; using Chess.com content to train neural networks requires separate authorization. **Only run in Play Computer against nonhuman bots**. It is not for live/rated games against humans. It does not attempt captcha bypass, browser injection, credential capture or anti-bot evasion. You are responsible for complying with the site's terms.

## What it does

- Loads your own `runs/run_20261123_072154_6a110b/checkpoints/latest.pt` or `best.pt` **without changing it**.
- Takes calibrated screenshots locally through `mss` (no DOM, no HTTP to chess.com).
- Learns the appearance of all pieces from the **standard starting position** on the screen, then compares each screenshot with *legal* moves from the C++ Chess AI engine.
- Clicks the model's move in the browser automatically, but **only after you opt in to computer-bot mode** and the foreground window title contains `Chess.com`.
- Verifies the move visually before proceeding; waits for two consistent recognitions of the opponent move. It **stops** if the position is uncertain.
- Can start or reuse local v0.7.0 Training Studio and resume **500 independent self-play iterations** using the same run. No Chess.com data enters training. The current test game has frozen weights; new games can use newly saved checkpoints.
- Records evaluation logs separately in `runs/<run>/botlab_sessions`.

## Install

1. Install the earlier `Computer Bot Lab` addon into ChessAI-v0.7.0 first (its `botlab/session.py` must exist).
2. Extract this ZIP separately and run `INSTALL_CHESS_VISION_BOT.bat`. Paste the full path of your **existing v0.7.0** folder; confirm YES.
3. From your **installed** ChessAI-v0.7.0 folder, open PowerShell and run:

   ```powershell
   .\.venv-cuda\Scripts\python.exe -m pip install -r requirements-vision.txt
   ```

   Or replace `.venv-cuda` with whichever Python environment you configured in `config/python_path.txt`. PyTorch CUDA itself must already be installed in that environment; the vision requirements **do not reinstall torch**.
4. Run `START_CHESS_VISION_BOT.bat` from the **installed project**.

If you deleted the old v0.6.0 Python environment, create a fresh `.venv-cuda` **inside v0.7.0** and install the project requirements and CUDA build there. A deleted virtual environment cannot be reused. Use the current matching PyTorch CUDA wheel for your Python version, not a hardcoded wheel from a different machine.

## One-time board calibration and use

1. Open `https://www.chess.com/play/computer` in Edge/Chrome; choose a **computer bot**, standard 8×8 chess, standard initial position. The browser must remain on screen at the same zoom/resolution and square position. **Do not start the Chess.com game until Vision Bot is ready.**
2. Start Vision Bot, pick the **AI side** (white/black), `latest.pt` or `best.pt`.
3. Press **Выделить область шахматной доски**. With the website visible in the screen preview, **drag a tight square around the entire board** from its top-left to bottom-right. This calibration is saved in `config/vision_bot.json` and is reusable if the board stays in the same location. One-time mouse setup is needed; **no manual chess moves** afterward.
4. Check the opt-in box and press **Запустить автопилот**. The Vision window minimizes; leave the Chess.com tab foreground and do not move/resize the browser or change zoom. If selected, self-play starts/resumes in parallel via localhost Training Studio on port 8765.
5. **ESC** anywhere stops the bot at its next poll. Restore the Vision window from the taskbar to inspect log messages or click Stop. Moving the mouse to the top-left also triggers PyAutoGUI's fail-safe.

## Current technical limitations (important)

- **Experimental**: algorithms were verified on synthetic boards, **not** on a live Chess.com browser. Piece themes, animation, move indicators, browser zoom, overlays and board flipping may cause recognition to stop or misclassify a move. Review the actual first run carefully; do not leave the browser unattended for a long period.
- Requires the standard initial chess position. The tool cannot reconstruct a midgame FEN from an arbitrary screenshot.
- Does **not** automatically select a bot, start another new game, handle puzzles or click through pop-ups. The user starts the on-site game and calibrates the board.
- In-game **promotion selector is not automated**. When AI chooses a promotion, it stops before clicking. This is safer than clicking an unverified popup.
- If UI focus changes, the Chess.com window-title guard blocks clicks. The bot cannot verify that the opponent is nonhuman by title alone; using it against people is expressly outside its intended mode.
- Requires `runs/.../checkpoints/latest.pt` and `build/Release/chessai.exe` (or build/chessai.exe). If these disappeared when you deleted v0.6.0, restore them before launching.
- Online test results are **not** used as training input. Only your own C++ self-play data goes to PPO.
- Chess.com account and site permissions are independent from whether the script technically operates. This prototype is not a claim of authorization by Chess.com.

## Privacy and data integrity

The addon writes only: `config/vision_bot.json`, optional `vision_dashboard.log`, and independent small test reports inside `botlab_sessions/`. It can request local Training Studio to resume a run, which updates normal training data. It **never overwrites or deletes** an existing checkpoint directly. Back up your trained `runs` before first use. An already-running self-play is reused rather than duplicated.
