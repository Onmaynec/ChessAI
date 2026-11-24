"""Non-mutating CPU/CUDA micro-benchmark; NOT a training-speed/Elo claim.

Run from the project root with the same Python that runs Training Studio.
  python -m tools.benchmark_runtime --engine build/chessai
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import torch
from neural.encoding import INPUT_CHANNELS
from neural.model import ChessNet
from neural.selfplay import START_FEN, ChessBridge, atomic_json

ROOT = Path(__file__).resolve().parents[1]


def torch_bench(device: str, config: dict, samples: int = 16) -> dict:
    dev = torch.device(device)
    torch.manual_seed(3407)
    net = ChessNet(**config).to(dev)
    optimizer = torch.optim.AdamW(net.parameters(),lr=0.0003)
    results = {}
    for batch in (1, 8, 32, 128):
        x = torch.randn((batch, INPUT_CHANNELS, 8, 8), device=dev)
        action = torch.zeros(batch,dtype=torch.long,device=dev)
        # Warm up kernels and lazy torch operations outside timed region.
        for _ in range(3):
            net.eval()
            with torch.inference_mode():net(x)
        if dev.type=='cuda':torch.cuda.synchronize()
        begin = time.perf_counter()
        net.eval()
        with torch.inference_mode():
            for _ in range(samples):net(x)
        if dev.type=='cuda':torch.cuda.synchronize()
        infer_ms = 1000*(time.perf_counter()-begin)/samples
        net.train()
        begin = time.perf_counter()
        for _ in range(samples):
            policy,value=net(x)
            loss=policy.gather(1,action[:,None]).mean() + (value**2).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        if dev.type=='cuda':torch.cuda.synchronize()
        train_ms = 1000*(time.perf_counter()-begin)/samples
        results[str(batch)]={'forward_ms':round(infer_ms,4),'forward_backward_ms':round(train_ms,4)}
    return results


def chess_core_bench(engine: Path, positions: int = 400) -> dict:
    if not engine.is_file():
        return {'status':'unavailable','reason':'C++ chess core executable missing'}
    start = time.perf_counter()
    with ChessBridge(engine) as bridge:
        state=bridge.new(42,START_FEN)
        for i in range(positions):
            if state['finished']:
                bridge.drop(42)
                state=bridge.new(42,START_FEN)
            action=state['legal_moves'][i%len(state['legal_moves'])]
            state=bridge.step(42,action)
        bridge.drop(42)
    seconds=time.perf_counter()-start
    return {'status':'ok','steps':positions,'seconds':round(seconds,4),
            'steps_per_second':round(positions/max(seconds,1e-6),1),
            'note':'Chess bridge I/O and legal moves, NOT full neural self-play.'}


def main(argv=None):
    p=argparse.ArgumentParser(description='CPU/CUDA and chess-core microbenchmark')
    p.add_argument('--engine',type=Path,default=ROOT/('build/Release/chessai.exe' if sys.platform=='win32' else 'build/chessai'))
    p.add_argument('--output',type=Path,default=ROOT/'diagnostics/hardware_benchmark.json')
    p.add_argument('--samples',type=int,default=10)
    a=p.parse_args(argv)
    if not 2<=a.samples<=100:p.error('samples must be 2..100')
    torch.set_num_threads(min(6,max(1,torch.get_num_threads())))
    try:
        gpu=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],
                           capture_output=True,text=True,timeout=4)
        nvidia=gpu.stdout.strip() if gpu.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired):nvidia=None
    report={'version':'0.6.0','created_at':datetime.now(timezone.utc).isoformat(),
            'torch_version':torch.__version__,'torch_cuda_version':torch.version.cuda,
            'cuda_available':torch.cuda.is_available(),'nvidia_smi':nvidia,
            'python':sys.version.split()[0],
            'configuration':{'channels':32,'blocks':2,'samples':a.samples},
            'device_results':{},'core':chess_core_bench(a.engine)}
    for device in ['cpu']+(['cuda'] if torch.cuda.is_available() else []):
        report['device_results'][device]=torch_bench(device,{'channels':32,'blocks':2},a.samples)
    report['note']='Synthetic neural batches. GPU can be slower for tiny networks. No weights/checkpoints/experiments are modified.'
    atomic_json(a.output,report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':main()
