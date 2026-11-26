# Vision Bot Reborn v0.10.0 — Qt Quick migration candidate

The prior versions retained CustomTkinter for real operations and a separate Qt preview. User rejected the real desktop redesign. This version changes the primary Python entrypoint to Qt, adds a new QML screen and connects the existing Vision worker; it is not yet an accepted stable release.

## Start
From the existing repository (do not clone into a new folder unless you migrate runs separately):
```powershell
git fetch origin
git switch vision-ui/reengineering
git pull --ff-only origin vision-ui/reengineering
.\START_VISION_REBORN.bat
```
The new launcher prefers .venv-cuda, then .venv, then .venv-qt, then python. It offers installation of missing Qt/capture packages; it does not install or replace Torch. The UI opens without a checkpoint; select any discovered runs/<id>/checkpoints/*.pt. An existing compatible Torch installation and C++ engine are needed for the worker. Existing launchers with old prechecks may still block before the Python entrypoint: use the new BAT. Old GUI available explicitly via START_VISION_LEGACY.bat or python -m visionbot.gui --legacy. Qt preview remains available separately.

## Scope
- Native Qt Quick Reborn.qml (sidebar, center board and analysis, inspector, narrow layout, styled dropdown, journal and settings).
- Run and checkpoint catalog from actual local disk; no fixed run ID; no changes to weights, PPO, optimizers or training records for discovery. Local raw telemetry import.
- Qt-only screenshot selection on the primary monitor; saved legacy calibration read, validated again at start. Native window bounds check requires per-monitor DPI awareness; if unavailable, launch fails closed.
- Qt session adapter calls the existing VisionAutoplay worker only in explicitly authorized computer-only tests. Window title and authorization are checked before launch; existing per-click computer-only guard enabled for Qt neural sessions. Existing recognition and recovery used; no new click logic. Stop / ESC and orderly close; Qt timer consumes events and logs. Board remains last reported analysis position, not continuous screenshot.
- No actual Qt runtime or Windows automation executed during development. Qt render, calibration, native monitor mapping, lifecycle and usability need testing. No full parity claim: attach-any-position, external UCI selection, agent switching, self-play toggle, compact/independent overlay windows and global start shortcuts not yet wired into Reborn. Legacy remains explicit fallback. Separate preview is not the primary product.
- New preference file config/vision_reborn_ui.json; existing vision_bot.json retains calibration schema. Do not run Qt and legacy sessions simultaneously.

## Verification
4 local Python tests passed on the exact run_catalog.py and test_vision_reborn.py Git blobs (empty catalog, actual runs, invalid/missing checkpoint, engine paths). One optional QML test skipped: PySide6 absent here. Independent Windows CI job configured to load Qt offscreen and exercise navigation and rejection of unauthorized start; no CI success confirmed. Native behavior and visual quality require real review. Keep draft PR, no merge to main.
