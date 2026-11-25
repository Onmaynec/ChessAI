"""Local position validation and test play using the existing C++ bridge."""
from __future__ import annotations
import json,subprocess,queue,threading
from pathlib import Path
from .uci import MOVE,START_FEN,ProtocolError

class Bridge:
    def __init__(self,exe):
        exe=Path(exe).resolve()
        self.proc=subprocess.Popen([str(exe),'bridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                   text=True,encoding='utf-8',bufsize=1)
        self.lines=queue.Queue()
        def read():
            for line in self.proc.stdout:self.lines.put(line)
            self.lines.put(None)
        threading.Thread(target=read,daemon=True).start()
    def call(self,command):
        if '\n' in command or '\r' in command:raise ValueError('Invalid command')
        self.proc.stdin.write(command+'\n');self.proc.stdin.flush()
        try:line=self.lines.get(timeout=10)
        except queue.Empty:raise ProtocolError('Local bridge timeout') from None
        if line is None:raise ProtocolError('Local bridge stopped')
        row=json.loads(line)
        if 'error' in row:raise ValueError('Local C++ rejected position or move: '+str(row['error']))
        return row
    def new(self,fen=START_FEN):
        if len(fen.split())!=6:raise ValueError('Expected six-field FEN')
        self.state=self.call('new 935001 '+fen);return self.state
    def step(self,move):
        if not MOVE.fullmatch(move) or move not in self.state['legal_moves'] or self.state['finished']:raise ValueError('Illegal move')
        self.state=self.call('step 935001 '+move);return self.state
    def __enter__(self):return self
    def __exit__(self,*_):
        try:
            if self.proc.poll() is None:self.proc.stdin.write('quit\n');self.proc.stdin.flush();self.proc.wait(timeout=2)
        except (OSError,subprocess.TimeoutExpired):self.proc.kill();self.proc.wait()
        finally:
            self.proc.stdin.close();self.proc.stdout.close()
