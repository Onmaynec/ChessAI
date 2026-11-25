# Neural Scaling & Generalization — 0.9.3.4

Experimental training only. Stop PPO and all local chess sessions. Never replace latest.pt automatically.

## Start
START_TACTICAL_TRAINER.bat → 11. Default initial checkpoint:
tactical_experiments\v0933_capacity_aefae56959\variant_04\candidate.pt
Default retention reference: runs\run_20261123_072154_6a110b\checkpoints\latest.pt.
Both paths can be changed. Existing candidate is the initialization and frozen teacher;
Latest is a separate frozen retention teacher. Advanced is not yet the production model.

Profiles (approximate train/validation counts due to whole families):
Pilot 5000/1000, 24 epochs, minimum 10; Standard 20000/4000, 20 epochs, minimum 8;
Full 50000/10000, 16 epochs, minimum 8. Total dataset sizes exact 6000/24000/60000.
All batch32, depth3, LR 1e-4, seed9342026, early stop patience6.
Generation is expensive and serial. Screening at depth2; full legal scores at depth3.
Attempt budget default 60 per requested row capped at 2 million. Stop with Ctrl+C and
resume via action 12 using the printed v0934 directory, same frozen inputs and optional
increased total attempt limit. No partial dataset is trained. Resume training at epoch boundaries.
Do not modify frozen initial weights, reference, earlier datasets, or suites during run.

## Data
All existing suite_v*.json (including required V4) and prior local dataset/replay JSONL
are excluded by canonical FEN. External prior datasets can be passed via CLI --exclude.
50% of generation attempts use generated trajectories (some start from known openings),
other attempts targeted synthetic positions. Acceptance ratios vary. Quotas prioritize
mate1 and check_evasion (20% each), mate2/fork/capture 12% each, others 4–5%.
The existing relaxed cap can produce quota shortfalls, reported in metadata.
Family ID = side-normalized piece counts and coarse paired king zones, invariant to
rank/color and file reflection. Whole families assigned to one split, approximate validation
size within 90–110% target. Not exhaustive near-duplicate detection; related motifs may
still cross families. Missing protected categories abort training. Prior data is exact
canonical excluded; historical PPO exposure is not proven absent in new validation.
Replay 2048/4096/5000 positions from bounded newest-first run sample, exact dataset/suite
and validation-family exclusion, engine legality checked. Replay is retention, not PPO.

## Training
Continue from Advanced weights (or other explicit checkpoint). Same feature version.
AdamW weight decay .02; training-only head-input dropout .10; train BN statistics;
CPU encoded position storage float16, float32 network batches. No AMP yet.
LR warmup 5 epochs; dynamic curriculum uses current TRAIN target mass and adds hard
positions by epoch6. All examples used after curriculum. Protected category weighting
1.35, capped at5; optimization negative weight .45, value .30, replay .20.
Original initial model remains frozen for policy/value retention; separate Latest teacher
temperature2 distillation with coefficient .15 and T² scaling, replay uses Latest.
Candidate must pass existing aggregate guard AND protected category accuracy must not
drop more than 5 percentage points against BOTH initial checkpoint and Latest on validation.
Early stopping selects best eligible candidate, can finish with none. No optimizer state
migration from PPO. Source and reference hash checked. Report includes separate reference
baseline and per-epoch protected category check. Dataset size, curriculum, initialization
and regularization change together: not an isolated architecture experiment.

## GPU Lab and tournament
Action13: synthetic FP32 forward and AdamW step for batch8/16/32/64; synchronized median
time, throughput and allocated/reserved memory, isolated RAM-only copy, OOM recorded.
Not full trainer throughput (teacher, replay and preprocessing excluded).
Benchmark supports repeatable --extra-agent NAME=CHECKPOINT, max6 models.
Use --suite v4 --profile standard --pairs 32 --max-plies 480 --seed 9342027
--audit-cache benchmark_reports/audit_cache; --extra-agent advanced=... etc.
Round-robin does not feed two-model Promotion Guard. V4 has already been used repeatedly,
so it is a known diagnostic, not an untouched final test. For promotion use two-model
benchmark and existing Guard plus genuinely independent evaluation.

## Independent external evaluation
Optional: install python-chess in the selected environment and supply a local trusted
Stockfish/UCI executable and a previously unused PGN corpus. No automatic download.
python -m benchmark.external_teacher --pgn path/to/new.pgn --uci path/to/stockfish.exe
 --agent latest=... --agent advanced=... --output benchmark_reports/external_01
 --run runs/... --audit-cache benchmark_reports/audit_cache
(One command, or use PowerShell continuation.) Samples at most one nonterminal position
per eligible game, excludes previous suites and datasets/replay, freezes 500 positions
before inference. Reservoir sampling across PGN, seed9349011. Use --positions
external_positions.json instead of --pgn to reuse frozen positions; do not select a new
set based on results. Fixed 50000 nodes per root search, single thread, reports exact best
move agreement/top3/estimated clipped regret/within100cp/missed mate. Finite budget,
not mathematical ground truth. PGN provenance remains user responsibility.
Optional full selected-run canonical audit via paired --run and --audit-cache. No training
with external answers. New independent corpus and teacher are not bundled.

## Reports
Send scaling_report.json, data/dataset_meta.json, replay/replay_meta.json and
train/training_report.json. Candidate is optional. Preserve original run, prior candidates,
all frozen evaluation libraries. No automatic promotion or changes to online gameplay.
