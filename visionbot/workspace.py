"""CustomTkinter presentation layer. One window, one existing Vision session.

No training or move execution is implemented here. All displayed analysis comes
from existing telemetry; the board is the last reported FEN, not a live capture.
"""
from __future__ import annotations

import datetime
import json
import re
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import messagebox

from .telemetry import rectangles_overlap
from neural.agent_profiles import ALIASES

BG='#101116'
PANEL='#171820'
FIELD='#20212b'
BORDER='#2b2d39'
TEXT='#f2f2f7'
MUTED='#a5a9bb'
ACCENT='#7154e8'
HOVER='#866cf4'
GREEN='#52d79a'
RED='#ff8585'
GLYPHS=dict(zip('KQRBNPkqrbnp','♔♕♖♗♘♙♚♛♜♝♞♟'))

def parse_board(fen):
    """Return eight ranks or None for malformed telemetry; no invented pieces."""
    ranks=str(fen).split()
    if not ranks: return None
    result=[]
    for rank in ranks[0].split('/'):
        cells=[]
        for ch in rank:
            if ch in '12345678': cells.extend(['.']*int(ch))
            elif ch in GLYPHS: cells.append(ch)
            else: return None
        if len(cells)!=8: return None
        result.append(cells)
    return result if len(result)==8 else None

def clamp_alpha(value):
    try: return max(.55,min(1.,float(value)))
    except (ValueError,TypeError): return .85

def safe_position(board, width, height, screen_width, screen_height):
    """Return a visible non-overlapping location or None; never cover board."""
    if width>screen_width or height>screen_height: return None
    if not board: return (max(0,screen_width-width-20),20)
    x,y,s=board
    for px,py in ((x+s+12,y),(x-width-12,y),(x,y-height-12),(x,y+s+12)):
        px=max(0,min(px,screen_width-width))
        py=max(0,min(py,screen_height-height))
        if not rectangles_overlap((px,py,width,height),(x,y,s,s)):
            return px,py
    return None

class Workspace:
    def tr(self,ru,en): return en if self.lang.get()=='EN' else ru

    def build_workspace(self):
        import customtkinter as ctk
        self.ctk=ctk
        r=self.root
        self.compact=False
        self.page='home'
        self._layout_width=None
        self._layout_pending=None
        self._status_cache=None
        self._full_geometry=None
        self._active=False
        self._seen_worker=None
        self._last_event=None
        self._fen=''
        self._messages=deque(maxlen=600)
        self._filter='all'
        self.filter_var=tk.StringVar(value='all')
        self._labels=[]
        self._locked=[]
        self._choices=[]
        self._workspace_path=self.path.with_name('vision_ui.json')
        try:
            settings=json.loads(self._workspace_path.read_text(encoding='utf-8'))
            if not isinstance(settings,dict): settings={}
        except (OSError,ValueError): settings={}
        self.lang=tk.StringVar(value='EN' if settings.get('language')=='EN' else 'RU')
        self.opacity=tk.DoubleVar(value=clamp_alpha(settings.get('opacity',.85)))
        self.preview=tk.BooleanVar(value=bool(settings.get('preview',True)))
        self.autoscroll=tk.BooleanVar(value=True)
        self.state_text=tk.StringVar(value=self.tr('Ожидание','Idle'))
        self.summary_text=tk.StringVar(value='')
        self.board_text=tk.StringVar(value='')
        self.fen_text=tk.StringVar(value='—')
        self.move_text=tk.StringVar(value='—')
        self.eval_text=tk.StringVar(value='—')
        self.depth_text=tk.StringVar(value='—')
        self.detail_text=tk.StringVar(value='')
        self.notice=tk.StringVar(value='')
        self.model_status=tk.StringVar(value='')
        self.side_status=tk.StringVar(value='')
        self.region_status=tk.StringVar(value='')
        self.engine_status=tk.StringVar(value='')
        self.checkpoint_status=tk.StringVar(value='')
        self.vision_status=tk.StringVar(value='')
        self.fen_short=tk.StringVar(value='—')
        self.fen_turn=tk.StringVar(value='—')
        self._system_signature=None
        self.alpha_text=tk.StringVar(value=f'{round(self.opacity.get()*100)}%')
        r.title('Chess AI · Vision Computer Bot Lab — Vision Studio 0.8.3')
        r.configure(fg_color=BG)
        sw,sh=r.winfo_screenwidth(),r.winfo_screenheight()
        r.geometry(f'{min(1360,max(540,sw-90))}x{min(850,max(550,sh-90))}')
        r.minsize(510,520)
        r.attributes('-topmost',bool(self.topmost.get()))
        self.full=ctk.CTkFrame(r,fg_color=BG,corner_radius=0)
        self.full.pack(fill='both',expand=True)
        self.full.grid_columnconfigure(1,weight=1)
        self.full.grid_rowconfigure(2,weight=1)
        bar=self.card(self.full)
        bar.grid(row=0,column=0,columnspan=2,sticky='ew',padx=10,pady=(9,4))
        self.label(bar,'♞  Chess AI · Vision Bot','♞  Chess AI · Vision Bot',size=16,bold=True).pack(side='left',padx=12,pady=5)
        self.label(bar,'0.8.3','0.8.3',color=MUTED,size=11).pack(side='left',padx=3)
        self.button(bar,'↗ Оверлей','↗ Overlay',self.toggle_overlay,width=88).pack(side='right',padx=6,pady=5)
        self.header_stop=self.button(bar,'■ Стоп','■ Stop',self.stop,width=66)
        self.header_stop.pack(side='right',padx=3,pady=5)
        self.statusbar=self.card(self.full)
        self.statusbar.grid(row=1,column=1,sticky='ew',padx=(0,10),pady=(4,5))
        for i,(var,color) in enumerate(((self.state_text,GREEN),(self.model_status,TEXT),(self.side_status,TEXT),(self.region_status,MUTED))):
            self.statusbar.grid_columnconfigure(i,weight=1)
            cell=self.label(self.statusbar,variable=var,color=color,size=12,bold=i==0)
            cell.grid(row=0,column=i,sticky='w',padx=10,pady=8)
        self.side=self.card(self.full)
        self.side.grid(row=1,column=0,rowspan=4,sticky='ns',padx=(10,8),pady=(4,10))
        self.nav={}
        for key,ru,en in [('home','⌂  Сессия','⌂  Session'),('vision','◎  Видение','◎  Vision'),('analysis','▥  Анализ','▥  Analysis'),('log','▤  Журнал','▤  Log'),('settings','⚙  Настройки','⚙  Settings')]:
            b=self.button(self.side,ru,en,lambda k=key:self.navigate(k),width=125)
            b.configure(anchor='w',height=42,fg_color='transparent',border_width=0)
            b.pack(fill='x',padx=7,pady=3)
            self.nav[key]=b
        system=self.card(self.side)
        system.pack(side='bottom',fill='x',padx=7,pady=8)
        self.label(system,'▥  Система','▥  System',bold=True).pack(anchor='w',padx=8,pady=(7,3))
        for var in (self.engine_status,self.checkpoint_status,self.vision_status):
            self.label(system,variable=var,color=MUTED,size=11,wrap=112).pack(anchor='w',padx=8,pady=2)
        self.label(system,'Компьютерный бот','Computer bot only',color=MUTED,size=10,wrap=112).pack(anchor='w',padx=8,pady=(3,7))
        self.body=ctk.CTkScrollableFrame(self.full,fg_color=BG,corner_radius=0,scrollbar_button_color=BORDER)
        self.body.grid(row=2,column=1,sticky='nsew',padx=(0,10),pady=(0,4))
        self.session=self.card(self.body)
        self.vision=self.card(self.body)
        self.analysis_card=self.card(self.body)
        self.settings=self.card(self.body)
        self.log_card=self.card(self.full)
        self.action_dock=self.card(self.full)
        self.action_dock.grid_columnconfigure(0,weight=1)
        self.action_dock.grid_columnconfigure(1,weight=1)
        self.dock_start=self.button(self.action_dock,'▶ Запуск','▶ Start',self.launch,primary=True)
        self.dock_start.grid(row=0,column=0,sticky='ew',padx=5,pady=5)
        self.dock_attach=self.button(self.action_dock,'Подключиться','Join game',lambda:self.launch(attach_any_position=True))
        self.dock_attach.grid(row=0,column=1,sticky='ew',padx=5,pady=5)
        self._locked.extend([self.dock_start,self.dock_attach])
        self.build_session()
        self.build_vision()
        self.build_analysis()
        self.build_log()
        self.build_settings()
        self.build_overlay()
        self.navigate('home')
        r.bind('<Configure>',self.on_resize,add='+')
        r.bind('<Escape>',lambda _:self.stop(),add='+')
        self.refresh_workspace()

    def card(self,parent):
        return self.ctk.CTkFrame(parent,fg_color=PANEL,border_width=1,border_color=BORDER,corner_radius=10)

    def label(self,parent,ru='',en='',*,variable=None,color=TEXT,size=12,bold=False,wrap=0):
        kw=dict(text_color=color,font=('Segoe UI',size,'bold' if bold else 'normal'),anchor='w',justify='left',wraplength=wrap)
        if variable is not None: kw['textvariable']=variable
        else: kw['text']=self.tr(ru,en)
        w=self.ctk.CTkLabel(parent,**kw)
        if variable is None:self._labels.append((w,ru,en))
        return w

    def button(self,parent,ru,en,command,*,primary=False,width=110):
        w=self.ctk.CTkButton(parent,text=self.tr(ru,en),command=command,height=34,width=width,
             corner_radius=8,fg_color=ACCENT if primary else FIELD,hover_color=HOVER if primary else '#353447',
             border_width=0 if primary else 1,border_color=BORDER,text_color=TEXT,
             font=('Segoe UI',13,'bold' if primary else 'normal'))
        self._labels.append((w,ru,en))
        return w

    def title(self,parent,ru,en,subtitle_ru='',subtitle_en=''):
        self.label(parent,ru,en,size=18,bold=True).pack(anchor='w',padx=14,pady=(12,2))
        if subtitle_ru:self.label(parent,subtitle_ru,subtitle_en,color=MUTED,wrap=320).pack(anchor='w',padx=14,pady=(0,9))

    def row(self,parent):
        w=self.ctk.CTkFrame(parent,fg_color='transparent')
        w.pack(fill='x',padx=12,pady=4)
        return w

    def section(self,parent,n,ru,en):
        row=self.ctk.CTkFrame(parent,fg_color='transparent')
        row.pack(fill='x',padx=14,pady=(8,3))
        marker=self.ctk.CTkLabel(row,text=str(n),width=26,height=26,corner_radius=13,
                                fg_color=ACCENT,text_color=TEXT,font=('Segoe UI',13,'bold'))
        marker.pack(side='left')
        self.label(row,ru,en,size=14,bold=True).pack(side='left',padx=9)

    def choice(self,parent,ru,en,var,values,*,change=None,lock=False):
        if ru:self.label(parent,ru,en,color=MUTED,size=11).pack(anchor='w',padx=3,pady=(0,1))
        def options(): return {self.tr(a,b):v for v,a,b in values}
        def picked(display):
            mapping=options()
            if display not in mapping:return
            var.set(mapping[display])
            if change:change()
        opts=options()
        widget=self.ctk.CTkOptionMenu(parent,values=list(opts),command=picked,height=34,width=110,
                 dynamic_resizing=False,corner_radius=7,fg_color=FIELD,button_color=BORDER,button_hover_color=ACCENT,
                 dropdown_fg_color=PANEL,dropdown_hover_color=ACCENT,text_color=TEXT,font=('Segoe UI',12))
        widget.pack(fill='x',padx=3,pady=(0,2))
        widget.set(next((k for k,v in opts.items() if v==var.get()),str(var.get())))
        self._choices.append((widget,var,values))
        if lock:self._locked.append(widget)
        return widget

    def switch(self,parent,ru,en,var,command=None,lock=False):
        w=self.ctk.CTkSwitch(parent,text=self.tr(ru,en),variable=var,command=command,
                           progress_color=ACCENT,fg_color=BORDER,button_color='#e9e9f4',text_color=TEXT,
                           font=('Segoe UI',12))
        w.pack(anchor='w',padx=14,pady=6)
        self._labels.append((w,ru,en))
        if lock:self._locked.append(w)
        return w

    def build_session(self):
        c=self.session
        self.title(c,'Новая сессия','New session','Подготовка, подключение к партии и запуск','Setup, connect to a game and launch')
        self.section(c,1,'Выбор модели','Choose model')
        row=self.row(c)
        self.agent_picker=self.choice(row,'','',self.checkpoint,[(n,n,n) for n in ALIASES],change=self.on_agent_change)
        self.section(c,2,'Область доски','Board region')
        row=self.row(c)
        b=self.button(row,'▣  Выделить область','▣  Select region',self.calibrate,width=150)
        b.configure(border_color=ACCENT,fg_color='#26213c')
        b.pack(side='left',fill='x',expand=True,padx=(3,5));self._locked.append(b)
        self.info=self.label(row,variable=self.board_text,color=MUTED,size=11,wrap=145)
        self.info.pack(side='right',padx=4)
        self.section(c,3,'Настройки партии','Game settings')
        row=self.row(c)
        self.option_cells=[]
        options=[
            ('Сторона','Side',self.color,[('white','Белые','White'),('black','Чёрные','Black')]),
            ('Очередь хода','Turn on import',self.turn,[('auto','Авто','Auto'),('white','Белые','White'),('black','Чёрные','Black')]),
            ('Анализ','Analysis',self.analysis_mode,[('Стандартный · 5 полуходов','Стандарт · 5 п/х','Standard · 5'),('Глубокий · до 7 полуходов','Глубокий · до 7','Deep · up to 7')])
        ]
        for i,(ru,en,var,values) in enumerate(options):
            cell=self.ctk.CTkFrame(row,fg_color='transparent')
            row.grid_columnconfigure(i,weight=1,uniform='opts')
            cell.grid(row=0,column=i,sticky='ew',padx=2)
            self.choice(cell,ru,en,var,values,lock=True)
            self.option_cells.append(cell)
        toggles=self.row(c)
        toggles.grid_columnconfigure((0,1),weight=1,uniform='toggles')
        self.toggle_cells=[]
        for i,(ru,en,var,command,lock) in enumerate([
            ('Фантом-X23','Phantom-X23',self.phantom,None,True),
            ('Восстановление','Recover game',self.resume,None,True),
            ('Self-play (+500)','Self-play (+500)',self.train,None,True),
            ('Поверх окон','Always on top',self.topmost,self.set_topmost,False)]):
            cell=self.ctk.CTkFrame(toggles,fg_color=FIELD,corner_radius=7)
            cell.grid(row=i//2,column=i%2,sticky='ew',padx=3,pady=3)
            toggle=self.ctk.CTkSwitch(cell,text='',variable=var,command=command,progress_color=ACCENT,
                                      fg_color=BORDER,button_color='#e9e9f4',width=36,switch_width=34,switch_height=18)
            toggle.pack(side='right',padx=7,pady=7)
            self.label(cell,ru,en,size=11).pack(side='left',padx=7)
            if lock:self._locked.append(toggle)
            self.toggle_cells.append(cell)
        self.section(c,4,'Запуск','Launch')
        consent=self.ctk.CTkCheckBox(c,text=self.tr('Только компьютерный соперник','Computer opponent only'),variable=self.consent,
                                    fg_color=ACCENT,hover_color=HOVER,text_color=TEXT,font=('Segoe UI',12),checkbox_width=18,checkbox_height=18)
        consent.pack(anchor='w',padx=17,pady=(2,4))
        self._labels.append((consent,'Только компьютерный соперник','Computer opponent only'))
        self._locked.append(consent)
        row=self.row(c)
        self.start=self.button(row,'▶ Запустить автопилот','▶ Start autopilot',self.launch,primary=True,width=150)
        self.start.configure(height=42)
        self.start.pack(side='left',fill='x',expand=True,padx=(3,5))
        self.stop_button=self.button(row,'■ Стоп','■ Stop',self.stop,width=82)
        self.stop_button.configure(height=42)
        self.stop_button.pack(side='right',padx=3)
        self.attach=self.button(c,'↪ Подключиться к текущей партии','↪ Join current game',lambda:self.launch(attach_any_position=True))
        self.attach.pack(fill='x',padx=15,pady=(2,10))
        self.warning_label=self.label(c,variable=self.notice,color=RED,wrap=300,size=11)
        self.notice.trace_add('write',lambda *_:self.show_notice())

    def show_notice(self):
        if self.notice.get():self.warning_label.pack(anchor='w',padx=14,pady=(0,5))
        else:self.warning_label.pack_forget()

    def build_vision(self):
        c=self.vision
        header=self.row(c)
        self.label(header,'◎  Предпросмотр доски','◎  Board preview',size=16,bold=True).pack(side='left',padx=2)
        toggle=self.ctk.CTkSwitch(header,text='',variable=self.preview,command=self.toggle_preview,
                                  width=38,switch_width=34,switch_height=18,progress_color=ACCENT,fg_color=BORDER)
        toggle.pack(side='right',padx=3)
        self.preview_body=self.row(c)
        self.board=tk.Canvas(self.preview_body,width=174,height=174,bg=PANEL,highlightthickness=0)
        self.board.pack(side='left',padx=(2,8),pady=2)
        self.board.bind('<Configure>',lambda _:self.draw_board())
        info=self.ctk.CTkFrame(self.preview_body,fg_color='transparent')
        info.pack(side='left',fill='both',expand=True,padx=3)
        self.label(info,'Позиция','Position',color=MUTED,size=11).pack(anchor='w')
        self.recognition=self.label(info,variable=self.fen_short,color=TEXT,size=11,wrap=125)
        self.recognition.pack(anchor='w',pady=(1,5))
        self.label(info,'Оценка · cp','Evaluation · cp',color=MUTED,size=11).pack(anchor='w')
        self.label(info,variable=self.eval_text,size=20,bold=True).pack(anchor='w')
        self.label(info,variable=self.fen_turn,color=MUTED,size=10).pack(anchor='w')
        self.button(info,'Копировать FEN','Copy FEN',self.copy_fen,width=100).pack(anchor='w',pady=(5,1))
        self.fen_label=self.label(c,variable=self.fen_text,color=MUTED,wrap=280,size=10)
        self.fen_label.pack(anchor='w',padx=14,pady=(0,8))
        self.toggle_preview()

    def build_analysis(self):
        c=self.analysis_card
        self.title(c,'▥  Анализ позиции','▥  Position analysis')
        stats=self.row(c)
        for i,(ru,en,v) in enumerate([('Ход','Move',self.move_text),('Оценка · cp','Score · cp',self.eval_text),('Глубина','Depth',self.depth_text)]):
            stats.grid_columnconfigure(i,weight=1,uniform='metrics')
            metric=self.ctk.CTkFrame(stats,fg_color=FIELD,corner_radius=7)
            metric.grid(row=0,column=i,sticky='ew',padx=3)
            self.label(metric,ru,en,color=MUTED,size=10).pack(anchor='w',padx=7,pady=(3,0))
            self.label(metric,variable=v,size=17,bold=True).pack(anchor='w',padx=7,pady=(0,4))
        self.candidates=self.ctk.CTkFrame(c,fg_color=FIELD,corner_radius=7)
        self.candidates.pack(fill='x',padx=14,pady=(3,7))
        self.detail_label=self.label(c,variable=self.detail_text,color=MUTED,wrap=280,size=11)
        self.detail_label.pack(anchor='w',padx=14,pady=(0,5))
        self.label(c,'Полосы: policy · оценки от стороны хода','Bars: policy · scores from side to move',color=MUTED,size=10,wrap=280).pack(anchor='w',padx=14,pady=(0,6))
        self.analysis=self.ctk.CTkTextbox(c,height=180,fg_color=FIELD,text_color=TEXT,font=('Consolas',12),wrap='word',state='disabled')
        self.draw_candidates([])

    def build_log(self):
        c=self.log_card
        header=self.row(c)
        self.label(header,'▤  Журнал сессии','▤  Session log',size=16,bold=True).pack(side='left',padx=2)
        self.button(header,'Очистить вид','Clear view',self.clear_log,width=90).pack(side='right',padx=2)
        filters=self.row(c)
        self.filter_values=[('all','Все','All'),('info','Система','System'),('analysis','Анализ','Analysis'),('move','Ходы','Moves'),('error','Ошибки','Errors')]
        def select(value):
            mapping={self.tr(a,b):v for v,a,b in self.filter_values}
            if value in mapping:
                self.filter_var.set(mapping[value]);self.filter_log(mapping[value])
        self.filter_choice=self.ctk.CTkSegmentedButton(filters,values=[self.tr(a,b) for _,a,b in self.filter_values],
                command=select,height=27,corner_radius=12,fg_color=FIELD,selected_color=ACCENT,
                selected_hover_color=HOVER,unselected_color=FIELD,unselected_hover_color=BORDER,
                font=('Segoe UI',11))
        self.filter_choice.pack(side='left',fill='x',expand=True)
        self.filter_choice.set(self.tr('Все','All'))
        self._choices.append((self.filter_choice,self.filter_var,self.filter_values))
        self.log=self.ctk.CTkTextbox(c,height=105,fg_color='#13141b',text_color=TEXT,font=('Consolas',11),wrap='word',state='disabled',corner_radius=7)
        self.log.pack(fill='both',expand=True,padx=12,pady=(1,9))
        for tag,color in [('error',RED),('move',GREEN),('analysis','#b7a5ff'),('info',TEXT)]:
            self.log.tag_config(tag,foreground=color)

    def build_settings(self):
        c=self.settings
        self.title(c,'Настройки интерфейса','Interface settings')
        self.choice(c,'Язык интерфейса','Interface language',self.lang,[('RU','Русский','Russian'),('EN','English','English')],change=self.change_language)
        self.switch(c,'Автопрокрутка журнала','Auto-scroll log',self.autoscroll)
        self.label(c,'Прозрачность оверлея','Overlay opacity',color=MUTED).pack(anchor='w',padx=14,pady=(8,0))
        row=self.row(c)
        self.ctk.CTkSlider(row,from_=.55,to=1,number_of_steps=45,variable=self.opacity,
                          command=self.change_opacity,progress_color=ACCENT,button_color=HOVER).pack(side='left',fill='x',expand=True)
        self.label(row,variable=self.alpha_text).pack(side='right',padx=8)
        self.label(c,'55–100%. Оверлей остаётся видимым и не перекрывает доску.','55–100%. Overlay stays visible and must not cover the board.',color=MUTED,wrap=300).pack(anchor='w',padx=14,pady=(0,8))
        self.button(c,'Сохранить настройки','Save settings',self.save_workspace_settings).pack(fill='x',padx=14,pady=(4,12))

    def build_overlay(self):
        ctk=self.ctk
        self.overlay=ctk.CTkFrame(self.root,fg_color=BG,corner_radius=0)
        header=self.row(self.overlay)
        grip=self.label(header,'⋮⋮  Vision Bot','⋮⋮  Vision Bot',bold=True,size=16)
        grip.pack(side='left')
        grip.bind('<ButtonPress-1>',self.drag_start)
        grip.bind('<B1-Motion>',self.drag_move)
        self.button(header,'↗ Развернуть','↗ Expand',self.toggle_overlay,width=92).pack(side='right')
        card=self.card(self.overlay)
        card.pack(fill='x',padx=10,pady=3)
        row=self.row(card)
        self.label(row,variable=self.state_text,color=GREEN,size=12,bold=True).pack(side='left')
        self.label(row,variable=self.summary_text,color=MUTED,size=10).pack(side='right')
        row=self.row(card)
        for i,(ru,en,var) in enumerate([('Выбранный ход','Chosen move',self.move_text),('Оценка · cp','Evaluation · cp',self.eval_text)]):
            row.grid_columnconfigure(i,weight=1,uniform='overlay')
            metric=ctk.CTkFrame(row,fg_color=FIELD,corner_radius=7)
            metric.grid(row=0,column=i,sticky='ew',padx=3)
            self.label(metric,ru,en,color=MUTED,size=10).pack(anchor='w',padx=8,pady=(3,0))
            self.label(metric,variable=var,bold=True,size=21).pack(anchor='w',padx=8,pady=(0,4))
        row=self.row(card)
        self.label(row,'Глубина','Depth',color=MUTED,size=11).pack(side='left')
        self.label(row,variable=self.depth_text).pack(side='right')
        self.label(card,variable=self.detail_text,color=MUTED,wrap=290,size=10).pack(anchor='w',padx=12,pady=(0,4))
        self.overlay_stop=self.button(self.overlay,'■ Остановить · Esc','■ Stop · Esc',self.stop)
        self.overlay_stop.configure(fg_color='#482631',hover_color='#703544',border_color='#73424c',text_color='#ffd9df')
        self.overlay_stop.pack(fill='x',padx=10,pady=(3,1))
        self.label(self.overlay,'Только компьютерный бот','Computer bot only',color=MUTED,size=10).pack(anchor='center')

    def navigate(self,key):
        self.page=key
        for k,b in self.nav.items():
            b.configure(fg_color='#30264c' if k==key else 'transparent',border_width=1 if k==key else 0,border_color=ACCENT if k==key else BORDER)
        self.layout()

    def layout(self):
        for panel in (self.session,self.vision,self.analysis_card,self.settings):panel.grid_forget()
        self.log_card.grid_forget();self.action_dock.grid_forget()
        self.analysis.pack_forget()
        width=self.root.winfo_width()
        wide=width>=1050
        self._layout_width=wide
        self.full.grid_rowconfigure(2,weight=1)
        self.full.grid_rowconfigure(4,weight=0)
        self.body.grid_columnconfigure(0,weight=3)
        self.body.grid_columnconfigure(1,weight=2 if wide and self.page=='home' else 0)
        for i in range(4):self.statusbar.grid_columnconfigure(i,weight=1 if wide or i<2 else 0)
        self.body.grid()
        for i,cell in enumerate(self.option_cells):
            cell.grid(row=0 if wide else i,column=i if wide else 0,columnspan=1 if wide else 3)
        for i,cell in enumerate(self.toggle_cells):
            cell.grid(row=i//2 if wide else i,column=i%2 if wide else 0,columnspan=1 if wide else 2)
        for i,child in enumerate(self.statusbar.winfo_children()):
            child.grid(row=0 if wide else i//2,column=i if wide else i%2,pady=5)
        if self.page=='log':
            self.body.grid_remove()
            self.full.grid_rowconfigure(2,weight=0);self.full.grid_rowconfigure(4,weight=1)
            self.log_card.grid(row=4,column=1,sticky='nsew',padx=(0,10),pady=(0,10))
        elif self.page=='home':
            if wide:
                self.session.grid(row=0,column=0,rowspan=2,sticky='nsew',padx=(0,5),pady=4)
                self.vision.grid(row=0,column=1,sticky='nsew',padx=(5,0),pady=4)
                self.analysis_card.grid(row=1,column=1,sticky='nsew',padx=(5,0),pady=4)
                self.log_card.grid(row=4,column=1,sticky='ew',padx=(0,10),pady=(4,10))
            else:
                # Narrow side-by-side use: other workspaces are one click away.
                self.session.grid(row=0,column=0,columnspan=2,sticky='ew',pady=4)
                self.action_dock.grid(row=3,column=1,sticky='ew',padx=(0,10),pady=(2,8))
        else:
            panels={'vision':self.vision,'analysis':self.analysis_card,'settings':self.settings}
            panels[self.page].grid(row=0,column=0,columnspan=2,sticky='ew',pady=4)
            if self.page=='analysis':self.analysis.pack(fill='both',padx=14,pady=(4,10))
        canvas=getattr(self.body,'_parent_canvas',None)
        if canvas is not None:canvas.yview_moveto(0)

    def on_resize(self,event):
        if event.widget is self.root and not self.compact and (event.width>=1050)!=self._layout_width:
            if self._layout_pending is not None:self.root.after_cancel(self._layout_pending)
            self._layout_pending=self.root.after(80,self.finish_resize)

    def finish_resize(self):
        self._layout_pending=None
        if not self.compact:self.layout()

    def change_language(self):
        for widget,ru,en in self._labels:widget.configure(text=self.tr(ru,en))
        for widget,var,values in self._choices:
            mapping={self.tr(a,b):v for v,a,b in values}
            widget.configure(values=list(mapping))
            widget.set(next((k for k,v in mapping.items() if v==var.get()),str(var.get())))
        self.draw_candidates((self._last_event or {}).get('details',{}).get('candidates',[]))
        self.fen_short.set(self.tr('Из телеметрии','Reported FEN') if self._fen else '—')
        if self._fen:self.set_fen(self._fen)
        else:self.draw_board()
        self.refresh_workspace()
        self.save_workspace_settings()

    def change_opacity(self,value):
        alpha=clamp_alpha(value)
        self.alpha_text.set(f'{round(alpha*100)}%')
        if self.compact:self.root.attributes('-alpha',alpha)

    def save_workspace_settings(self):
        try:
            self._workspace_path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self._workspace_path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'language':self.lang.get(),'opacity':clamp_alpha(self.opacity.get()),'preview':self.preview.get()},indent=2),encoding='utf-8')
            tmp.replace(self._workspace_path)
        except OSError as exc:self.add_view_log('error',str(exc))

    def toggle_preview(self):
        if self.preview.get():self.preview_body.pack(fill='x',padx=12,pady=4,before=self.fen_label)
        else:self.preview_body.pack_forget()
        self.draw_board()

    def copy_fen(self):
        if self._fen:
            self.root.clipboard_clear();self.root.clipboard_append(self._fen)

    def draw_board(self):
        self.board.delete('all')
        ranks=parse_board(self._fen)
        size=min(max(80,self.board.winfo_width()),max(80,self.board.winfo_height()))
        # Coordinate gutter and a square board; empty state is not a claimed position.
        step=(size-16)/8
        black=self.color.get()=='black'
        if ranks and black:ranks=[list(reversed(row)) for row in reversed(ranks)]
        for y in range(8):
            self.board.create_text(6,(y+.5)*step,text=str(y+1 if black else 8-y),fill=MUTED,font=('Segoe UI',8))
            for x in range(8):
                left=12+x*step
                self.board.create_rectangle(left,y*step,left+step,(y+1)*step,fill='#b3b2c5' if (x+y)%2==0 else '#696b83',outline='')
                piece=ranks[y][x] if ranks else '.'
                if piece in GLYPHS:
                    self.board.create_text(left+step/2,(y+.5)*step,text=GLYPHS[piece],fill='#ffffff' if piece.isupper() else '#121318',font=('Segoe UI Symbol',max(12,int(step*.76))))
        for x in range(8):
            self.board.create_text(12+(x+.5)*step,8*step+7,text=('hgfedcba' if black else 'abcdefgh')[x],fill=MUTED,font=('Segoe UI',8))
        if not ranks:
            self.board.create_rectangle(15,size/2-15,size-3,size/2+15,fill=PANEL,outline=BORDER)
            self.board.create_text(size/2,size/2,text=self.tr('Нет позиции','No position'),fill=TEXT,font=('Segoe UI',10))

    def draw_candidates(self,candidates):
        for widget in self.candidates.winfo_children():widget.destroy()
        selected=(self._last_event or {}).get('move')
        if not candidates:
            self.ctk.CTkLabel(self.candidates,text=self.tr('Ожидание данных анализа','Waiting for analysis'),text_color=MUTED,font=('Segoe UI',11)).pack(padx=8,pady=7)
            return
        entries=[c for c in candidates if isinstance(c,dict)]
        entries.sort(key=lambda c:c.get('move')!=selected)
        for c in entries[:4]:
            if not isinstance(c,dict):continue
            cp=c.get('cp');policy=c.get('policy');move=c.get('move')
            chosen=move==selected
            row=self.ctk.CTkFrame(self.candidates,fg_color='#30264c' if chosen else 'transparent',corner_radius=5)
            row.pack(fill='x',padx=4,pady=1)
            self.ctk.CTkLabel(row,text=('◆ ' if chosen else '   ')+str(move or '—'),text_color=TEXT,width=74,anchor='w',font=('Consolas',12,'bold')).pack(side='left',padx=5)
            value=f'{cp:+d}' if isinstance(cp,int) else '—'
            self.ctk.CTkLabel(row,text=value,text_color=GREEN if isinstance(cp,int) and cp>0 else RED if isinstance(cp,int) and cp<0 else MUTED,width=54,font=('Consolas',11)).pack(side='left')
            if isinstance(policy,(float,int)) and 0<=policy<=1:
                bar=self.ctk.CTkProgressBar(row,width=45,height=6,progress_color=ACCENT,fg_color=BORDER)
                bar.set(policy);bar.pack(side='left',expand=True,fill='x',padx=4)
                self.ctk.CTkLabel(row,text=f'{policy:.0%}',text_color=MUTED,width=36,font=('Segoe UI',10)).pack(side='right',padx=5)

    def set_fen(self,fen):
        if parse_board(fen):
            self._fen=fen
            self.fen_text.set('FEN: '+(fen[:42]+'…' if len(fen)>42 else fen))
            self.fen_short.set(self.tr('Из телеметрии','Reported FEN'))
            self.fen_turn.set(self.tr('Ход белых','White to move') if fen.split()[1:2]==['w'] else self.tr('Ход чёрных','Black to move'))
            self.draw_board()

    def reset_analysis(self):
        self._last_event=None;self._fen='';self.fen_text.set('—');self.fen_short.set('—');self.fen_turn.set('—');self.notice.set('')
        self.move_text.set('—');self.eval_text.set('—');self.depth_text.set('—');self.detail_text.set('')
        self.draw_board();self.draw_candidates([])
        self.analysis.configure(state='normal');self.analysis.delete('1.0','end');self.analysis.configure(state='disabled')

    def render_analysis(self,event,lines):
        self._last_event=event
        self.set_fen(event.get('fen',''))
        d=event['details']
        self.move_text.set(str(event.get('move','—')))
        cp=d.get('engine_cp');self.eval_text.set(f'{cp:+d} cp' if isinstance(cp,int) else '—')
        self.depth_text.set(str(d.get('search_depth','—')))
        self.detail_text.set(self.tr('Ответ: ','Reply: ')+str(d.get('expected_reply') or '—')+' · '+str(d.get('search_time_s','—'))+' s')
        self.draw_candidates(d.get('candidates') or [])
        self.analysis.configure(state='normal');self.analysis.delete('1.0','end')
        self.analysis.insert('end','\n'.join(lines));self.analysis.configure(state='disabled')

    def observe_message(self,t,tag):
        match=re.search(r'(?:[Ff][Ee][Nn][: ]+|Начальная позиция: |Подключено к текущей партии без истории: )([prnbqkPRNBQK1-8/]+ [wb] [KQkq-]+ [a-h1-8-]+ \d+ \d+)',t)
        if match:self.set_fen(match.group(1))
        if tag=='error':self.notice.set(t[:180])

    def add_view_log(self,tag,text):
        line=(tag,f'[{datetime.datetime.now():%H:%M:%S}] {text}\n')
        self._messages.append(line)
        if self._filter in ('all',tag):
            self.log.configure(state='normal');self.log.insert('end',line[1],tag)
            if int(self.log.index('end-1c').split('.')[0])>1200:self.log.delete('1.0','301.0')
            self.log.configure(state='disabled')
            if self.autoscroll.get():self.log.see('end')

    def filter_log(self,value):
        self._filter=value
        self.log.configure(state='normal');self.log.delete('1.0','end')
        for tag,line in self._messages:
            if value in ('all',tag):self.log.insert('end',line,tag)
        self.log.configure(state='disabled')
        if self.autoscroll.get():self.log.see('end')

    def clear_view_log(self):
        self._messages.clear();self.filter_log(self._filter)

    def panel_overlaps(self):
        if not self.rect:return False
        x,y,s=(getattr(self.bot,'rect',None) or self.rect)
        r=self.root
        return rectangles_overlap((r.winfo_rootx(),r.winfo_rooty(),r.winfo_width(),r.winfo_height()),(x,y,s,s))

    def refresh_workspace(self):
        active=bool(self.worker and self.worker.is_alive())
        if active!=self._active:
            self._active=active
            for w in self._locked+[self.start,self.attach]:w.configure(state='disabled' if active else 'normal')
        self.model_status.set('▱  '+self.checkpoint.get())
        self.side_status.set('♙  '+(self.tr('Белые','White') if self.color.get()=='white' else self.tr('Чёрные','Black')))
        self.region_status.set('◎  '+(f'{self.rect[2]} × {self.rect[2]}' if self.rect else self.tr('Нет области','No region')))
        import time
        now=time.monotonic()
        signature=(self.checkpoint.get(),bool(self.rect),self.lang.get())
        if signature!=self._system_signature or now-getattr(self,'_system_checked',0)>1:
            self._system_signature=signature;self._system_checked=now
            self._engine_exists=self.engine.is_file()
            self._model_exists=(self.run/'checkpoints'/self.checkpoint.get()).is_file()
            self.engine_status.set(('● ' if self._engine_exists else '○ ')+self.tr('Движок','Engine'))
            self.checkpoint_status.set(('● ' if self._model_exists else '○ ')+self.tr('Модель','Model'))
            self.vision_status.set(('● ' if self.rect else '○ ')+self.tr('Область','Region'))
        if self.rect:
            x,y,s=self.rect;self.board_text.set(f'x={x}  y={y}  {s} × {s} px')
        else:self.board_text.set(self.tr('Область не задана','No region selected'))
        self.summary_text.set(self.checkpoint.get()+' · '+self.tr('Белые','White') if self.color.get()=='white' else self.checkpoint.get()+' · '+self.tr('Чёрные','Black'))
        if active and self.panel_overlaps() and not self.ev.is_set():
            self.ev.set();self.add_view_log('error',self.tr('Окно перекрывает доску. Запрошена остановка.','Window overlaps board. Stop requested.'))
        if active:self.state_text.set(self.tr('Остановка…','Stopping…') if self.ev.is_set() else self.tr('Сессия активна','Session active'))
        elif self.worker:self.state_text.set(self.tr('● Остановлено','● Stopped'))
        elif self.rect and self._engine_exists and self._model_exists and self.consent.get():
            self.state_text.set(self.tr('● Готов к работе','● Ready'))
        else:self.state_text.set(self.tr('○ Настройка','○ Setup'))
        if self._status_cache!=active:
            self._status_cache=active
            for w in (self.stop_button,self.overlay_stop,self.header_stop):w.configure(state='normal' if active else 'disabled')

    def prepare_launch_layout(self):
        """Prefer an actual non-overlapping window; shrink the full panel if needed."""
        r=self.root;r.update_idletasks()
        board=self.rect
        sw,sh=r.winfo_screenwidth(),r.winfo_screenheight()
        width,height=r.winfo_width(),r.winfo_height()
        # Include some space for native window borders and title bar.
        for candidate in (width, min(width,720), min(width,560),510):
            pos=safe_position(board,candidate+16,height+42,sw,sh)
            if pos is not None:
                r.geometry(f'{candidate}x{height}+{pos[0]}+{pos[1]}')
                r.update_idletasks()
                return not self.panel_overlaps()
        return False

    def toggle_overlay(self):
        r=self.root;r.update_idletasks()
        if not self.compact:
            pos=safe_position(getattr(self.bot,'rect',None) or self.rect,376,326,r.winfo_screenwidth(),r.winfo_screenheight())
            if pos is None:
                messagebox.showwarning('Vision Bot',self.tr('Нет свободного места рядом с доской.','No space beside the board.'));return
            self._full_geometry=r.geometry()
            self.compact=True;self.full.pack_forget();self.overlay.pack(fill='both',expand=True)
            r.minsize(340,280);r.geometry(f'360x300+{pos[0]}+{pos[1]}')
            r.attributes('-alpha',clamp_alpha(self.opacity.get()));r.attributes('-topmost',True)
        else:
            geometry=self._full_geometry or '560x650'
            if self.worker and self.worker.is_alive():
                match=re.match(r'(\d+)x(\d+)',geometry)
                width,height=(map(int,match.groups()) if match else (560,650))
                rect=getattr(self.bot,'rect',None) or self.rect
                sw,sh=r.winfo_screenwidth(),r.winfo_screenheight()
                result=None
                for candidate in (width,min(width,720),min(width,560),510):
                    pos=safe_position(rect,candidate+16,height+42,sw,sh)
                    if pos is not None:
                        result=f'{candidate}x{height}+{pos[0]}+{pos[1]}'
                        break
                if result is None:
                    messagebox.showwarning('Vision Bot',self.tr('Для развёрнутой панели нет места. Остановите сессию перед раскрытием.','No space for the full panel. Stop the session before expanding.'))
                    return
                geometry=result
            self.compact=False;self.overlay.pack_forget();self.full.pack(fill='both',expand=True)
            r.attributes('-alpha',1.);r.minsize(510,520)
            r.geometry(geometry)
            self.set_topmost();self.layout()
        self.save_workspace_settings()

    def drag_start(self,event):
        self._drag=(event.x_root-self.root.winfo_x(),event.y_root-self.root.winfo_y())

    def drag_move(self,event):
        if not self.compact or not hasattr(self,'_drag'):return
        r=self.root
        x=max(0,min(event.x_root-self._drag[0],r.winfo_screenwidth()-r.winfo_width()))
        y=max(0,min(event.y_root-self._drag[1],r.winfo_screenheight()-r.winfo_height()))
        rect=getattr(self.bot,'rect',None) or self.rect
        if rect and rectangles_overlap((x,y,r.winfo_width(),r.winfo_height()),(*rect[:2],rect[2],rect[2])):return
        r.geometry(f'+{x}+{y}')
