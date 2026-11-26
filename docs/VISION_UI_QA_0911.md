# Vision Bot 0.9.11 — Visual QA & Final Refinement

This is a review candidate, not final visual acceptance. The Qt application is still an offline read-only preview; the operational Tk host and its safety boundaries are retained. No change to models, training, recognition or move execution.

## Refinement
Static review identified narrow-window header pressure, missing explicit scroll content heights, oversized panel layout minima, initial page animation risk, and minimized overlay reopening. QML adjustments address these issues; actual rendering has not yet been verified. Overlay metrics are scrollable, and button labels render as plain text.

## Visual evidence
Run in the existing optional Qt environment from the repository root:
```powershell
git pull origin vision-ui/reengineering
.\.venv-qt\Scripts\python.exe -m tools.vision_qt_capture
.\.venv-qt\Scripts\python.exe -m tools.vision_qa_manifest artifacts/vision-qt/manifest.json
```
30 required cases: 15 page/size combinations (5 pages at 1200x800, 800x650, 560x480), 3 workspace modes, 4 overlay windows, 5 pages at 130% text scale and 560x480, and 3 empty-state pages. Synthetic fixture explicitly labeled; idle cases clear the in-memory state. Preferences are not written. Captures include actual logical and PNG dimensions, device pixel ratio, sampled color count, Qt version, platform and warnings. The tool writes a manifest on recoverable capture failure. It checks required case names, duplicates, PNG header/dimensions, requested sizes, uniform frames and QML warnings. A passing manifest is only machine evidence, not image quality or accessibility proof. Platform warnings are retained for manual review. The CI job requests software/offscreen Qt capture and uploads evidence; no CI execution confirmed here.

## Acceptance matrix (all unverified until evidence)
| Criterion | Evidence required |
|---|---|
| Visual hierarchy / typography | Human review of actual images at all sizes |
| Layout / responsiveness | No clipped labels, overlaps or unreachable controls at 100% and 130% |
| Chessboard / data integrity | Compare reported FEN, candidate and evaluation semantics |
| Navigation / keyboard | Real Tab/Shift+Tab, shortcuts, visible focus |
| Motion / reduced motion | Native recording or direct review |
| Overlay lifecycle | Open, minimize, reopen, pin, close, monitor removal |
| Windows DPI | Native runs at 100/125/150/175/200%, mixed monitors |
| Performance | Measure process CPU/RAM and frame timings, not just Python filter benchmark |
| Functional parity | Existing operational GUI behavior and guarded session lifecycle verified before replacement |
| Reliability / recovery | Settings restoration, errors, shutdown, no data loss |

No numeric visual score assigned. The target of 95/100 is not established by pure tests. Do not merge or declare v1.0.0 acceptance before real visual and functional review. The new Qt preview does not have the old host's calibration, session controls, recovery, or live telemetry integration; those gaps are explicit blockers to replacement.

## Local verification
35 Python tests passed (31 existing + 4 new manifest tests), 1 Qt workspace test skipped because PySide6 is absent. The new manifest and its test files were locally reproduced with exact Git blob hashes. Test images are deliberately minimal header fixtures, not real screenshots. No screenshot was generated or reviewed, no actual Qt rendering or Windows behavior claimed. CI and native acceptance remain pending.
