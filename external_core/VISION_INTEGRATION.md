# External engine selection in Vision Studio — 0.9.3.5.2

The existing model selector now includes installed Stockfish 19 and Lc0. Choose
a UCI profile, side and board. External browser automation is only for computer
opponents with prior written authorization from Chess.com; Fair Play's computer
exception does not by itself authorize automation. The user must confirm this
and that training is stopped. Computer-specific window title and existing
foreground/legality checks are required, including before each physical click.
Title checks are conservative, not authentication of opponent identity.
No rated/human play support or anti-detection, no browser/API scraping.
If authorization is absent, use the existing manual/local Multi-Engine Lab.
No edits to trainer/weights/suites/venv. Separate external recovery journal per
engine/profile and color under external_engines/v0935/vision_sessions.
The immutable recovery snapshot is installed.json, not a neural checkpoint.
The installation is reverified when UCI starts. Changing engine/profile requires
stopping the session; external recovery cannot switch engines mid-game.
UCI telemetry shows actual depth, score/mate, PV, nodes, NPS and WDL, no fabricated
policy or value. One bounded restart on UCI failure, never choose random fallback.
Lc0 requires successful CUDA test. Use Fast first. Existing computer-only
recognition, calibration and recovery limits remain. Do not install while Vision
runs; Scaling generation can continue while installing but stop before playing.
