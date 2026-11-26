# Vision Bot 0.9.8 — Workspace & Overlay Reengineering

Review candidate on vision-ui/reengineering. Read-only local Qt preview; no live game connection or worker commands. Existing operational Tk UI, engine, recognition, training and checkpoints are unchanged.

## Workspace
- Compact (default 360x300): metrics, quick access to board and journal, pin toggle.
- Standard (1040x720): main navigation and focused pages.
- Expanded (1440x900): overview includes position and variations side by side when width permits, or stacked on smaller screens.
- Mode selector in header; Ctrl+Shift+M toggles Compact/Standard. Ctrl+1–4 changes pages in standard/expanded.
- Four independent preview windows: metrics, board, variations, journal. Open via Settings or compact shortcuts; each has a pin toggle. Position history, candidate selection, orientation and journal filters share the same model. Window positions and pins are independent. Closing the main window closes the auxiliary windows.
- Per-mode and per-panel geometry stored in config/vision_qt_workspace.json (gitignored). Persist last mode and main/panel pins. Geometry uses Qt available screen rects, negative coordinates allowed, offscreen windows clamped to an available monitor. Native minimum sizes can still constrain very small displays. Positions restore when windows are opened, not automatic reopening of previously open panels.
- Settings are isolated from operational Vision Bot. JSON validated, atomically replaced; save errors displayed in main settings. Fixture and screenshot tools use memory-only settings; --no-save also disables persistence. Multiple simultaneous preview instances can overwrite each other's preference file; use one instance for persistence.

## Run
```powershell
git pull origin vision-ui/reengineering
.\RUN_VISION_QT_PREVIEW_WINDOWS.bat --fixture
```
Remove --fixture for offline empty preview with saved layout, or use --replay PATH for local telemetry. Existing Qt environment setup is documented in VISION_UI_QT_096.md. Fixture is deliberately synthetic and settings are not persisted.
```powershell
.\.venv-qt\Scripts\python.exe -m tools.vision_qt_capture
```
Capture tool now covers four pages at three sizes, three modes and four panels (19 captures if successful). Output artifacts/vision-qt. No capture was executed in the authoring environment.

## Verification
23 Python tests passed (6 new workspace tests, 17 earlier controller/board/replay tests); one optional Qt workspace test skipped due to missing PySide6. The new workspace module/test and changed replay module/test matched Git blob hashes. Qt smoke test extended for mode switching and panel visibility; not yet executed. CI is configured, not verified. Native window placement, multi-monitor DPI, pin behavior, rendering and screenshot review remain unverified. No visual quality score claimed. Keep main unchanged until acceptance.

Next: v0.9.9 Motion Design & Component Gallery. Operational host integration and regression testing are still required for full replacement.
