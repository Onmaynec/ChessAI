"""Primary Qt Quick desktop entry point; no CustomTkinter or Tk imports."""
from .qt_preview import create_engine, make_controller, ROOT

def main():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print('[ERROR] Qt Quick is missing. Run START_VISION_REBORN.bat to install dependencies.')
        return 2
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    controller, journal = make_controller()
    engine, model = create_engine(controller,journal,'QT REBORN',ROOT/'config'/'vision_reborn_ui.json',reborn=True)
    if not engine.rootObjects():
        print('[ERROR] Reborn QML failed to load. See Qt messages above.')
        return 1
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())
