"""Neural move selection through the v0.2 C++ legal move generator.

Modes:
  python -m neural.agent rank --fen "..."
  python -m neural.agent play --color white
  python -m neural.agent uci

A legal move is always selected from the trusted C++ generator. No screen control.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import torch

from .checkpoint import load_model
from .encoding import encode_fen, encode_move

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def call_core(engine: Path, *args: str) -> str:
    proc = subprocess.run([str(engine.resolve()), *args], capture_output=True, text=True,
                          timeout=10, check=False)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "Chess core failed")
    return proc.stdout.strip()


def legal(engine: Path, fen: str) -> list[str]:
    return json.loads(call_core(engine, "legal-json", fen))["moves"]


def apply(engine: Path, fen: str, move: str) -> str:
    return call_core(engine, "apply", move, fen)


@torch.inference_mode()
def rank(model, fen: str, moves: list[str]) -> tuple[list[tuple[str, float]], float]:
    if not moves:
        return [], 0.0
    device = next(model.parameters()).device
    x = torch.from_numpy(encode_fen(fen)).unsqueeze(0).to(device)
    policy, value = model(x)
    # Rank ONLY legal moves. Non-promotions and queen promotions are distinct by origin/target;
    # minor promotions use their own special action plane.
    indices = [encode_move(m) for m in moves]
    legal_logits = policy[0, indices]
    probs = legal_logits.softmax(0).cpu().tolist()
    order = sorted(zip(moves, probs), key=lambda pair: pair[1], reverse=True)
    return order, float(value.item())


def pretty_board(fen: str) -> str:
    rows = fen.split()[0].split("/")
    lines = []
    for r, row in enumerate(rows):
        expanded = "".join("." * int(c) if c.isdigit() else c for c in row)
        lines.append(f"{8-r}  {' '.join(expanded)}")
    return "\n".join(lines) + "\n   a b c d e f g h\n"


def local_play(engine: Path, model, color: str) -> None:
    fen = START_FEN
    print("Local chess versus YOUR trained network. Enter UCI moves (e2e4) or 'quit'.")
    print("It may play badly on a tiny/weak training dataset.")
    while True:
        moves = legal(engine, fen)
        print("\n" + pretty_board(fen))
        if not moves:
            print("No legal moves — checkmate or stalemate.")
            return
        human = (fen.split()[1] == "w") == (color == "white")
        if human:
            text = input("Your move > ").strip().lower()
            if text in ("quit", "exit"):
                return
            if text not in moves:
                print("Illegal move. Available:", " ".join(moves))
                continue
            fen = apply(engine, fen, text)
        else:
            candidates, value = rank(model, fen, moves)
            chosen = candidates[0][0]
            print(f"Neural move: {chosen} | predicted value (side to move): {value:+.3f}")
            fen = apply(engine, fen, chosen)


def uci_session(engine: Path, model) -> None:
    fen = START_FEN
    for line in sys.stdin:
        bits = line.strip().split()
        if not bits:
            continue
        cmd = bits[0]
        try:
            if cmd == "quit":
                return
            if cmd == "uci":
                print("id name ChessAI-v0.4-Neural-Agent")
                print("id author Chess AI Project")
                print("uciok")
            elif cmd == "isready":
                print("readyok")
            elif cmd == "ucinewgame":
                fen = START_FEN
            elif cmd == "position":
                if len(bits) < 2:
                    raise ValueError("Missing position details")
                if bits[1] == "startpos":
                    fen = START_FEN
                    rest = bits[2:]
                elif bits[1] == "fen":
                    fen = " ".join(bits[2:8])
                    rest = bits[8:]
                else:
                    raise ValueError("Expected startpos or fen")
                if rest:
                    if rest[0] != "moves":
                        raise ValueError("Expected moves marker")
                    for move in rest[1:]:
                        fen = apply(engine, fen, move)
            elif cmd == "go":
                moves = legal(engine, fen)
                best = rank(model, fen, moves)[0]
                print("bestmove " + (best[0][0] if best else "0000"))
            elif cmd == "stop":
                pass  # 'go' is synchronous in this foundation release.
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"info string ChessAI error: {exc}")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("rank", "play", "uci"))
    parser.add_argument("--checkpoint", type=Path, default=Path("models/neural_best.pt"))
    parser.add_argument("--engine", type=Path, default=(Path("build/Release/chessai.exe") if sys.platform == "win32" else Path("build/chessai")))
    parser.add_argument("--fen", default=START_FEN)
    parser.add_argument("--color", choices=("white", "black"), default="white")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    if not args.engine.is_file():
        parser.error(f"C++ chess core executable not found: {args.engine}. Build first.")
    if not args.checkpoint.is_file():
        parser.error(f"Model checkpoint not found: {args.checkpoint}. Train first.")
    torch.set_num_threads(min(6, max(1, torch.get_num_threads())))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_model(args.checkpoint, device)
    if args.mode == "play":
        local_play(args.engine, model, args.color)
    elif args.mode == "uci":
        uci_session(args.engine, model)
    else:
        candidates, value = rank(model, args.fen, legal(args.engine, args.fen))
        print("Value (side to move):", round(value, 4))
        for move, probability in candidates[:max(1, args.top)]:
            print(f"{move:6} {probability:.4%}")


if __name__ == "__main__":
    main()
