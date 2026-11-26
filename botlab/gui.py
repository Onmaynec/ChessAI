"""ChessAI Bot Lab: chess.com *computer bots only*, manual synchronization.

No browser hooks, screen reading, credential handling or automatic clicks.
Self-play training is started independently in existing Training Studio.
"""
from __future__ import annotations

import argparse
import sys
import tkinter as tk
import webbrowser
import json
from urllib import request, error
from pathlib import Path
from tkinter import messagebox, ttk, simpledialog

from .session import BotLabSession, parse_board, safe_session_record, to_coord, trainer_status

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = 'run_20261123_072154_6a110b'
PIECES = {'K':'♔','Q':'♕','R':'♖','B':'♗','N':'♘','P':'♙',
          'k':'♚','q':'♛','r':'♜','b':'♝','n':'♞','p':'♟'}


class BotLabUI:
    def __init__(self, root: tk.Tk, run_dir: Path, engine: Path, device: str):
        self.root = root
        self.run_dir = run_dir
        self.engine = engine
        self.device = device
        self.session: BotLabSession | None = None
        self.selected = None
        self.last_record_path = None
        root.title('Chess AI — Bot Lab · Chess.com computer only')
        root.geometry('1020x760')
        root.minsize(860, 690)
        root.configure(bg='#0d1117')
        try:
            ttk.Style().theme_use('clam')
        except tk.TclError:
            pass
        self.status = tk.StringVar(value='Партия ещё не началась')
        self.trainer = tk.StringVar(value='Self-play: статус проверяется…')
        self.ai_color = tk.StringVar(value='white')
        from neural.model_catalog import vision_entries
        self.catalog={r['label']:r['path'] for r in vision_entries(run_dir) if not r.get('external')}
        self.checkpoint_choice = tk.StringVar(value=next(iter(self.catalog),''))
        self.opponent = tk.StringVar(value='Chess.com Computer · уровень/имя')
        self.move_input = tk.StringVar()
        self.result = tk.StringVar(value='unfinished')
        self.notes = tk.StringVar()
        self._ui()
        self.refresh_training()
        root.protocol('WM_DELETE_WINDOW', self.close)

    def _ui(self):
        bg='#0d1117'; card='#161b22'; fg='#f2f6fa'; muted='#9ba8b7'
        tk.Label(self.root,text='Chess AI · Bot Lab',bg=bg,fg=fg,font=('Segoe UI',20,'bold')).pack(anchor='w',padx=22,pady=(18,2))
        tk.Label(self.root,text='Только против компьютерных ботов Chess.com · Ходы синхронизируются вручную · Self-play работает отдельно',
                 bg=bg,fg=muted,font=('Segoe UI',10)).pack(anchor='w',padx=22,pady=(0,12))
        body=tk.Frame(self.root,bg=bg)
        body.pack(fill='both',expand=True,padx=20,pady=(0,10))
        left=tk.Frame(body,bg=bg)
        left.pack(side='left',anchor='n')
        self.board=tk.Canvas(left,width=552,height=552,highlightthickness=0,bg=card,cursor='hand2')
        self.board.pack()
        self.board.bind('<Button-1>',self.board_clicked)
        right=tk.Frame(body,bg=bg)
        right.pack(side='left',fill='both',expand=True,padx=(18,0))
        row=tk.Frame(right,bg=bg);row.pack(fill='x',pady=(0,8))
        tk.Label(row,text='ИИ:',bg=bg,fg=fg).pack(side='left')
        ttk.Radiobutton(row,text='Белые',variable=self.ai_color,value='white').pack(side='left',padx=3)
        ttk.Radiobutton(row,text='Чёрные',variable=self.ai_color,value='black').pack(side='left',padx=4)
        tk.Label(row,text='Модель:',bg=bg,fg=fg).pack(side='left',padx=(8,2))
        ttk.Combobox(row,textvariable=self.checkpoint_choice,values=list(self.catalog),width=28,state='readonly').pack(side='left')
        tk.Label(right,text='Бот на Chess.com:',fg=fg,bg=bg).pack(anchor='w')
        tk.Entry(right,textvariable=self.opponent,bg='#202733',fg=fg,insertbackground=fg,relief='flat').pack(fill='x',ipady=7,pady=(3,8))
        self._button(right,'1. Новая партия / загрузить checkpoint',self.new_game).pack(fill='x',pady=3)
        self._button(right,'Открыть Chess.com → Play Bots',lambda:webbrowser.open('https://www.chess.com/play/computer')).pack(fill='x',pady=3)
        tk.Label(right,textvariable=self.status,fg='#8ee5ab',bg=bg,wraplength=390,justify='left',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(12,6))
        self._button(right,'2. Подтвердить ход ИИ на Chess.com',self.confirm_ai).pack(fill='x',pady=3)
        tk.Label(right,text='Ход компьютерного бота (UCI):',fg=fg,bg=bg).pack(anchor='w',pady=(10,3))
        move_row=tk.Frame(right,bg=bg);move_row.pack(fill='x')
        ent=tk.Entry(move_row,textvariable=self.move_input,bg='#202733',fg=fg,insertbackground=fg,relief='flat',font=('Consolas',12))
        ent.pack(side='left',fill='x',expand=True,ipady=7)
        ent.bind('<Return>',lambda _:self.receive_opponent())
        self._button(move_row,'Ввести',self.receive_opponent).pack(side='left',padx=(6,0))
        tk.Label(right,text='Можно также нажимать клетки доски: откуда → куда.',fg=muted,bg=bg,wraplength=380,justify='left').pack(anchor='w',pady=(4,7))
        tk.Label(right,text='Ходы тестовой партии:',bg=bg,fg=fg).pack(anchor='w')
        self.history_box=tk.Text(right,height=6,bg='#1c2531',fg=fg,relief='flat',font=('Consolas',10),state='disabled',wrap='word')
        self.history_box.pack(fill='x',pady=(4,7))
        tk.Label(right,textvariable=self.trainer,bg=bg,fg='#c9a6ff',wraplength=390,justify='left').pack(anchor='w',pady=4)
        self._button(right,'Открыть Training Studio (self-play)',lambda:webbrowser.open('http://127.0.0.1:8765')).pack(fill='x',pady=(2,3))
        self._button(right,'Начать / продолжить self-play в фоне',self.resume_training).pack(fill='x',pady=(2,8))
        tk.Label(right,text='Итог (от лица ИИ):',bg=bg,fg=fg).pack(anchor='w')
        ttk.Combobox(right,textvariable=self.result,values=['win','draw','loss','unfinished'],state='readonly').pack(fill='x',pady=3)
        tk.Entry(right,textvariable=self.notes,bg='#202733',fg=fg,insertbackground=fg,relief='flat').pack(fill='x',ipady=6,pady=3)
        self._button(right,'Сохранить результат теста (не обучение)',self.save_result).pack(fill='x',pady=5)
        tk.Label(self.root,text='Важно: Chess.com запрещает AI-игру против людей. Бот Lab не управляет браузером и не использует партии Chess.com для обучения.',
                 bg=bg,fg='#aab6c5',wraplength=950,justify='left').pack(anchor='w',padx=20,pady=(0,14))
        self.draw_board()

    def _button(self, parent, title, command):
        return tk.Button(parent,text=title,command=command,bg='#293548',fg='white',activebackground='#3f5572',activeforeground='white',
                         relief='flat',font=('Segoe UI',10),padx=9,pady=8,cursor='hand2')

    def checkpoint_path(self):
        return ROOT/self.catalog.get(self.checkpoint_choice.get(),'__missing__')

    def new_game(self):
        if self.session and self.session.history:
            if not messagebox.askyesno('Новая партия','Текущий тест не сохранён автоматически. Начать новую партию?'):
                return
        cp=self.checkpoint_path()
        if not cp.exists():
            messagebox.showerror('Нет checkpoint',f'Не найден файл:\n{cp}\n\nСначала перенеси runs из старой версии.');return
        if not self.engine.is_file():
            messagebox.showerror('Нет C++ движка',f'Не найден:\n{self.engine}\n\nСначала собери проект.');return
        # Load a fresh copy per game. Never read changing checkpoints mid-game.
        old=self.session
        try:
            new=BotLabSession(self.engine,cp,self.ai_color.get(),device=self.device)
        except Exception as exc:
            messagebox.showerror('Не удалось загрузить модель',str(exc));return
        if old:old.close()
        self.session=new
        self.selected=None
        self.move_input.set('')
        self.result.set('unfinished')
        self.history_box.config(state='normal');self.history_box.delete('1.0','end');self.history_box.config(state='disabled')
        self.update_game()

    def update_game(self):
        self.draw_board()
        s=self.session
        if not s:return
        self.history_box.config(state='normal')
        self.history_box.delete('1.0','end')
        self.history_box.insert('1.0',' '.join(f'{i//2+1}. ' + m if i%2==0 else m for i,m in enumerate(s.history)))
        self.history_box.config(state='disabled')
        if s.state['finished']:
            self.status.set(f"Партия завершена по шахматным правилам: {s.state['result']} ({s.state['reason']}). Сохрани итог.")
        elif s.ai_turn():
            try:
                move,value=s.propose()
                self.status.set(f'Ход ИИ: {move} | value={value:+.3f}\nСделай {move} на Chess.com и нажми «Подтвердить».')
            except Exception as exc:
                self.status.set(f'Ошибка расчёта: {exc}')
        else:
            self.status.set('Ход бота Chess.com. Введи ход в формате e7e5 или нажми две клетки на доске.')

    def confirm_ai(self):
        if not self.session:return
        try:
            self.session.confirm_ai()
            self.selected=None
            self.update_game()
        except ValueError as exc: messagebox.showwarning('Ход не подтверждён',str(exc))

    def receive_opponent(self):
        if not self.session:return
        try:
            self.session.opponent_move(self.move_input.get())
            self.move_input.set('')
            self.selected=None
            self.update_game()
        except ValueError as exc: messagebox.showwarning('Неверный ход',str(exc))
        except Exception as exc: messagebox.showerror('Ошибка движка',str(exc))

    def board_clicked(self,event):
        s=self.session
        if not s or s.ai_turn() or s.state['finished'] or s.pending:return
        col=int(event.x//69);row=int(event.y//69)
        if not (0<=col<8 and 0<=row<8):return
        coord=to_coord(row,col)
        if self.selected is None:
            if any(m.startswith(coord) for m in s.state['legal_moves']):self.selected=coord
            self.draw_board();return
        if self.selected==coord:
            self.selected=None;self.draw_board();return
        prefix=self.selected+coord
        matches=[m for m in s.state['legal_moves'] if m.startswith(prefix)]
        if len(matches)>1:
            selection=simpledialog.askstring('Превращение пешки','Фигура: q, r, b, n',initialvalue='q',parent=self.root)
            if selection is None:return
            attempt=prefix+selection.lower()
        elif matches:
            attempt=matches[0]
        else:
            self.selected=coord if any(m.startswith(coord) for m in s.state['legal_moves']) else None
            self.draw_board();return
        self.move_input.set(attempt)
        self.receive_opponent()

    def draw_board(self):
        c=self.board;c.delete('all')
        b=parse_board(self.session.state['fen'] if self.session else 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
        for r in range(8):
            for f in range(8):
                x=f*69;y=r*69
                color='#769656' if (r+f)%2 else '#eeeed2'
                if self.selected==to_coord(r,f):color='#d9c955'
                c.create_rectangle(x,y,x+69,y+69,fill=color,outline=color)
                p=b[r][f]
                if p!='.':
                    c.create_text(x+34.5,y+34.5,text=PIECES[p],font=('Segoe UI Symbol',40),
                                  fill='#ffffff' if p.isupper() else '#151515')
                if f==0:c.create_text(x+5,y+5,text=str(8-r),fill='#353535',anchor='nw',font=('Consolas',9))
                if r==7:c.create_text(x+63,y+64,text='abcdefgh'[f],fill='#353535',anchor='se',font=('Consolas',9))
        if self.selected and self.session:
            for m in self.session.state['legal_moves']:
                if m.startswith(self.selected):
                    dest=m[2:4];f=ord(dest[0])-97;r=8-int(dest[1]);x=f*69+34;y=r*69+34
                    c.create_oval(x-7,y-7,x+7,y+7,fill='#44693e',outline='')

    def save_result(self):
        if not self.session:
            messagebox.showwarning('Нет партии','Создай тестовую партию.');return
        try:
            record=self.session.report(self.opponent.get(),self.result.get(),self.notes.get())
            path=safe_session_record(self.run_dir/'botlab_sessions',record)
            self.last_record_path=path
            messagebox.showinfo('Тест записан',f'Сохранено:\n{path}\n\nВеса модели и PPO-данные не изменены.')
        except Exception as exc:messagebox.showerror('Не удалось сохранить',str(exc))

    def resume_training(self):
        """Launch only through the existing v0.7.0 dashboard and explicit click."""
        count=simpledialog.askinteger('Продолжить обучение',
                'Количество дополнительных итераций self-play:',
                initialvalue=20,minvalue=1,maxvalue=100000,parent=self.root)
        if count is None:return
        if not messagebox.askyesno('Подтверждение',
            f'Продолжить локальное self-play на {count} итераций?\n'
            'Существующий checkpoint останется основой обучения.\n'
            'Партии Chess.com НЕ будут использоваться для обучения.'):
            return
        try:
            with request.urlopen('http://127.0.0.1:8765/api/health',timeout=4) as response:
                health=json.load(response)
            if health.get('version')!='0.7.0':
                raise ValueError('На порту 8765 не запущена Training Studio v0.7.0')
            reported=Path(health.get('engine_path','')).resolve()
            if reported != self.engine.resolve():
                raise ValueError('На порту 8765 открыта другая установка Chess AI. Запусти Training Studio из той же папки, что Bot Lab.')
            data=json.dumps({'iterations':count}).encode('utf-8')
            url=f'http://127.0.0.1:8765/api/resume/{self.run_dir.name}'
            req=request.Request(url,data=data,headers={'Content-Type':'application/json'},method='POST')
            with request.urlopen(req,timeout=6) as response:
                result=json.load(response)
            messagebox.showinfo('Обучение запущено',
                f'Запущено {count} дополнительных итераций self-play.\n'
                'Следи за прогрессом в Training Studio.\n'
                'Bot Lab продолжит текущую партию с зафиксированной моделью.')
            self.refresh_training(schedule=False)
        except error.HTTPError as exc:
            text=exc.read(600).decode('utf-8',errors='replace')
            messagebox.showerror('Сервер не запустил обучение',f'HTTP {exc.code}: {text}')
        except Exception as exc:
            messagebox.showerror('Training Studio недоступна',
                f'{exc}\n\nОткрой START_CHESS_AI.bat из этой же установки, потом повтори.')

    def refresh_training(self, schedule=True):
        s=trainer_status(self.run_dir)
        self.trainer.set(f"Self-play: {s['status']} | итерация: {s['iteration']} | устройство: {s['device']}.\n"
                         'Для продолжения обучения открой Training Studio. Во время партии checkpoint не меняется.')
        if schedule:
            self.root.after(5000,self.refresh_training)

    def close(self):
        if self.session:self.session.close()
        self.root.destroy()


def main():
    p=argparse.ArgumentParser(description='Manual Chess.com computer-bot challenge; no automation or training on Chess.com content')
    p.add_argument('--run-id',default=RUN_ID)
    p.add_argument('--engine',type=Path,default=ROOT/'build'/'Release'/'chessai.exe' if sys.platform=='win32' else ROOT/'build'/'chessai')
    p.add_argument('--device',choices=['cpu','cuda'],default='cpu',help='Inference device. CPU leaves GPU free for concurrent self-play.')
    a=p.parse_args()
    # Do not put user controlled path outside runs folder.
    if any(x in a.run_id for x in ('/','\\','..')):p.error('Invalid training run ID')
    engine=a.engine
    if not engine.is_file():
        alternate=ROOT/'build'/'chessai.exe' if sys.platform=='win32' else ROOT/'build'/'Release'/'chessai'
        if alternate.is_file():engine=alternate
    root=tk.Tk()
    BotLabUI(root,ROOT/'runs'/a.run_id,engine,a.device)
    root.mainloop()

if __name__=='__main__':
    main()
