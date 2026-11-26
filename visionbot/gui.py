"""Primary Vision entry point: Qt Quick Reborn. Legacy remains explicit."""
import sys

def main():
    if '--legacy' in sys.argv:
        sys.argv.remove('--legacy')
        from .legacy_gui import main as run
    else:
        from .qt_reborn import main as run
    return run()

def __getattr__(name):
    # Preserve compatibility with existing screenshot tools and old imports.
    if name in ('App','ROOT','RUN_ID'):
        from . import legacy_gui
        return getattr(legacy_gui,name)
    raise AttributeError(name)

if __name__ == '__main__':
    raise SystemExit(main())
