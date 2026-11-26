"""Render real preview windows in a Qt environment, with marked synthetic data."""
import argparse
from pathlib import Path
from visionbot.qt_preview import create_engine, make_controller, fixture_messages

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/vision-qt'))
    args = parser.parse_args()
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    app = QGuiApplication([])
    controller, journal = make_controller(fixture_messages(), True)
    engine, model = create_engine(controller, journal, 'QA FIXTURE')
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    args.output.mkdir(parents=True, exist_ok=True)
    for width, height in ((1200,800),(800,650),(560,480)):
        window.resize(width,height)
        for page, name in enumerate(('overview','analysis','journal','settings')):
            window.setProperty('page',page)
            QTest.qWait(300)
            image = window.grabWindow()
            path = args.output/f'{name}-{width}x{height}.png'
            if image.isNull() or not image.save(str(path)):
                raise RuntimeError(f'Capture failed: {path}')
            print(path)
    window.close()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
