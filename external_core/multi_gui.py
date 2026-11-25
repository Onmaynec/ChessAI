"""Graphical local board for human/engine and engine/engine games."""
from __future__ import annotations
import argparse,queue,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,filedialog,simpledialog
from .uci import PROFILES,START_FEN
from .install import ROOT
from .match import ENGINES,checkpoints,installed,play

GLYPHS=dict(zip('KQRBNPkqrbnp','♔♕♖♗♘♙♚♛♜♝♞♟'))
BG='#000000';FG='#ffffff';PANEL='#181818'

def expand(fen):
    result=[]
    for rank in fen.split()[0].split('/'):
        row=[p for c in rank for p in ('.'*int(c) if c.isdigit() else c)]
        if len(row)!=8:raise ValueError('Invalid board rank')
        result.extend(row)
    if len(result)!=64:raise ValueError('Invalid board')
    return result

class Lab:
    def __init__(self,root,core):
        self.root=root;self.core=core;self.events=queue.Queue();self.commands=queue.Queue()
        self.stop=threading.Event();self.worker=None;self.state=None;self.human=False;self.selected=None;self.last=None
        self.closing=False;self.flip=tk.BooleanVar(value=False);self.top=tk.BooleanVar(value=False)
        self.status=tk.StringVar(value='Ready — local games only')
        root.title('Chess AI | Multi-Engine Lab 0.9.3.5.1');root.configure(bg=BG);root.minsize(820,640);root.geometry('1000x730')
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',background=PANEL,foreground=FG,fieldbackground=PANEL)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',FG)])
        main=tk.Frame(root,bg=BG);main.pack(fill='both',expand=True,padx=12,pady=12)
        left=tk.Frame(main,bg=BG);left.pack(side='left',fill='both',expand=True)
        right=tk.Frame(main,bg=BG,width=360);right.pack(side='right',fill='y',padx=(12,0))
        right.pack_propagate(False)
        self.canvas=tk.Canvas(left,bg=BG,highlightthickness=0,width=520,height=520)
        self.canvas.pack(fill='both',expand=True);self.canvas.bind('<Configure>',lambda _:self.draw())
        self.canvas.bind('<Button-1>',self.click)
        ttk.Label(left,textvariable=self.status,wraplength=500).pack(fill='x',pady=6)
        ttk.Checkbutton(left,text='Flip board',variable=self.flip,command=self.draw).pack(side='left')
        ttk.Checkbutton(left,text='Always on top',variable=self.top,command=lambda:root.attributes('-topmost',self.top.get())).pack(side='left',padx=8)
        options=['Human']+(['Stockfish 19'] if installed('stockfish') else [])+(['Leela Chess Zero'] if installed('lc0') else [])+['ChessNet Policy','ChessNet Hybrid']
        paths=checkpoints();default=next((p for p in paths if p.endswith('latest.pt')),paths[0] if paths else '')
        self.fields={};self.locked=[]
        for side,name in (('w','WHITE'),('b','BLACK')):
            f=ttk.LabelFrame(right,text=name);f.pack(fill='x',pady=(0,7),ipadx=4,ipady=3)
            v={'kind':tk.StringVar(value='Human' if side=='w' else options[1]),
               'profile':tk.StringVar(value='balanced'),'checkpoint':tk.StringVar(value=default),
               'device':tk.StringVar(value='cpu'),'weights':tk.StringVar(value=''),'multipv':tk.StringVar(value='1')}
            self.fields[side]=v
            f.columnconfigure(1,weight=1)
            for i,(key,values) in enumerate((('kind',options),('profile',list(PROFILES)),('checkpoint',paths),('device',['cpu','cuda']),('multipv',['1','2','3']))):
                ttk.Label(f,text=key).grid(row=i,column=0,sticky='w',padx=4,pady=1)
                cb=ttk.Combobox(f,textvariable=v[key],values=values,state='readonly',width=22)
                cb.grid(row=i,column=1,sticky='ew',padx=4,pady=1);self.locked.append(cb)
            b=ttk.Button(f,text='Choose Lc0 weights (optional)',command=lambda v=v:self.weights(v))
            b.grid(row=5,column=0,columnspan=2,sticky='ew',padx=4,pady=2);self.locked.append(b)
        self.fen=tk.StringVar(value=START_FEN)
        ttk.Label(right,text='Starting FEN').pack(anchor='w');e=ttk.Entry(right,textvariable=self.fen);e.pack(fill='x');self.locked.append(e)
        row=ttk.Frame(right);row.pack(fill='x',pady=6)
        self.go=ttk.Button(row,text='Start match',command=self.start);self.go.pack(side='left',fill='x',expand=True)
        self.halt=ttk.Button(row,text='Stop',command=self.request_stop,state='disabled');self.halt.pack(side='right')
        self.log=tk.Text(right,bg=PANEL,fg=FG,insertbackground=FG,height=8,wrap='word',state='disabled')
        self.log.pack(fill='both',expand=True)
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(80,self.pump);self.draw()

    def weights(self,v):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('Lc0 network','*.pb.gz *.pb *.nn.gz'),('All files','*.*')])
        if path:v['weights'].set(path);self.append('Lc0 weights: '+path)

    def append(self,text):
        self.log.configure(state='normal');self.log.insert('end',text+'\n')
        self.log.see('end');self.log.configure(state='disabled')

    def geometry(self):
        size=max(8,min(self.canvas.winfo_width(),self.canvas.winfo_height())-24)//8
        return size,(self.canvas.winfo_width()-size*8)//2,(self.canvas.winfo_height()-size*8)//2

    def draw(self):
        c=self.canvas;c.delete('all')
        fen=self.state['fen'] if self.state else START_FEN
        board=expand(fen);s,x,y=self.geometry()
        for i in range(64):
            j=63-i if self.flip.get() else i
            r,col=divmod(j,8);square=chr(97+col)+str(8-r)
            a=x+(i%8)*s;b=y+(i//8)*s
            color='#e3e3e3' if (r+col)%2==0 else '#707070'
            if self.last and square in (self.last[:2],self.last[2:4]):color='#a4aa63'
            if square==self.selected:color='#d0b54b'
            c.create_rectangle(a,b,a+s,b+s,fill=color,outline=color)
            p=board[j]
            if p!='.':
                c.create_text(a+s/2,b+s/2,text=GLYPHS[p],font=('Segoe UI Symbol',max(8,int(s*.7))),fill='#101010')
            if self.selected and self.state and any(m[:2]==self.selected and m[2:4]==square for m in self.state['legal_moves']):
                c.create_oval(a+s*.4,b+s*.4,a+s*.6,b+s*.6,fill='#326d3c',outline='')
            if i%8==0:c.create_text(a+6,b+7,text=str(8-r),fill='#222222',font=('Segoe UI',8))
            if i//8==7:c.create_text(a+s-6,b+s-7,text=chr(97+col),fill='#222222',font=('Segoe UI',8))

    def click(self,event):
        if not self.human or not self.state:return
        s,x,y=self.geometry();col=(event.x-x)//s;r=(event.y-y)//s
        if not (0<=r<8 and 0<=col<8):return
        j=r*8+col
        if self.flip.get():j=63-j
        r,col=divmod(j,8);sq=chr(97+col)+str(8-r)
        legal=self.state['legal_moves']
        candidates=[m for m in legal if self.selected and m[:4]==self.selected+sq]
        if candidates:
            m=candidates[0]
            if len(candidates)>1:
                choice=simpledialog.askstring('Promotion','Choose q, r, b or n',initialvalue='q',parent=self.root)
                m=next((m for m in candidates if choice and m[-1]==choice.lower()),None)
                if m is None:return
            self.commands.put(m);self.human=False;self.selected=None
        else:self.selected=sq if any(m.startswith(sq) for m in legal) else None
        self.draw()

    def start(self):
        if self.worker and self.worker.is_alive():return
        if not messagebox.askyesno('Local testing','Confirm Scaling/PPO and other GPU sessions are stopped or completed. Start a LOCAL game?',parent=self.root):return
        specs={s:{k:v.get() for k,v in fields.items()} for s,fields in self.fields.items()}
        for spec in specs.values():
            spec['multipv']=int(spec['multipv'])
            if spec['kind'].startswith('ChessNet'):
                p=ROOT/spec['checkpoint']
                if not p.is_file():messagebox.showerror('Checkpoint','Select a checkpoint',parent=self.root);return
                spec['checkpoint']=str(p)
        if sum(s['kind']=='Leela Chess Zero' for s in specs.values())+sum(s['kind'].startswith('ChessNet') and s['device']=='cuda' for s in specs.values())>1:
            messagebox.showwarning('GPU','Use at most one CUDA player on this 8 GB system; select CPU for ChessNet.',parent=self.root);return
        if len(self.fen.get().split())!=6:messagebox.showerror('FEN','Expected six fields',parent=self.root);return
        self.stop=threading.Event();self.commands=queue.Queue();self.state=None;self.selected=None;self.last=None
        self.go.configure(state='disabled');self.halt.configure(state='normal')
        for w in self.locked:w.configure(state='disabled')
        self.status.set('Loading engines…');self.worker=threading.Thread(target=play,
            args=(self.core,specs,self.fen.get(),480,self.commands,self.events,self.stop),daemon=False);self.worker.start()

    def request_stop(self):
        self.stop.set();self.human=False;self.status.set('Stopping after current engine request…')

    def pump(self):
        for _ in range(100):
            try:event=self.events.get_nowait()
            except queue.Empty:break
            kind,*args=event
            if kind=='state':
                self.state,self.human,player=args;self.human=self.human and not self.stop.is_set()
                self.status.set(('White' if self.state['fen'].split()[1]=='w' else 'Black')+' · '+player)
                self.draw()
            elif kind=='move':
                self.state,side,self.last,detail=args;self.selected=None;self.human=False;self.draw()
                lines=detail.get('lines') or [];best=lines[0] if lines else {}
                self.append(f'{side}: {self.last} | {detail.get("engine")} | {detail.get("elapsed_ms",0):.0f} ms')
                if best:self.append(f'depth={best.get("depth")} score={best.get("score")} nodes={best.get("nodes")} nps={best.get("nps")} PV={" ".join(best.get("pv",[]))}')
                if detail.get('recovered'):self.append('UCI restarted successfully')
            elif kind=='notice':self.append(args[0])
            elif kind=='done':
                status,result,reason,path=args;self.human=False
                self.status.set(f'{status} | {result} | {reason}');self.append('Report: '+path)
                self.go.configure(state='normal');self.halt.configure(state='disabled')
                for w in self.locked:w.configure(state='readonly' if isinstance(w,ttk.Combobox) else 'normal')
        if self.closing and not (self.worker and self.worker.is_alive()):self.root.destroy();return
        self.root.after(80,self.pump)

    def close(self):
        self.closing=True;self.request_stop()

def main():
    p=argparse.ArgumentParser();p.add_argument('--core',type=Path);a=p.parse_args()
    core=a.core or next((p for p in (ROOT/'build/Release/chessai.exe',ROOT/'build/chessai.exe') if p.is_file()),None)
    if core is None or not core.is_file():p.error('Local C++ core missing')
    root=tk.Tk();Lab(root,core);root.mainloop()
if __name__=='__main__':main()
