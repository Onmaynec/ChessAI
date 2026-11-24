"""Supervised chess policy/value training. Run: python -m neural.train --data output/teacher.jsonl"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from .encoding import FEATURE_VERSION, POLICY_SIZE, encode_fen, encode_move, score_to_value
from .model import ChessNet


class PositionDataset(Dataset):
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        legal_mask = torch.zeros(POLICY_SIZE, dtype=torch.bool)
        legal_mask[[encode_move(m) for m in row["legal_moves"]]] = True
        return (torch.from_numpy(encode_fen(row["fen"])),
                torch.tensor(encode_move(row["best_move"]), dtype=torch.long),
                torch.tensor(score_to_value(row["score_cp"]), dtype=torch.float32), legal_mask)


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")
    rows = []
    seen = set()
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row["fen"], str) or not isinstance(row["best_move"], str):
                    raise ValueError("Invalid fields")
                if not isinstance(row["score_cp"], (float, int)) or not math.isfinite(row["score_cp"]):
                    raise ValueError("Nonfinite centipawn score")
                # Fail early with helpful line numbers.
                move_id = encode_move(row["best_move"])
                encode_fen(row["fen"])
                legal_ids = [encode_move(m) for m in row["legal_moves"]]
                if not legal_ids or move_id not in legal_ids:
                    raise ValueError("Teacher's best_move must be in legal_moves")
                if row["fen"] in seen:
                    continue
                rows.append(row)
                seen.add(row["fen"])
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"Malformed teacher example at line {line_number}: {exc}") from exc
    if len(rows) < 8:
        raise ValueError("At least 8 unique valid teacher positions are required")
    return rows


def run_epoch(model: ChessNet, loader: DataLoader, device: torch.device,
              optimizer: torch.optim.Optimizer | None, value_weight: float) -> dict:
    training = optimizer is not None
    model.train(training)
    total = count = correct = 0
    total_policy = total_value = total_abs_value = 0.0
    for x, labels, targets, legal_mask in loader:
        x = x.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        legal_mask = legal_mask.to(device, non_blocking=True)
        with torch.set_grad_enabled(training):
            logits, value = model(x)
            # Mask illegal moves DURING training, identically to live inference.
            logits = logits.masked_fill(~legal_mask, -1e9)
            policy_loss = nn.functional.cross_entropy(logits, labels)
            value_loss = nn.functional.mse_loss(value, targets)
            loss = policy_loss + value_weight * value_loss
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
        batch = labels.size(0)
        count += batch
        total += loss.item() * batch
        total_policy += policy_loss.item() * batch
        total_value += value_loss.item() * batch
        total_abs_value += (value.detach() - targets).abs().sum().item()
        correct += int((logits.detach().argmax(dim=1) == labels).sum().item())
    return {"loss": round(total / count, 6), "policy_ce": round(total_policy / count, 6),
            "value_mse": round(total_value / count, 6),
            "value_mae": round(total_abs_value / count, 6),
            "policy_top1_legal": round(correct / count, 6)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ChessAI's ORIGINAL compact policy/value network")
    parser.add_argument("--data", default="output/teacher.jsonl", type=Path)
    parser.add_argument("--out", default="models", type=Path)
    parser.add_argument("--epochs", default=12, type=int)
    parser.add_argument("--batch-size", default=64, type=int)
    parser.add_argument("--lr", default=0.001, type=float)
    parser.add_argument("--channels", default=48, type=int)
    parser.add_argument("--blocks", default=3, type=int)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--resume", type=Path, help="Resume from last or best checkpoint")
    parser.add_argument("--value-weight", default=0.25, type=float)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.lr <= 0 or args.value_weight < 0:
        parser.error("epochs, batch-size, lr must be positive; value-weight must be nonnegative")
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    torch.set_num_threads(min(6, max(1, torch.get_num_threads())))
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else
                          "cpu" if args.device == "auto" else args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was requested but this PyTorch installation has no CUDA support")
    rows = read_rows(args.data)
    ids = list(range(len(rows)))
    random.Random(args.seed).shuffle(ids)
    split = min(len(rows) - 1, max(1, round(len(rows) * 0.10)))
    train_rows = [rows[i] for i in ids[split:]]
    val_rows = [rows[i] for i in ids[:split]]
    train_loader = DataLoader(PositionDataset(train_rows), batch_size=args.batch_size,
                              shuffle=True, num_workers=0, pin_memory=device.type == "cuda")
    val_loader = DataLoader(PositionDataset(val_rows), batch_size=args.batch_size,
                            shuffle=False, num_workers=0, pin_memory=device.type == "cuda")
    model = ChessNet(args.channels, args.blocks).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    start_epoch, best_loss = 0, float("inf")
    if args.resume:
        ckpt = torch.load(str(args.resume), map_location="cpu", weights_only=True)
        if ckpt.get("feature_version") != FEATURE_VERSION:
            raise ValueError("Feature version mismatch")
        if ckpt["config"] != model.config:
            raise ValueError("Network config mismatch: use the checkpoint's --channels and --blocks")
        if ckpt.get("seed") != args.seed or ckpt.get("data_count") != len(rows):
            raise ValueError("For reproducible validation, resume with the same seed/dataset")
        model.load_state_dict(ckpt["model"])
        if ckpt.get("optimizer") is not None:
            optimizer.load_state_dict(ckpt["optimizer"])
        start_epoch = int(ckpt["epoch"])
        best_loss = float(ckpt.get("best_val_loss", float("inf")))
    args.out.mkdir(parents=True, exist_ok=True)
    history_file = args.out / "train_history.jsonl"
    if not args.resume:
        history_file.write_text("", encoding="utf-8")
    parameter_count = sum(p.numel() for p in model.parameters())
    print(f"Device: {device} | train: {len(train_rows)} | validation: {len(val_rows)}"
          f" | parameters: {parameter_count:,} | teacher examples: {len(rows)}", flush=True)
    print("Teacher policy is a WEAK alpha-beta baseline. Supervised learning is NOT RL/self-play.", flush=True)
    for epoch in range(start_epoch + 1, start_epoch + args.epochs + 1):
        train_metrics = run_epoch(model, train_loader, device, optimizer, args.value_weight)
        with torch.no_grad():
            val_metrics = run_epoch(model, val_loader, device, None, args.value_weight)
        improved = val_metrics["loss"] < best_loss
        if improved:
            best_loss = val_metrics["loss"]
        record = {"epoch": epoch, "train": train_metrics, "validation": val_metrics,
                  "device": str(device), "best": improved, "feature_version": FEATURE_VERSION}
        ckpt = {"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                "config": model.config, "feature_version": FEATURE_VERSION,
                "epoch": epoch, "seed": args.seed, "data_count": len(rows),
                "best_val_loss": best_loss, "metrics": record}
        torch.save(ckpt, args.out / "neural_last.pt")
        if improved:
            torch.save(ckpt, args.out / "neural_best.pt")
        with history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"Epoch {epoch:>3} | train={train_metrics['loss']:.4f} | val={val_metrics['loss']:.4f}"
              f" | val_policy_top1={val_metrics['policy_top1_legal']:.1%}"
              f" | val_value_mae={val_metrics['value_mae']:.4f}"
              f" | best={'yes' if improved else 'no'}", flush=True)
    print(f"Checkpoints: {args.out/'neural_best.pt'} and {args.out/'neural_last.pt'}")


if __name__ == "__main__":
    main()
