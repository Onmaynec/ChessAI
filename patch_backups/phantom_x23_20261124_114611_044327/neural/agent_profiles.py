"""Independent game personalities. Style is a *bounded tie breaker*, not a
replacement for search or a claim that chess knowledge was learned.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

RUN_ID='run_20261123_072154_6a110b'

@dataclass(frozen=True)
class AgentProfile:
    name: str
    filename: str
    search_style: str
    depth: int
    deep_depth: int | None
    shortlist: int
    category_weights: dict[str,float]

_PROFILES = {
    'aggressive': AgentProfile('Aggressive','aggressive.pt','aggressive',3,6,5,
        {'attack':3.6,'counter':2.8,'trade':1.5,'opening':2.0,'defense':1.0,'endgame':1.1,'general':1.0}),
    'defender': AgentProfile('Defender','defender.pt','defender',3,6,7,
        {'attack':1.1,'counter':1.5,'trade':2.5,'opening':1.8,'defense':3.7,'endgame':2.5,'general':1.0}),
}
ALIASES = ('latest.pt','lasttest.pt','best.pt','skillboost.pt','skillboost_v2.pt','aggressive.pt','defender.pt')

def profile_for_filename(filename: str) -> AgentProfile | None:
    name=Path(filename).name.lower()
    for profile in _PROFILES.values():
        if name==profile.filename:
            return profile
    return None

def get_profile(name: str) -> AgentProfile:
    if name not in _PROFILES:
        raise ValueError(f'Unknown agent profile: {name}')
    return _PROFILES[name]

def resolve_source_checkpoints(run: Path, base: str = 'auto') -> dict[str, Path]:
    """No weight averaging; every checkpoint is a separately loaded teacher."""
    root=run/'checkpoints'
    base_file=next((root/n for n in ('lasttest.pt','latest.pt') if (root/n).is_file()),root/'latest.pt') if base=='auto' else root/Path(base).name
    out={'latest':base_file,'skillboost':root/'skillboost.pt','skillboost_v2':root/'skillboost_v2.pt'}
    missing=[f'{name}: {path}' for name,path in out.items() if not path.is_file()]
    if missing:raise FileNotFoundError('Required sources are missing; no model created. '+ '; '.join(missing))
    return out
