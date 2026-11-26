# Vision Bot 0.9.9 — Motion Design & Component Gallery

Review candidate on vision-ui/reengineering. The Qt shell remains a local, read-only preview. No change to training, model weights, recognition, chess engine or operational session control.

## Motion and component system

- Shared typography roles in design.py: caption 11, body 13, section 17, heading 24, metric 26 logical pixels.
- Motion intervals: fast 90 ms (button/toggle color), normal 150 ms (toggle thumb), page 180 ms (short opacity transition). No artificial loading, continuously animated decorations or animated telemetry values.
- UiButton: distinct hover/pressed/selected/disabled states, 2 px keyboard focus border, shared typography.
- UiToggle: actual switch with keyboard semantics and shared focus styling; StatusLabel: color and text together.
- Page transitions retain StackLayout; only opacity changes. A reduce-motion preference skips new transitions and immediately cancels the page fade. A color/thumb animation already running may finish within its short duration.
- Reduce motion is a manual preference, not OS automatic detection. Stored as optional boolean reduced_motion in config/vision_qt_workspace.json; existing geometry and pins preserved. Fixture and --no-save use memory only.
- Component Gallery is the fifth page (Ctrl+5): actual primary/secondary/selected/disabled buttons, switches, semantic statuses, typography, palette and empty metric. Demonstration clicks and statuses are not real session data.
- Settings and Gallery share the same reduced-motion property. All Qt panels consume the same theme and motion preference.

## Launch and review
```powershell
git pull origin vision-ui/reengineering
.\RUN_VISION_QT_PREVIEW_WINDOWS.bat --fixture
```
Use Ctrl+5 in Standard or Expanded mode. Use normal launch without --fixture to persist preferences. If Qt is not installed, see VISION_UI_QT_096.md.

```powershell
.\.venv-qt\Scripts\python.exe -m tools.vision_qt_capture
```
The capture utility now requests 22 images: five pages at three sizes, three modes and four auxiliary windows. No actual captures were generated here.

## Verification
27 Python tests passed locally: 4 motion, 6 preferences, 6 board projection, 7 controller, 4 replay. One Qt workspace test skipped due to missing PySide6. Local design.py, workspace_preferences.py, test_vision_motion_design.py, qt_preview.py and test_vision_qt_preview.py matched branch Git blob hashes. CI adds motion tests and extends the Qt smoke test to fifth-page navigation and binding of reduced motion. Native Qt rendering, animation quality, focus traversal, Windows DPI and frame-time measurements remain unverified. No 95/100 quality score claimed. Keep the PR draft; operational host integration still required.

Next: v0.9.10 Performance & Accessibility.
