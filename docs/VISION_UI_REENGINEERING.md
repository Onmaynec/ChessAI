# Vision UI 0.9.4 / UI Foundation — review candidate

Baseline: main commit 74390b70c265b371d1f8baac13e88c0611d2b3cc; VERSION 0.9.3.4.
Target VERSION: 0.9.4. This is a review branch, not a verified production release.

## Audit and architectural decision
The existing App (visionbot/gui.py) inherits Workspace. The presentation layer owns Tk variables, a queue pump, responsive layout, analysis rendering, log presentation and settings. OverlayManager opens five independent windows with shared session state. Calibration, browser focus, worker lifecycle, consent checks, model switching and stop handling are coupled to Tk callbacks. Replacing Tk with QML without testing these contracts would introduce a significant regression risk. This first increment retains CustomTkinter and isolates reusable presentation logic. Qt/QML remains an option after a tested controller boundary exists.

Observed in source (not runtime): duplicated blue-purple color constants, numbered badges in form sections, repetitive panels, board placed after session controls, scroll reset on geometry changes, no primary journal search/export/pause, and no main-window geometry persistence. The preview is the last reported FEN, not a live camera or confidence map. No fabricated confidence or telemetry is added.

## Design system and navigation
- visionbot/design.py: semantic neutral colors, typography roles, button states, spacing and radius foundations. White primary button has black text; secondary actions use dark surfaces. Green/red remain informational; labels accompany states.
- visionbot/workspace.py: wide composition is board/analysis first, session controls second; narrow composition has focused pages; compact mode remains available (Ctrl+Shift+M). Explicit version reads VERSION. Native Windows decorations are retained.
- visionbot/overlays.py: shared colors and control styles for Control, Journal, Analysis, Board and Console.
- visionbot/log_model.py: pure filtering and search. Journal's full page has pause/follow/copy/export; pause uses a frozen snapshot while worker logging continues. Copy/export contain displayed text, not the entire persistent file. In-memory history is limited to 600 events; existing on-disk rotation is unchanged.
- Settings retain previous JSON keys, with additive geometry, follow_log and topmost. Primary-screen clamping is conservative; multi-monitor negative-coordinate restoration is not yet implemented.

## 0.9.4 refinement
- Responsive board sizing based on actual preview width, stacked details on narrow panels, two-column forms only where the panel width permits.
- Labeled navigation rail, Ctrl+1–5 page navigation, visible Compact action and compact latest-event summary. Stop buttons use a separate semantic style.
- Deferred page scroll restoration, bounded filtered journal with displayed/total counters, separated search and export controls, frozen pause snapshots. New installations default to opaque windows; existing opacity settings remain respected.
- Explicit setup / ready / active / stopping / stopped state mapping; ready and active are distinct in text. No synthetic telemetry.
- CustomTkinter retained for this foundation increment; QML/controller split belongs to a later migration.

## Regression checklist (not executed here)
| Contract | Verification |
|---|---|
| Start / join / stop; computer-only consent | Test permitted local/computer sessions, cancel and close |
| Calibration and overlap guard | Calibrate, move panels, reject overlap |
| Agent / UCI profiles and live agent switch | Test idle and permitted active sessions |
| FEN / orientation / preview / candidate analysis | Known positions including castling and promotion |
| All five overlays / presets / opacity / topmost | Open, resize, close and reopen each |
| Journal | 600+ mixed events; filtering, pause, export, follow, scrolling |
| Preferences | RU/EN, reopen, change screen resolution; old JSON remains readable |
| Layout | 420x440, 560x600, 900x650, 1280x800 where screen permits |
| Windows DPI | 100/125/150/175/200%, separate runs; multiple monitors |
| Performance | Measure queue, input latency, CPU/RAM with existing local workload |
| Empty / error / loading / recovery | Verify real permitted-session states; no invented telemetry |

## Install and run
From project root, use the existing configured Python environment and Vision requirements:
```powershell
python -m pip install -r requirements-vision.txt
python -m visionbot.gui
python -m unittest discover -s tests -p test_vision_ui_design.py
python -m unittest discover -s tests -p test_vision_presentation_rules.py
python -m tools.vision_ui_capture --fixture
```
If the project uses a separate CUDA interpreter, invoke that interpreter instead of python. Screenshot output: artifacts/vision-ui. The capture utility explicitly disables start/join/calibration and hotkeys, does not write UI preferences, and labels synthetic fixture entries. It records real client-area screenshots; do not cover the window. Run once without --fixture for idle state and repeat at each Windows display scale. It skips sizes that cannot fit the current screen. Inspect before/after from a separate main checkout, then refine with actual screenshots.

## Status / scorecard
Local verification: six pure Python tests passed (two design/journal and four presentation-rule tests). The five tested source/test files were reproduced locally and their Git blob SHA values matched the branch. Full source compilation, CI completion, and the Windows GUI were not verified in the authoring environment: GitHub DNS and CustomTkinter were unavailable. The remote branch is not a local build. No screenshot, native DPI/accessibility validation, load benchmark or full integration regression result is claimed. CI is provided for syntax and focused pure tests, not visual validation. All ten 10-point criteria are **unverified**, total not scored. The 95/100 target remains an acceptance gate. Remaining scope includes full visual iterations, independent component gallery, SVG piece assets, multi-monitor validation, keyboard/focus audit, polished motion and deeper controller separation. No model weights or training/core changes are part of this increment.
