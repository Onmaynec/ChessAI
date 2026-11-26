# Vision Bot 0.9.7 — Advanced Chessboard & Analysis

Review candidate on vision-ui/reengineering. The standalone Qt preview is still read-only and offline; no connection to live games, worker commands, recognition or model changes. The existing operational Tk application is retained.

## Changes
- Original 12 monochrome SVG chess pieces, board coordinates and both orientations.
- Pure board_projection.py: structural FEN board/turn validation, coordinate transformation, reported candidate list, selected move arrow and bounded history (up to 600 analysis records).
- Chessboard.qml, PositionPanel.qml, VariationPanel.qml integrated in overview/analysis with a shared history selection. Navigation uses the records that actually arrived; it is not complete PGN reconstruction.
- Arrows indicate a proposed move or selected candidate, not a move confirmed on a board. The source FEN is the position before the proposed move. Selecting a candidate only changes the arrow, not the position or the reported principal variation. No new engine search.
- Score scale is linear and clamped at ±800 cp, white-oriented conversion of the reported side-to-move score. Mate indication is separate; unknown scores show no bar. Not a win probability or independent position evaluation.
- Two explicitly labeled synthetic analysis events in --fixture exercise history, orientation and candidate selection. Raw structured replay is also supported; old formatted text logs cannot reconstruct structured position records.

## Run on Windows
Use the optional Qt environment from 0.9.6:
```powershell
git pull origin vision-ui/reengineering
.\RUN_VISION_QT_PREVIEW_WINDOWS.bat --fixture
```
If not yet installed:
```powershell
py -3.13 -m venv .venv-qt
.\.venv-qt\Scripts\python.exe -m pip install -r requirements-vision-qt.txt
```
Use the overview/analysis navigation, previous/next buttons, flip and candidate buttons.
Capture the pages:
```powershell
.\.venv-qt\Scripts\python.exe -m tools.vision_qt_capture
```
Output: artifacts/vision-qt.

## Verification
Local execution: 17 Python tests passed (6 board projection, 4 replay, 7 controller), 1 Qt workspace test skipped because PySide6 is unavailable. New board projection and test, modified replay and test, existing analysis_view and ui_state files matched Git blob hashes. Full Qt load/renderer, SVG display, keyboard accessibility, Windows DPI and screenshots have not been verified. CI includes the optional Qt workspace smoke test and pure board test. No visual quality score is claimed.

Next: v0.9.8 workspace and overlay reengineering, with compact/standard/expanded layouts. Full functional integration remains a separate requirement before replacing the existing application.
