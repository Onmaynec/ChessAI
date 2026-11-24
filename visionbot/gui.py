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
from tkinter import messagebox
from .workspace import Workspace

from .autoplay import Screen,VisionAutoplay
from .focus import find_browser,activate_browser
from neural.agent_profiles import ALIASES
from .telemetry import read_event, formatted_analysis, rotate_and_append, rectangles_overlap

ROOT=Path(__file__).resolve().parents[1]
RUN_ID='run_20261123_072154_6a110b'


class App(Workspace):
    def __init__(self,root:tk.Tk):
        self.root=root;self.run=ROOT/'runs'/RUN_ID
        self.engine=ROOT/'build'/'Release'/'chessai.exe'
        if not self.engine.is_file():self.engine=ROOT/'build'/'chessai.exe'
        self.path=ROOT/'config'/'vision_bot.json'
        self.rect=None
        self.ev=threading.Event();self.worker=None;self.bot=None;self.agent_pending_on_start=None
        self.msg=queue.Queue()
        self.color=tk.StringVar(value='white');self.checkpoint=tk.StringVar(value='latest.pt')
        self.consent=tk.BooleanVar(value=False)
        self.train=tk.BooleanVar(value=False)
        self.resume=tk.BooleanVar(value=True)
        self.turn=tk.StringVar(value='auto')
        self.phantom=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value='Ожидаю калибровку доски')
        self.topmost=tk.BooleanVar(value=True)
        self.analysis_mode=tk.StringVar(value='Глубокий · до 7 полуходов')
        self.latest_eval=tk.StringVar(value='Оценка: —')
        self.latest_depth=tk.StringVar(value='Глубина: —')
        self.latest_move=tk.StringVar(value='Ход: —')
        self.log_file=self.run/'vision_logs'/'vision_current.log'
        if self.path.exists():
            try:
                cfg=json.loads(self.path.read_text(encoding='utf-8'))
                self.rect=tuple(int(x) for x in cfg['rect']);self.color.set(cfg['color'])
            except (OSError,ValueError,KeyError,TypeError):pass
        self.build_workspace()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(100,self.pump)

    def on_agent_change(self,event=None):
        name=self.checkpoint.get()
        if self.worker is not None and self.worker.is_alive():
            if self.bot is None:
                self.agent_pending_on_start=name
                self.logline('Агент будет применён после запуска: '+name)
            else:
                try:
                    self.bot.request_agent_switch(name)
                    self.logline('Запрошена смена агента на '+name+'; применится перед следующим решением')
                except ValueError as exc:self.logline('ВНИМАНИЕ: '+str(exc))
        else:
            self.logline('Агент для следующей партии: '+name)

    def set_topmost(self):
        self.root.attributes('-topmost', bool(self.topmost.get()) or getattr(self,'compact',False))

    def clear_log(self):
        self.clear_view_log()

    def logline(self,t):
        # Queue is thread-safe; Tk operations happen only on the main thread.
        self.msg.put(t)

    def pump(self):
        import datetime
        for _ in range(100):
            try: raw=self.msg.get_nowait()
            except queue.Empty: break
            try: event=read_event(raw)
            except (ValueError,TypeError): event=None
            if event is not None:
                try:
                    lines=formatted_analysis(event)
                    self.render_analysis(event,lines)
                    rotate_and_append(self.log_file,event.get('when','')+' [ANALYSIS] '+' | '.join(lines))
                    self.add_view_log('analysis', ' | '.join(lines[:2]))
                except (OSError,ValueError,TypeError,KeyError) as exc:
                    self.add_view_log('error',str(exc))
                continue
            t=str(raw)
            tag='error' if any(x in t.upper() for x in ('ОСТАНОВКА','ОШИБКА','ВНИМАНИЕ')) else ('move' if ('Ход ' in t or 'подтверждён' in t) else 'info')
            self.add_view_log(tag,t)
            self.observe_message(t,tag)
            try:rotate_and_append(self.log_file,f'[{datetime.datetime.now():%H:%M:%S}] {t}')
            except OSError:pass
        self.refresh_workspace()
        self.root.after(100,self.pump)

    def place_away_from_board(self):
        """Try docking to the side so the panel doesn't conceal a chess square."""
        if not self.rect or not hasattr(self.root, 'update_idletasks'):
            return
        self.root.update_idletasks()
        sx,sy,size=self.rect
        width=max(self.root.winfo_width(),320 if getattr(self,'compact',False) else 540)
        monitor_width=self.root.winfo_screenwidth()
        monitor_height=self.root.winfo_screenheight()
        if sx+size+width+14<=monitor_width:
            x=sx+size+10
        elif sx-width-14>=0:
            x=sx-width-10
        else:
            self.logline('ВНИМАНИЕ: панели и доске мало места рядом. Сдвинь окно вручную, чтобы оно не закрывало клетки.')
            return
        y=max(0,min(sy,monitor_height-self.root.winfo_height()))
        self.root.geometry(f'+{x}+{y}')

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
                self.info.configure(text=f'Доска: x={sx}, y={sy}, размер={size} px')
                selector.destroy();self.root.deiconify();self.place_away_from_board()
            canvas.bind('<ButtonPress-1>',down);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',up)
            def close(e=None):selector.destroy();self.root.deiconify();self.place_away_from_board()
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
        # Validate window placement before starting optional local training.
        if not self.prepare_launch_layout():
            messagebox.showwarning('Vision Bot','Move the window outside the calibrated board.')
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
        chosen_phantom=bool(self.phantom.get()) if hasattr(self,'phantom') else False
        chosen_resume=(self.resume.get() if hasattr(self,'resume') else True)
        chosen_turn={'auto':None,'white':'w','black':'b'}[(self.turn.get() if hasattr(self,'turn') else 'auto')]
        # Topmost controls must not cover a square: the screenshot recognizer
        # would otherwise see the panel instead of the chessboard.
        if hasattr(self.root,'winfo_rootx'):
            self.root.update_idletasks()
            ui=(self.root.winfo_rootx(),self.root.winfo_rooty(),
                self.root.winfo_width(),self.root.winfo_height())
            x,y,size=self.rect
            if self.topmost.get() and rectangles_overlap(ui,(x,y,size,size)):
                messagebox.showwarning('Панель перекрывает доску',
                    'Перетащи окно Vision Bot в сторону от шахматной доски. '
                    'Иначе компьютерное зрение будет видеть само окно вместо фигур.')
                return
        try:
            activate_browser(browser)
        except RuntimeError as exc:
            self.root.deiconify()
            self.logline('ОСТАНОВКА: '+str(exc))
            messagebox.showerror('Не удалось активировать Chess.com',str(exc))
            self.logline('Локальное самообучение (если запущено) не остановлено.')
            return
        self.logline('Vision: переключение Latest / SkillBoost / Aggressive / Defender во время партии включено')
        self.logline(f'Браузер активирован: {browser.title}')
        chosen_level='deep' if self.analysis_mode.get().startswith('Глубокий') else 'standard'
        chosen_rect=tuple(self.rect)
        self.reset_analysis()
        def run():
            import time
            time.sleep(0.6)
            bot=VisionAutoplay(self.engine,ck,self.run,chosen_color,chosen_rect,
                               self.logline,self.ev,expected_hwnd=browser.hwnd,
                               browser_window=browser,
                               resume=chosen_resume,
                               attach_any_position=attach_any_position,
                               explicit_turn=chosen_turn,
                               phantom_opening=chosen_phantom,
                               analysis_level=chosen_level)
            self.bot=bot
            if getattr(self,'agent_pending_on_start',None):
                bot.request_agent_switch(self.agent_pending_on_start)
                self.agent_pending_on_start=None
            try:bot.run()
            finally:self.bot=None
        self.worker=threading.Thread(target=run,name='VisionBot',daemon=True)
        self.worker.start()
        self.logline('Автопилот запущен. При проблеме нажми ESC (окно можно восстановить с панели задач).')

    def stop(self):
        self.ev.set();self.logline('Запрошена остановка…')

    def close(self):
        self.stop()
        self.save_workspace_settings()
        self._wait_close()

    def _wait_close(self):
        if self.worker and self.worker.is_alive():
            self.root.after(100,self._wait_close)
        else:
            self.root.destroy()


def main():
    if sys.platform=='win32':
        try:ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError,OSError):pass
    import customtkinter as ctk
    ctk.set_appearance_mode('dark')
    root=ctk.CTk();App(root);root.mainloop()

if __name__=='__main__':main()
