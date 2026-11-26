# Vision Bot 0.9.6 — Professional Desktop Interface (Qt preview)

This review candidate introduces the first executable Qt Quick presentation shell. It is a read-only local preview, not a replacement for the operational CustomTkinter host. The existing launch and model/checkpoint paths remain unchanged. No live game, browser automation, calibration, or worker command is exposed by the Qt preview.

## Run on Windows

From the repository root, create an optional isolated environment (Python 3.13 recommended for matching CI):

```powershell
py -3.13 -m venv .venv-qt
.\.venv-qt\Scripts\python.exe -m pip install -r requirements-vision-qt.txt
.\RUN_VISION_QT_PREVIEW_WINDOWS.bat --fixture
```

Without --fixture the preview is empty and offline. Use --replay PATH for a local UTF-8 file containing raw worker telemetry lines (including the @CHESSAI_ANALYSIS@ prefix) or ordinary log messages. Existing formatted text logs can be read as journal text, but they are not raw structured analysis; do not infer metrics from those logs. Fixture values are synthetic and visibly labeled. No files are changed by replay. Up to 600 lines retained; oversized lines are skipped. The entire source is scanned, so huge files may take time. Ctrl+1–4 navigates the four pages.

## Components

- Main.qml: native window, adaptive side navigation, header/footer, overview, analysis, journal and UI settings. At narrower widths metrics stack vertically. Minimum size 560x480.
- UiButton, Surface, Metric, SectionTitle: reusable controls with shared Python design tokens, Basic Qt style, hover/focus/selection states.
- qt_preview.py: isolated launch, source replay and controller initialization; no dependency on the active Tk process.
- qt_viewmodel.py: read-only metrics, filtered local journal and change notifications.
- Settings: optional always-on-top for the preview only; no writes to operational settings.
- FEN is text only in this milestone; dedicated chessboard visualization is reserved for 0.9.7.

## Validation

Four replay tests and seven existing controller tests were actually run locally (11 passed). The new test and replay module match Git blob hashes. QML workspace test was skipped because PySide6 is unavailable. The existing Qt property test and new full workspace test are configured in Windows CI in separate Python processes. No Qt render or screenshots have been verified in this environment, and no Windows GUI quality score is claimed.

Capture actual QML preview screenshots on a machine with PySide6:

```powershell
.\.venv-qt\Scripts\python.exe -m tools.vision_qt_capture
```

Output: artifacts/vision-qt, four pages at three sizes, synthetic source clearly marked. Inspect the results for clipping, layout, contrast and focus. Capture does not launch gameplay. Full migration requires a functional host boundary, live telemetry integration, and regression testing. Keep the old GUI and draft PR until acceptance.
