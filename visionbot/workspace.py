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
PANEL='#171922'
FIELD='#20232e'
BORDER='#303341'
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
        self.alpha_text=tk.StringVar(value=f'{round(self.opacity.get()*100)}%')
        r.title('Chess AI · Vision Computer Bot Lab — Vision Studio')
        r.configure(fg_color=BG)
        sw,sh=r.winfo_screenwidth(),r.winfo_screenheight()
        r.geometry(f'{min(1180,max(540,sw-100))}x{min(820,max(550,sh-100))}')
        r.minsize(510,520)
        r.attributes('-topmost',bool(self.topmost.get()))
        self.full=ctk.CTkFrame(r,fg_color=BG,corner_radius=0)
        self.full.pack(fill='both',expand=True)
        self.full.grid_columnconfigure(1,weight=1)
        self.full.grid_rowconfigure(1,weight=1)
        bar=self.card(self.full)
        bar.grid(row=0,column=0,columnspan=2,sticky='ew',padx=10,pady=(10,5))
        self.label(bar,'Chess AI · Vision Bot','Chess AI · Vision Bot',size=17,bold=True).pack(side='left',padx=12,pady=9)
        self.button(bar,'Оверлей','Overlay',self.toggle_overlay,width=76).pack(side='right',padx=5,pady=6)
        self.header_stop=self.button(bar,'■ Стоп','■ Stop',self.stop,width=66)
        self.header_stop.pack(side='right',padx=3,pady=6)
        self.label(bar,variable=self.state_text,color=GREEN,size=11).pack(side='left',padx=4)
        self.side=self.card(self.full)
        self.side.grid(row=1,column=0,sticky='ns',padx=(10,5),pady=(5,10))
        self.nav={}
        for key,ru,en in [('home','Сессия','Session'),('vision','Видение','Vision'),('analysis','Анализ','Analysis'),('log','Журнал','Log'),('settings','Настройки','Settings')]:
            b=self.button(self.side,ru,en,lambda k=key:self.navigate(k),width=118)
            b.pack(fill='x',padx=7,pady=5)
            self.nav[key]=b
        self.label(self.side,'Только компьютерный бот','Computer bot only',color=MUTED,wrap=110).pack(side='bottom',padx=7,pady=10)
        self.body=ctk.CTkScrollableFrame(self.full,fg_color=BG,corner_radius=0,scrollbar_button_color=BORDER)
        self.body.grid(row=1,column=1,sticky='nsew',padx=(0,10),pady=(5,10))
        self.body.grid_columnconfigure(0,weight=3)
        self.body.grid_columnconfigure(1,weight=2)
        self.session=self.card(self.body)
        self.vision=self.card(self.body)
        self.analysis_card=self.card(self.body)
        self.log_card=self.card(self.body)
        self.settings=self.card(self.body)
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
             corner_radius=7,fg_color=ACCENT if primary else FIELD,hover_color=HOVER if primary else BORDER,
             border_width=0 if primary else 1,border_color=BORDER,text_color=TEXT,
             font=('Segoe UI',12,'bold' if primary else 'normal'))
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
        self.label(parent,f'{n}   {ru}',f'{n}   {en}',size=13,bold=True).pack(anchor='w',padx=14,pady=(10,3))

    def choice(self,parent,ru,en,var,values,*,change=None,lock=False):
        self.label(parent,ru,en,color=MUTED).pack(anchor='w',padx=14,pady=(5,0))
        def options(): return {self.tr(a,b):v for v,a,b in values}
        def picked(display):
            mapping=options()
            if display not in mapping:return
            var.set(mapping[display])
            if change:change()
        opts=options()
        widget=self.ctk.CTkOptionMenu(parent,values=list(opts),command=picked,height=33,
                 fg_color=FIELD,button_color=BORDER,button_hover_color=ACCENT,
                 dropdown_fg_color=PANEL,dropdown_hover_color=ACCENT,text_color=TEXT)
        widget.pack(fill='x',padx=14,pady=(0,4))
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
        self.title(c,'Новая сессия','New session','Подготовка, подключение и управление','Setup, connection and controls')
        self.section(c,1,'Выбор модели','Choose model')
        self.agent_picker=self.choice(c,'Агент','Agent',self.checkpoint,[(n,n,n) for n in ALIASES],change=self.on_agent_change)
        self.section(c,2,'Область доски','Board region')
        b=self.button(c,'Выделить / изменить область','Select / change region',self.calibrate)
        b.pack(fill='x',padx=14,pady=4);self._locked.append(b)
        self.info=self.label(c,variable=self.board_text,color=MUTED,wrap=300)
        self.info.pack(anchor='w',padx=14)
        self.label(c,variable=self.notice,color=RED,wrap=290).pack(anchor='w',padx=14,pady=2)
        self.section(c,3,'Настройки партии','Game settings')
        self.choice(c,'Сторона','Side',self.color,[('white','Белые','White'),('black','Чёрные','Black')],lock=True)
        self.choice(c,'Очередь хода при импорте','Turn on import',self.turn,[('auto','Авто','Auto'),('white','Белые','White'),('black','Чёрные','Black')],lock=True)
        self.choice(c,'Анализ','Analysis',self.analysis_mode,[('Стандартный · 5 полуходов','Стандартный · 5 полуходов','Standard · 5 plies'),('Глубокий · до 7 полуходов','Глубокий · до 7 полуходов','Deep · up to 7 plies')],lock=True)
        self.switch(c,'Фантом-X23 за белых','Phantom-X23 as White',self.phantom,lock=True)
        self.switch(c,'Восстановить партию','Recover previous game',self.resume,lock=True)
        self.switch(c,'Локальный self-play (+500)','Local self-play (+500)',self.train,lock=True)
        self.switch(c,'Поверх других окон','Always on top',self.topmost,self.set_topmost)
        self.section(c,4,'Запуск','Launch')
        consent=self.ctk.CTkCheckBox(c,text=self.tr('Только компьютерный соперник','Computer opponent only'),variable=self.consent,
                                    fg_color=ACCENT,hover_color=HOVER,text_color=TEXT)
        consent.pack(anchor='w',padx=14,pady=7)
        self._labels.append((consent,'Только компьютерный соперник','Computer opponent only'))
        self._locked.append(consent)
        self.start=self.button(c,'▶ Запустить автопилот','▶ Start autopilot',self.launch,primary=True)
        self.start.pack(fill='x',padx=14,pady=4)
        self.attach=self.button(c,'Подключиться к текущей партии','Join current game',lambda:self.launch(attach_any_position=True))
        self.attach.pack(fill='x',padx=14,pady=4)
        self.stop_button=self.button(c,'■ Остановить · Esc','■ Stop · Esc',self.stop)
        self.stop_button.pack(fill='x',padx=14,pady=(4,12))

    def build_vision(self):
        c=self.vision
        self.title(c,'Предпросмотр доски','Board preview','Последняя позиция из телеметрии, не видеопоток','Last reported FEN, not a video feed')
        self.switch(c,'Показывать доску','Show board',self.preview,self.toggle_preview)
        self.board=tk.Canvas(c,width=232,height=232,bg=PANEL,highlightthickness=0)
        self.board.pack(padx=12,pady=8)
        self.board.bind('<Configure>',lambda _:self.draw_board())
        self.fen_label=self.label(c,variable=self.fen_text,color=MUTED,wrap=265)
        self.fen_label.pack(anchor='w',padx=14,pady=4)
        self.button(c,'Копировать FEN','Copy FEN',self.copy_fen).pack(fill='x',padx=14,pady=(2,12))
        self.toggle_preview()

    def build_analysis(self):
        c=self.analysis_card
        self.title(c,'Анализ позиции','Position analysis','Только измеренные данные','Actual reported values only')
        for ru,en,v in [('Ход','Move',self.move_text),('Оценка (cp, сторона хода)','Evaluation (cp, side to move)',self.eval_text),('Глубина (полуходы)','Depth (plies)',self.depth_text)]:
            row=self.row(c);self.label(row,ru,en,color=MUTED).pack(side='left');self.label(row,variable=v,size=16,bold=True).pack(side='right')
        self.label(c,variable=self.detail_text,color=MUTED,wrap=290).pack(anchor='w',padx=14,pady=5)
        self.candidates=self.ctk.CTkFrame(c,fg_color=FIELD,corner_radius=6)
        self.candidates.pack(fill='x',padx=14,pady=4)
        self.analysis=self.ctk.CTkTextbox(c,height=150,fg_color=FIELD,text_color=TEXT,font=('Consolas',11),wrap='word',state='disabled')
        self.analysis.pack(fill='both',padx=14,pady=(5,12))
        self.draw_candidates([])

    def build_log(self):
        c=self.log_card
        self.title(c,'Журнал сессии','Session log')
        row=self.row(c)
        values=[('all','Все','All'),('info','Система','System'),('analysis','Анализ','Analysis'),('move','Ходы','Moves'),('error','Ошибки','Errors')]
        def select(value):
            mapping={self.tr(a,b):v for v,a,b in values}
            self.filter_var.set(mapping[value])
            self.filter_log(mapping[value])
        self.filter_choice=self.ctk.CTkOptionMenu(row,values=[self.tr(a,b) for _,a,b in values],command=select,fg_color=FIELD,button_color=BORDER,button_hover_color=ACCENT,width=100)
        self.filter_choice.pack(side='left');self.filter_choice.set(self.tr('Все','All'))
        self._choices.append((self.filter_choice,self.filter_var,values))
        self.button(row,'Очистить вид','Clear view',self.clear_log,width=90).pack(side='right')
        self.switch(c,'Автопрокрутка','Auto-scroll',self.autoscroll)
        self.log=self.ctk.CTkTextbox(c,height=190,fg_color=FIELD,text_color=TEXT,font=('Consolas',11),wrap='word',state='disabled')
        self.log.pack(fill='both',padx=12,pady=(3,12))
        for tag,color in [('error',RED),('move',GREEN),('analysis','#b7a5ff'),('info',TEXT)]:
            self.log.tag_config(tag,foreground=color)

    def build_settings(self):
        c=self.settings
        self.title(c,'Настройки интерфейса','Interface settings')
        self.choice(c,'Язык интерфейса','Interface language',self.lang,[('RU','Русский','Russian'),('EN','English','English')],change=self.change_language)
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
        grip=self.label(header,'⋮⋮  Vision Bot','⋮⋮  Vision Bot',bold=True,size=15)
        grip.pack(side='left')
        grip.bind('<ButtonPress-1>',self.drag_start)
        grip.bind('<B1-Motion>',self.drag_move)
        self.button(header,'Развернуть','Expand',self.toggle_overlay,width=80).pack(side='right')
        self.label(self.overlay,variable=self.state_text,color=GREEN,size=13,bold=True).pack(anchor='w',padx=14)
        self.label(self.overlay,'Только компьютерный бот','Computer bot only',color=MUTED).pack(anchor='w',padx=14)
        row=self.row(self.overlay)
        self.label(row,variable=self.move_text,bold=True,size=23).pack(side='left')
        self.label(row,variable=self.eval_text,bold=True,size=19).pack(side='right')
        row=self.row(self.overlay)
        self.label(row,'Глубина','Depth',color=MUTED).pack(side='left')
        self.label(row,variable=self.depth_text).pack(side='right')
        self.label(self.overlay,variable=self.summary_text,color=MUTED,wrap=300).pack(anchor='w',padx=14)
        self.label(self.overlay,variable=self.detail_text,color=MUTED,wrap=300,size=11).pack(anchor='w',padx=14)
        self.overlay_stop=self.button(self.overlay,'■ Остановить · Esc','■ Stop · Esc',self.stop)
        self.overlay_stop.pack(fill='x',padx=12,pady=6)

    def navigate(self,key):
        self.page=key
        for k,b in self.nav.items():b.configure(fg_color=ACCENT if k==key else FIELD)
        self.layout()

    def layout(self):
        for w in (self.session,self.vision,self.analysis_card,self.log_card,self.settings):w.grid_forget()
        wide=self.root.winfo_width()>=1000
        self._layout_width=wide
        self.body.grid_columnconfigure(1,weight=2 if wide and self.page=='home' else 0)
        panels={'vision':self.vision,'analysis':self.analysis_card,'log':self.log_card,'settings':self.settings}
        if self.page in panels:
            panels[self.page].grid(row=0,column=0,columnspan=2,sticky='ew',padx=5,pady=5)
        elif wide:
            self.session.grid(row=0,column=0,rowspan=2,sticky='nsew',padx=5,pady=5)
            self.vision.grid(row=0,column=1,sticky='nsew',padx=5,pady=5)
            self.analysis_card.grid(row=1,column=1,sticky='nsew',padx=5,pady=5)
            self.log_card.grid(row=2,column=0,columnspan=2,sticky='ew',padx=5,pady=5)
        else:
            for i,w in enumerate((self.session,self.vision,self.analysis_card,self.log_card)):
                w.grid(row=i,column=0,columnspan=2,sticky='ew',padx=5,pady=5)

    def on_resize(self,event):
        if event.widget is self.root and not self.compact and (event.width>=1000)!=self._layout_width:self.layout()

    def change_language(self):
        for widget,ru,en in self._labels:widget.configure(text=self.tr(ru,en))
        for widget,var,values in self._choices:
            mapping={self.tr(a,b):v for v,a,b in values}
            widget.configure(values=list(mapping))
            widget.set(next((k for k,v in mapping.items() if v==var.get()),str(var.get())))
        self.draw_candidates((self._last_event or {}).get('details',{}).get('candidates',[]))
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
        if self.preview.get():self.board.pack(padx=12,pady=8,before=self.fen_label)
        else:self.board.pack_forget()
        self.draw_board()

    def copy_fen(self):
        if self._fen:
            self.root.clipboard_clear();self.root.clipboard_append(self._fen)

    def draw_board(self):
        self.board.delete('all')
        ranks=parse_board(self._fen)
        size=min(max(80,self.board.winfo_width()),max(80,self.board.winfo_height()))
        if not ranks:
            self.board.create_text(size/2,size/2,text=self.tr('Нет позиции','No position'),fill=MUTED,font=('Segoe UI',12))
            return
        if self.color.get()=='black':ranks=[list(reversed(row)) for row in reversed(ranks)]
        step=size/8
        for y,row in enumerate(ranks):
            for x,piece in enumerate(row):
                self.board.create_rectangle(x*step,y*step,(x+1)*step,(y+1)*step,fill='#aaaabd' if (x+y)%2==0 else '#62657d',outline='')
                if piece in GLYPHS:
                    self.board.create_text((x+.5)*step,(y+.5)*step,text=GLYPHS[piece],fill='#ffffff' if piece.isupper() else '#121318',font=('Segoe UI Symbol',max(12,int(step*.69))))

    def draw_candidates(self,candidates):
        for w in self.candidates.winfo_children():w.destroy()
        self.label(self.candidates,self.tr('Варианты · cp / policy','Candidates · cp / policy'),self.tr('Варианты · cp / policy','Candidates · cp / policy'),color=MUTED).pack(anchor='w',padx=8)
        # Transient labels aren't part of the translation registry.
        self._labels.pop()
        if not candidates:
            self.ctk.CTkLabel(self.candidates,text=self.tr('Нет данных','No data'),text_color=MUTED).pack(padx=8,pady=4)
        for i,c in enumerate(candidates[:5]):
            if not isinstance(c,dict):continue
            cp=c.get('cp'); policy=c.get('policy')
            value=(f'{cp:+d} cp' if isinstance(cp,int) else '—')+'    '+(f'{policy:.3f}' if isinstance(policy,(float,int)) else '—')
            row=self.ctk.CTkFrame(self.candidates,fg_color='#30264c' if i==0 else 'transparent')
            row.pack(fill='x',padx=5,pady=2)
            self.ctk.CTkLabel(row,text=str(c.get('move','—')),text_color=TEXT,font=('Consolas',12,'bold')).pack(side='left',padx=8)
            self.ctk.CTkLabel(row,text=value,text_color=TEXT,font=('Consolas',11)).pack(side='right',padx=8)

    def set_fen(self,fen):
        if parse_board(fen):
            self._fen=fen;self.fen_text.set('FEN: '+fen);self.draw_board()

    def reset_analysis(self):
        self._last_event=None;self._fen='';self.fen_text.set('—');self.notice.set('')
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
        if self.rect:
            x,y,s=self.rect;self.board_text.set(f'x={x}  y={y}  {s} × {s} px')
        else:self.board_text.set(self.tr('Область не задана','No region selected'))
        self.summary_text.set(self.checkpoint.get()+' · '+self.tr('Белые','White') if self.color.get()=='white' else self.checkpoint.get()+' · '+self.tr('Чёрные','Black'))
        if active and self.panel_overlaps() and not self.ev.is_set():
            self.ev.set();self.add_view_log('error',self.tr('Окно перекрывает доску. Запрошена остановка.','Window overlaps board. Stop requested.'))
        if active:self.state_text.set(self.tr('Остановка…','Stopping…') if self.ev.is_set() else self.tr('Сессия активна','Session active'))
        else:self.state_text.set(self.tr('Остановлено','Stopped') if self.worker else self.tr('Ожидание','Idle'))
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
            pos=safe_position(getattr(self.bot,'rect',None) or self.rect,360,294,r.winfo_screenwidth(),r.winfo_screenheight())
            if pos is None:
                messagebox.showwarning('Vision Bot',self.tr('Нет свободного места рядом с доской.','No space beside the board.'));return
            self._full_geometry=r.geometry()
            self.compact=True;self.full.pack_forget();self.overlay.pack(fill='both',expand=True)
            r.minsize(320,250);r.geometry(f'344x278+{pos[0]}+{pos[1]}')
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
