"""Isolated synthetic hardware benchmark; uses temporary model/optimizer in RAM."""
from __future__ import annotations
import argparse,time,statistics,gc
from pathlib import Path
from .tactical_data import output_dir,hash_file
from .tactical_learning import atomic_json

def run(source,out,batches=(8,16,32,64),iterations=10,device='auto'):
    import torch
    from .checkpoint import load_model
    from .encoding import INPUT_CHANNELS,POLICY_SIZE
    dev=torch.device('cuda' if device=='auto' and torch.cuda.is_available() else 'cpu' if device=='auto' else device)
    if dev.type=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA unavailable')
    h=hash_file(source);rows=[]
    def sync():
        if dev.type=='cuda':torch.cuda.synchronize(dev)
    for batch in batches:
        model=opt=x=target=logits=value=loss=None
        row={'batch':batch}
        try:
            model=load_model(source,dev);row['model_config']=model.config
            opt=torch.optim.AdamW(model.parameters(),lr=1e-4)
            x=torch.randn(batch,INPUT_CHANNELS,8,8,device=dev)
            target=torch.arange(batch,device=dev)%POLICY_SIZE
            def step(training):
                nonlocal logits,value,loss
                if training:
                    opt.zero_grad(set_to_none=True)
                    logits,value=model(x)
                    loss=torch.nn.functional.cross_entropy(logits,target)+value.square().mean()
                    loss.backward();opt.step()
                else:
                    with torch.inference_mode():logits,value=model(x)
            for training in (False,True):
                model.train(training)
                for _ in range(3):step(training)
                sync()
                if dev.type=='cuda':torch.cuda.reset_peak_memory_stats(dev)
                times=[]
                for _ in range(iterations):
                    sync();start=time.perf_counter();step(training);sync();times.append(time.perf_counter()-start)
                label='train' if training else 'inference'
                row[label]={'median_ms':statistics.median(times)*1000,'positions_per_second':batch/statistics.mean(times),
                            'peak_allocated_mib':torch.cuda.max_memory_allocated(dev)/1048576 if dev.type=='cuda' else None,
                            'peak_reserved_mib':torch.cuda.max_memory_reserved(dev)/1048576 if dev.type=='cuda' else None}
            row['status']='complete'
        except torch.cuda.OutOfMemoryError:
            row['status']='oom'
        finally:
            model=opt=x=target=logits=value=loss=None
            gc.collect()
            if dev.type=='cuda':torch.cuda.empty_cache()
        rows.append(row);print('[GPU LAB]',row,flush=True)
        atomic_json(out/'gpu_report.json',{'schema':'scaling_gpu_v1','checkpoint_sha256':h,'device':str(dev),
                    'gpu':torch.cuda.get_device_name(dev) if dev.type=='cuda' else None,'torch':str(torch.__version__),
                    'iterations':iterations,'results':rows,'complete':len(rows)==len(batches),
                    'warning':'Synthetic FP32 forward and AdamW step; not full trainer or total VRAM.'})
        if row['status']=='oom':break
    if hash_file(source)!=h:raise RuntimeError('Checkpoint changed')

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--batches',type=int,nargs='+',default=[8,16,32,64]);p.add_argument('--iterations',type=int,default=10)
    p.add_argument('--device',choices=['auto','cpu','cuda'],default='auto');a=p.parse_args()
    if not all(1<=b<=256 for b in a.batches) or not 3<=a.iterations<=100:p.error('Invalid budget')
    run(a.source,output_dir(a.output),a.batches,a.iterations,a.device)
if __name__=='__main__':main()
