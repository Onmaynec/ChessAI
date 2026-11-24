"""Conservative Windows foreground selection for visible Chess.com browser windows.

Only restores the confirmed browser window at the beginning of an opted-in
computer-bot test. Does not defeat foreground restrictions or regain focus
later if the user switches away; all clicks remain guarded.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import ntpath
import sys
import time

BROWSER_EXES = frozenset({
    'chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe',
    'opera.exe', 'opera_gx.exe', 'vivaldi.exe', 'browser.exe'
})


@dataclass(frozen=True)
class Window:
    hwnd: int
    title: str
    exe: str


def choose_browser(windows: list[Window], foreground: int | None) -> Window:
    """Do not guess between multiple distinct Chess.com browser windows."""
    matches = [w for w in windows if 'chess.com' in w.title.casefold() and w.exe.casefold() in BROWSER_EXES]
    if not matches:
        raise RuntimeError('Chess.com browser window not found. Open a computer-bot game in Chrome/Edge/Firefox, make the Chess.com tab active, and retry.')
    active = [w for w in matches if w.hwnd == foreground]
    if active:
        return active[0]
    if len(matches) != 1:
        names = '; '.join(w.title[:70] for w in matches[:4])
        raise RuntimeError(f'Multiple Chess.com windows found ({len(matches)}). Leave only one window visible, or focus the desired browser before pressing Start. Windows: {names}')
    return matches[0]


def _api():
    if sys.platform != 'win32':
        raise RuntimeError('Automatic browser focus is supported on Windows only')
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    return user32, kernel32, wintypes


def _title(user32, hwnd: int) -> str:
    length = min(2047, max(user32.GetWindowTextLengthW(hwnd) + 1, 2))
    buf = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, buf, length)
    return buf.value


def _exe(kernel32, wintypes, pid: int) -> str:
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(4096)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ntpath.basename(buf.value).casefold()
        return ''
    finally:
        kernel32.CloseHandle(handle)


def current_foreground() -> tuple[int, str]:
    if sys.platform != 'win32':
        return 0, ''
    user32, _kernel32, _wintypes = _api()
    hwnd = user32.GetForegroundWindow()
    return int(hwnd or 0), _title(user32, hwnd) if hwnd else ''


def find_browser() -> Window:
    user32, kernel32, wintypes = _api()
    windows: list[Window] = []
    cb_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @cb_type
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _title(user32, hwnd)
        if 'chess.com' not in title.casefold():
            return True
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        windows.append(Window(int(hwnd), title, _exe(kernel32, wintypes, pid.value)))
        return True

    if not user32.EnumWindows(visit, 0):
        raise RuntimeError('Could not enumerate Windows desktop windows')
    return choose_browser(windows, current_foreground()[0])


def activate_browser(target: Window, *, wait_seconds: float = 0.75) -> None:
    """One-time foreground transfer, no workarounds if Windows denies it."""
    user32, _kernel32, _wintypes = _api()
    if user32.IsIconic(target.hwnd):
        user32.ShowWindow(target.hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(target.hwnd)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        hwnd, _ = current_foreground()
        if hwnd == target.hwnd:
            return
        time.sleep(0.05)
    _hwnd, actual = current_foreground()
    raise RuntimeError(f'Windows did not focus Chess.com. Foreground window: {actual or "[untitled]"}. Click the Chess.com browser once and retry; mouse clicks remain blocked.')


def ensure_browser_foreground(target_hwnd: int | None = None) -> None:
    """Never click another window, even if browser lost focus after launch."""
    if sys.platform != 'win32':
        return
    current_hwnd, actual_title = current_foreground()
    if target_hwnd is not None and current_hwnd != target_hwnd:
        raise RuntimeError(f'Chess.com browser lost foreground focus (now: {actual_title or "[untitled]"}); clicks blocked')
    if 'chess.com' not in actual_title.casefold():
        raise RuntimeError(f'Chess.com tab is not foreground (now: {actual_title or "[untitled]"}); clicks blocked')
