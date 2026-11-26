# Chess AI Lab — Design Renaissance (draft)
Base: v0.9.3.4. Local HTML/CSS/JavaScript and FastAPI retained. No new runtime dependency, API or model format changes. No changes to C++/neural code.

## Audit / mapping
| Existing | New |
|---|---|
| Overview / training start, stop, resume, CSV | Overview / training control |
| Games and analysis | Games / replay with FEN copy |
| Analysis / completion, PPO, warnings | Metrics |
| Analysis / evaluation and tournament | Evaluation |
| Analysis / best checkpoint | Models |
| Analysis / specialists | Agent Lab |
| Analysis / storage, profiling, preservation | Resources and data |
| Runs / logs | Experiments / filtered, pausable log |
| Guide | Methodology |

Two layouts considered: equal-weight dashboard cards versus main research chart plus contextual column. Selected latter: emphasizes real metrics, keeps arena score and process context near primary chart. No fake hardware metrics, Elo or pause control. Available history limited by API (overview 600 metrics, log tail). Charts retain nulls and use supplied iteration IDs; range is local subset, not full disk history. Evaluation score is descriptive, not Elo.

## Tokens and components
CSS custom properties define neutral surfaces, borders, text, semantic colors, spacing and motion. Existing compatible controls retained; sidebar, grouped screens, property rows, chart inspector, dialog and log toolbar added. Local system font fallback; no CDN or external telemetry.

## Start and test
Run START_CHESS_AI.bat as before; open http://127.0.0.1:8765. No frontend build step. Do not expose unauthenticated local API to the internet.
Draft: browser and real API regression checks NOT executed in authoring environment. No screenshots or score claimed. Second iteration replaced resume prompts and destructive confirmations with native accessible styled dialogs, added global selected-run context, and cleared no-run diagnostic views. JavaScript syntax and DOM ID references checked statically.
Use tests/lab_ui.spec.js with Playwright in a disposable checkout. Test mocks are isolated browser route fixtures; never run a real training or compaction action in the UI test.
Manual matrix: first launch; stopped/running/failed; self-play/optimization/arena; disconnect/reconnect; CUDA absent; stale files; long history; logs; config and advanced fields; replay; 1920x1080, 1366x768, 1280x720, 1024x768, 390x844; 200% zoom; keyboard focus, dropdowns, reduced motion. Verify before merge.
Known limits: no OS telemetry beyond supplied fields; existing server tail limits; no full chart zoom/pan; local fonts not bundled; no independent visual/accessibility/performance score.

## Visual Excellence — second development stage
Replaced the old cascading legacy stylesheet with a consolidated local stylesheet covering shell, controls, typography, tables, graphs, diagnostics, log viewer, forms, dialogs and replay. Training status/progress now share one surface, self-play outcome diagram and legend sit side by side, evaluation controls and results history use a responsive research grid. Added visible last-update/disconnection footer and responsive graph geometry with cached data (no network requests on resize). The sidebar mobile tabs retain readable labels. No changes to API, training core, checkpoints or repository VERSION.

### Visual evidence (isolated fixture only)
Local Chromium + Python Playwright rendered a standalone visual fixture using the exact final stylesheet (FNV-1a over UTF-16 units: de5dda42). Fixture states: populated Overview, empty Overview, Evaluation, configuration dialog. Fixture markup was reconstructed from the repository markup, not loaded from FastAPI; all numbers are explicitly synthetic. Initial mobile grid overflow was fixed and retested; second visual refinement corrected mobile navigation and Evaluation layout. Overview document widths matched viewport widths at 1920×1080, 1440×1000, 1366×768, 1280×720, 1024×768, 768×1024, 390×844 and 320×720. Responsive graph text in the fixture is adjusted for display; production JS resize behavior still requires a real integration test. Production screenshots and API regression, full nine-screen visual QA, accessibility audit, actual performance profile and independent score remain pending. Do not merge until verified.

## Advanced Data Visualization — stage 3
- Overview: selectable 25/100/250/all available rows (server maximum 600); history scrubber anchors the iteration while new rows arrive; reset to latest; optional trailing mean of 10 contiguous observations, original values remain visible; comparison snapshot from an explicitly selected other run, aligned by iteration number only, no assertion of comparable training conditions; visible CSV export of raw/mean/reference values.
- Analysis: separate KL, clip fraction, completion and value MSE plots, bounded to the latest 600 rows. Server summaries still cover up to 100,000 rows. Missing measurements are gaps, not zeros, including completion rate for zero games.
- Evaluation: report selection, candidate/reference names, seed, suite, limits, paired score and counts, unique trajectories, W/D/L/unfinished distribution. No fabricated Elo, interval or statistical ranking. Reports expose two additive metadata fields when present. No changes to evaluation execution.
- Resources: measured stage durations and average inference batch history; no invented GPU utilization, no adding potentially overlapping durations. Local SVG; no new dependencies.
- Known limitations: comparison is a manually refreshed snapshot and only intersects visible current-run iterations; smoothing uses the selected window, first nine contiguous observations are blank; scrubber pans rather than free-drag zoom; existing API still returns full analysis series (up to 100,000). Browser integration, actual CUDA training performance, full visual/accessibility regression remain pending.
