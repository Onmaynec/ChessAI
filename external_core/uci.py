"""Persistent bounded UCI process, with no website/client automation."""
from __future__ import annotations
import queue,re,subprocess,threading,time
from collections import deque
from pathlib import Path

MOVE=re.compile(r'[a-h][1-8][a-h][1-8][qrbn]?')
START_FEN='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
PROFILES={'fast':(4,256,500),'balanced':(6,512,2000),'strong':(8,1024,5000),'maximum':(12,2048,15000)}

class ProtocolError(RuntimeError):pass

class UCI:
    def __init__(self,exe,extra=(),timeout=20):
        exe=Path(exe).resolve()
        self.proc=subprocess.Popen([str(exe),*extra],cwd=exe.parent,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        self.lines=queue.Queue(maxsize=8192);self.tail=deque(maxlen=30);self.options={};self.name=None
        self.closed=threading.Event()
        def read():
            try:
                for line in self.proc.stdout:
                    while not self.closed.is_set():
                        try:self.lines.put(line.strip(),timeout=.1);break
                        except queue.Full:pass
                    if self.closed.is_set():break
            finally:
                try:self.lines.put_nowait(None)
                except queue.Full:pass
        self.thread=threading.Thread(target=read,daemon=True);self.thread.start()
        try:
            self.send('uci')
            for line in self.until(lambda l:l=='uciok',timeout):
                if line.startswith('id name '):self.name=line[8:]
                m=re.match(r'option name (.+?) type (\w+)(.*)$',line)
                if m:self.options[m[1]]=(m[2],m[3])
            if not self.name:raise ProtocolError('No engine identity')
        except BaseException:
            self.close();raise
    def send(self,line):
        if '\n' in line or '\r' in line or self.proc.poll() is not None:raise ProtocolError('Invalid command or engine stopped')
        self.proc.stdin.write(line+'\n');self.proc.stdin.flush()
    def until(self,done,timeout):
        deadline=time.monotonic()+timeout
        while True:
            try:line=self.lines.get(timeout=max(0,deadline-time.monotonic()))
            except queue.Empty:raise ProtocolError('UCI timeout: '+' | '.join(self.tail)) from None
            if line is None:raise ProtocolError('UCI process exited: '+' | '.join(self.tail))
            self.tail.append(line)
            if 'CRITICAL ERROR' in line.upper():raise ProtocolError(line)
            yield line
            if done(line):return
            if time.monotonic()>=deadline:raise ProtocolError('UCI deadline exceeded')
    def set_option(self,name,value,required=True):
        if name not in self.options:
            if required:raise ProtocolError('Missing option: '+name)
            return False
        typ,detail=self.options[name]
        if typ=='spin':
            lo=re.search(r'\bmin (-?\d+)',detail);hi=re.search(r'\bmax (-?\d+)',detail)
            if not lo or not hi:raise ProtocolError('Malformed spin option')
            value=max(int(lo[1]),min(int(hi[1]),int(value)))
        if typ=='combo' and str(value) not in re.findall(r'\bvar (.*?)(?= var |$)',detail):raise ProtocolError('Unsupported '+name+': '+str(value))
        self.send(f'setoption name {name} value {value}');return True
    def ready(self,timeout=90):
        self.send('isready');list(self.until(lambda l:l=='readyok',timeout))
    def new_game(self):
        self.send('ucinewgame');self.ready()
    def analyse(self,fen,legal,moves=(),movetime=2000,multipv=1):
        if not 50<=movetime<=60000 or not 1<=multipv<=5 or not legal or any(not MOVE.fullmatch(m) for m in [*legal,*moves]):
            raise ValueError('Invalid search budget, history or empty legal moves')
        if len(fen.split())!=6 or '\r' in fen or '\n' in fen:raise ValueError('Invalid FEN')
        if multipv>1:self.set_option('MultiPV',multipv)
        elif 'MultiPV' in self.options:self.set_option('MultiPV',1)
        self.ready()
        self.send('position fen '+fen+(' moves '+' '.join(moves) if moves else ''))
        self.send(f'go movetime {movetime}')
        start=time.perf_counter();infos={};best=None
        try:
            for line in self.until(lambda l:l.startswith('bestmove '),movetime/1000+45):
                if line.startswith('info ') and ' pv ' in line:
                    def number(k):
                        m=re.search(r'\b'+k+r' (-?\d+)\b',line);return int(m[1]) if m else None
                    score=re.search(r'\bscore (cp|mate) (-?\d+)',line);wdl=re.search(r'\bwdl (\d+) (\d+) (\d+)',line)
                    pv=line.split(' pv ',1)[1].split()
                    if pv and pv[0] in legal and all(MOVE.fullmatch(m) for m in pv):
                        infos[number('multipv') or 1]={'depth':number('depth'),'nodes':number('nodes'),'nps':number('nps'),
                            'score':{'kind':score[1],'value':int(score[2]),'bound':'lower' if ' lowerbound' in line else 'upper' if ' upperbound' in line else 'exact'} if score else None,
                            'wdl':list(map(int,wdl.groups())) if wdl else None,'pv':pv}
                elif line.startswith('bestmove '):best=line.split()[1]
            if best not in legal:raise ProtocolError('Illegal or missing bestmove: '+str(best))
        except BaseException:
            self.close();raise
        return {'engine':self.name,'bestmove':best,'elapsed_ms':round((time.perf_counter()-start)*1000,2),
                'lines':[infos[k] for k in sorted(infos)],'budget_ms':movetime}
    def close(self):
        self.closed.set()
        if self.proc.poll() is None:
            try:self.send('quit');self.proc.wait(timeout=2)
            except (OSError,RuntimeError,subprocess.TimeoutExpired):self.proc.kill();self.proc.wait()
        for f in (self.proc.stdin,self.proc.stdout):
            if f:f.close()
        self.thread.join(timeout=1)
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

def configured(name,profile='balanced',weights=None):
    from .install import DEST,verify_install,digest
    folder=DEST/name;m=verify_install(folder,name)
    engine=UCI(folder/m['exe'])
    try:
        threads,hash_mb,_=PROFILES[profile]
        if name=='stockfish':
            if not re.search(r'\bStockfish 19\b',engine.name,re.I):raise ProtocolError('Unexpected Stockfish identity')
            engine.set_option('Threads',threads);engine.set_option('Hash',hash_mb)
            engine.set_option('UCI_LimitStrength','false');engine.set_option('Skill Level',20,False)
            engine.set_option('UCI_ShowWDL','true',False)
        else:
            if '0.32.1' not in engine.name:raise ProtocolError('Unexpected Lc0 identity')
            w=Path(weights).resolve() if weights else folder/m['weights']
            if not w.is_file():raise FileNotFoundError(w)
            engine.set_option('WeightsFile',str(w));engine.set_option('Backend','cuda-fp16')
            engine.set_option('Threads',2,False);engine.set_option('MinibatchSize',32,False)
            engine.set_option('UCI_ShowWDL','true',False)
            engine.weights_sha256=digest(w)
        engine.ready();return engine
    except BaseException:
        engine.close();raise
