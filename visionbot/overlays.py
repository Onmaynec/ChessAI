"""Independent, resizable presentation windows sharing one Vision session."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox
from .analysis_view import arrows, geometry_parts, line_moves, report_sections, square_xy
from .telemetry import rectangles_overlap

BG='#101116'
PANEL='#171820'
FIELD='#20212b'
TEXT='#f2f2f7'
MUTED='#a5a9bb'
ACCENT='#7154e8'
GREEN='#52d79a'
RED='#ff8585'
BORDER='#303341'
NAMES={
    'control':('Управление','Control',(360,370)),
    'log':('Журнал сессии','Session log',(470,310)),
    'analysis':('Анализ партии','Game analysis',(420,350)),
    'board':('Доска и варианты','Board and lines',(350,425)),
    'console':('Консоль расчётов','Model console',(460,430)),
}
GLYPHS=dict(zip('KQRBNPkqrbnp','♔♕♖♗♘♙♚♛♜♝♞♟'))

class OverlayManager:
    def __init__(self, app):
        self.app=app;self.root=app.root;self.ctk=app.ctk
        self.path=app.path.with_name('vision_overlays.json')
        self.windows={};self.preferences={}
        self._hidden=[];self._closing=False;self._capturing=False
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data,dict):
                self.preferences={k:v for k,v in data.items() if k in NAMES and isinstance(v,dict)}
        except (OSError,ValueError):pass

    def tr(self,ru,en):return self.app.tr(ru,en)

    def name(self,key):return self.tr(*NAMES[key][:2])

    def open(self,key):
        if self._closing or self._capturing:return
        if key in self.windows:
            w=self.windows[key]
            w.win.deiconify();w.win.lift();return
        w=OverlayWindow(self,key)
        self.windows[key]=w
        if self.app.worker and self.app.worker.is_alive() and not self.place(w):
            self.close(key)
            messagebox.showwarning('Vision Bot',self.tr('Нет свободного места вне доски.','No space outside the captured board.'))
            return
        w.refresh()

    def toggle(self,key):
        if key in self.windows:self.close(key)
        else:self.open(key)

    def close(self,key):
        w=self.windows.pop(key,None)
        if w:
            self.preferences[key]=w.snapshot()
            w.dispose()
            self.save()

    def close_all(self):
        for key in list(self.windows):self.close(key)

    def shutdown(self):
        self._closing=True
        self.save()
        for w in list(self.windows.values()):w.dispose()
        self.windows.clear()

    def save(self):
        for key,w in self.windows.items():self.preferences[key]=w.snapshot()
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.preferences,indent=2),encoding='utf-8')
            temp.replace(self.path)
        except OSError as exc:self.app.logline('ВНИМАНИЕ: overlay settings: '+str(exc))

    def reset(self):
        if self.app.worker and self.app.worker.is_alive():
            messagebox.showwarning('Vision Bot',self.tr('Сначала остановите сессию.','Stop the session first.'));return
        self.close_all();self.preferences={};self.save()

    def apply_preset(self,preset):
        self.close_all()
        for key in {'minimal':('control',),'review':('board','analysis','console'),
                    'full':tuple(NAMES)}.get(preset,()):
            self.open(key)
        self.arrange()

    def arrange(self):
        # Try a non-overlapping tile layout; when space is exhausted keep windows movable.
        used=[]
        rect=self.rect()
        if rect:used.append((*rect[:2],rect[2],rect[2]))
        if self.root.winfo_ismapped():
            used.append((self.root.winfo_rootx(),self.root.winfo_rooty(),self.root.winfo_width(),self.root.winfo_height()))
        for overlay in self.windows.values():
            win=overlay.win;win.update_idletasks()
            width,height=win.winfo_width()+16,win.winfo_height()+42
            sw,sh=win.winfo_screenwidth(),win.winfo_screenheight()
            positions=[(x,y) for y in range(8,max(9,sh-height+1),32) for x in range(8,max(9,sw-width+1),32)]
            positions.extend((max(0,sw-width),y) for y in range(8,max(9,sh-height+1),32))
            found=next(((x,y) for x,y in positions if x+width<=sw and y+height<=sh and not any(rectangles_overlap((x,y,width,height),r) for r in used)),None)
            if found:
                win.geometry(f'+{found[0]}+{found[1]}');used.append((*found,width,height))
            else:
                used.append(overlay.bounds())
        self.save()

    def rect(self):
        return getattr(self.app.bot,'rect',None) or self.app.rect

    def overlaps(self):
        rect=self.rect()
        if not rect:return False
        x,y,s=rect
        for w in self.windows.values():
            if w.win.winfo_ismapped() and rectangles_overlap(w.bounds(),(x,y,s,s)):return True
        return False

    def place(self,w):
        rect=self.rect()
        if not rect:return True
        from .workspace import safe_position
        w.win.update_idletasks()
        x,y,s=rect
        if not rectangles_overlap(w.bounds(),(x,y,s,s)):return True
        scale=w.scale()
        width,height=w.win.winfo_width(),w.win.winfo_height()
        pos=safe_position(rect,width+16,height+42,w.win.winfo_screenwidth(),w.win.winfo_screenheight())
        if pos is None:return False
        w.win.geometry(f'{round(width/scale)}x{round(height/scale)}+{pos[0]}+{pos[1]}')
        w.win.update_idletasks()
        return not rectangles_overlap(w.bounds(),(x,y,s,s))

    def prepare_launch(self):
        return all(self.place(w) for w in self.windows.values() if w.win.winfo_ismapped())

    def hide_for_capture(self):
        self._capturing=True
        self._hidden=[k for k,w in self.windows.items() if w.win.winfo_ismapped()]
        for key in self._hidden:self.windows[key].win.withdraw()

    def restore_after_capture(self):
        for key in self._hidden:
            if key in self.windows:self.windows[key].win.deiconify()
        self._hidden=[];self._capturing=False

    def refresh(self):
        for w in tuple(self.windows.values()):
            if w.win.winfo_ismapped():w.refresh()

    def language_changed(self):
        # Preserve controls and geometry; rebuilding only on explicit language change.
        keys=list(self.windows)
        for key in keys:self.close(key)
        for key in keys:self.open(key)

class OverlayWindow:
    def __init__(self, manager,key):
        self.manager=manager;self.app=manager.app;self.ctk=manager.ctk;self.key=key
        self.win=self.ctk.CTkToplevel(manager.root)
        self.win.withdraw()
        self.win.title('Chess AI · Vision Computer Bot Lab — '+manager.name(key))
        self.win.configure(fg_color=BG)
        self.win.protocol('WM_DELETE_WINDOW',lambda:manager.close(key))
        self.win.bind('<Escape>',lambda _:self.app.stop())
        cfg=manager.preferences.get(key,{})
        self.alpha=tk.DoubleVar(master=self.win,value=self.alpha_value(cfg.get('opacity',self.app.opacity.get())))
        self.top=tk.BooleanVar(master=self.win,value=bool(cfg.get('topmost',True)))
        self.signature=object();self._resize_job=None;self._board_signature=None
        self.line_index=0;self._event_id=None
        self.board_mode=tk.StringVar(master=self.win,value='analysis')
        self.layer=tk.StringVar(master=self.win,value='all')
        self.log_filter=tk.StringVar(master=self.win,value='all')
        self.win.minsize(310 if key=='control' else 280,320 if key=='control' else 280 if key=='board' else 210)
        default_w,default_h=NAMES[key][2]
        scale=self.scale()
        sw,sh=self.win.winfo_screenwidth(),self.win.winfo_screenheight()
        old=geometry_parts(cfg.get('geometry'))
        if old:
            width,height,x,y=old
            width=max(280,min(width,int(sw/scale)-20))
            height=max(240,min(height,int(sh/scale)-55))
            x=max(0,min(x,sw-round(width*scale)-16));y=max(0,min(y,sh-round(height*scale)-42))
        else:
            width,height=default_w,default_h
            width=min(width,max(280,int(sw/scale)-20));height=min(height,max(240,int(sh/scale)-55))
            offset=list(NAMES).index(key)*28
            x=max(0,sw-round(width*scale)-35-offset);y=min(65+offset,max(0,sh-round(height*scale)-45))
        self.win.geometry(f'{width}x{height}+{x}+{y}')
        self.win.attributes('-alpha',self.alpha.get());self.win.attributes('-topmost',self.top.get())
        header=self.ctk.CTkFrame(self.win,fg_color=PANEL,corner_radius=9,border_width=1,border_color=BORDER)
        header.pack(fill='x',padx=8,pady=(8,4))
        grip=self.label(header,manager.name(key),size=15,bold=True)
        grip.pack(side='left',padx=9,pady=5)
        grip.bind('<ButtonPress-1>',self.drag_start)
        grip.bind('<B1-Motion>',self.drag_move)
        self.button(header,'×',lambda:manager.close(key),width=30).pack(side='right',padx=5)
        prefs=self.ctk.CTkFrame(self.win,fg_color='transparent')
        prefs.pack(fill='x',padx=10,pady=(0,4))
        self.label(prefs,self.tr('Прозрачность','Opacity'),size=10,color=MUTED).pack(side='left',padx=(0,4))
        self.ctk.CTkSlider(prefs,from_=.55,to=1,variable=self.alpha,command=self.change_alpha,width=90,height=13,
                           progress_color=ACCENT,button_color=ACCENT).pack(side='left',fill='x',expand=True)
        self.ctk.CTkSwitch(prefs,text=self.tr('Поверх','On top'),variable=self.top,command=self.change_top,
                           font=('Segoe UI',10),switch_width=30,switch_height=16,width=68,progress_color=ACCENT).pack(side='right',padx=5)
        self.body=self.ctk.CTkFrame(self.win,fg_color=PANEL,corner_radius=9,border_width=1,border_color=BORDER)
        self.body.pack(fill='both',expand=True,padx=8,pady=(0,8))
        getattr(self,'build_'+key)()
        self.win.deiconify()
        self.win.bind('<Configure>',self.resize,add='+')

    def tr(self,ru,en):return self.manager.tr(ru,en)

    @staticmethod
    def alpha_value(value):
        try:return min(1.,max(.55,float(value)))
        except (ValueError,TypeError):return .85

    def scale(self):return max(.5,float(getattr(self.win,'_get_window_scaling',lambda:1.)() or 1.))

    def bounds(self):
        return (self.win.winfo_rootx(),self.win.winfo_rooty(),self.win.winfo_width(),self.win.winfo_height())

    def snapshot(self):
        return {'geometry':self.win.geometry(),'opacity':self.alpha_value(self.alpha.get()),'topmost':self.top.get()}

    def change_alpha(self,value):self.win.attributes('-alpha',self.alpha_value(value))

    def change_top(self):self.win.attributes('-topmost',self.top.get())

    def dispose(self):
        if self._resize_job is not None:
            self.win.after_cancel(self._resize_job);self._resize_job=None
        self.win.destroy()

    def drag_start(self,event):
        self._drag=(event.x_root-self.win.winfo_x(),event.y_root-self.win.winfo_y())

    def drag_move(self,event):
        if not hasattr(self,'_drag'):return
        w=self.win
        x=max(0,min(event.x_root-self._drag[0],w.winfo_screenwidth()-w.winfo_width()-16))
        y=max(0,min(event.y_root-self._drag[1],w.winfo_screenheight()-w.winfo_height()-42))
        rect=self.manager.rect()
        if self.app.worker and self.app.worker.is_alive() and rect:
            if rectangles_overlap((x,y,w.winfo_width()+16,w.winfo_height()+42),(*rect[:2],rect[2],rect[2])):return
        w.geometry(f'+{x}+{y}')

    def resize(self,event):
        if event.widget is not self.win or self.key!='board':return
        self.schedule_board()

    def schedule_board(self,event=None):
        if self._resize_job is not None:self.win.after_cancel(self._resize_job)
        self._resize_job=self.win.after(100,self.draw_board)

    def label(self,parent,text='',size=12,bold=False,color=TEXT,variable=None):
        kw={'font':('Segoe UI',size,'bold' if bold else 'normal'),'text_color':color,'anchor':'w'}
        if variable is None:kw['text']=text
        else:kw['textvariable']=variable
        return self.ctk.CTkLabel(parent,**kw)

    def button(self,parent,text,command,width=90,primary=False):
        return self.ctk.CTkButton(parent,text=text,command=command,width=width,height=30,corner_radius=7,
            fg_color=ACCENT if primary else FIELD,hover_color='#866cf4' if primary else '#353447',text_color=TEXT)

    def row(self,parent=None):
        row=self.ctk.CTkFrame(parent or self.body,fg_color='transparent')
        row.pack(fill='x',padx=8,pady=3);return row

    def menu(self,parent,values,command,default):
        w=self.ctk.CTkOptionMenu(parent,values=values,command=command,fg_color=FIELD,button_color=BORDER,
                                button_hover_color=ACCENT,dropdown_fg_color=PANEL,dropdown_hover_color=ACCENT,
                                dynamic_resizing=False,height=28,width=100)
        w.set(default);w.pack(side='left',fill='x',expand=True,padx=2);return w

    def text(self):
        t=self.ctk.CTkTextbox(self.body,fg_color='#13141b',text_color=TEXT,font=('Segoe UI',12),
                              wrap='word',state='disabled',corner_radius=6)
        t.pack(fill='both',expand=True,padx=8,pady=7)
        for tag,color,font in [('heading','#b7a5ff',('Segoe UI',13,'bold')),('info',TEXT,('Segoe UI',12)),
                               ('analysis','#c4b8ff',('Segoe UI',12)),('move',GREEN,('Segoe UI',12)),('error',RED,('Segoe UI',12))]:
            t.tag_config(tag,foreground=color)
            # CTkTextbox disallows custom tag font scaling on some releases.
        return t

    def set_text(self,parts):
        self.output.configure(state='normal');self.output.delete('1.0','end')
        for tag,content in parts:self.output.insert('end',str(content),tag)
        self.output.configure(state='disabled')

    def build_control(self):
        self.label(self.body,variable=self.app.state_text,size=14,bold=True,color=GREEN).pack(anchor='w',padx=10)
        self.label(self.body,variable=self.app.model_status,color=MUTED).pack(anchor='w',padx=10)
        r=self.row()
        for title,var in [(self.tr('Ход','Move'),self.app.move_text),(self.tr('Оценка','Score'),self.app.eval_text),(self.tr('Глубина','Depth'),self.app.depth_text)]:
            c=self.ctk.CTkFrame(r,fg_color=FIELD,corner_radius=7);c.pack(side='left',fill='x',expand=True,padx=2)
            self.label(c,title,size=10,color=MUTED).pack(anchor='w',padx=5)
            self.label(c,variable=var,size=17,bold=True).pack(anchor='w',padx=5)
        r=self.row()
        colors={self.tr('Белые','White'):'white',self.tr('Чёрные','Black'):'black'}
        self.color_menu=self.menu(r,list(colors),lambda v:self.app.color.set(colors[v]),
                                  next(k for k,v in colors.items() if v==self.app.color.get()))
        self.color_names=colors
        r=self.row()
        self.start=self.button(r,self.tr('▶ Вкл. AI','▶ Start AI'),self.app.launch,primary=True)
        self.start.pack(side='left',fill='x',expand=True,padx=2)
        self.join=self.button(r,self.tr('Присоед.','Join'),lambda:self.app.launch(attach_any_position=True))
        self.join.pack(side='left',fill='x',expand=True,padx=2)
        self.stop=self.button(self.body,self.tr('■ Стоп · Esc','■ Stop · Esc'),self.app.stop)
        self.stop.pack(fill='x',padx=8,pady=4)
        self.label(self.body,self.tr('Только компьютерный бот','Computer bot only'),size=10,color=MUTED).pack(padx=8)
        self.button(self.body,self.tr('Основная панель','Main panel'),self.show_main).pack(fill='x',padx=8,pady=4)

    def show_main(self):self.app.root.deiconify();self.app.root.lift()

    def build_log(self):
        row=self.row()
        names={self.tr('Все','All'):'all',self.tr('Система','System'):'info',
               self.tr('Анализ','Analysis'):'analysis',self.tr('Ходы','Moves'):'move',self.tr('Ошибки','Errors'):'error'}
        def select(v):self.log_filter.set(names[v]);self.signature=None;self.refresh()
        self.menu(row,list(names),select,next(iter(names)))
        self.follow=tk.BooleanVar(master=self.win,value=True)
        self.ctk.CTkSwitch(row,text=self.tr('Следить','Follow'),variable=self.follow,progress_color=ACCENT,
                           font=('Segoe UI',11),width=80).pack(side='right')
        self.output=self.text()

    def build_analysis(self):
        r=self.row()
        self.label(r,variable=self.app.move_text,size=21,bold=True).pack(side='left',padx=4)
        self.label(r,variable=self.app.eval_text,size=18,bold=True,color='#b7a5ff').pack(side='right',padx=4)
        self.output=self.text()

    def build_console(self):self.output=self.text()

    def build_board(self):
        r=self.row()
        modes={self.tr('Расчёт','Analysis'):'analysis',self.tr('Текущая доска','Current board'):'current'}
        layers={self.tr('Варианты','Candidates'):'all',self.tr('Только ход','Chosen only'):'one'}
        self.menu(r,list(modes),lambda v:self.set_board_mode(modes[v]),next(iter(modes)))
        self.menu(r,list(layers),lambda v:self.set_layer(layers[v]),next(iter(layers)))
        self.caption=tk.StringVar(master=self.win,value='—')
        self.label(self.body,variable=self.caption,size=11,color=MUTED).pack(anchor='w',padx=8)
        self.canvas=tk.Canvas(self.body,bg=PANEL,highlightthickness=0,width=220,height=220)
        self.canvas.pack(fill='both',expand=True,padx=7,pady=3)
        self.canvas.bind('<Configure>',self.schedule_board,add='+')
        r=self.row()
        self.prev=self.button(r,'‹',lambda:self.step(-1),width=35);self.prev.pack(side='left')
        self.next=self.button(r,'›',lambda:self.step(1),width=35);self.next.pack(side='right')
        self.step_text=tk.StringVar(master=self.win,value='—')
        self.label(r,variable=self.step_text,size=11).pack(side='left',expand=True)
        self.label(self.body,self.tr('Выбор · варианты · линия · ловушка*','Chosen · alternatives · line · trap*'),size=10,color=MUTED).pack(pady=(0,4))

    def set_board_mode(self,value):
        self.board_mode.set(value);self.line_index=0;self.draw_board()

    def set_layer(self,value):
        self.layer.set(value);self.draw_board()

    def step(self,delta):
        if self.board_mode.get()!='analysis':return
        line=line_moves(self.app._last_event)
        self.line_index=max(0,min(len(line),self.line_index+delta));self.draw_board()

    def draw_board(self):
        if self._resize_job is not None:
            self.win.after_cancel(self._resize_job);self._resize_job=None
        from .workspace import parse_board
        from .recognizer import board_after
        event=self.app._last_event or {}
        current=self.board_mode.get()=='current'
        fen=self.app._fen if current else event.get('fen','')
        moves=[] if current else line_moves(event)
        index=min(self.line_index,len(moves))
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        black=self.app.color.get()=='black'
        sig=(fen,tuple(moves),tuple(arrows(event,self.layer.get()=='all')),index,current,width,height,black)
        if sig==self._board_signature:return
        self._board_signature=sig
        ranks=parse_board(fen)
        if ranks:
            try:
                for move in moves[:index]:ranks=board_after(ranks,move)
            except (ValueError,IndexError):ranks=None
        self.canvas.delete('all')
        s=max(8,min(width,height)-24)/8
        ox=(width-8*s)/2;oy=(height-8*s)/2
        for y in range(8):
            for x in range(8):
                self.canvas.create_rectangle(ox+x*s,oy+y*s,ox+(x+1)*s,oy+(y+1)*s,outline='',
                                             fill='#b3b2c5' if (x+y)%2==0 else '#696b83')
                p=ranks[7-y if black else y][7-x if black else x] if ranks else '.'
                if p in GLYPHS:
                    self.canvas.create_text(ox+(x+.5)*s,oy+(y+.5)*s,text=GLYPHS[p],fill='white' if p.isupper() else '#171820',
                                            font=('Segoe UI Symbol',max(9,int(s*.75))))
        for x in range(8):
            self.canvas.create_text(ox+(x+.5)*s,oy+8*s+7,text=('hgfedcba' if black else 'abcdefgh')[x],fill=MUTED,font=('Segoe UI',9))
            self.canvas.create_text(ox-7,oy+(x+.5)*s,text=str(x+1 if black else 8-x),fill=MUTED,font=('Segoe UI',9))
        markings=[]
        if ranks and not current:
            if index==0:markings=arrows(event,self.layer.get()=='all')
            elif index<len(moves):markings=[(moves[index],'line')]
            if index==1 and self.layer.get()=='all':
                from .analysis_view import uci
                for trap in (event.get('details',{}).get('possible_traps') or [])[:2]:
                    if isinstance(trap,dict) and uci(trap.get('bait')):markings.append((trap['bait'],'trap'))
        for move,kind in markings:
            x1,y1=square_xy(move[:2],black);x2,y2=square_xy(move[2:4],black)
            color=GREEN if kind=='chosen' else '#a78bfa' if kind=='alternative' else RED if kind=='trap' else '#e9b963'
            self.canvas.create_rectangle(ox+x2*s+2,oy+y2*s+2,ox+(x2+1)*s-2,oy+(y2+1)*s-2,outline=color,width=2)
            self.canvas.create_line(ox+(x1+.5)*s,oy+(y1+.5)*s,ox+(x2+.5)*s,oy+(y2+.5)*s,fill=color,
                                    width=max(2,int(s*.10)),dash=(4,3) if kind=='trap' else (),arrow='last',arrowshape=(max(6,int(s*.30)),max(7,int(s*.36)),max(3,int(s*.16))))
        if not ranks:self.canvas.create_text(width/2,height/2,text=self.tr('Нет позиции','No position'),fill=TEXT,font=('Segoe UI',12),tags='empty')
        self.caption.set(self.tr('Последняя позиция из событий','Last reported position') if current else self.tr('Снимок расчёта · ловушки условны','Analysis snapshot · traps conditional'))
        self.step_text.set('—' if current else f'{index}/{len(moves)}'+(' · '+moves[index-1] if index else ''))
        self.prev.configure(state='normal' if index>0 and not current else 'disabled')
        self.next.configure(state='normal' if index<len(moves) and not current else 'disabled')

    def refresh(self):
        event=self.app._last_event
        if self.key=='control':
            active=bool(self.app.worker and self.app.worker.is_alive())
            side=self.app.color.get()
            sig=(active,side)
            if sig==self.signature:return
            self.signature=sig
            for w in (self.start,self.join,self.color_menu):w.configure(state='disabled' if active else 'normal')
            self.stop.configure(state='normal' if active else 'disabled')
            self.color_menu.set(next(k for k,v in self.color_names.items() if v==side))
        elif self.key=='board':
            if event is not self._event_id:
                self._event_id=event;self.line_index=0
            self.draw_board()
        elif self.key=='log':
            items=tuple(self.app._messages)
            mode=self.log_filter.get()
            sig=(items,mode)
            if sig==self.signature:return
            previous=self.signature
            self.signature=sig
            old=self.output.yview()[0]
            # Append only when old buffer is an unchanged prefix; rebuild on rollover/filter.
            if isinstance(previous,tuple) and len(previous)==2 and previous[1]==mode and items[:len(previous[0])]==previous[0]:
                self.output.configure(state='normal')
                for tag,line in items[len(previous[0]):]:
                    if mode in ('all',tag):self.output.insert('end',line,tag)
                self.output.configure(state='disabled')
            else:self.set_text([(tag,line) for tag,line in items if mode in ('all',tag)])
            if self.follow.get():self.output.see('end')
            else:self.output.yview_moveto(old)
        else:
            if event is self.signature:return
            self.signature=event
            en=self.app.lang.get()=='EN'
            if self.key=='console':
                sections=report_sections(event,en)
            else:
                sections=report_sections(event,en)
                sections=[section for i,section in enumerate(sections) if i in (0,1,3) or 'continuation' in section[0].lower() or 'продолжение' in section[0].lower() or 'линия поиска' in section[0].lower() or 'principal variation' in section[0].lower()]
                d=(event or {}).get('details',{})
                rows=[]
                for c in d.get('candidates') or []:
                    if isinstance(c,dict):rows.append(f'{c.get("move","—"):6}  {c.get("cp","—")} cp  ·  p={c.get("policy","—")}  ·  {c.get("expected_reply") or "—"}')
                sections.append((self.tr('Кандидаты · cp / policy / ответ','Candidates · cp / policy / reply'),'\n'.join(rows) or '—'))
            self.set_text([(tag,text) for title,body in sections for tag,text in (('heading',title+'\n'),('info',body+'\n\n'))])
