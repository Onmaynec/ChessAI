# Vision Bot 0.9.10 — Performance & Accessibility

Review candidate, read-only local Qt preview. Existing operational Tk GUI, engine, recognition, model and training data unchanged.

## Optimizations
- JournalIndex precomputes casefolded text and reuses equivalent queries. Journal displays up to 600 rows and 8192 characters per row (truncation marked with ellipsis; search applies to displayed text). Source files are not modified.
- Replay retains the newest 600 lines within a 16 MiB raw-byte budget; individual oversized lines skipped. This is an input-retention limit, not a total process RAM guarantee. The full file is still scanned.
- Qt viewmodel caches board snapshots and signals cell changes separately from candidate arrow changes. Journal result and filter signals are separate; equivalent result lists do not trigger reload. SVG raster sizes quantized and cached; ListView delegates reused; gallery lazy-loaded.
- Text scale 100/115/130%, persisted alongside existing workspace preferences. Explicit accessible labels, stronger focus indications, keyboard navigation for journal. Qt uses logical coordinates; no claim of full Windows mixed-DPI or screen-reader validation.

## Reproducible benchmark
```powershell
python -m tools.vision_ui_benchmark --repeats 1000
```
Local synthetic 600-row journal, five samples each with 1000 queries, median mean per query: baseline 1.192771 ms; indexed 0.120096 ms. This is Python filtering only, excluding Qt rendering and index construction. No measured overall CPU/RAM/FPS improvement claimed. Palette contrast on white/muted/dim against black/panel/field: 4.66:1 to 21:1; not a complete accessibility compliance audit.

## Verification and run
31 Python tests passed locally, one Qt workspace test skipped (PySide6 unavailable). New index/test/benchmark and changed replay/preferences files matched Git blob hashes. Qt tests extend board-cell signal and scaling checks but were not run. CI configured; actual Windows rendering, screen reader, native scaling and performance remain unverified. 
```powershell
git pull origin vision-ui/reengineering
.\RUN_VISION_QT_PREVIEW_WINDOWS.bat --fixture
```
Text scaling in Settings. Remove --fixture for persistence. Current Qt preview has no live session commands. Keep draft PR until operational integration and visual acceptance. Next: 0.9.11 Visual QA & Final Refinement.
