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
from .focus import ensure_browser_foreground
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


def click_move(move,rect,color,screen, *, clicker=None, expected_hwnd=None):
    import pyautogui
    check_computer_browser_focus(expected_hwnd)
    if clicker is None:clicker=pyautogui.click
    for x,y in move_points(move,rect,color):
        check_computer_browser_focus(expected_hwnd)
        px,py=screen.pixel(x,y)
        clicker(px,py)
        time.sleep(.09)
    # Promotions require the chess.com promotion popup; stop rather than click
    # an unverified square or guess where the button appears.
    if len(move)==5:
        raise RuntimeError('Promotion requires site-specific visual confirmation; automatic clicks stopped safely')


def save_progress(run_dir:Path,record:dict):
    safe_session_record(run_dir/'botlab_sessions',record)


class VisionAutoplay:
    def __init__(self,engine:Path,checkpoint:Path,run_dir:Path,color:str,rect:tuple[int,int,int],
                 report,stop,device:str='cpu',screen=None,session_factory=BotLabSession,expected_hwnd=None,
                 *, resume: bool = True, recovery_enabled: bool | None = None):
        self.engine=engine;self.checkpoint=checkpoint;self.run_dir=run_dir
        self.color=color;self.rect=rect;self.report=report;self.stop=stop
        self.device=device;self.screen=screen;self.session_factory=session_factory
        self.move_count=0;self.expected_hwnd=expected_hwnd
        self.resume = resume
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
            if store is not None and store.exists() and self.resume:
                data = store.load()
                recognizer = VisionRecognizer(store.first_image(), self.color)
                sess = self.session_factory(self.engine, store.model_path, self.color, device=self.device)
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
                good1 = [moves for moves, fen in possible if _board_agrees(snapshot1, fen)]
                good2 = [moves for moves, fen in possible if _board_agrees(snapshot2, fen)]
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
            self.report('Vision Resume v0.7.3: журнал ходов и сверка позиции включены')
            while not sess.state.get('finished'):
                self._check_stop()
                if sess.ai_turn():
                    move,value=sess.propose()
                    details = getattr(sess, 'last_analysis', {})
                    if details.get('mode') == 'neural_plus_cpp_search':
                        self.report(f"Анализ: поиск {details['search_depth']} полуходов; "
                                    f"оценка {details['engine_cp']:+d} cp; "
                                    f"лучший тактический {details['best_engine_cp']:+d} cp")
                    elif details.get('mode') == 'neural_fallback':
                        self.report(f"ВНИМАНИЕ: поиск недоступен; резервный выбор нейросети: {details.get('reason','')}")
                    if len(move)==5:
                        raise RuntimeError('AI chose a promotion. VisionBot does not yet support the on-site promotion selector; stopped safely.')
                    self.report(f'Нейросеть: {move} (value={value:+.3f}); проверяю окно и отправляю ход')
                    if store is not None:
                        store.intent(move, sess.state['fen'])
                    click_move(move,self.rect,self.color,screen,expected_hwnd=self.expected_hwnd)
                    self.report(f'Клик выполнен: {move}; проверяю изображение доски')
                    replies = self._preview_opponent_replies(sess, move)
                    recognized, fast_reply = self._wait_own_or_immediate_reply(
                        recognizer, sess, move, replies, 8)
                    if recognized != move:
                        raise RuntimeError('Own move verification failed')
                    sess.confirm_ai(); self.move_count += 1
                    if store is not None:
                        store.commit(sess)
                    self.report(f'Ход подтверждён: {move}')
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
                    self.report('Ожидаю ход компьютерного бота…')
                    move=self._wait_one(recognizer,sess,sess.state['legal_moves'],160)
                    sess.opponent_move(move);self.move_count+=1
                    if store is not None:
                        store.commit(sess)
                    self.report(f'Ход соперника: {move}')
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
