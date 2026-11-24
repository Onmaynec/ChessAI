# Chess AI Vision Bot — browser focus hotfix v0.1.1

Fixes the startup error `Chess.com browser window is not foreground; clicks blocked`.

## Why it happened

Previously, the GUI only minimized itself. Windows could bring the desktop, File Explorer, terminal or another application to the foreground. Before the first mouse click the bot correctly refused to click an unrelated window.

## How the fix works

- Finds a **visible Chess.com browser window** running in Chrome, Edge, Firefox, Brave, Opera, Vivaldi, or Yandex Browser.
- If multiple Chess.com windows exist and none is already foreground, refuses to guess and asks you to select/close windows.
- On **Start**, minimizes Vision Bot and requests Windows to focus that precise browser window.
- Verifies the exact same window handle before **each** mouse click. If the focus later changes, it **stops**, never steals focus repeatedly or clicks into other apps.
- Reports a more specific failure including the window title. A focus denial by Windows is reported, not bypassed.

## Install

1. Stop/close **Vision Bot**. Existing **self-play can continue**.
2. Unzip into an unrelated folder and run `INSTALL_VISION_FOCUS_FIX.bat`.
3. Paste the path to the **installed** `ChessAI-v0.7.0` folder, not to this ZIP's extracted folder.
4. Type `YES`. The installer updates only `visionbot/focus.py`, `visionbot/autoplay.py`, `visionbot/gui.py`, and this README.
5. Keep **one Chrome/Edge/Firefox/etc. window** with an active Chess.com **Play Computer** tab open, visible and not covered by popups.
6. Run `START_CHESS_VISION_BOT.bat` as before, and start the computer-bot test. It will transfer focus to Chess.com once at startup.

No need to re-install CUDA, restore the old v0.6.0 environment, or import a new checkpoint.

## Remaining limitations

- This is an experimental computer-bot-only adapter, **not** an official Chess.com integration. Site automation may be restricted by its terms. Never use it against human players or in rated games.
- Windows may disallow a programmatic foreground switch; in that case the bot gives a clear error and prevents clicks.
- If the selected tab title does not include `Chess.com`, if there are multiple active browser windows, or if another application grabs focus, the bot stops safely.
- Screenshot parsing requires a stable browser zoom, orientation, window placement and piece theme. Promotions and new-game selection are not automated.
- Existing self-play is **independent**. Closing/stopping Vision Bot does not imply stopping its training process. Stop training through Training Studio when needed, after a checkpoint is saved.
- The change was unit-tested on this development environment; the Windows GUI and live Chess.com website still require local testing.
