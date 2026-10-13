"""Native Windows shell for TripOrders.exe (pywebview + WebView2). Falls back to the system browser when WebView2 is missing."""
import os
import sys
import time
import urllib.error
import urllib.request

WINDOW_TITLE = 'Trip Orders'
MUTEX_NAME = r'Global\TripOrders-51A5FF77-EE7F-474F-9A55-53DEEF2A4B7A'
_MUTEX_HANDLE = None


def installed_exe():
    return sys.platform == 'win32' and getattr(sys, 'frozen', False)


def icon_path():
    """Best .ico next to the running program (Nuitka onefile/standalone layout)."""
    bases = []
    if getattr(sys, 'frozen', False):
        bases.append(os.path.dirname(sys.executable))
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        bases.append(meipass)
    here = os.path.dirname(os.path.abspath(__file__))
    bases.append(os.path.join(here, '..', 'build'))
    bases.append(here)
    for base in bases:
        p = os.path.normpath(os.path.join(base, 'triporders.ico'))
        if os.path.isfile(p):
            return p
    return None


def wait_for_server(port, host='127.0.0.1', timeout=60.0):
    url = f'http://{host}:{port}/api/auth/status'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.25)
    return False


def _win32():
    import ctypes
    from ctypes import wintypes
    return ctypes, wintypes


def focus_existing_window():
    """Bring an already-open Trip Orders window to the front. Returns True if a window was found."""
    if sys.platform != 'win32':
        return False
    ctypes, wintypes = _win32()
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True


def exit_if_duplicate_instance():
    """Named mutex: a second interactive launch focuses the first window and tells the caller to exit."""
    global _MUTEX_HANDLE
    if sys.platform != 'win32':
        return False
    ctypes, _wintypes = _win32()
    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return False
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        focus_existing_window()
        return True
    _MUTEX_HANDLE = handle
    return False


def webview_runtime_available():
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    if sys.platform != 'win32':
        return False
    for sub in (
        os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Microsoft', 'EdgeWebView', 'Application'),
        os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Microsoft', 'EdgeWebView', 'Application'),
        os.path.join(os.environ.get('LocalAppData', ''), 'Microsoft', 'EdgeWebView', 'Application'),
    ):
        if sub and os.path.isdir(sub):
            return True
    return False


def open_system_browser(url):
    import webbrowser
    webbrowser.open(url)


def run_window(url, on_closed):
    """Show the office UI in a native window. Calls on_closed() after the window is dismissed."""

    def _on_closing():
        try:
            on_closed()
        except Exception:
            pass
        return True

    import webview

    webview.create_window(
        WINDOW_TITLE,
        url,
        width=1280,
        height=840,
        min_size=(960, 640),
        text_select=True,
        icon=icon_path(),
    )
    webview.start(_on_closing)


def set_taskbar_overlay_badge(count):
    """Optional pending-count badge on the taskbar icon (Windows 7+). No-op when unsupported."""
    if sys.platform != 'win32' or count is None or count < 1:
        return
    ctypes, wintypes = _win32()
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    size = 16
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(220, 53, 69, 255))
    label = str(count if count < 100 else '99+')
    draw.text((size // 2, size // 2), label, fill=(255, 255, 255, 255), anchor='mm')
    # HICON creation is platform-specific; skip when we cannot build one cheaply.
    _ = img  # placeholder: full COM ITaskbarList3 wiring needs a stable HWND from webview


def should_use_desktop_window(cfg, background, desktop_requested):
    if background or not desktop_requested:
        return False
    if cfg.get('ui_mode') == 'browser':
        return False
    return installed_exe() or os.environ.get('TO_DESKTOP_WINDOW') == '1'
