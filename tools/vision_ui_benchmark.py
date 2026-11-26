"""Synthetic UI data-path benchmark; not a GPU, FPS or game-strength test."""
from __future__ import annotations
import argparse
import json
import statistics
import time
from types import SimpleNamespace
from visionbot.journal_index import JournalIndex
from visionbot.design import TEXT, MUTED, DIM, BG, PANEL, FIELD

def luminance(color):
    channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))

def contrast(a,b):
    x,y = sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)

def benchmark(repeats=1000):
    events = [SimpleNamespace(category='error' if i%5==0 else 'info',
              text=f'Событие {i} · '+('данные '+str(i)+' ')*40) for i in range(600)]
    rows = [dict(category=e.category,text=e.text) for e in events]
    index = JournalIndex(events)
    queries = [str(i%50) for i in range(repeats)]
    def baseline(q):
        return [r for r in rows if q in r['text'].casefold()]
    def indexed(q):
        return index.filter(q,'all')
    for q in queries[:50]:
        assert baseline(q) == indexed(q)
    def measure(fn):
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            for q in queries:
                fn(q)
            samples.append((time.perf_counter()-start)*1000/repeats)
        return round(statistics.median(samples),6)
    return {'scope':'synthetic Python journal filters only','rows':600,
            'queries_per_sample':repeats,'baseline_ms_per_query':measure(baseline),
            'indexed_ms_per_query':measure(indexed),
            'contrast':{f'{fg}/{bg}':round(contrast(fg,bg),2)
                        for fg in (TEXT,MUTED,DIM) for bg in (BG,PANEL,FIELD)}}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repeats',type=int,default=1000)
    args=p.parse_args()
    if args.repeats < 50:
        p.error('--repeats must be >= 50')
    print(json.dumps(benchmark(args.repeats),indent=2))

if __name__=='__main__':
    main()
