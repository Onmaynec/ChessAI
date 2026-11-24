"""Visible desktop automation limited by UI to computer-bot games.

No credential access, browser injection, HTTP calls to chess.com, network
scraping, anti-detection, training on third-party games, or rated play support.
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from botlab.session import BotLabSession, parse_board, safe_session_record
from .recognizer import VisionRecognizer
from .focus import ensure_browser_foreground, focus_browser_from_panel
from .recovery import RecoveryStore, RecoveryError, replay_session, recover_moves, _board_agrees


class Screen:
    def __init__(self):
        import mss
        self.sct=mss.mss()
        self.monitor=self.sct.monitors[1]

    def grab(self,rect):
        import numpy as np
        x,y,s=rect
        mon={'left':self.monitor['left']+x,'top':self.monitor['top']+y,'width':s,'height':s}
        return np.asarray(self.sct.grab(mon))[:,:,:3].copy()

    def full(self):
        import numpy as np
        return np.asarray(self.sct.grab(self.monitor))[:,:,:3].copy()

    def pixel(self,x,y):
        return (self.monitor['left']+x,self.monitor['top']+y)

    def close(self):self.sct.close()


def move_points(move:str,rect:tuple[int,int,int],color:str):
    """Square center coordinates; UI-independent and unit-testable."""
    from .recognizer import cell,orient_rc
    x,y,size=rect
    out=[]
    for algebraic in (move[:2],move[2:4]):
        r,c=cell(algebraic)
        r,c=orient_rc(r,c,color)
        out.append((x+int((c+0.5)*size/8),y+int((r+0.5)*size/8)))
    return out


def check_computer_browser_focus(expected_hwnd: int | None = None):
    """Keep a strict focus guard before every mouse click."""
    ensure_browser_foreground(expected_hwnd)


def click_move(move,rect,color,screen, *, clicker=None, expected_hwnd=None,
               report=None, sleep=time.sleep):
    """Make a move; if promoting, use visual piece-picker confirmation.

    Chess.com may auto-queen, or display a four-piece promotion menu.
    Never guess the menu ordering. Alt held during an underpromotion attempts
    to force the menu even when the site has auto-queen configured.
    """
    import pyautogui
    import numpy as np
    from .promotion import (is_promotion, promotion_picker_choices,
                            identify_promoted_piece)
    from .recognizer import cell, orient_rc
    check_computer_browser_focus(expected_hwnd)
    if clicker is None:
        clicker=pyautogui.click
    promotion=is_promotion(move)
    before=screen.grab(rect) if promotion else None
    modifier=promotion and move[4].lower()!='q'
    try:
        if modifier:
            pyautogui.keyDown('alt')
        for x,y in move_points(move,rect,color):
            check_computer_browser_focus(expected_hwnd)
            px,py=screen.pixel(x,y)
            clicker(px,py)
            sleep(.09)
    finally:
        if modifier:
            pyautogui.keyUp('alt')
    if not promotion:
        return 'ordinary'
    side='white' if color=='white' else 'black'
    # Queen promotion on Chess.com: many board themes show a popover with
    # the queen on the DESTINATION square. A second click there confirms it.
    # Never double-click an ordinary move or an underpromotion.
    queen_reclicked=False
    if move[4].lower()=='q':
        from .recognizer import tiles
        from types import SimpleNamespace
        # Let the browser finish the first click and render the menu / queen.
        sleep(.22)
        check_computer_browser_focus(expected_hwnd)
        first=screen.grab(rect)
        observed=SimpleNamespace(raw_tiles=tiles(first,color),sides=None)
        seen=identify_promoted_piece(observed,move[2:4],side)
        if seen.kind=='q':
            if report:report('Превращение в ферзя уже подтверждено на доске; лишний клик не нужен')
            return 'automatic'
        if seen.kind is not None:
            raise RuntimeError('На последней горизонтали распознана не выбранная фигура: '+seen.kind.upper())
        # Prefer the visually recognised queen menu item; on standard
        # Chess.com menu the first item is centered on the target square.
        popup=promotion_picker_choices(before,first,color,move[2:4],side)
        if popup:
            r,c=popup['q']
            r,c=orient_rc(r,c,color)
            x,y,size=rect
            target=(x+int((c+.5)*size/8),y+int((r+.5)*size/8))
            method='распознанный пункт меню'
        else:
            target=move_points(move,rect,color)[1]
            method='повторный клик в центр клетки назначения'
        check_computer_browser_focus(expected_hwnd)
        clicker(*screen.pixel(*target))
        queen_reclicked=True
        if report:report('Превращение в ферзя: '+method+' ('+move[2:4]+'); подтверждаю изображением')
        # Only ONE additional click is sent. The rest of this function is
        # read-only verification; it never clicks again on an uncertain board.
        sleep(.22)
        check_computer_browser_focus(expected_hwnd)
        confirmed=screen.grab(rect)
        observed=SimpleNamespace(raw_tiles=tiles(confirmed,color),sides=None)
        seen=identify_promoted_piece(observed,move[2:4],side)
        if seen.kind=='q':
            if report:report('Ферзь подтверждён визуально на '+move[2:4])
            return 'queen_reclick'
        if seen.kind is not None:
            raise RuntimeError('После выбора обнаружена другая фигура: '+seen.kind.upper())
    # Prefer reading the actual picker UI; do NOT index a guessed fixed
    # order of Q/R/B/N, which differs between clients and site versions.
    timeout=time.monotonic()+3.3
    while time.monotonic()<timeout:
        check_computer_browser_focus(expected_hwnd)
        sleep(.16)
        current=screen.grab(rect)
        popup=promotion_picker_choices(before,current,color,move[2:4],side)
        if popup:
            if queen_reclicked:
                continue  # Extra queen click already sent; never click twice on uncertainty.
            r,c=popup[move[4].lower()]
            visual_row, visual_col=orient_rc(r,c,color)
            x,y,size=rect
            cx=x+int((visual_col+.5)*size/8)
            cy=y+int((visual_row+.5)*size/8)
            check_computer_browser_focus(expected_hwnd)
            clicker(*screen.pixel(cx,cy))
            if report:report('Выбрана фигура превращения: '+move[4].upper())
            return 'picker'
        # With autoqueen enabled the popup can be skipped. But never mistake
        # an unclassified FOUR-ICON popup for an already promoted queen.
        from .recognizer import tiles,cell,orient_rc
        base_tiles=tiles(before,color)
        now_tiles=tiles(current,color)
        cr,cc=cell(move[2:4]);vr,vc=orient_rc(cr,cc,color)
        sign=1 if vr==0 else -1
        changed=0
        for offset in range(1,4):
            chess_r=cr+offset*(1 if color=='white' else -1)*sign
            if 0<=chess_r<8:
                delta=np.mean(np.abs(base_tiles[chess_r][cc].astype('float32')-
                                     now_tiles[chess_r][cc].astype('float32')))
                changed+=delta>=8
        if changed>=2:
            continue  # likely a promotion popup; don't auto-confirm
        # For underpromotion never accept autoqueen as a knight/rook/bishop.
        class OneSquare:
            pass
        one=OneSquare()
        one.raw_tiles=tiles(current,color)
        one.sides=None
        found=identify_promoted_piece(one,move[2:4],side)
        if found.kind is not None:
            if found.kind==move[4].lower():
                if report:report('Превращение отображено на доске: '+found.kind.upper())
                return 'automatic'
            # Other piece seen: could still be an animation or popup;
            # wait, never confirm a mismatched underpromotion as our move.
    raise RuntimeError('Превращение: не удалось надёжно определить меню или нужную фигуру. '
                       'Клики остановлены. Выбери фигуру вручную, затем продолжи из журнала '
                       'или подключись к текущей позиции.')


def save_progress(run_dir:Path,record:dict):
    safe_session_record(run_dir/'botlab_sessions',record)


class VisionAutoplay:
    def __init__(self,engine:Path,checkpoint:Path,run_dir:Path,color:str,rect:tuple[int,int,int],
                 report,stop,device:str='cpu',screen=None,session_factory=BotLabSession,expected_hwnd=None,
                 *, resume: bool = True, recovery_enabled: bool | None = None,
                 attach_any_position: bool = False, explicit_turn: str | None = None,
                 analysis_level: str = 'standard', browser_window=None):
        self.engine=engine;self.checkpoint=checkpoint;self.run_dir=run_dir
        self.color=color;self.rect=rect;self.report=report;self.stop=stop
        self.device=device;self.screen=screen;self.session_factory=session_factory
        self.move_count=0;self.expected_hwnd=expected_hwnd
        self.resume = resume
        self.attach_any_position = attach_any_position
        self.explicit_turn = explicit_turn
        self.analysis_level = analysis_level
        self.browser_window=browser_window
        # Test-injected mock sessions do not necessarily support the C++ journal.
        self.recovery_enabled = (session_factory is BotLabSession) if recovery_enabled is None else recovery_enabled

    def _check_stop(self):
        if self.stop.is_set():raise InterruptedError('Stopped by user')
        # Esc pressed anywhere, even when browser has focus.
        import sys
        if sys.platform=='win32':
            import ctypes
            if ctypes.windll.user32.GetAsyncKeyState(0x1B)&0x8000:
                raise InterruptedError('Emergency stop: ESC')

    def _observe(self,recognizer):
        return recognizer.observe(self.screen.grab(self.rect))

    def _wait_one(self,recognizer,sess,allowed,timeout):
        """Require matching move in two samples; on timeout stop, no guessing."""
        old=parse_board(sess.state['fen'])
        last=None;hits=0;deadline=time.monotonic()+timeout;last_reason='No frame';last_gain=0.0
        while time.monotonic()<deadline:
            self._check_stop()
            time.sleep(.48)
            obs=self._observe(recognizer)
            match=recognizer.detect(obs,old,allowed)
            last_reason=getattr(match,'reason','Recognition inconclusive')
            last_gain=getattr(match,'gain',0.0)
            if match.move is None:
                last=None;hits=0;continue
            if match.move==last:hits+=1
            else:last=match.move;hits=1
            if hits>=2:return match.move
        raise TimeoutError(f'Move recognition timeout ({timeout}s): '
                           f'{last_reason}, gain={last_gain:+.3f}. '
                           'Клики остановлены; перезапусти Vision Bot с восстановлением.')

    def _preview_opponent_replies(self, sess, our_move):
        """Ask the existing C++ bridge for legal replies, without changing game 444.

        The main game isn't advanced until screenshots confirm the click. The
        temporary game is discarded unconditionally, even on a bridge error.
        """
        if not hasattr(sess, 'bridge'):
            return []  # test/manual session without speculative bridge support
        preview_id = 445  # main session 444; tactical search uses 999999
        try:
            sess.bridge.new(preview_id, sess.state['fen'])
            state = sess.bridge.step(preview_id, our_move)
            return list(state.get('legal_moves', ()))
        finally:
            try:
                sess.bridge.drop(preview_id)
            except (OSError, RuntimeError):
                pass

    def _wait_own_or_immediate_reply(self, recognizer, sess, move, legal_replies, timeout=8):
        """Observe either the verified own move or one verified fast reply.

        A frame is accepted after two consecutive equivalent observations.
        Never click again on a timeout; errors are diagnosed, not guessed.
        Returns (own_move, opponent_move_or_none).
        """
        old = parse_board(sess.state['fen'])
        previous = None
        matches = 0
        last_reason = 'No frame'
        last_gain = 0.0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._check_stop()
            time.sleep(0.35)
            observed = self._observe(recognizer)
            one = recognizer.detect(observed, old, [move])
            last_reason = getattr(one, 'reason', 'One-move visual confirmation')
            last_gain = getattr(one, 'gain', 1.0 if one.move else 0.0)
            if one.move == move:
                result = (move, None)
            else:
                two = recognizer.detect_immediate_reply(observed, old, move, legal_replies)
                if two.move:
                    if len(move)==5:
                        # A promoted piece can disappear in the immediate
                        # recapture; do not pretend its type was confirmed.
                        from .promotion import identify_promoted_piece
                        from .recognizer import cell, board_after
                        r,c=cell(move[2:4])
                        final = board_after(board_after(old,move),two.move)
                        if final[r][c].lower() != move[4].lower() or identify_promoted_piece(
                                observed,move[2:4],self.color).kind!=move[4].lower():
                            result=None
                            last_reason='Promoted piece was immediately captured or unclear'
                            continue
                    result = (move, two.move)
                    last_reason, last_gain = two.reason, two.gain
                else:
                    result = None
                    last_reason += '; ' + two.reason
            if result is None:
                previous = None
                matches = 0
                continue
            matches = matches + 1 if result == previous else 1
            previous = result
            if matches >= 2:
                return result
        raise TimeoutError(f'Move recognition timeout ({timeout}s): {last_reason}, '
                           f'gain={last_gain:+.3f}. Клики остановлены, '
                           'повторный ход не отправлен. Перезапусти с восстановлением.')

    def run(self):
        # A supplied screen is owned by the caller; an internally-created
        # screen must be kept on self for _observe() and closed on exit.
        # Previously run() used a local variable only, causing:
        # AttributeError: 'NoneType' object has no attribute 'grab'
        owns_screen = self.screen is None
        screen = None
        sess = None
        try:
            screen = self.screen if self.screen is not None else Screen()
            self.screen = screen
            initial = screen.grab(self.rect)
            store = RecoveryStore(self.run_dir, self.color) if self.recovery_enabled else None
            if self.attach_any_position:
                if store is None:
                    raise RecoveryError('Подключение к текущей партии требует сохранения журнала')
                from .position_import import import_position
                first = import_position(initial, self.color, explicit_turn=self.explicit_turn)
                time.sleep(.45)
                self._check_stop()
                second_frame = screen.grab(self.rect)
                second = import_position(second_frame, self.color, explicit_turn=self.explicit_turn)
                if first.fen != second.fen:
                    raise RecoveryError('Доска изменилась между снимками. Подожди окончания анимации и повтори.')
                # Check C++ parser/legal state BEFORE archiving the previous
                # journal. This avoids losing a recoverable old game on bad FEN.
                from neural.selfplay import ChessBridge
                with ChessBridge(self.engine) as probe:
                    tested = probe.new(447, first.fen)
                    if tested.get('finished'):
                        raise RecoveryError('Распознанная позиция уже завершена')
                recognizer = VisionRecognizer(second_frame, self.color, initial_fen=first.fen)
                if store.exists():
                    store.archive()
                    self.report('Предыдущая партия безопасно архивирована')
                store.create(self.checkpoint, second_frame, self.rect, initial_fen=first.fen)
                sess = self.session_factory(self.engine, store.model_path, self.color,
                                            device=self.device, initial_fen=first.fen)
                self.report('Подключено к текущей партии без истории: '+first.fen)
                self.report(first.warning)
                self.report('Распознана очередь хода: '+('белые' if first.side_to_move=='w' else 'чёрные'))
            elif store is not None and store.exists() and self.resume:
                data = store.load()
                base_fen=data.get('initial_fen')
                recognizer = VisionRecognizer(store.first_image(), self.color, initial_fen=base_fen)
                sess = self.session_factory(self.engine, store.model_path, self.color, device=self.device,
                                            **({'initial_fen': base_fen} if base_fen else {}))
                replay_session(sess, data)
                # Don't act on an animation frame. Both snapshots must independently
                # identify the same legal continuation (or exactly the saved board).
                snapshot1 = recognizer.observe(initial)
                time.sleep(.35)
                self._check_stop()
                snapshot2 = self._observe(recognizer)
                # Reconciliation against the journal, not inference from arbitrary
                # silhouettes. It can detect our uncommitted move + rapid reply.
                from .recovery import _recovery_candidates, _board_agrees
                possible = list(_recovery_candidates(sess, data.get('pending')))
                good1 = [moves for moves, fen in possible if _board_agrees(snapshot1, fen, moves)]
                good2 = [moves for moves, fen in possible if _board_agrees(snapshot2, fen, moves)]
                if len(good1) != 1 or good1 != good2:
                    raise RecoveryError(
                        'Невозможно однозначно сверить текущую доску с журналом: '
                        f'первый снимок {len(good1)} вариантов, второй {len(good2)}. '
                        'Ходы заблокированы, история сохранена.')
                restored = recover_moves(sess, store, snapshot2)
                store.mark_rect(self.rect)
                self.move_count = len(sess.history)
                self.report(f'Партия восстановлена: {self.move_count} полуходов, FEN: {sess.state["fen"]}')
                if restored:
                    self.report('Ходы, выполненные во время сбоя: ' + ', '.join(restored))
                else:
                    self.report('Доска совпадает с последней сохранённой позицией')
                if data.get('pending') and not restored:
                    self.report('Внимание: прошлый клик не подтверждён; убедись, что на сайте не выделена фигура')
                self.report('Модель восстановлена из неизменяемого снимка checkpoint этой партии')
            else:
                # New game is allowed only after the starting-board visual check.
                recognizer = VisionRecognizer(initial, self.color)
                if store is not None:
                    if store.exists() and not self.resume:
                        store.archive()
                        self.report('Предыдущая партия архивирована без удаления журнала')
                    store.create(self.checkpoint, initial, self.rect)
                    checkpoint = store.model_path
                else:
                    checkpoint = self.checkpoint
                sess = self.session_factory(self.engine, checkpoint, self.color, device=self.device)
                self.report('Новая партия: исходная доска проверена, модель загружена')
            # Deep analysis affects only move inference, never checkpoint or PPO.
            if hasattr(sess,'analysis_level'):
                sess.analysis_level=self.analysis_level
            self.report('Vision v0.7.6: расширенный журнал и углублённый анализ включены')
            self.report('Режим расчёта: '+('выборочный поиск до 7 полуходов' if self.analysis_level=='deep' else 'обычный поиск до 5 полуходов'))
            self.report('Начальная позиция: '+sess.state['fen'])
            from .telemetry import position_summary
            self.report(position_summary(sess.state['fen']))
            while not sess.state.get('finished'):
                self._check_stop()
                if sess.ai_turn():
                    move,value=sess.propose()
                    details = getattr(sess, 'last_analysis', {})
                    from .telemetry import analysis_event
                    self.report(analysis_event(details, move=move, fen=sess.state['fen'],
                                               ply=len(getattr(sess,'history',[])), value=value))
                    if details.get('mode') == 'neural_plus_cpp_search':
                        self.report(f"Анализ: поиск {details['search_depth']} полуходов; "
                                    f"оценка {details['engine_cp']:+d} cp; "
                                    f"лучший тактический {details['best_engine_cp']:+d} cp")
                    elif details.get('mode') == 'neural_fallback':
                        self.report(f"ВНИМАНИЕ: поиск недоступен; резервный выбор нейросети: {details.get('reason','')}")
                        self.report(f'Нейросеть: {move} (value={value:+.3f}); проверяю окно и отправляю ход')
                    if store is not None:
                        store.intent(move, sess.state['fen'])
                    # A persistent topmost panel may be clicked to scroll logs.
                    # Return focus ONLY from our own control window, never from
                    # an unrelated application, and keep all click guards.
                    if focus_browser_from_panel(self.browser_window):
                        self.report('Фокус возвращён браузеру после просмотра панели анализа')
                    click_move(move,self.rect,self.color,screen,expected_hwnd=self.expected_hwnd,report=self.report)
                    self.report(f'Клик выполнен: {move}; проверяю изображение доски')
                    replies = self._preview_opponent_replies(sess, move)
                    recognized, fast_reply = self._wait_own_or_immediate_reply(
                        recognizer, sess, move, replies, 8)
                    if recognized != move:
                        raise RuntimeError('Own move verification failed')
                    sess.confirm_ai(); self.move_count += 1
                    if store is not None:
                        store.commit(sess)
                    self.report(f'Ход подтверждён: {move} · полуходов {self.move_count} · FEN {sess.state["fen"]}')
                    self.report(position_summary(sess.state['fen']))
                    if fast_reply is not None:
                        # Both plies happened before the first screenshot.
                        # Update the C++ session in the same legal order,
                        # otherwise subsequent moves become desynchronized.
                        sess.opponent_move(fast_reply); self.move_count += 1
                        if store is not None:
                            store.commit(sess)
                        self.report(f'Быстрый ответ компьютерного бота: {fast_reply}; '
                                    'оба хода подтверждены одним снимком')
                else:
                    self.report('Ожидаю ход компьютерного бота… · очередь: '+sess.state['fen'].split()[1])
                    move=self._wait_one(recognizer,sess,sess.state['legal_moves'],160)
                    sess.opponent_move(move);self.move_count+=1
                    if store is not None:
                        store.commit(sess)
                    self.report(f'Ход соперника: {move} · полуходов {self.move_count} · FEN {sess.state["fen"]}')
                    self.report(position_summary(sess.state['fen']))
            if store is not None:
                store.commit(sess)
            self.report(f'Партия завершена: {sess.state.get("result") or "unknown"}')
        except (InterruptedError,TimeoutError,RuntimeError,ValueError,FileNotFoundError) as e:
            self.report('ОСТАНОВКА: '+str(e))
        except Exception as e:
            self.report(f'НЕОЖИДАННАЯ ОШИБКА: {type(e).__name__}: {e}')
            self.report(traceback.format_exc(limit=2))
        finally:
            if sess:
                try:
                    record=sess.report('Chess.com computer bot','unfinished',notes='Desktop vision experimental test; not a training data source')
                    record['source']='vision_desktop_computer_bot_test'
                    record['vision_verified_plies']=self.move_count
                    save_progress(self.run_dir,record)
                except Exception as ex:self.report('Не удалось сохранить отчёт: '+str(ex))
                sess.close()
            if owns_screen and screen is not None:
                try:
                    screen.close()
                except Exception as exc:
                    self.report('Не удалось закрыть захват экрана: '+str(exc))
                finally:
                    self.screen = None
            self.report('Vision Bot остановлен. Веса и оптимизатор не изменены.')
