"""External UCI session for explicitly authorized computer-only Vision tests.
Separate journal namespace; snapshot is an engine manifest, never a fake neural net.
"""
from __future__ import annotations
import json,math,re
from pathlib import Path
from functools import partial
from botlab.session import BotLabSession
from .recovery import RecoveryStore,RecoveryError
from external_core.install import DEST,digest
from external_core.uci import configured,PROFILES,ProtocolError

EXTERNAL={'Stockfish 19':'stockfish','Leela Chess Zero':'lc0'}

def available():
    return tuple(label for label,key in EXTERNAL.items() if (DEST/key/'installed.json').is_file())

def computer_title(title):
    title=title.casefold()
    return 'chess.com' in title and bool(re.search(r'\bcomputer\b|\bbots?\b|компьютер|бот[а-я]*',title)) and not bool(re.search(r'\brated\b|\bmultiplayer\b|against a friend|против друга',title))

def input_spec(label,profile):
    key=EXTERNAL[label]
    if profile not in PROFILES:raise ValueError('Unknown UCI profile')
    manifest=DEST/key/'installed.json'
    if not manifest.is_file():raise FileNotFoundError(manifest)
    # Keep separate histories per engine and profile. Never touch neural recovery.
    run=DEST/'vision_sessions'/key/profile
    return manifest,run,partial(ExternalSession,key=key,profile=profile)

class ExternalRecovery(RecoveryStore):
    @property
    def model_path(self):
        return self.dir/f'engine_manifest_{self.color}.json'
    def switch_checkpoint(self,source):
        raise RecoveryError('Stop external game before selecting another engine')
    def first_image(self):
        # Unicode-safe Windows path; old cv2.imread narrow path can fail.
        import cv2,numpy as np
        self.load()
        frame=cv2.imdecode(np.frombuffer(self.photo.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
        if frame is None:raise RecoveryError('Cannot decode saved calibration')
        return frame

class ExternalSession(BotLabSession):
    def __init__(self,engine,checkpoint,color,*,key,profile,device='cpu',**kw):
        self.key=key;self.profile=profile;self.uci=None
        self.manifest=DEST/key/'installed.json'
        if digest(checkpoint)!=digest(self.manifest):raise RecoveryError('External engine installation changed; cannot resume this journal')
        self.engine_manifest=json.loads(self.manifest.read_text(encoding='utf-8'))
        self.label=next(k for k,v in EXTERNAL.items() if v==key)
        # Predict is only a sentinel for the base initializer; never invoked.
        super().__init__(engine,checkpoint,color,device='cpu',predict=lambda _:None,**kw)
        try:
            self.uci=configured(key,profile)
            self.uci.new_game()
        except BaseException:
            self.close();raise
        self.agent_label=self.label;self.agent_profile=None
        self.restarts=0
    def switch_agent(self,*a,**kw):
        raise ValueError('Stop external session before changing engine')
    def propose(self):
        if self.pending is not None:return self.pending,self.value
        if self.state['finished'] or not self.ai_turn():raise ValueError('Not the AI turn')
        try:
            result=self.uci.analyse(self.initial_fen,self.state['legal_moves'],self.history,PROFILES[self.profile][2],1)
        except (ProtocolError,OSError):
            self.uci.close()
            # One bounded restart, no fallback and no unverified action.
            self.uci=configured(self.key,self.profile);self.uci.new_game();self.restarts+=1
            result=self.uci.analyse(self.initial_fen,self.state['legal_moves'],self.history,PROFILES[self.profile][2],1)
        move=result['bestmove']
        if move not in self.state['legal_moves']:raise ProtocolError('Illegal UCI move')
        chosen=next((l for l in result['lines'] if l.get('pv',[None])[0]==move),{})
        score=chosen.get('score') or {}
        pv=chosen.get('pv') or [move]
        self.last_analysis={'mode':'external_uci','engine':result['engine'],'profile':self.profile,
          'engine_cp':score.get('value') if score.get('kind')=='cp' else None,
          'uci_score':score,'search_depth':chosen.get('depth'),'search_nodes':chosen.get('nodes'),
          'nps':chosen.get('nps'),'wdl':chosen.get('wdl'),'search_time_s':round(result['elapsed_ms']/1000,3),
          'illustrative_line':pv,'line_kind':'searched_pv','expected_reply':pv[1] if len(pv)>1 else None,
          'candidates':[{'move':move,'cp':score.get('value') if score.get('kind')=='cp' else None,'policy':None,
                         'expected_reply':pv[1] if len(pv)>1 else None}],'uci_restarts':self.restarts}
        # No neural value from UCI. Compatibility placeholder not displayed as a probability.
        self.pending=move;self.value=0.0
        return move,self.value
    def report(self,opponent,result,notes=''):
        if self.state.get('finished'):
            actual=self.state.get('result')
            result='draw' if actual=='1/2-1/2' else 'win' if actual==('1-0' if self.color=='white' else '0-1') else 'loss' if actual in ('1-0','0-1') else 'unfinished'
        r=super().report(opponent,result,notes)
        r.update(checkpoint_file=None,checkpoint_sha256=None,last_agent_profile=self.label,
                 external_engine=self.label,external_profile=self.profile,
                 external_manifest_sha256=digest(self.manifest),external_archive_sha256=self.engine_manifest['archive_sha256'],
                 weights_sha256=getattr(self.uci,'weights_sha256',None),uci_restarts=self.restarts)
        return r
    def close(self):
        try:
            if self.uci is not None:self.uci.close()
        finally:super().close()
