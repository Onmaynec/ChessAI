"""Review manifest validation. Machine checks are not visual acceptance."""
from __future__ import annotations
import json
from pathlib import Path

PAGES = ('overview','analysis','journal','settings','gallery')
SIZES = ((1200,800),(800,650),(560,480))
MODES = ('compact','standard','expanded')
PANELS = ('metrics','board','analysis','journal')

def expected_cases():
    cases = [f'{page}-{w}x{h}' for w,h in SIZES for page in PAGES]
    cases += [f'mode-{mode}' for mode in MODES]
    cases += [f'overlay-{key}' for key in PANELS]
    cases += [f'scale130-{page}' for page in PAGES]
    cases += ['idle-overview','idle-analysis','idle-journal']
    return tuple(cases)

def review_manifest(report, directory: Path):
    """Return missing/invalid evidence, without pretending to score aesthetics."""
    issues = []
    if not isinstance(report,dict) or report.get('schema') != 1:
        return ['Unknown report schema']
    rows = report.get('captures')
    if not isinstance(rows,list):
        return ['Missing captures']
    seen = set()
    for row in rows:
        if not isinstance(row,dict):
            issues.append('Malformed capture row')
            continue
        key = row.get('case')
        if not isinstance(key,str) or key not in expected_cases():
            issues.append('Unexpected capture case')
            continue
        if key in seen:
            issues.append(f'{key}: duplicate')
        seen.add(key)
        path = directory/(key+'.png')
        if row.get('file') != path.name or not path.is_file():
            issues.append(f'{key}: missing image')
        else:
            # Check actual PNG signature and dimensions; no external dependency.
            with path.open('rb') as f:
                header = f.read(24)
            if (len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n'
                    or header[12:16] != b'IHDR'):
                issues.append(f'{key}: invalid PNG header')
            elif [int.from_bytes(header[16:20],'big'),int.from_bytes(header[20:24],'big')] != row.get('image_size'):
                issues.append(f'{key}: PNG dimensions differ from manifest')
        logical = row.get('logical_size')
        if (not isinstance(logical,list) or len(logical)!=2
                or not all(type(v) is int and v > 0 for v in logical)):
            issues.append(f'{key}: invalid logical dimensions')
        else:
            for w,h in SIZES:
                if key.endswith(f'-{w}x{h}') and logical != [w,h]:
                    issues.append(f'{key}: requested size not reached')
        if type(row.get('sample_colors')) is not int or row['sample_colors'] < 3:
            issues.append(f'{key}: blank or nearly uniform frame')
    for key in expected_cases():
        if key not in seen:
            issues.append(f'{key}: missing capture')
    warnings = report.get('qml_warnings')
    if not isinstance(warnings,list):
        issues.append('Missing QML warning record')
    elif warnings:
        issues.append(f'{len(warnings)} QML warning(s)')
    if report.get('errors'):
        issues.append('Capture reported errors')
    return issues

def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('report',type=Path)
    args = p.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding='utf-8'))
        issues = review_manifest(report,args.report.parent)
    except (OSError,ValueError) as exc:
        issues = [str(exc)]
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print('Capture evidence complete; human visual and functional review still required.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
