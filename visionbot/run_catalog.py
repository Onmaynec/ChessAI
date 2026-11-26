"""Local run discovery without loading weights or modifying training data."""
from pathlib import Path

def discover_runs(root: Path):
    rows = []
    directory = root/'runs'
    if directory.is_dir():
        for run in sorted(directory.iterdir(), key=lambda p:p.name, reverse=True):
            if not run.is_dir() or not (run/'checkpoints').is_dir():
                continue
            models = sorted(p.name for p in (run/'checkpoints').glob('*.pt') if p.is_file())
            if models:
                rows.append({'id':run.name,'models':models})
    return rows

def checkpoint_path(root: Path, run: str, model: str):
    if not run or Path(run).name != run or not model or Path(model).name != model or not model.endswith('.pt'):
        raise ValueError('Invalid run or checkpoint name')
    base = (root/'runs').resolve()
    path = (base/run/'checkpoints'/model).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise FileNotFoundError(path)
    return path

def engine_path(root: Path):
    paths = (root/'build'/'Release'/'chessai.exe',root/'build'/'chessai.exe')
    return next((p for p in paths if p.is_file()),paths[0])
