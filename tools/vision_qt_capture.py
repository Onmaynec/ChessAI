"""Capture real Qt windows and emit machine-checkable review evidence."""
import argparse
import json
import platform
from pathlib import Path
from visionbot.qt_preview import create_engine, make_controller, fixture_messages
from visionbot.ui_state import SessionSnapshot
from tools.vision_qa_manifest import PAGES, SIZES, MODES, PANELS, review_manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/vision-qt'))
    args = parser.parse_args()
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QMetaObject, Q_ARG, QtMsgType, qInstallMessageHandler, qVersion
    app = QGuiApplication([])
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(schema=1, platform=platform.platform(), qt=qVersion(),
                  platform_plugin=app.platformName(), captures=[], qml_warnings=[],
                  other_warnings=[], errors=[])
    def handler(kind, context, message):
        if kind not in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            return
        origin = str(context.file or '')
        entry = f'{origin}: {message}' if origin else message
        is_qml = '.qml' in entry.lower() or 'qml' in entry.lower() or 'binding loop' in entry.lower()
        report['qml_warnings' if is_qml else 'other_warnings'].append(entry)
    old = qInstallMessageHandler(handler)
    window = None
    def capture(target, name, source):
        QTest.qWait(350)
        image = target.grabWindow()
        path = args.output/(name+'.png')
        if image.isNull() or not image.save(str(path)):
            raise RuntimeError(f'Capture failed: {name}')
        colors = {image.pixel(x,y) for x in range(0,image.width(),max(1,image.width()//40))
                  for y in range(0,image.height(),max(1,image.height()//40))}
        report['captures'].append(dict(case=name,file=path.name,source=source,
            logical_size=[target.width(),target.height()],
            image_size=[image.width(),image.height()], dpr=target.devicePixelRatio(),
            sample_colors=len(colors)))
        print(path)

    def invoke(method, value):
        if not QMetaObject.invokeMethod(window,method,Q_ARG('QVariant',value)):
            raise RuntimeError(f'QML method unavailable: {method}')

    try:
        controller, journal = make_controller(fixture_messages(), True)
        engine, model = create_engine(controller,journal,'QA FIXTURE')
        if not engine.rootObjects():
            raise RuntimeError('QML workspace failed to load')
        window = engine.rootObjects()[0]
        workspace = engine.rootContext().contextProperty('workspaceModel')
        workspace.setReducedMotion(True)
        for width,height in SIZES:
            window.resize(width,height)
            for page,name in enumerate(PAGES):
                window.setProperty('page',page)
                capture(window,f'{name}-{width}x{height}','QA FIXTURE')
        for mode in MODES:
            invoke('switchMode',mode)
            window.setProperty('page',0)
            capture(window,f'mode-{mode}','QA FIXTURE')
        for key in PANELS:
            invoke('openOverlay',key)
            QTest.qWait(350)
            panel = next((w for w in app.topLevelWindows()
                          if w.objectName() == 'overlay_'+key and w.isVisible()),None)
            if panel is None:
                raise RuntimeError(f'Overlay did not open: {key}')
            capture(panel,f'overlay-{key}','QA FIXTURE')
            panel.close()
        invoke('switchMode','standard')
        window.resize(560,480)
        workspace.setTextScale(130)
        for page,name in enumerate(PAGES):
            window.setProperty('page',page)
            capture(window,f'scale130-{name}','QA FIXTURE')
        workspace.setTextScale(100)
        window.resize(800,650)
        controller.reset_analysis()
        controller.update_session(SessionSnapshot())
        model.set_journal([])
        model.refresh()
        engine.rootContext().setContextProperty('sourceLabel','OFFLINE / IDLE')
        for page,name in enumerate(PAGES[:3]):
            window.setProperty('page',page)
            capture(window,f'idle-{name}','OFFLINE / IDLE')
    except Exception as exc:
        report['errors'].append(str(exc))
    finally:
        if window is not None:
            window.close()
            app.processEvents()
        qInstallMessageHandler(old)
        issues = review_manifest(report,args.output)
        report['machine_issues'] = issues
        (args.output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for issue in issues:
        print(issue)
    return int(bool(issues))

if __name__ == '__main__':
    raise SystemExit(main())
