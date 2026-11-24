"""Desktop Vision Autoplay UI. Requires opt-in for computer-only games.

Run from installed ChessAI-v0.7.0 via python -m visionbot.gui.
"""
from __future__ import annotations

import ctypes
import json
import queue
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox,ttk

from .autoplay import Screen,VisionAutoplay
from .focus import find_browser,activate_browser

ROOT=Path(__file__).resolve().parents[1]
RUN_ID='run_20261123_072154_6a110b'


class App:
    def __init__(self,root:tk.Tk):
        self.root=root;self.run=ROOT/'runs'/RUN_ID
        self.engine=ROOT/'build'/'Release'/'chessai.exe'
        if not self.engine.is_file():self.engine=ROOT/'build'/'chessai.exe'
        self.path=ROOT/'config'/'vision_bot.json'
        self.rect=None
        self.ev=threading.Event();self.worker=None
        self.msg=queue.Queue()
        self.color=tk.StringVar(value='white');self.checkpoint=tk.StringVar(value='latest.pt')
        self.consent=tk.BooleanVar(value=False)
        self.train=tk.BooleanVar(value=True)
        self.resume=tk.BooleanVar(value=True)
        self.turn=tk.StringVar(value='auto')
        self.status=tk.StringVar(value='Ожидаю калибровку доски')
        if self.path.exists():
            try:
                cfg=json.loads(self.path.read_text(encoding='utf-8'))
                self.rect=tuple(int(x) for x in cfg['rect']);self.color.set(cfg['color'])
            except (OSError,ValueError,KeyError,TypeError):pass
        root.title('Chess AI · Vision Computer Bot Lab v0.7.5 (promotions)')
        root.geometry('680x760');root.minsize(610,690)
        root.configure(bg='#10151c')
        tk.Label(root,text='CHESS AI · VISION BOT',bg='#10151c',fg='white',font=('Segoe UI',19,'bold')).pack(anchor='w',padx=22,pady=(18,3))
        tk.Label(root,text='Поиск до 5 полуходов, дебюты, защита от зевков · только компьютерный бот',
                 bg='#10151c',fg='#b0c1cd',wraplength=595,justify='left').pack(anchor='w',padx=22)
        opts=tk.Frame(root,bg='#10151c');opts.pack(fill='x',padx=22,pady=15)
        tk.Label(opts,text='Нейросеть:',bg='#10151c',fg='white').pack(side='left')
        ttk.Combobox(opts,textvariable=self.checkpoint,values=['latest.pt','best.pt','skillboost.pt','skillboost_v2.pt'],width=12,state='readonly').pack(side='left',padx=8)
        tk.Label(opts,text='Сторона:',bg='#10151c',fg='white').pack(side='left',padx=(10,0))
        ttk.Combobox(opts,textvariable=self.color,values=['white','black'],width=9,state='readonly').pack(side='left',padx=8)
        tk.Label(opts,text='Ход:',bg='#10151c',fg='white').pack(side='left',padx=(8,0))
        ttk.Combobox(opts,textvariable=self.turn,values=['auto','white','black'],width=8,state='readonly').pack(side='left',padx=5)
        tk.Button(root,text='1. Выделить область шахматной доски (один раз)',command=self.calibrate,
                  bg='#344963',fg='white',padx=8,pady=9).pack(fill='x',padx=22,pady=(2,7))
        self.info=tk.Label(root,text=f'Доска: {self.rect if self.rect else "не задана"}',bg='#10151c',fg='#b4c9dc')
        self.info.pack(anchor='w',padx=25)
        tk.Checkbutton(root,text='Подтверждаю: на экране партия Chess.com против КОМПЬЮТЕРНОГО бота, не человека',
                       variable=self.consent,bg='#10151c',fg='white',selectcolor='#25384c',activebackground='#10151c',
                       activeforeground='white',wraplength=585,justify='left').pack(anchor='w',padx=21,pady=13)
        tk.Checkbutton(root,text='Параллельно продолжать локальное self-play: +500 итераций (без данных Chess.com)',
                       variable=self.train,bg='#10151c',fg='white',selectcolor='#25384c',activebackground='#10151c',
                       activeforeground='white').pack(anchor='w',padx=21,pady=(0,5))
        tk.Checkbutton(root,text='Восстановить предыдущую партию после сбоя (рекомендуется)',
                       variable=self.resume,bg='#10151c',fg='white',selectcolor='#25384c',activebackground='#10151c',
                       activeforeground='white').pack(anchor='w',padx=21,pady=(0,8))
        tk.Label(root,text='Для НОВОЙ партии сними галочку: старая история будет архивирована. '
                 'Восстановление доступно только после установки этого патча.',
                 bg='#10151c',fg='#9eb4c3',wraplength=600,justify='left').pack(anchor='w',padx=22,pady=(0,8))
        row=tk.Frame(root,bg='#10151c');row.pack(fill='x',padx=22)
        self.start=tk.Button(row,text='▶ Запустить автопилот',command=self.launch,bg='#24734f',fg='white',padx=15,pady=10)
        self.start.pack(side='left',fill='x',expand=True,padx=(0,6))
        tk.Button(row,text='■ Остановить',command=self.stop,bg='#9b3c45',fg='white',padx=14,pady=10).pack(side='left')
        tk.Button(root,text='▶ Подключиться к ТЕКУЩЕЙ партии (без истории)',
                  command=lambda:self.launch(attach_any_position=True),
                  bg='#344963',fg='white',padx=12,pady=8).pack(fill='x',padx=22,pady=(7,2))
        tk.Label(root,text='Экстренная остановка: ESC. При неопределённой позиции клики прекращаются.',
                 bg='#10151c',fg='#d6ad77',wraplength=600).pack(anchor='w',padx=22,pady=(9,1))
        self.log=tk.Text(root,height=9,bg='#161e29',fg='#e2ebf4',insertbackground='white',wrap='word',relief='flat',font=('Consolas',9))
        self.log.pack(fill='both',expand=True,padx=22,pady=(6,18))
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(250,self.pump)

    def logline(self,t):self.msg.put(t)
    def pump(self):
        try:
            while True:
                s=self.msg.get_nowait()
                self.log.insert('end',s+'\n');self.log.see('end')
        except queue.Empty:pass
        self.root.after(250,self.pump)

    def calibrate(self):
        """Screen screenshot; drag from top-left to bottom-right of board."""
        if self.worker and self.worker.is_alive():return
        self.root.withdraw()
        self.root.after(650,self._capture)

    def _capture(self):
        try:
            from PIL import Image,ImageTk
            import cv2
            with_screen=Screen()
            try:image=with_screen.full()
            finally:with_screen.close()
            original_h,original_w=image.shape[:2]
            factor=min(1,1160/original_w,800/original_h)
            width=round(original_w*factor);height=round(original_h*factor)
            rgb=cv2.cvtColor(cv2.resize(image,(width,height)),cv2.COLOR_BGR2RGB)
            selector=tk.Toplevel(self.root)
            selector.title('Выдели шахматную доску: от a8-угла изображения до противоположного')
            selector.geometry(f'{width}x{height+42}')
            photo=ImageTk.PhotoImage(Image.fromarray(rgb))
            canvas=tk.Canvas(selector,width=width,height=height,highlightthickness=0)
            canvas.image=photo;canvas.pack()
            canvas.create_image(0,0,anchor='nw',image=photo)
            info=tk.Label(selector,text='Зажми кнопку и выдели 8×8 доску целиком. ESC — отмена.')
            info.pack()
            ref=[None,None]
            def down(e):ref[0]=(e.x,e.y)
            def drag(e):
                if not ref[0]:return
                canvas.delete('selection')
                canvas.create_rectangle(*ref[0],e.x,e.y,outline='red',width=3,tags='selection')
            def up(e):
                if not ref[0]:return
                x1,y1=ref[0];x2,y2=e.x,e.y
                x,y=sorted((x1,x2)),sorted((y1,y2))
                sx=int(round(x[0]/factor));sy=int(round(y[0]/factor))
                size=int(round(min(x[1]-x[0],y[1]-y[0])/factor))
                if size<320:
                    messagebox.showerror('Размер','Нужно выделить доску не менее 320×320 пикселей',parent=selector);return
                self.rect=(sx,sy,size)
                self.path.parent.mkdir(parents=True,exist_ok=True)
                self.path.write_text(json.dumps({'rect':self.rect,'color':self.color.get()},indent=2),encoding='utf-8')
                self.info.config(text=f'Доска: x={sx}, y={sy}, размер={size} px')
                selector.destroy();self.root.deiconify()
            canvas.bind('<ButtonPress-1>',down);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',up)
            def close(e=None):selector.destroy();self.root.deiconify()
            selector.bind('<Escape>',close)
            selector.protocol('WM_DELETE_WINDOW',close)
        except Exception as e:
            self.root.deiconify()
            messagebox.showerror('Снимок экрана',str(e))

    def launch(self, attach_any_position: bool = False):
        if self.worker and self.worker.is_alive():return
        if not self.consent.get():messagebox.showwarning('Режим','Подтверди, что играешь против компьютерного бота.');return
        if not self.rect:messagebox.showwarning('Калибровка','Сначала выдели шахматную доску.');return
        ck=self.run/'checkpoints'/self.checkpoint.get()
        from .recovery import RecoveryStore
        is_resume=not attach_any_position and (self.resume.get() if hasattr(self, 'resume') else True) and RecoveryStore(self.run,self.color.get()).exists()
        if not ck.is_file() and not is_resume:messagebox.showerror('Checkpoint',f'Не найден:\n{ck}');return
        if not self.engine.is_file():messagebox.showerror('Движок','C++ chessai.exe не собран. Запусти START_CHESS_AI.bat.');return
        # The tactical v0.7.1 GUI accidentally dropped the focus handoff
        # from the earlier Vision Browser Focus hotfix. Resolve the exact
        # computer-game browser BEFORE minimizing our Tk window.
        try:
            browser=find_browser()
        except RuntimeError as exc:
            messagebox.showerror('Chess.com browser',str(exc))
            return
        self.ev.clear()
        if self.train.get():
            try:
                from .trainer import ensure_selfplay
                self.logline(ensure_selfplay(RUN_ID,self.engine,500))
            except Exception as ex:
                messagebox.showerror('Self-play не запустился',str(ex)+'\n\nАвтопилот не запущен. Можно отключить self-play и попробовать ещё раз.')
                return
        self.path.write_text(json.dumps({'rect':self.rect,'color':self.color.get()},indent=2),encoding='utf-8')
        chosen_color=self.color.get()
        chosen_resume=(self.resume.get() if hasattr(self,'resume') else True)
        chosen_turn={'auto':None,'white':'w','black':'b'}[(self.turn.get() if hasattr(self,'turn') else 'auto')]
        self.root.iconify()
        try:
            activate_browser(browser)
        except RuntimeError as exc:
            self.root.deiconify()
            self.logline('ОСТАНОВКА: '+str(exc))
            messagebox.showerror('Не удалось активировать Chess.com',str(exc))
            self.logline('Локальное самообучение (если запущено) не остановлено.')
            return
        self.logline('Vision v0.7.5: превращение пешек, подключение к партии и безопасное восстановление')
        self.logline(f'Браузер активирован: {browser.title}')
        def run():
            import time
            time.sleep(0.6)
            bot=VisionAutoplay(self.engine,ck,self.run,chosen_color,self.rect,
                               self.logline,self.ev,expected_hwnd=browser.hwnd,
                               resume=chosen_resume,
                               attach_any_position=attach_any_position,
                               explicit_turn=chosen_turn)
            bot.run()
        self.worker=threading.Thread(target=run,name='VisionBot',daemon=True)
        self.worker.start()
        self.logline('Автопилот запущен. При проблеме нажми ESC (окно можно восстановить с панели задач).')

    def stop(self):
        self.ev.set();self.logline('Запрошена остановка…')

    def close(self):
        self.stop();self.root.destroy()


def main():
    if sys.platform=='win32':
        try:ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError,OSError):pass
    root=tk.Tk();App(root);root.mainloop()

if __name__=='__main__':main()
