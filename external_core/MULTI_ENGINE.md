# Multi-Engine Integration 0.9.3.5.1
Separate graphical LOCAL board, opened from Vision Studio session page (Multi-Engine
Lab button) or START_MULTI_ENGINE_LAB.bat. The external engines are NOT connected to
browser clicking/screen-based autopilot. This supports actual complete local games
including human vs engine and engine vs engine, FEN imports, legal promotions,
move history, live UCI telemetry, a saved JSON journal and one UCI restart/retry.
Both sides choose independently: Human, Stockfish 19, Leela Chess Zero, ChessNet
Policy, ChessNet Hybrid. ChessNet checkpoint picker scans local candidates and
runs/checkpoints. External choices appear if installed.json exists; full file
verification occurs when opening engine. Existing Lc0 relative path fix retained.
Settings are per side. For custom Lc0 weights choose an ASCII filename relative
to the Lc0 executable directory, as required by the existing path hotfix.
ChessNet defaults CPU; limit to one CUDA player per match. UCI profiles use
existing time budgets; neural hybrid uses depth2 (not equal compute). Max 480 plies,
unfinished games never scored as draws. Stop waits for current bounded request;
no force kill of training. Reports external_engines/v0935/matches/match_*.json.
No automatic model updates. Not a tournament rating or online gameplay tool.
Installing changes only Vision GUI/workspace and new local modules, no training,
benchmark libraries, models, config, engine binaries, Python env. Close Vision
before updating. Scaling may continue during installation; do not run matches
while training is active. Core VERSION remains 0.9.3.4 during isolated add-ons.
