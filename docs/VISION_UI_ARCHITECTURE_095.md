# Vision Bot 0.9.5 — UI Architecture & QML Preparation

Review candidate on vision-ui/reengineering, based on 0.9.4. No model, checkpoint, recognition or move-execution changes.

## Architecture

Worker -> VisionUiController.submit -> thread-safe FIFO -> drain on owning UI thread -> typed UiEvent -> existing Tk presentation / diagnostic log.
SessionSnapshot and AnalysisSnapshot are immutable presentation contracts. Session phase derives from worker/stop/readiness state. Analysis contains only reported engine data (FEN is the last analysis snapshot, not a live captured board).
VisionViewModel exposes read-only QObject properties and change signals; the host must call refresh on the Qt thread. It is not a full application or a second concurrent consumer.

## Changed contracts

- gui.py uses the controller rather than directly parsing worker messages.
- The queue processes up to 24 events within an approximately 8 ms budget per 100 ms pump; time spent by the consumer is counted between events. A single expensive render or synchronous disk write can still exceed the budget.
- The queue remains unbounded to preserve existing delivery semantics; no claim of bounded memory under sustained producer overload.
- Malformed analysis telemetry is classified as a diagnostic error instead of being presented as a normal log.
- workspace.py uses shared session and analysis snapshots. UCI centipawn and mate scores are handled separately; missing values remain unknown.
- Existing start/stop, consent, calibration, overlap safety, worker lifecycle, overlay windows and disk log rotation are retained in the existing host. This increment does not extract the worker lifecycle or all settings into a framework-neutral controller.

## Optional Qt environment

Existing launch remains unchanged: python -m visionbot.gui.
For migration development, use a separate Python environment if necessary:
```powershell
python -m pip install -r requirements-vision-qt.txt
python -m unittest discover -s tests -p test_vision_qt_viewmodel.py -v
```
The Qt test creates a QML object bound to the real QObject adapter; no engine or gameplay is started. No production QML window is included yet.

## Verification

Seven controller tests executed locally and passed on reproduced files matching the Git blob hashes for ui_state.py, ui_controller.py, presentation_rules.py, telemetry.py and test_vision_ui_controller.py. Covered FIFO, time budget, concurrent producers, classification and malformed JSON, analysis/reset, mate and missing values, and idempotent session updates.
Optional Qt/QML test and Windows CI were added but have not been executed locally: PySide6 and CustomTkinter are unavailable and direct GitHub checkout is blocked by DNS in the authoring environment.
No complete GUI regression, Windows DPI, performance benchmark or screenshot results claimed. Prior v0.9.4 visual acceptance remains pending. Keep review PR draft until validated.

## Next milestone

v0.9.6: professional Qt Quick workspace and reusable components, using this adapter as a foundation. Command/lifecycle migration requires a separately tested host boundary, including explicit authorization and stop/capture behavior. Do not remove the existing host until feature parity and visual/functional checks pass.
