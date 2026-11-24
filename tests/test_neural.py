import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import torch

from neural.encoding import encode_fen, encode_move, POLICY_SIZE, score_to_value
from neural.model import ChessNet
from neural.agent import START_FEN, rank, apply, legal
from neural.train import read_rows
from neural.checkpoint import load_model
from neural.encoding import FEATURE_VERSION


class FeatureTests(unittest.TestCase):
    def test_start_planes(self):
        x = encode_fen(START_FEN)
        self.assertEqual(x.shape, (19, 8, 8))
        self.assertEqual(x[:12].sum(), 32)
        self.assertEqual(x[0, 1].sum(), 8)
        self.assertEqual(x[6, 6].sum(), 8)
        self.assertEqual(x[12].sum(), 64)
        self.assertEqual(x[13:17].sum(), 256)
        self.assertEqual(x[17:].sum(), 0)

    def test_turn_and_ep(self):
        x = encode_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
        self.assertEqual(x[12].sum(), 0)
        self.assertEqual(x[17, 2, 4], 1)

    def test_actions(self):
        actions = ["e2e4", "e2e3", "e1g1", "e1c1", "g1f3", "a7a8q", "a7a8n", "a7b8r", "h2h1b", "e5d6"]
        for uci in actions:
            a = encode_move(uci)
            self.assertTrue(0 <= a < POLICY_SIZE, uci)
        self.assertEqual(encode_move("a7a8q"), encode_move("a7a8"))
        self.assertNotEqual(encode_move("a7a8n"), encode_move("a7a8q"))
        self.assertNotEqual(encode_move("a7a8r"), encode_move("a7a8n"))
        self.assertNotEqual(encode_move("a7b8r"), encode_move("a7a8r"))
        with self.assertRaises(ValueError):
            encode_move("e2e9")
        with self.assertRaises(ValueError):
            encode_fen("invalid")

    def test_model_policy_and_value(self):
        model = ChessNet(16, 1).eval()
        with torch.no_grad():
            logits, values = model(torch.randn(2, 19, 8, 8))
        self.assertEqual(logits.shape, (2, POLICY_SIZE))
        self.assertEqual(values.shape, (2,))
        self.assertTrue((values.abs() <= 1.0).all().item())
        self.assertLess(score_to_value(-300), 0)
        self.assertGreater(score_to_value(300), 0)

    def test_teacher_data_validation_and_dedup(self):
        with TemporaryDirectory() as temp:
            filename = Path(temp) / "positions.jsonl"
            example = {"fen": START_FEN, "best_move": "e2e4", "score_cp": 12,
                       "legal_moves": ["e2e4", "e2e3"]}
            filename.write_text("\n".join(json.dumps(example) for _ in range(9)) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "At least 8 unique"):
                read_rows(filename)
            example["legal_moves"] = ["a2a3"]
            filename.write_text(json.dumps(example) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "best_move must be in legal_moves"):
                read_rows(filename)

    def test_checkpoint_round_trip(self):
        with TemporaryDirectory() as temp:
            filename = Path(temp) / "model.pt"
            model = ChessNet(16, 1).eval()
            torch.save({"model": model.state_dict(), "config": model.config,
                        "feature_version": FEATURE_VERSION}, filename)
            restored = load_model(filename)
            with torch.no_grad():
                a, b = model(torch.randn(1, 19, 8, 8))
                self.assertEqual(a.shape, (1, POLICY_SIZE))
                self.assertEqual(b.shape, (1,))
                for parameter, restored_parameter in zip(model.parameters(), restored.parameters()):
                    self.assertTrue(torch.equal(parameter, restored_parameter))

    def test_cpp_protocol_when_built(self):
        engine = next((p for p in (Path("build/chessai"), Path("build/Release/chessai.exe"),
                                  Path("build/chessai.exe")) if p.is_file()), None)
        if engine is None:
            self.skipTest("C++ engine executable is not built")
        self.assertIn("e2e4", legal(engine, START_FEN))
        self.assertIn(" b ", apply(engine, START_FEN, "e2e4"))

    def test_masking_always_legal(self):
        model = ChessNet(16, 1).eval()
        moves = ["e2e3", "e2e4", "g1f3"]
        result, value = rank(model, START_FEN, moves)
        self.assertEqual(set(m for m, _ in result), set(moves))
        self.assertAlmostEqual(sum(p for _, p in result), 1.0, places=5)
        self.assertTrue(-1 <= value <= 1)


if __name__ == "__main__":
    unittest.main()
