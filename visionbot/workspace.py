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
from tkinter import messagebox, filedialog

from .telemetry import rectangles_overlap
from .ui_layout import ScrollViewport, StableStringVar, layout_mode
from .ui_icons import icon_image
from .overlays import OverlayManager,NAMES
from .analysis_view import report_sections
from neural.agent_profiles import ALIASES
from .design import (BG, PANEL, FIELD, BORDER, TEXT, MUTED, DIM, ACCENT,
                     ACCENT_TEXT, HOVER, SURFACE_HOVER, ACTIVE, TRACK, GREEN, RED,
                     BOARD_LIGHT, BOARD_DARK, STOP_BG, STOP_HOVER, STOP_BORDER, WARNING,
                     FONT, MONO, RADIUS, button_style)
from .log_model import matches, select_entries
from .presentation_rules import preview_layout, form_columns, session_state, short_text

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
        self._last_window_size=None
        self._board_pending=None
        self._board_signature=None
        self._layout_key=None
        self._layout_mode=None
        self._layout_pending=None
        self._status_cache=None
        self._full_geometry=None
        self._active=False
        self._seen_worker=None
        self._last_event=None
        self._fen=''
        self._messages=deque(maxlen=600)
        self._filter='all'
        self.log_query=tk.StringVar(value='')
        self.log_paused=tk.BooleanVar(value=False)
        self._paused_messages=()
        self._log_search_job=None
        self._visible_entries=deque()
        self._applied_query=''
        self._preview_layout_key=None
        self._form_layout_key=None
        self._preview_resize_job=None
        self._form_resize_job=None
        self._page_scroll={}
        self.filter_var=StableStringVar(value='all')
        self._labels=[]
        self._locked=[]
        self._choices=[]
        self._workspace_path=self.path.with_name('vision_ui.json')
        try:
            settings=json.loads(self._workspace_path.read_text(encoding='utf-8'))
            if not isinstance(settings,dict): settings={}
        except (OSError,ValueError): settings={}
        self.lang=StableStringVar(value='EN' if settings.get('language')=='EN' else 'RU')
        self.opacity=tk.DoubleVar(value=clamp_alpha(settings.get('opacity',1.0)))
        self.preview=tk.BooleanVar(value=bool(settings.get('preview',True)))
        self.autoscroll=tk.BooleanVar(value=bool(settings.get('follow_log',True)))
        self.topmost.set(bool(settings.get('topmost',self.topmost.get())))
        self.log_collapsed=tk.BooleanVar(value=bool(settings.get('log_collapsed',False)))
        self.state_text=StableStringVar(value=self.tr('Ожидание','Idle'))
        self.latest_event_text=StableStringVar(value='—')
        self.log_count=StableStringVar(value='0 / 0')
        self.summary_text=StableStringVar(value='')
        self.board_text=StableStringVar(value='')
        self.fen_text=StableStringVar(value='—')
        self.move_text=StableStringVar(value='—')
        self.eval_text=StableStringVar(value='—')
        self.depth_text=StableStringVar(value='—')
        self.detail_text=StableStringVar(value='')
        self.notice=StableStringVar(value='')
        self.model_status=StableStringVar(value='')
        self.side_status=StableStringVar(value='')
        self.region_status=StableStringVar(value='')
        self.engine_status=StableStringVar(value='')
        self.checkpoint_status=StableStringVar(value='')
        self.vision_status=StableStringVar(value='')
        self.fen_short=StableStringVar(value='—')
        self.fen_turn=StableStringVar(value='—')
        self._system_signature=None
        self.alpha_text=StableStringVar(value=f'{round(self.opacity.get()*100)}%')
        r.title('Vision Bot · Chess AI')
        try: version=(Path(__file__).resolve().parents[1]/'VERSION').read_text(encoding='utf-8').strip()
        except OSError: version='—'
        r.configure(fg_color=BG)
        scale=self.window_scale()
        sw,sh=round(r.winfo_screenwidth()/scale),round(r.winfo_screenheight()/scale)
        width,height=min(1360,max(420,sw-70)),min(850,max(440,sh-90))
        saved=re.fullmatch(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)',str(settings.get('geometry','')))
        if saved:
            w,h,x,y=map(int,saved.groups())
            width=max(420,min(w,sw-30));height=max(440,min(h,sh-60))
            x=max(0,min(x,r.winfo_screenwidth()-round(width*scale)-16))
            y=max(0,min(y,r.winfo_screenheight()-round(height*scale)-42))
            r.geometry(f'{width}x{height}+{x}+{y}')
        else:r.geometry(f'{width}x{height}')
        r.minsize(420,440)
        r.attributes('-topmost',bool(self.topmost.get()))
        self.full=ctk.CTkFrame(r,fg_color=BG,corner_radius=0)
        self.full.pack(fill='both',expand=True)
        self.full.grid_columnconfigure(1,weight=1)
        self.full.grid_rowconfigure(2,weight=1)
        bar=self.card(self.full)
        bar.grid(row=0,column=0,columnspan=2,sticky='ew',padx=10,pady=(9,4))
        self.label(bar,'VISION BOT','VISION BOT',size=14,bold=True).pack(side='left',padx=12,pady=5)
        self.label(bar,version,version,color=MUTED,size=11).pack(side='left',padx=3)
        self.button(bar,'Компакт','Compact',self.toggle_overlay,width=78).pack(side='right',padx=6,pady=5)
        self.header_stop=self.button(bar,'Стоп','Stop',self.stop,width=66)
        self.header_stop.pack(side='right',padx=3,pady=5)
        self.header_stop.configure(fg_color=STOP_BG,hover_color=STOP_HOVER,border_color=STOP_BORDER,text_color=RED)
        self.statusbar=self.card(self.full)
        self.statusbar.grid(row=1,column=1,sticky='ew',padx=(0,10),pady=(4,5))
        self.status_cells=[]
        for i,(var,color) in enumerate(((self.state_text,GREEN),(self.model_status,TEXT),(self.side_status,TEXT),(self.region_status,MUTED))):
            self.statusbar.grid_columnconfigure(i,weight=1)
            cell=self.label(self.statusbar,variable=var,color=color,size=12,bold=i==0)
            if i>0:cell.configure(image=icon_image(ctk,('home','model','side','vision')[i],size=16),compound='left')
            cell.grid(row=0,column=i,sticky='w',padx=10,pady=8)
            self.status_cells.append(cell)
        self.side=self.card(self.full)
        self.side.grid(row=1,column=0,rowspan=4,sticky='ns',padx=(10,8),pady=(4,10))
        self.nav={}
        self.nav_names={'home':('Сессия','Session'),'vision':('Доска','Board'),'analysis':('Анализ','Analysis'),
                        'log':('Журнал','Log'),'settings':('Настройки','Settings')}
        for key,(ru,en) in self.nav_names.items():
            b=self.button(self.side,ru,en,lambda k=key:self.navigate(k),width=125)
            b.configure(image=icon_image(ctk,key),compound='left',anchor='w',height=36,fg_color='transparent',border_width=0)
            b.pack(fill='x',padx=7,pady=3)
            self.nav[key]=b
        system=self.card(self.side)
        self.system_card=system
        system.pack(side='bottom',fill='x',padx=7,pady=8)
        self.label(system,'Система','System',bold=True).pack(anchor='w',padx=8,pady=(7,3))
        for var in (self.engine_status,self.checkpoint_status,self.vision_status):
            self.label(system,variable=var,color=MUTED,size=11,wrap=112).pack(anchor='w',padx=8,pady=2)
        self.label(system,'Компьютерный бот','Computer bot only',color=MUTED,size=10,wrap=112).pack(anchor='w',padx=8,pady=(3,7))
        self.viewport=ScrollViewport(self.full,BG,ctk.CTkScrollbar)
        self.viewport.grid(row=2,column=1,sticky='nsew',padx=(0,10),pady=(0,4))
        self.body=self.viewport.body
        self.session=self.card(self.body)
        self.vision=self.card(self.body)
        self.analysis_card=self.card(self.body)
        self.settings=self.card(self.body)
        self.log_card=self.card(self.full)
        self.action_dock=self.card(self.full)
        self.action_dock.grid_columnconfigure(0,weight=3)
        self.action_dock.grid_columnconfigure(1,weight=2)
        self.action_dock.grid_columnconfigure(2,weight=1)
        self.start=self.button(self.action_dock,'Запустить','Start',self.launch,primary=True,width=90)
        self.start.configure(height=36)
        self.start.grid(row=0,column=0,sticky='ew',padx=(8,4),pady=6)
        self.attach=self.button(self.action_dock,'Подключиться','Join game',lambda:self.launch(attach_any_position=True),width=75)
        self.attach.grid(row=0,column=1,sticky='ew',padx=4,pady=6)
        self.stop_button=self.button(self.action_dock,'Стоп','Stop',self.stop,width=58)
        self.stop_button.grid(row=0,column=2,sticky='ew',padx=(4,8),pady=6)
        self.stop_button.configure(fg_color=STOP_BG,hover_color=STOP_HOVER,border_color=STOP_BORDER,text_color=RED)
        self.build_session()
        self.build_vision()
        self.build_analysis()
        self.build_log()
        self.overlays=OverlayManager(self)
        self.build_settings()
        self.build_overlay()
        self.color.trace_add('write',self.sync_color)
        self.navigate('home')
        r.bind('<Configure>',self.on_resize,add='+')
        r.bind('<Escape>',lambda _:self.stop(),add='+')
        r.bind('<Control-Shift-m>',lambda _:self.toggle_overlay(),add='+')
        for index,key in enumerate(self.nav_names,1):
            r.bind(f'<Control-Key-{index}>',lambda _,k=key:self.navigate(k) if not self.compact else None,add='+')
        self.refresh_workspace()

    def card(self,parent):
        return self.ctk.CTkFrame(parent,fg_color=PANEL,border_width=1,
                                 border_color=BORDER,corner_radius=RADIUS)

    def label(self,parent,ru='',en='',*,variable=None,color=TEXT,size=12,bold=False,wrap=0):
        kw=dict(text_color=color,font=(FONT,size,'bold' if bold else 'normal'),anchor='w',justify='left',wraplength=wrap,height=max(16,size+5))
        if variable is not None: kw['textvariable']=variable
        else: kw['text']=self.tr(ru,en)
        w=self.ctk.CTkLabel(parent,**kw)
        if variable is None:self._labels.append((w,ru,en))
        return w

    def button(self,parent,ru,en,command,*,primary=False,width=110):
        w=self.ctk.CTkButton(parent,text=self.tr(ru,en),command=command,width=width,
                             **button_style(primary))
        self._labels.append((w,ru,en))
        return w

    def title(self,parent,ru,en,subtitle_ru='',subtitle_en=''):
        self.label(parent,ru,en,size=18,bold=True).pack(anchor='w',padx=14,pady=(12,3))
        if subtitle_ru:self.label(parent,subtitle_ru,subtitle_en,color=MUTED,wrap=320).pack(anchor='w',padx=14,pady=(0,4))

    def row(self,parent):
        w=self.ctk.CTkFrame(parent,fg_color='transparent')
        w.pack(fill='x',padx=12,pady=3)
        return w

    def section(self,parent,n,ru,en):
        divider=self.ctk.CTkFrame(parent,fg_color=BORDER,height=1,corner_radius=0)
        divider.pack(fill='x',padx=16,pady=(12,5))
        self.label(parent,ru,en,size=13,bold=True).pack(anchor='w',padx=17,pady=(0,4))

    def choice(self,parent,ru,en,var,values,*,change=None,lock=False):
        if ru:self.label(parent,ru,en,color=MUTED,size=11).pack(anchor='w',padx=3,pady=(0,1))
        def options(): return {self.tr(a,b):v for v,a,b in values}
        def picked(display):
            mapping=options()
            if display not in mapping:return
            var.set(mapping[display])
            if change:change()
        opts=options()
        widget=self.ctk.CTkOptionMenu(parent,values=list(opts),command=picked,height=32,width=104,
                 dynamic_resizing=False,corner_radius=RADIUS,fg_color=FIELD,button_color=BORDER,button_hover_color=ACTIVE,
                 dropdown_fg_color=PANEL,dropdown_hover_color=ACTIVE,dropdown_text_color=TEXT,text_color=TEXT,font=(FONT,13))
        widget.pack(fill='x',padx=3,pady=(0,2))
        widget.set(next((k for k,v in opts.items() if v==var.get()),str(var.get())))
        self._choices.append((widget,var,values))
        if lock:self._locked.append(widget)
        return widget

    def switch(self,parent,ru,en,var,command=None,lock=False):
        w=self.ctk.CTkSwitch(parent,text=self.tr(ru,en),variable=var,command=command,
                           progress_color=TRACK,fg_color=BORDER,button_color=TEXT,text_color=TEXT,
                           font=(FONT,12))
        w.pack(anchor='w',padx=14,pady=6)
        self._labels.append((w,ru,en))
        if lock:self._locked.append(w)
        return w

    def build_session(self):
        c=self.session
        self.title(c,'Настройка сессии','Session setup','Модель, область захвата и режим игры','Model, capture region and game mode')
        self.section(c,1,'Выбор модели','Choose model')
        row=self.row(c)
        picker=self.ctk.CTkFrame(row,fg_color='transparent')
        picker.pack(side='left',fill='x',expand=True)
        from .external_session import available
        self.agent_picker=self.choice(picker,'','',self.checkpoint,[(n,n,n) for n in (*ALIASES,*available())],change=self.on_agent_change)
        self.model_hint=self.ctk.CTkFrame(row,fg_color=FIELD,corner_radius=RADIUS)
        self.label(self.model_hint,'Выбранная модель','Selected model',size=10,color=MUTED).pack(anchor='w',padx=8,pady=(2,0))
        self.model_hint_text=StableStringVar(value='')
        self.label(self.model_hint,variable=self.model_hint_text,size=11).pack(anchor='w',padx=8,pady=(0,2))
        from external_core.uci import PROFILES
        profile_row=self.row(c)
        self.choice(profile_row,'Мощность UCI','UCI performance',self.external_profile,[(n,n,n) for n in PROFILES],lock=True)
        self.button(c,'Multi-Engine Lab · локальная доска','Multi-Engine Lab · local board',self.open_multi_engine,width=240).pack(fill='x',padx=17,pady=6)
        self.section(c,2,'Область доски','Board region')
        row=self.row(c)
        b=self.button(row,'▣  Выделить область','▣  Select region',self.calibrate,width=150)
        b.configure(border_color=ACCENT,fg_color=ACTIVE)
        b.pack(side='left',fill='x',expand=True,padx=(3,5));self._locked.append(b)
        self.info=self.label(row,variable=self.board_text,color=MUTED,size=11,wrap=145)
        self.info.pack(side='right',padx=4)
        self.section(c,3,'Настройки партии','Game settings')
        row=self.row(c)
        self.option_row=row
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
        self.toggle_row=toggles
        toggles.grid_columnconfigure((0,1),weight=1,uniform='toggles')
        self.toggle_cells=[]
        for i,(ru,en,var,command,lock) in enumerate([
            ('Фантом-X23','Phantom-X23',self.phantom,None,True),
            ('Восстановление','Recover game',self.resume,None,True),
            ('Self-play (+500)','Self-play (+500)',self.train,None,True),
            ('Поверх окон','Always on top',self.topmost,self.set_topmost,False)]):
            cell=self.ctk.CTkFrame(toggles,fg_color=FIELD,corner_radius=RADIUS)
            cell.grid(row=i//2,column=i%2,sticky='ew',padx=3,pady=3)
            toggle=self.ctk.CTkSwitch(cell,text='',variable=var,command=command,progress_color=TRACK,
                                      fg_color=BORDER,button_color=TEXT,width=36,switch_width=34,switch_height=18)
            toggle.pack(side='right',padx=7,pady=5)
            self.label(cell,ru,en,size=12).pack(side='left',padx=7)
            if lock:self._locked.append(toggle)
            self.toggle_cells.append(cell)
        self.section(c,4,'Запуск','Launch')
        consent=self.ctk.CTkCheckBox(c,text=self.tr('Только компьютерный соперник','Computer opponent only'),variable=self.consent,
                                    fg_color=TRACK,hover_color=ACTIVE,text_color=TEXT,font=(FONT,12),checkbox_width=18,checkbox_height=18)
        consent.pack(anchor='w',padx=17,pady=(2,4))
        self._labels.append((consent,'Только компьютерный соперник','Computer opponent only'))
        self._locked.append(consent)
        self.label(c,'Запуск и подключение — в нижней панели.','Start and join are in the bottom action bar.',color=MUTED,size=11,wrap=280).pack(anchor='w',padx=17,pady=(0,5))
        self.warning_label=self.label(c,variable=self.notice,color=RED,wrap=300,size=11)
        self.notice.trace_add('write',lambda *_:self.show_notice())
        c.bind('<Configure>',self.schedule_form_layout,add='+')

    def show_notice(self):
        if self.notice.get():self.warning_label.pack(anchor='w',padx=14,pady=(0,5))
        else:self.warning_label.pack_forget()

    def build_vision(self):
        c=self.vision
        header=self.row(c)
        self.label(header,'Позиция на доске','Board position',size=16,bold=True).pack(side='left',padx=2)
        toggle=self.ctk.CTkSwitch(header,text='',variable=self.preview,command=self.toggle_preview,
                                  width=38,switch_width=34,switch_height=18,progress_color=TRACK,fg_color=BORDER)
        toggle.pack(side='right',padx=3)
        self.preview_body=self.row(c)
        self.board=tk.Canvas(self.preview_body,width=186,height=186,bg=PANEL,highlightthickness=0)
        self.board.grid(row=0,column=0,padx=(2,8),pady=2,sticky='n')
        self.board.bind('<Configure>',self.schedule_board)
        info=self.ctk.CTkFrame(self.preview_body,fg_color='transparent')
        self.preview_info=info
        info.grid(row=0,column=1,sticky='nsew',padx=3)
        self.preview_body.grid_columnconfigure(1,weight=1)
        self.preview_body.bind('<Configure>',self.schedule_preview_layout,add='+')
        self.label(info,'Источник позиции','Position source',color=MUTED,size=11).pack(anchor='w')
        self.recognition=self.label(info,variable=self.fen_short,color=TEXT,size=11,wrap=125)
        self.recognition.pack(anchor='w',pady=(1,5))
        self.label(info,'Оценка · cp','Evaluation · cp',color=MUTED,size=11).pack(anchor='w')
        self.label(info,variable=self.eval_text,size=20,bold=True).pack(anchor='w')
        self.label(info,variable=self.fen_turn,color=MUTED,size=10).pack(anchor='w')
        self.button(info,'Копировать FEN','Copy FEN',self.copy_fen,width=100).pack(anchor='w',pady=(5,1))
        self.fen_label=self.label(c,variable=self.fen_text,color=MUTED,wrap=280,size=10)
        self.fen_label.pack(anchor='w',padx=14,pady=(0,8))
        self.toggle_preview()

    def schedule_preview_layout(self,event=None):
        if self._preview_resize_job is not None:self.root.after_cancel(self._preview_resize_job)
        self._preview_resize_job=self.root.after(90,self.apply_preview_layout)

    def apply_preview_layout(self):
        self._preview_resize_job=None
        if not self.preview_body.winfo_ismapped():return
        scale=self.window_scale()
        width=self.preview_body.winfo_width()/scale
        if width<80:return
        plan=preview_layout(width)
        if plan==self._preview_layout_key:return
        self._preview_layout_key=plan
        self.preview_body.grid_columnconfigure(0,weight=1 if plan.stacked else 0)
        self.preview_body.grid_columnconfigure(1,weight=0 if plan.stacked else 1)
        self.board.grid_configure(row=0,column=0,columnspan=2 if plan.stacked else 1,
                                  padx=0 if plan.stacked else (2,8))
        self.preview_info.grid_configure(row=1 if plan.stacked else 0,column=0 if plan.stacked else 1,
                                         columnspan=2 if plan.stacked else 1,pady=(6,2) if plan.stacked else 0)
        self.board.configure(width=round(plan.size*scale),height=round(plan.size*scale))
        self.schedule_board()

    def schedule_form_layout(self,event=None):
        if self._form_resize_job is not None:self.root.after_cancel(self._form_resize_job)
        self._form_resize_job=self.root.after(90,self.apply_form_layout)

    def apply_form_layout(self):
        self._form_resize_job=None
        if not self.session.winfo_ismapped():return
        width=self.option_row.winfo_width()/self.window_scale()
        if width<80:return
        columns=form_columns(width)
        if columns==self._form_layout_key:return
        self._form_layout_key=columns
        for row in (self.option_row,self.toggle_row):
            for col in range(3):
                row.grid_columnconfigure(col,weight=1 if col<columns else 0,
                                         uniform='form' if col<columns else '')
        for i,cell in enumerate(self.option_cells):
            cell.grid_configure(row=i//columns,column=i%columns,
                                columnspan=columns if i==2 else 1)
        for i,cell in enumerate(self.toggle_cells):
            cell.grid_configure(row=i//columns,column=i%columns,columnspan=1)

    def build_analysis(self):
        c=self.analysis_card
        self.title(c,'Анализ позиции','Position analysis')
        stats=self.row(c)
        for i,(ru,en,v) in enumerate([('Ход','Move',self.move_text),('Оценка · cp','Score · cp',self.eval_text),('Глубина','Depth',self.depth_text)]):
            stats.grid_columnconfigure(i,weight=1,uniform='metrics')
            metric=self.ctk.CTkFrame(stats,fg_color=FIELD,corner_radius=RADIUS)
            metric.grid(row=0,column=i,sticky='ew',padx=3)
            self.label(metric,ru,en,color=MUTED,size=10).pack(anchor='w',padx=7,pady=(3,0))
            self.label(metric,variable=v,size=17,bold=True).pack(anchor='w',padx=7,pady=(0,4))
        self.candidates=self.ctk.CTkFrame(c,fg_color=FIELD,corner_radius=RADIUS)
        self.candidates.pack(fill='x',padx=14,pady=(3,7))
        self.detail_label=self.label(c,variable=self.detail_text,color=MUTED,wrap=280,size=11)
        self.detail_label.pack(anchor='w',padx=14,pady=(0,5))
        self.label(c,'Полосы: policy · оценки от стороны хода','Bars: policy · scores from side to move',color=MUTED,size=10,wrap=280).pack(anchor='w',padx=14,pady=(0,6))
        self.analysis=self.ctk.CTkTextbox(c,height=180,fg_color=FIELD,text_color=TEXT,font=(MONO,12),wrap='word',state='disabled')
        self.analysis.tag_config('heading',foreground=MUTED)
        self.build_candidate_rows()
        self.draw_candidates([])

    def build_log(self):
        c=self.log_card
        header=self.row(c)
        self.label(header,'Журнал сессии','Session log',size=16,bold=True).pack(side='left',padx=2)
        self.button(header,'Очистить вид','Clear view',self.clear_log,width=90).pack(side='right',padx=2)
        self.log_toggle=self.button(header,'⌄','⌄',self.toggle_log,width=30)
        self.log_toggle.pack(side='right',padx=2)
        filters=self.row(c)
        self.log_filters=filters
        self.filter_values=[('all','Все','All'),('info','Система','System'),('analysis','Анализ','Analysis'),('move','Ходы','Moves'),('error','Ошибки','Errors')]
        def select(value):
            mapping={self.tr(a,b):v for v,a,b in self.filter_values}
            if value in mapping:
                self.filter_var.set(mapping[value]);self.filter_log(mapping[value])
        self.filter_choice=self.ctk.CTkOptionMenu(filters,values=[self.tr(a,b) for _,a,b in self.filter_values],
                command=select,height=30,corner_radius=RADIUS,fg_color=FIELD,button_color=BORDER,
                button_hover_color=ACTIVE,dropdown_fg_color=PANEL,dropdown_hover_color=ACTIVE,
                dropdown_text_color=TEXT,text_color=TEXT,font=(FONT,12),dynamic_resizing=False,width=110)
        self.filter_choice.pack(side='left',padx=(0,8))
        self.label(filters,variable=self.log_count,color=MUTED,size=11).pack(side='right')
        self.filter_choice.set(self.tr('Все','All'))
        self._choices.append((self.filter_choice,self.filter_var,self.filter_values))
        self.log_tools=self.ctk.CTkFrame(c,fg_color='transparent')
        self.log_search=self.ctk.CTkEntry(self.log_tools,textvariable=self.log_query,
            fg_color=FIELD,border_color=BORDER,text_color=TEXT,height=30,corner_radius=RADIUS,
            font=(FONT,12))
        self.label(self.log_tools,'Поиск','Search',size=11,color=MUTED).pack(side='left',padx=(0,5))
        self.log_search.pack(side='left',fill='x',expand=True,padx=(0,4))
        self.log_actions=self.ctk.CTkFrame(c,fg_color='transparent')
        self.button(self.log_actions,'Копировать','Copy',self.copy_log,width=76).pack(side='left',padx=(0,4))
        self.button(self.log_actions,'Экспорт','Export',self.export_log,width=65).pack(side='left',padx=2)
        self.log_options=self.ctk.CTkFrame(c,fg_color='transparent')
        self.switch(self.log_options,'Пауза','Pause',self.log_paused,self.toggle_log_pause)
        self.switch(self.log_options,'Следить','Follow',self.autoscroll,self.follow_log)
        for child in self.log_options.winfo_children():
            child.pack_configure(side='left',padx=(0,10),pady=2)
        self.log=self.ctk.CTkTextbox(c,height=76,fg_color=FIELD,text_color=TEXT,font=(MONO,11),wrap='word',state='disabled',corner_radius=RADIUS)
        self.log.pack(fill='both',expand=True,padx=12,pady=(1,7))
        for tag,color in [('error',RED),('move',GREEN),('analysis',MUTED),('info',TEXT)]:
            self.log.tag_config(tag,foreground=color)

        self.log_query.trace_add('write',self.schedule_log_search)

    def build_settings(self):
        c=self.settings
        self.title(c,'Настройки интерфейса','Interface settings')
        self.choice(c,'Язык интерфейса','Interface language',self.lang,[('RU','Русский','Russian'),('EN','English','English')],change=self.change_language)
        self.switch(c,'Автопрокрутка журнала','Auto-scroll log',self.autoscroll)
        self.label(c,'Прозрачность оверлея','Overlay opacity',color=MUTED).pack(anchor='w',padx=14,pady=(8,0))
        row=self.row(c)
        self.ctk.CTkSlider(row,from_=.55,to=1,number_of_steps=45,variable=self.opacity,
                          command=self.change_opacity,progress_color=TRACK,button_color=TEXT).pack(side='left',fill='x',expand=True)
        self.label(row,variable=self.alpha_text).pack(side='right',padx=8)
        self.label(c,'Ctrl+1–5: разделы. Ctrl+Shift+M: компактный режим. Left Alt+1 / 2: запуск / подключение в разрешённом тесте','Ctrl+1–5: pages. Ctrl+Shift+M: compact mode. Left Alt+1 / 2: start / join in a permitted test',color=MUTED,wrap=300).pack(anchor='w',padx=14,pady=(2,5))
        self.label(c,'55–100%. Оверлей остаётся видимым и не перекрывает доску.','55–100%. Overlay stays visible and must not cover the board.',color=MUTED,wrap=300).pack(anchor='w',padx=14,pady=(0,8))
        self.section(c,'+','Рабочее пространство оверлеев','Overlay workspace')
        for key,(ru,en,_) in NAMES.items():
            row=self.row(c)
            self.label(row,ru,en,bold=True).pack(side='left',padx=3)
            self.button(row,'Открыть / закрыть','Open / close',lambda k=key:self.overlays.toggle(k),width=130).pack(side='right')
        row=self.row(c)
        self.button(row,'Минимум','Minimal',lambda:self.overlays.apply_preset('minimal'),width=75).pack(side='left',expand=True,padx=2)
        self.button(row,'Анализ','Review',lambda:self.overlays.apply_preset('review'),width=75).pack(side='left',expand=True,padx=2)
        self.button(row,'Все','All',lambda:self.overlays.apply_preset('full'),width=65).pack(side='left',expand=True,padx=2)
        self.button(c,'Разместить окна','Arrange windows',self.overlays.arrange).pack(fill='x',padx=14,pady=3)
        self.button(c,'Скрыть основную панель','Hide main panel',self.hide_main_for_overlays).pack(fill='x',padx=14,pady=3)
        self.button(c,'Скрыть все оверлеи','Close all overlays',self.overlays.close_all).pack(fill='x',padx=14,pady=3)
        self.button(c,'Сбросить расположение','Reset layout',self.overlays.reset).pack(fill='x',padx=14,pady=3)
        self.button(c,'Компактный вид основной панели','Compact main panel',self.toggle_overlay).pack(fill='x',padx=14,pady=3)
        self.button(c,'Сохранить настройки','Save settings',self.save_workspace_settings).pack(fill='x',padx=14,pady=(4,12))

    def hide_main_for_overlays(self):
        self.overlays.open('control')
        if 'control' in self.overlays.windows:
            self.root.iconify()

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
            metric=ctk.CTkFrame(row,fg_color=FIELD,corner_radius=RADIUS)
            metric.grid(row=0,column=i,sticky='ew',padx=3)
            self.label(metric,ru,en,color=MUTED,size=10).pack(anchor='w',padx=8,pady=(3,0))
            self.label(metric,variable=var,bold=True,size=21).pack(anchor='w',padx=8,pady=(0,4))
        row=self.row(card)
        self.label(row,'Глубина','Depth',color=MUTED,size=11).pack(side='left')
        self.label(row,variable=self.depth_text).pack(side='right')
        self.label(card,variable=self.detail_text,color=MUTED,wrap=290,size=10).pack(anchor='w',padx=12,pady=(0,4))
        self.label(card,variable=self.latest_event_text,color=MUTED,wrap=285,size=10).pack(anchor='w',padx=12,pady=(0,4))
        actions=self.row(self.overlay)
        self.overlay_start=self.button(actions,'▶ Вкл. AI','▶ Start AI',self.launch,primary=True,width=75)
        self.overlay_start.pack(side='left',fill='x',expand=True,padx=2)
        self.overlay_attach=self.button(actions,'Войти','Join',lambda:self.launch(attach_any_position=True),width=75)
        self.overlay_attach.pack(side='left',fill='x',expand=True,padx=2)
        colors=self.row(self.overlay)
        self.label(colors,'Сторона','Side',size=11,color=MUTED).pack(side='left',padx=(2,6))
        self.overlay_color=self.choice(colors,'','',self.color,[('white','Белые','White'),('black','Чёрные','Black')],lock=True)
        self._locked.extend([self.overlay_start,self.overlay_attach])
        self.overlay_stop=self.button(self.overlay,'■ Остановить · Esc','■ Stop · Esc',self.stop)
        self.overlay_stop.configure(fg_color=STOP_BG,hover_color=STOP_HOVER,border_color=STOP_BORDER,text_color=RED)
        self.overlay_stop.pack(fill='x',padx=10,pady=(3,1))
        self.label(self.overlay,'Только компьютерный бот · LAlt+1 / 2','Computer bot only · LAlt+1 / 2',color=MUTED,size=10).pack(anchor='center')

    def navigate(self,key):
        if key not in self.nav_names:return
        if self.page!=key:
            self._page_scroll[self.page]=self.viewport.canvas.yview()[0]
        self.page=key
        for k,b in self.nav.items():
            b.configure(fg_color=ACTIVE if k==key else 'transparent',border_width=1 if k==key else 0,border_color=ACCENT if k==key else BORDER)
        self.layout()

    def layout(self, force=False):
        if self.compact:return
        width,height=self.root.winfo_width(),self.root.winfo_height()
        scale=getattr(self.root,'_get_window_scaling',lambda:1.)() or 1.
        mode=layout_mode(width/scale,height/scale,self._layout_mode)
        key=(self.page,mode,self.log_collapsed.get())
        previous_page=self._layout_key[0] if self._layout_key else None
        previous_scroll=self.viewport.canvas.yview()[0]
        if not force and self._layout_key==key:return
        self._layout_mode=mode;self._layout_key=key
        wide,short=mode
        self._layout_width=wide
        for panel in (self.session,self.vision,self.analysis_card,self.settings):panel.grid_forget()
        self.log_card.grid_forget();self.analysis.pack_forget()
        self.full.grid_rowconfigure(2,weight=1)
        self.full.grid_rowconfigure(4,weight=0)
        self.body.grid_columnconfigure(0,weight=4,minsize=0)
        self.body.grid_columnconfigure(1,weight=3 if wide and self.page=='home' else 0,minsize=0)
        self.body.grid_rowconfigure(0,weight=0)
        self.body.grid_rowconfigure(1,weight=0)
        self.viewport.grid()
        # Compact navigation rail saves working space at side-by-side widths.
        for key_name,button in self.nav.items():
            ru,en=self.nav_names[key_name]
            short_names={'home':('Сессия','Session'),'vision':('Доска','Board'),
                         'analysis':('Анализ','Analysis'),'log':('Журнал','Log'),'settings':('Опции','Settings')}
            button.configure(text=self.tr(ru,en) if wide else self.tr(*short_names[key_name]),
                             width=126 if wide else 61,height=36 if wide else 45,
                             font=(FONT,13 if wide else 10),compound='left' if wide else 'top',
                             anchor='w' if wide else 'center')
        if wide:
            self.system_card.pack(side='bottom',fill='x',padx=7,pady=8)
            self.model_hint.pack(side='right',padx=(4,3))
        else:
            self.system_card.pack_forget();self.model_hint.pack_forget()
        for i in range(4):self.statusbar.grid_columnconfigure(i,weight=1 if wide or i<2 else 0)
        for i,child in enumerate(self.status_cells):
            child.grid(row=0 if wide else i//2,column=i if wide else i%2,pady=4)
        self.action_dock.grid(row=3,column=1,sticky='ew',padx=(0,10),pady=(2,5))
        self.start.configure(text=self.tr('Запустить','Start') if wide else self.tr('Запуск','Start'))
        self.attach.configure(text=self.tr('Подключиться','Join game') if wide else self.tr('Войти','Join'))
        if self.page=='log':
            self.viewport.grid_remove()
            self.full.grid_rowconfigure(2,weight=0);self.full.grid_rowconfigure(4,weight=1)
            self.log_card.grid(row=4,column=1,sticky='nsew',padx=(0,10),pady=(0,10))
            self.set_log_visibility(True)
        elif self.page=='home':
            if wide:
                self.session.grid(row=0,column=1,rowspan=2,sticky='new',padx=(5,0),pady=4)
                self.vision.grid(row=0,column=0,sticky='new',padx=(0,5),pady=4)
                self.analysis_card.grid(row=1,column=0,sticky='new',padx=(0,5),pady=4)
                self.log_card.grid(row=4,column=1,sticky='ew',padx=(0,10),pady=(0,8))
                self.log.configure(height=56 if short else 84)
                self.set_log_visibility(not self.log_collapsed.get() and not short)
            else:
                self.session.grid(row=0,column=0,columnspan=2,sticky='ew',pady=4)
        else:
            panels={'vision':self.vision,'analysis':self.analysis_card,'settings':self.settings}
            panels[self.page].grid(row=0,column=0,columnspan=2,sticky='ew',pady=4)
            if self.page=='analysis':self.analysis.pack(fill='both',padx=14,pady=(4,10))
        self.schedule_preview_layout()
        self.schedule_form_layout()
        destination=self._page_scroll.get(self.page,0) if previous_page!=self.page else previous_scroll
        self.viewport.restore_scroll(destination)

    def set_log_visibility(self, visible):
        self.log_toggle.configure(state='disabled' if self.page=='log' else 'normal',text='⌄' if visible else '⌃')
        if visible:
            self.log.pack_forget();self.log_filters.pack_forget()
            self.log_tools.pack_forget();self.log_actions.pack_forget();self.log_options.pack_forget()
            self.log_filters.pack(fill='x',padx=12,pady=3)
            if self.page=='log':
                self.log_tools.pack(fill='x',padx=12,pady=(2,0))
                self.log_actions.pack(fill='x',padx=12,pady=(2,0))
                self.log_options.pack(fill='x',padx=12,pady=(0,2))
            else:
                self.log_tools.pack_forget();self.log_actions.pack_forget();self.log_options.pack_forget()
            self.log.pack(fill='both',expand=True,padx=12,pady=(1,7))
        else:
            self.log_filters.pack_forget();self.log_tools.pack_forget();self.log_actions.pack_forget();self.log_options.pack_forget();self.log.pack_forget()

    def toggle_log(self):
        visible=bool(self.log.winfo_manager())
        self.log_collapsed.set(visible)
        self.set_log_visibility(not visible)
        self._layout_key=(self.page,self._layout_mode,self.log_collapsed.get())
        self.save_workspace_settings()

    def on_resize(self,event):
        if event.widget is not self.root or self.compact:return
        size=(event.width,event.height)
        if size==self._last_window_size:return
        self._last_window_size=size
        if self._layout_pending is not None:self.root.after_cancel(self._layout_pending)
        self._layout_pending=self.root.after(180,self.finish_resize)

    def finish_resize(self):
        self._layout_pending=None
        if not self.compact:self.layout()

    def change_language(self):
        for widget,ru,en in self._labels:widget.configure(text=self.tr(ru,en))
        for widget,var,values in self._choices:
            mapping={self.tr(a,b):v for v,a,b in values}
            widget.configure(values=list(mapping))
            widget.set(next((k for k,v in mapping.items() if v==var.get()),str(var.get())))
        self.log_search.configure(placeholder_text=self.tr('Поиск по журналу','Search journal'))
        self.draw_candidates((self._last_event or {}).get('details',{}).get('candidates',[]))
        self.fen_short.set(self.tr('Из телеметрии','Reported FEN') if self._fen else '—')
        if self._fen:self.set_fen(self._fen)
        else:self.draw_board()
        self.refresh_workspace()
        self.layout(force=True)
        self.overlays.language_changed()
        self.save_workspace_settings()

    def change_opacity(self,value):
        alpha=clamp_alpha(value)
        self.alpha_text.set(f'{round(alpha*100)}%')
        if self.compact:self.root.attributes('-alpha',alpha)

    def save_workspace_settings(self):
        self.overlays.save()
        try:
            self._workspace_path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self._workspace_path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'language':self.lang.get(),'opacity':clamp_alpha(self.opacity.get()),'preview':self.preview.get(),'log_collapsed':self.log_collapsed.get(),
                                       'follow_log':self.autoscroll.get(),'topmost':self.topmost.get(),
                                       'geometry':(self._full_geometry or '') if self.compact else self.root.geometry()},indent=2),encoding='utf-8')
            tmp.replace(self._workspace_path)
        except OSError as exc:self.add_view_log('error',str(exc))

    def toggle_preview(self):
        if self.preview.get():self.preview_body.pack(fill='x',padx=12,pady=4,before=self.fen_label)
        else:self.preview_body.pack_forget()
        self.draw_board()

    def copy_fen(self):
        if self._fen:
            self.root.clipboard_clear();self.root.clipboard_append(self._fen)

    def schedule_board(self,event=None):
        if self._board_pending is not None:self.root.after_cancel(self._board_pending)
        self._board_pending=self.root.after(100,self.draw_board)

    def sync_color(self,*_):
        for widget,var,values in self._choices:
            if var is self.color:
                label=next((self.tr(a,b) for v,a,b in values if v==var.get()),var.get())
                if widget.get()!=label:widget.set(label)
        self.schedule_board()

    def draw_board(self):
        if self._board_pending is not None:
            self.root.after_cancel(self._board_pending);self._board_pending=None
        size=min(max(80,self.board.winfo_width()),max(80,self.board.winfo_height()))
        signature=(self._fen,size,self.color.get(),self.lang.get())
        if signature==self._board_signature:return
        self._board_signature=signature
        self.board.delete('all')
        ranks=parse_board(self._fen)
        # Coordinate gutter and a square board; empty state is not a claimed position.
        step=(size-16)/8
        black=self.color.get()=='black'
        if ranks and black:ranks=[list(reversed(row)) for row in reversed(ranks)]
        for y in range(8):
            self.board.create_text(6,(y+.5)*step,text=str(y+1 if black else 8-y),fill=MUTED,font=(FONT,8))
            for x in range(8):
                left=12+x*step
                self.board.create_rectangle(left,y*step,left+step,(y+1)*step,fill=BOARD_LIGHT if (x+y)%2==0 else BOARD_DARK,outline='')
                piece=ranks[y][x] if ranks else '.'
                if piece in GLYPHS:
                    self.board.create_text(left+step/2,(y+.5)*step,text=GLYPHS[piece],fill=TEXT if piece.isupper() else BG,font=('Segoe UI Symbol',max(12,int(step*.76))))
        for x in range(8):
            self.board.create_text(12+(x+.5)*step,8*step+7,text=('hgfedcba' if black else 'abcdefgh')[x],fill=MUTED,font=(FONT,8))
        if not ranks:
            self.board.create_rectangle(15,size/2-15,size-3,size/2+15,fill=PANEL,outline=BORDER)
            self.board.create_text(size/2,size/2,text=self.tr('Нет позиции','No position'),fill=TEXT,font=(FONT,10))

    def build_candidate_rows(self):
        self.candidate_empty=self.ctk.CTkLabel(self.candidates,text='',text_color=MUTED,font=(FONT,11),height=24)
        self.candidate_rows=[]
        for _ in range(4):
            row=self.ctk.CTkFrame(self.candidates,fg_color='transparent',corner_radius=5)
            move=self.ctk.CTkLabel(row,text='',text_color=TEXT,width=70,height=23,anchor='w',font=(MONO,12,'bold'))
            move.pack(side='left',padx=5)
            score=self.ctk.CTkLabel(row,text='',text_color=MUTED,width=52,height=23,font=(MONO,11))
            score.pack(side='left')
            bar=self.ctk.CTkProgressBar(row,width=45,height=6,progress_color=TRACK,fg_color=BORDER)
            bar.pack(side='left',expand=True,fill='x',padx=4)
            percent=self.ctk.CTkLabel(row,text='',text_color=MUTED,width=36,height=23,font=(FONT,10))
            percent.pack(side='right',padx=5)
            self.candidate_rows.append((row,move,score,bar,percent))
        self._candidate_signature=None

    def draw_candidates(self,candidates):
        selected=(self._last_event or {}).get('move')
        entries=[c for c in candidates if isinstance(c,dict)]
        entries.sort(key=lambda c:c.get('move')!=selected)
        entries=entries[:4]
        signature=(self.lang.get(),selected,tuple((c.get('move'),c.get('cp'),c.get('policy')) for c in entries))
        if signature==self._candidate_signature:return
        self._candidate_signature=signature
        if not entries:
            self.candidate_empty.configure(text=self.tr('Ожидание данных анализа','Waiting for analysis'))
            self.candidate_empty.pack(padx=8,pady=5)
        else:self.candidate_empty.pack_forget()
        for i,(row,move,score,bar,percent) in enumerate(self.candidate_rows):
            if i>=len(entries):row.pack_forget();continue
            c=entries[i];cp=c.get('cp');policy=c.get('policy');chosen=c.get('move')==selected
            row.configure(fg_color=ACTIVE if chosen else 'transparent')
            move.configure(text=('◆ ' if chosen else '   ')+str(c.get('move') or '—'))
            score.configure(text=f'{cp:+d}' if isinstance(cp,int) else '—',
                            text_color=GREEN if isinstance(cp,int) and cp>0 else RED if isinstance(cp,int) and cp<0 else MUTED)
            valid=isinstance(policy,(int,float)) and 0<=policy<=1
            bar.set(policy if valid else 0)
            percent.configure(text=f'{policy:.0%}' if valid else '—')
            if not row.winfo_manager():row.pack(fill='x',padx=4,pady=1)

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
        cp=d.get('engine_cp');score=d.get('uci_score') or {}
        self.eval_text.set(f'{cp:+d} cp' if isinstance(cp,int) else f'M{score["value"]}' if score.get('kind')=='mate' else '—')
        self.depth_text.set(str(d.get('search_depth','—')))
        self.detail_text.set(self.tr('Ответ: ','Reply: ')+str(d.get('expected_reply') or '—')+' · '+str(d.get('search_time_s','—'))+' s')
        self.draw_candidates(d.get('candidates') or [])
        self.analysis.configure(state='normal');self.analysis.delete('1.0','end')
        for title,body in report_sections(event,self.lang.get()=='EN'):
            self.analysis.insert('end',title+'\n','heading')
            self.analysis.insert('end',body+'\n\n')
        self.analysis.configure(state='disabled')

    def observe_message(self,t,tag):
        match=re.search(r'(?:[Ff][Ee][Nn][: ]+|Начальная позиция: |Подключено к текущей партии без истории: )([prnbqkPRNBQK1-8/]+ [wb] [KQkq-]+ [a-h1-8-]+ \d+ \d+)',t)
        if match:self.set_fen(match.group(1))
        if tag=='error':self.notice.set(t[:180])

    def add_view_log(self,tag,text):
        line=(tag,f'[{datetime.datetime.now():%H:%M:%S}] {text}\n')
        evicted=self._messages[0] if len(self._messages)==self._messages.maxlen else None
        self._messages.append(line)
        self.latest_event_text.set(short_text(text,75))
        if self.log_paused.get():return
        query=self._applied_query
        remove=bool(evicted and self._visible_entries and evicted is self._visible_entries[0])
        append=matches(line,self._filter,query)
        if not (remove or append):
            self.log_count.set(f'{len(self._visible_entries)} / {len(self._messages)}')
            return
        follow=self.autoscroll.get() and self.log.yview()[1]>=.999
        self.log.configure(state='normal')
        if remove:
            old=self._visible_entries.popleft()[1]
            self.log.delete('1.0',f'{old.count(chr(10))+1}.0')
        if append:
            self._visible_entries.append(line)
            self.log.insert('end',line[1],tag)
        self.log.configure(state='disabled')
        if follow:self.log.see('end')
        self.log_count.set(f'{len(self._visible_entries)} / {len(self._messages)}')

    def schedule_log_search(self,*_):
        if self._log_search_job is not None:self.root.after_cancel(self._log_search_job)
        self._log_search_job=self.root.after(150,self.apply_log_search)

    def apply_log_search(self):
        self._log_search_job=None
        self.filter_log(self._filter)

    def filter_log(self,value):
        same=value==self._filter and self._applied_query==self.log_query.get()
        old_view=self.log.yview()[0]
        self._filter=value
        entries=self._paused_messages if self.log_paused.get() else self._messages
        self._applied_query=self.log_query.get()
        self._visible_entries=deque(select_entries(entries,value,self._applied_query))
        self.log.configure(state='normal');self.log.delete('1.0','end')
        for tag,line in self._visible_entries:self.log.insert('end',line,tag)
        self.log.configure(state='disabled')
        if self.autoscroll.get():self.log.see('end')
        else:self.log.yview_moveto(old_view if same else 0)
        self.log_count.set(f'{len(self._visible_entries)} / {len(entries)}')

    def toggle_log_pause(self):
        if self.log_paused.get():self._paused_messages=tuple(self._messages)
        else:self._paused_messages=()
        self.filter_log(self._filter)

    def follow_log(self):
        if self.autoscroll.get():self.log.see('end')

    def copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log.get('1.0','end-1c'))

    def export_log(self):
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.log',
            filetypes=[('Log','*.log'),('Text','*.txt')])
        if not path:return
        try:Path(path).write_text(self.log.get('1.0','end-1c'),encoding='utf-8')
        except OSError as exc:messagebox.showerror('Vision Bot',str(exc),parent=self.root)

    def clear_view_log(self):
        self._messages.clear();self._paused_messages=();self.filter_log(self._filter)

    def panel_overlaps(self):
        if not self.rect:return False
        x,y,s=(getattr(self.bot,'rect',None) or self.rect)
        r=self.root
        return (r.winfo_ismapped() and rectangles_overlap((r.winfo_rootx(),r.winfo_rooty(),r.winfo_width(),r.winfo_height()),(x,y,s,s))) or self.overlays.overlaps()

    def refresh_workspace(self):
        active=bool(self.worker and self.worker.is_alive())
        if active!=self._active:
            self._active=active
            for w in self._locked+[self.start,self.attach]:w.configure(state='disabled' if active else 'normal')
        self.model_status.set(self.tr('Модель: ','Model: ')+self.checkpoint.get())
        self.side_status.set(self.tr('Сторона: ','Side: ')+(self.tr('Белые','White') if self.color.get()=='white' else self.tr('Чёрные','Black')))
        self.region_status.set(self.tr('Доска: ','Board: ')+(f'{self.rect[2]} × {self.rect[2]}' if self.rect else '—'))
        import time
        now=time.monotonic()
        signature=(self.checkpoint.get(),bool(self.rect),self.lang.get())
        if signature!=self._system_signature or now-getattr(self,'_system_checked',0)>1:
            self._system_signature=signature;self._system_checked=now
            self._engine_exists=self.engine.is_file()
            from .external_session import EXTERNAL,available
            self._model_exists=(self.checkpoint.get() in available()) if self.checkpoint.get() in EXTERNAL else (self.run/'checkpoints'/self.checkpoint.get()).is_file()
            self.engine_status.set(('● ' if self._engine_exists else '○ ')+self.tr('Движок','Engine'))
            self.checkpoint_status.set(('● ' if self._model_exists else '○ ')+self.tr('Модель','Model'))
            self.model_hint_text.set(self.tr('Файл найден','File available') if self._model_exists else self.tr('Файл отсутствует','File missing'))
            self.vision_status.set(('● ' if self.rect else '○ ')+self.tr('Область','Region'))
        if self.rect:
            x,y,s=self.rect;self.board_text.set(f'x={x}  y={y}  {s} × {s} px')
        else:self.board_text.set(self.tr('Область не задана','No region selected'))
        self.summary_text.set(self.checkpoint.get()+' · '+self.tr('Белые','White') if self.color.get()=='white' else self.checkpoint.get()+' · '+self.tr('Чёрные','Black'))
        if active and self.panel_overlaps() and not self.ev.is_set():
            self.ev.set();self.add_view_log('error',self.tr('Окно перекрывает доску. Запрошена остановка.','Window overlaps board. Stop requested.'))
        state=session_state(active,self.ev.is_set(),self.worker is not None,bool(self.rect),
                            self._engine_exists,self._model_exists,self.consent.get())
        names={'active':('Сессия активна','Session active'),'stopping':('Остановка…','Stopping…'),
               'stopped':('Остановлено','Stopped'),'ready':('Готов к работе','Ready'),
               'setup':('Настройка','Setup')}
        self.state_text.set(self.tr(*names[state]))
        state_color=GREEN if state in ('active','ready') else WARNING if state=='stopping' else MUTED
        if getattr(self,'_status_color',None)!=state_color:
            self.status_cells[0].configure(text_color=state_color)
            self._status_color=state_color
        self.overlays.refresh()
        if self._status_cache!=active:
            self._status_cache=active
            for w in (self.stop_button,self.overlay_stop,self.header_stop):w.configure(state='normal' if active else 'disabled')

    def window_scale(self):
        return max(.5,float(getattr(self.root,'_get_window_scaling',lambda:1.)() or 1.))

    def prepare_launch_layout(self):
        """Use physical coordinates for board safety and logical Tk sizes."""
        r=self.root;r.update_idletasks()
        if not self.overlays.prepare_launch():return False
        if not r.winfo_ismapped():return True
        scale=self.window_scale()
        width=round(r.winfo_width()/scale)
        height=round(r.winfo_height()/scale)
        sw,sh=r.winfo_screenwidth(),r.winfo_screenheight()
        if not self.panel_overlaps() and r.winfo_rootx()>=0 and r.winfo_rooty()>=0 and r.winfo_rootx()+r.winfo_width()<=sw and r.winfo_rooty()+r.winfo_height()<=sh:return True
        sizes=(width,) if self.compact else (width,min(width,720),min(width,560),420)
        for candidate in sizes:
            pos=safe_position(self.rect,round(candidate*scale)+16,round(height*scale)+42,sw,sh)
            if pos is not None:
                r.geometry(f'{candidate}x{height}+{pos[0]}+{pos[1]}')
                r.update_idletasks()
                return not self.panel_overlaps()
        return False

    def toggle_overlay(self):
        r=self.root;r.update_idletasks()
        scale=self.window_scale()
        sw,sh=r.winfo_screenwidth(),r.winfo_screenheight()
        rect=getattr(self.bot,'rect',None) or self.rect
        if not self.compact:
            pos=safe_position(rect,round(360*scale)+16,round(350*scale)+42,sw,sh)
            if pos is None:
                messagebox.showwarning('Vision Bot',self.tr('Нет свободного места рядом с доской.','No space beside the board.'));return
            self._full_geometry=r.geometry()
            if self._layout_pending is not None:
                r.after_cancel(self._layout_pending);self._layout_pending=None
            self.compact=True;self.full.pack_forget();self.overlay.pack(fill='both',expand=True)
            r.minsize(340,340);r.geometry(f'360x350+{pos[0]}+{pos[1]}')
            r.attributes('-alpha',clamp_alpha(self.opacity.get()));r.attributes('-topmost',True)
        else:
            geometry=self._full_geometry or '560x650'
            if self.worker and self.worker.is_alive():
                match=re.match(r'(\d+)x(\d+)',geometry)
                width,height=(map(int,match.groups()) if match else (560,650))
                result=None
                for candidate in (width,min(width,720),min(width,560),420):
                    pos=safe_position(rect,round(candidate*scale)+16,round(height*scale)+42,sw,sh)
                    if pos is not None:
                        result=f'{candidate}x{height}+{pos[0]}+{pos[1]}'
                        break
                if result is None:
                    messagebox.showwarning('Vision Bot',self.tr('Для развёрнутой панели нет места. Остановите сессию перед раскрытием.','No space for the full panel. Stop the session before expanding.'))
                    return
                geometry=result
            self.compact=False;self.overlay.pack_forget();self.full.pack(fill='both',expand=True)
            r.attributes('-alpha',1.);r.minsize(420,440)
            r.geometry(geometry)
            self.set_topmost()
            self._layout_key=None
            self._layout_pending=r.after(180,self.finish_resize)
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
