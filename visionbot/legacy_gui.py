"""Desktop Vision Autoplay UI. Requires opt-in for computer-only games.

Run from installed ChessAI-v0.7.0 via python -m visionbot.gui.
"""
from __future__ import annotations

import ctypes
import json
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from .workspace import Workspace
from .ui_layout import shortcut_edge

from .autoplay import Screen,VisionAutoplay
from .focus import find_browser,activate_browser
from neural.agent_profiles import ALIASES
from .telemetry import rotate_and_append, rectangles_overlap
from .ui_controller import VisionUiController

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
        self.ui_controller=VisionUiController()
        self.color=tk.StringVar(value='white');self.checkpoint=tk.StringVar(value='latest.pt')
        self.consent=tk.BooleanVar(value=False)
        self.external_profile=tk.StringVar(value='balanced')
        self._active_external=False
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
        self._launching=False
        self._closing=False
        self._hotkey_previous=(False,False)
        self.root.after(100,self.pump)
        if sys.platform=='win32':self.root.after(40,self.poll_shortcuts)

    def on_agent_change(self,event=None):
        name=self.checkpoint.get()
        from .external_session import EXTERNAL
        if self.worker is not None and self.worker.is_alive() and (self._active_external or name in EXTERNAL):
            self.checkpoint.set(self._active_selection)
            self.agent_picker.set(self._active_selection)
            self.logline('Останови текущую партию перед сменой типа движка.')
            return
        if self.worker is not None and self.worker.is_alive():
            self._active_selection=name
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
        self.ui_controller.submit(t)

    def pump(self):
        # This is the Tk adapter; the controller has no toolkit dependency.
        try:
            for event in self.ui_controller.drain():
                try:
                    if event.analysis is not None:
                        self.render_analysis(event.analysis,event.lines)
                    self.add_view_log(event.category,event.text)
                    if event.analysis is None:
                        self.observe_message(event.text,event.category)
                except (ValueError,TypeError,KeyError,AttributeError) as exc:
                    self.add_view_log('error','UI event: '+str(exc))
                try:
                    rotate_and_append(self.log_file,event.disk_line)
                except OSError:
                    pass
            self.refresh_workspace()
        finally:
            if not self._closing:self.root.after(100,self.pump)

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
        self.overlays.hide_for_capture()
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
                selector.destroy();self.root.deiconify();self.overlays.restore_after_capture();self.place_away_from_board()
            canvas.bind('<ButtonPress-1>',down);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',up)
            def close(e=None):selector.destroy();self.root.deiconify();self.overlays.restore_after_capture();self.place_away_from_board()
            selector.bind('<Escape>',close)
            selector.protocol('WM_DELETE_WINDOW',close)
        except Exception as e:
            self.root.deiconify()
            self.overlays.restore_after_capture()
            messagebox.showerror('Снимок экрана',str(e))

    def poll_shortcuts(self):
        """Read only the requested chords; no hooks, key logging or key injection."""
        if self._closing:return
        try:
            key=lambda code:bool(ctypes.windll.user32.GetAsyncKeyState(code)&0x8000)
            action,self._hotkey_previous=shortcut_edge(key(0xA4),key(0xA5),key(0x11),key(0x31),key(0x32),self._hotkey_previous)
            if action and self.consent.get() and self.rect and not self._launching and not (self.worker and self.worker.is_alive()):
                from .focus import current_foreground,our_panel_is_foreground
                _,title=current_foreground()
                title=title.casefold()
                # Outside our own panel, require a visible computer-game title.
                computer='chess.com' in title and any(word in title for word in ('computer','bot','компьютер','бот'))
                if (self.root.state() in ('normal','zoomed') or 'control' in self.overlays.windows) and not self.overlays._capturing and (our_panel_is_foreground() or computer) and not self.root.grab_current():
                    self.launch(attach_any_position=action==2)
        finally:
            if not self._closing:self.root.after(40,self.poll_shortcuts)

    def open_multi_engine(self):
        import subprocess
        if self.worker and self.worker.is_alive():
            messagebox.showwarning('Multi-Engine','Stop Vision session first.');return
        child=getattr(self,'_multi_engine_child',None)
        if child is not None and child.poll() is None:
            messagebox.showinfo('Multi-Engine','Local lab is already open.');return
        try:
            self._multi_engine_child=subprocess.Popen([sys.executable,'-B','-m','external_core.multi_gui','--core',str(self.engine)],cwd=ROOT)
        except OSError as exc:messagebox.showerror('Multi-Engine',str(exc))

    def launch(self, attach_any_position: bool = False):
        child=getattr(self,'_multi_engine_child',None)
        if child is not None and child.poll() is None:
            messagebox.showwarning('Multi-Engine','Close local lab before using the Vision session.');return
        if getattr(self,'_launching',False) or getattr(self,'_closing',False):return
        self._launching=True
        try:self._launch(attach_any_position)
        finally:
            self._launching=False
            if not getattr(self,'_closing',False):self.refresh_workspace()

    def _launch(self, attach_any_position: bool = False):
        if self.worker and self.worker.is_alive():return
        if self.overlays._capturing:return
        if not self.consent.get():messagebox.showwarning('Режим','Подтверди, что играешь против компьютерного бота.');return
        if not self.rect:messagebox.showwarning('Калибровка','Сначала выдели шахматную доску.');return
        from .external_session import EXTERNAL,ExternalRecovery,input_spec,computer_title
        from .recovery import RecoveryStore
        from botlab.session import BotLabSession
        selection=self.checkpoint.get();external=selection in EXTERNAL
        game_run=self.run;factory=BotLabSession;store_factory=RecoveryStore
        if external:
            try:ck,game_run,factory=input_spec(selection,self.external_profile.get())
            except (ValueError,OSError) as exc:messagebox.showerror('External UCI',str(exc));return
            store_factory=ExternalRecovery
            if not messagebox.askyesno('Authorized computer test',
                'Confirm written authorization from Chess.com for automated testing, a computer-only opponent, and that Scaling/PPO/GPU training is stopped. No human games.',parent=self.root):return
        else:ck=self.run/'checkpoints'/selection
        is_resume=not attach_any_position and (self.resume.get() if hasattr(self, 'resume') else True) and store_factory(game_run,self.color.get()).exists()
        if not ck.is_file() and not is_resume:messagebox.showerror('Checkpoint',f'Не найден:\n{ck}');return
        if not self.engine.is_file():messagebox.showerror('Движок','C++ chessai.exe не собран. Запусти START_CHESS_AI.bat.');return
        # The tactical v0.7.1 GUI accidentally dropped the focus handoff
        # from the earlier Vision Browser Focus hotfix. Resolve the exact
        # computer-game browser BEFORE minimizing our Tk window.
        try:
            browser=find_browser()
            if external and not computer_title(browser.title):raise RuntimeError('Computer-only Chess.com page title required for external UCI test')
        except RuntimeError as exc:
            messagebox.showerror('Chess.com browser',str(exc))
            return
        # Validate window placement before starting optional local training.
        if not self.prepare_launch_layout():
            messagebox.showwarning('Vision Bot','Move the window outside the calibrated board.')
            return
        self.ev.clear()
        if self.train.get() and not external:
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
            if self.root.winfo_ismapped() and self.topmost.get() and rectangles_overlap(ui,(x,y,size,size)):
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
        self._active_external=external;self._active_selection=selection
        self.logline('Внешний UCI: '+selection+' · '+self.external_profile.get() if external else 'Vision: переключение нейросетей во время партии включено')
        self.logline(f'Браузер активирован: {browser.title}')
        chosen_level='deep' if self.analysis_mode.get().startswith('Глубокий') else 'standard'
        chosen_rect=tuple(self.rect)
        self.reset_analysis()
        def run():
            import time
            if self.ev.wait(0.6):return
            bot=VisionAutoplay(self.engine,ck,game_run,chosen_color,chosen_rect,
                               self.logline,self.ev,expected_hwnd=browser.hwnd,
                               browser_window=browser,
                               resume=chosen_resume,
                               attach_any_position=attach_any_position,
                               explicit_turn=chosen_turn,
                               phantom_opening=chosen_phantom,
                               analysis_level=chosen_level,
                               session_factory=factory,recovery_enabled=True,store_factory=store_factory,
                               external_authorized=external)
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
        if self._closing:return
        self._closing=True
        self.stop()
        self.save_workspace_settings()
        self.overlays.shutdown()
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
