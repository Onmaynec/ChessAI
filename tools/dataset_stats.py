#!/usr/bin/env python3
"""Summarize raw JSONL self-play records. Standard library only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def main() -> None:
    parser = argparse.ArgumentParser(description="Chess AI self-play dataset summary")
    parser.add_argument("file", type=Path, help="JSONL file written by chessai selfplay")
    args = parser.parse_args()
    reasons: Counter[str] = Counter()
    results: Counter[str] = Counter()
    plies = []
    ids = set()
    for line_no, line in enumerate(args.file.open(encoding="utf-8"), 1):
        if not line.strip():
            continue
        try:
            game = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON line {line_no}: {exc}")
        gid = game["game_id"]
        if gid in ids:
            raise SystemExit(f"Duplicate game id: {gid}")
        ids.add(gid)
        if game["plies"] != len(game["moves"]):
            raise SystemExit(f"Bad ply count for game {gid}")
        if game.get("policy") != "random":
            print(f"Warning: unexpected policy for game {gid}")
        results[game["result"]] += 1
        reasons[game["reason"]] += 1
        plies.append(game["plies"])
    print(f"Games: {len(plies):,}")
    print(f"Total plies: {sum(plies):,}")
    if plies:
        print(f"Average plies: {statistics.mean(plies):.1f}")
        print(f"Median plies: {statistics.median(plies):.1f}")
    print("Results:", dict(results))
    print("Termination reasons:", dict(reasons))
    print("IMPORTANT: '*' means unfinished. Random games do NOT equal trained chess skill.")


if __name__ == "__main__":
    main()
