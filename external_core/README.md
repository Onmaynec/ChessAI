# External Intelligence Core 0.9.3.5 (additive preview)

This is a separate local component. Root VERSION and existing trainer, Vision Bot,
benchmark, C++ executable, config, checkpoints and Python environment are unchanged.
It may be installed while Scaling Pilot runs because it only adds new files and
downloads/extracts official releases; disk/network/CPU load can still slow generation.
Do not launch either external engine until training is stopped or completed.
No pip install, global CUDA modification, git pull, or automatic promotion.

Pinned official releases:
- Stockfish 19 Windows x86-64 universal (CPU auto-detection).
- Lc0 0.32.1 Windows CUDA 12 full package, bundled default network (not claimed strongest).
Assets JSON includes release SHA-256 and exact size from GitHub release metadata.
All archive files, licenses, source notices and runtime DLLs retained.
Each archive verified before extraction; installed files individually hashed.
The installer does not launch executable files; tests use a fake UCI process.
If an installation is incomplete, rerun; existing verified engine folders are reused.
Corrupt existing engine files cause failure instead of overwrite. Inspect and rename
only the affected external_engines/v0935/<engine> folder before retrying.

Run START_EXTERNAL_INTELLIGENCE.bat after stopping training. Choices 1/2 perform
handshake + legal move test; choices 3/4 play locally from standard position.
Reports go into external_engines/v0935/reports. For analysis using PowerShell:
  & $python -B -m external_core.lab --engine stockfish --mode analyse --profile strong --multipv 3
  & $python -B -m external_core.lab --engine lc0 --mode analyse --profile balanced --fen "..."
  Optional --weights path/to/approved.pb.gz for Lc0; local hash recorded.
Profiles fast/balanced/strong/maximum: 4/6/8/12 CPU threads,
256/512/1024/2048 MiB hash and 500/2000/5000/15000 ms search budget;
Lc0 uses cuda-fp16, 2 CPU threads, minibatch 32 and same time budget.
Check actual GPU backend availability on the target PC. No silent CPU fallback.
All moves checked against local C++ legal moves; local game keeps full move history.
The lab is standalone and does not control other software or websites.
Vision Bot integration, external teacher dataset generation, Fusion and GPU scaling
are later work. Existing benchmark/external_teacher.py can already use Stockfish
as an external UCI evaluator when its optional dependencies are installed.

Official downloads: https://stockfishchess.org/download/ and
https://lczero.org/play/download/. Source: https://github.com/official-stockfish/Stockfish
and https://github.com/LeelaChessZero/lc0. Respect their licenses if redistributing.
