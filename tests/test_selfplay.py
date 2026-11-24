"""Integration and numerical tests for neural self-play v0.3.

Run after building C++ core: python -m unittest discover -s tests -p test_selfplay.py -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import torch

from neural.encoding import encode_fen, encode_move, FEATURE_VERSION
from neural.model import ChessNet
from neural.storage import iter_records
from neural.selfplay import (START_FEN, ChessBridge, Game, ppo_train,
                             read_jsonl, returns_for, parse_args, run, sample_moves)

ROOT = Path(__file__).resolve().parents[1]
ENGINE = next((p for p in [ROOT / "build/Release/chessai.exe",
                           ROOT / "build/chessai.exe", ROOT / "build/chessai"] if p.is_file()), None)


@unittest.skipIf(ENGINE is None, "Build C++ core before running bridge integration tests")
class CoreBridgeTests(unittest.TestCase):
    def test_parallel_isolation_and_full_game(self):
        with ChessBridge(ENGINE) as bridge:
            a = bridge.new(1)
            b = bridge.new(2)
            self.assertEqual(a["fen"], START_FEN)
            self.assertEqual(a["legal_moves"].__len__(), 20)
            a = bridge.step(1, "f2f3")
            a = bridge.step(1, "e7e5")
            a = bridge.step(1, "g2g4")
            a = bridge.step(1, "d8h4")  # Fool's mate
            self.assertTrue(a["finished"])
            self.assertEqual(a["result"], "0-1")
            self.assertEqual(a["reason"], "checkmate")
            self.assertEqual(a["legal_moves"], [])
            self.assertEqual(bridge.call("state 2")["fen"], b["fen"])
            bridge.drop(1)
            bridge.drop(2)

    def test_state_and_illegal_move_rejected(self):
        with ChessBridge(ENGINE) as bridge:
            s=bridge.new(17)
            with self.assertRaises(RuntimeError):
                bridge.step(17, "e2e5")
            self.assertEqual(bridge.call("state 17")["fen"],s["fen"])

    def test_actual_endgame_training_and_resume(self):
        # Fast micro-run with a real C++ position, real legal actions and own-policy samples.
        with tempfile.TemporaryDirectory() as location:
            path = Path(location) / "micro"
            fen = "6k1/8/8/8/8/5K2/8/Q7 w - - 0 1"
            opts = ["--engine",str(ENGINE),"--out",str(path),"--iterations","1",
                    "--games-per-iteration","2","--parallel","2","--max-plies","120",
                    "--ppo-epochs","1","--batch-size","16","--arena-games","0",
                    "--start-fen",fen]
            run(parse_args(opts))
            state = json.loads((path/"run_state.json").read_text())
            self.assertEqual(state["status"],"completed")
            self.assertEqual(state["counters"]["games"],2)
            before = read_jsonl(path/"metrics.jsonl")
            self.assertEqual(len(before),1)
            self.assertEqual(before[-1]["iteration"],1)
            self.assertTrue((path/"checkpoints"/"latest.pt").exists())
            run(parse_args(opts+["--resume","--max-plies","140"]))
            self.assertEqual(json.loads((path/"run_metadata.json").read_text())["config"]["max_plies"],140)
            after=read_jsonl(path/"metrics.jsonl")
            self.assertEqual(len(after),2)
            self.assertEqual(after[-1]["iteration"],2)
            self.assertEqual(len(list(iter_records(path,"games.jsonl"))),4)
            first_game=list(iter_records(path,"games.jsonl"))[0]
            self.assertEqual(len(first_game["fens"]),len(first_game["moves"])+1)
            for g in iter_records(path,"games.jsonl"):
                self.assertTrue(g["finished"] if "finished" in g else g["result"] in ("1-0","0-1","1/2-1/2","*"))


class SelfPlayLearningTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(10)
        torch.set_num_threads(2)

    def test_outcomes_match_side_to_move(self):
        initial = {"fen":START_FEN,"legal_moves":["e2e4"]}
        game=Game(1,initial,[START_FEN])
        game.experience=[{"fen":START_FEN,"legal_moves":["e2e4"],"move":"e2e4",
                          "old_logp":0.0,"old_value":0.1,"side":"w"},
                         {"fen":START_FEN.replace(" w "," b "),
                          "legal_moves":["e7e5"],"move":"e7e5","old_logp":0.0,
                          "old_value":-0.1,"side":"b"}]
        game.finished=True
        game.result="1-0"
        self.assertEqual([r["outcome_value"] for r in returns_for(game)],[1.0,-1.0])
        game.result="1/2-1/2"
        self.assertEqual([r["outcome_value"] for r in returns_for(game)],[0.0,0.0])
        game.finished=False
        self.assertEqual(returns_for(game),[])

    def test_ppo_performs_actual_weight_update(self):
        model=ChessNet(8,1).eval()
        opt=torch.optim.AdamW(model.parameters(),lr=0.002)
        moves=["e2e4","d2d4","g1f3","b1c3","e2e3","g2g3","c2c4","f2f4"]
        rows=[]
        for i, move in enumerate(moves):
            legal=["e2e4","d2d4","g1f3","b1c3","e2e3","g2g3","c2c4","f2f4"]
            rows.append({"fen":START_FEN,"legal_moves":legal,"move":move,
                         "old_logp":-2.0,"old_value":0.1,"outcome_value":1.0 if i%2 else -1.0})
        before=model.stem[0].weight.detach().clone()
        metric=ppo_train(model,opt,rows,torch.device("cpu"),temperature=1.1,
                         epochs=2,batch_size=4,clip=.2,value_weight=.5,entropy_weight=.005)
        self.assertEqual(metric["samples"],8)
        self.assertGreater(metric["updates"],0)
        self.assertFalse(torch.equal(before,model.stem[0].weight.detach()))
        for k in ["total_loss","policy_loss","value_mse","entropy"]:
            self.assertIsInstance(metric[k],float)

    def test_no_finished_episodes_no_update(self):
        model=ChessNet(8,1)
        optimizer=torch.optim.AdamW(model.parameters())
        metric=ppo_train(model,optimizer,[],torch.device("cpu"),temperature=1.1,
                         epochs=1,batch_size=4,clip=.2,value_weight=.5,entropy_weight=.005)
        self.assertEqual(metric["samples"],0)
        self.assertIsNone(metric["policy_loss"])


class DashboardApiTests(unittest.TestCase):
    def test_routes_and_validation(self):
        from fastapi.testclient import TestClient
        from dashboard.server import app
        with TestClient(app) as cli:
            self.assertEqual(cli.get("/").status_code,200)
            self.assertEqual(cli.get("/static/app.js").status_code,200)
            self.assertEqual(cli.get("/api/health").status_code,200)
            self.assertEqual(cli.get("/api/overview").status_code,200)
            self.assertEqual(cli.get("/api/overview?run=..%2F..%2Fetc").status_code,400)
            self.assertEqual(cli.post("/api/start",json={"iterations":-1}).status_code,422)
            self.assertEqual(cli.post("/api/stop").status_code,409)


if __name__ == "__main__":
    unittest.main()
