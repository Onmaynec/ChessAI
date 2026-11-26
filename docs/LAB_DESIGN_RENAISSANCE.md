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
Draft: browser and real API regression checks NOT executed in authoring environment. No screenshots or score claimed.
Use tests/lab_ui.spec.js with Playwright in a disposable checkout. Test mocks are isolated browser route fixtures; never run a real training or compaction action in the UI test.
Manual matrix: first launch; stopped/running/failed; self-play/optimization/arena; disconnect/reconnect; CUDA absent; stale files; long history; logs; config and advanced fields; replay; 1920x1080, 1366x768, 1280x720, 1024x768, 390x844; 200% zoom; keyboard focus, dropdowns, reduced motion. Verify before merge.
Known limits: native resume prompts remain; no OS telemetry beyond supplied fields; existing server tail limits; no full chart zoom/pan; local fonts not bundled; no independent visual/accessibility/performance score.
