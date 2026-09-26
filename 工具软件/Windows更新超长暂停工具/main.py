# -*- coding: utf-8 -*-
"""
Windows 更新超长暂停工具（纯 Win32 原生窗口版）

一键修改 -> 把 Windows 更新暂停 PAUSE_DAYS 天
一键还原 -> 清除全部暂停相关注册表项，恢复系统默认

界面直接用 Windows 系统 API（user32 / gdi32）绘制，只依赖 Python 标准库 ctypes，
不依赖 WebView2 运行时、不依赖 tkinter、不依赖任何第三方 GUI 库，
因此打包出的 exe 在目标机器上不需要任何额外组件。

注册表位置与取值格式严格按 Windows 自身写入的写法（已在 Windows 11 22H2 实机只读核对）：

  1) HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings
       PauseFeatureUpdatesStartTime  REG_SZ    UTC  ISO8601  2026-09-26T10:44:12Z
       PauseFeatureUpdatesEndTime    REG_SZ
       PauseQualityUpdatesStartTime  REG_SZ
       PauseQualityUpdatesEndTime    REG_SZ
       PauseUpdatesStartTime         REG_SZ
       PauseUpdatesExpiryTime        REG_SZ
       FlightSettingsMaxPauseDays    REG_DWORD  天数（抬高 35 天上限的开关）

  2) HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UpdatePolicy\\Settings
       PausedFeatureStatus           REG_DWORD  0=未暂停 1=已暂停 2=暂停后自动恢复
       PausedQualityStatus           REG_DWORD
       PausedFeatureDate             REG_SZ    本地时间  2026-09-26 10:44:12
       PausedQualityDate             REG_SZ

依赖：无（仅 Python 标准库）
运行：python main.py          （必须管理员权限）
打包：pyinstaller --onefile --windowed --uac-admin main.py
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import threading
import time
import winreg
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_TITLE = "Windows 更新超长暂停工具"
PAUSE_DAYS = 10000          # 一键修改固定写入的暂停天数（约 27.4 年）
DAYS_PER_YEAR = 365

HKEY = winreg.HKEY_LOCAL_MACHINE
UX_PATH = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
POLICY_PATH = r"SOFTWARE\Microsoft\WindowsUpdate\UpdatePolicy\Settings"

UX_TIME_VALUES = (
    "PauseFeatureUpdatesStartTime",
    "PauseFeatureUpdatesEndTime",
    "PauseQualityUpdatesStartTime",
    "PauseQualityUpdatesEndTime",
    "PauseUpdatesStartTime",
    "PauseUpdatesExpiryTime",
)
UX_MAX_DAYS_VALUE = "FlightSettingsMaxPauseDays"
POLICY_STATUS_VALUES = ("PausedFeatureStatus", "PausedQualityStatus")
POLICY_DATE_VALUES = ("PausedFeatureDate", "PausedQualityDate")

# 实测来源：Windows 自己写这两个值时用的格式
UX_TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"
POLICY_TIME_FMT = "%Y-%m-%d %H:%M:%S"

# 系统「设置」里的 Windows 更新页
SETTINGS_URI = "ms-settings:windowsupdate"
SETTINGS_PROCESS = "SystemSettings.exe"


# --------------------------------------------------------------------------- #
# 注册表逻辑
# --------------------------------------------------------------------------- #
def _writable_dir() -> Path:
    """可写目录（备份文件放这里）；单文件模式下是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _is_admin() -> bool:
    """当前进程是否具备管理员权限。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _parse_ux_time(text):
    """解析 Windows 写入的 UTC 时间串，返回 aware datetime（UTC）；失败返回 None。"""
    if not text or not isinstance(text, str):
        return None
    cleaned = text.strip().rstrip("Zz").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _backup_once() -> None:
    """首次执行前备份原始注册表值，仅备份一次，不覆盖。"""
    target = _writable_dir() / "pause-backup.json"
    if target.exists():
        return

    snapshot = {}
    sections = (
        (UX_PATH, UX_TIME_VALUES + (UX_MAX_DAYS_VALUE,)),
        (POLICY_PATH, POLICY_STATUS_VALUES + POLICY_DATE_VALUES),
    )
    try:
        for path, names in sections:
            try:
                key = winreg.OpenKey(HKEY, path, 0, winreg.KEY_READ)
            except FileNotFoundError:
                continue
            with key:
                for name in names:
                    try:
                        value, vtype = winreg.QueryValueEx(key, name)
                        snapshot[f"{path}\\{name}"] = {"value": value, "type": vtype}
                    except FileNotFoundError:
                        continue
        target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except OSError:
        # 备份失败不应阻断主流程
        pass


def _refresh_update_service() -> None:
    """通知 Windows 更新服务重读设置（失败不影响结果）。"""
    try:
        subprocess.run(
            ["UsoClient.exe", "RefreshSettings"],
            capture_output=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _sync_settings_app() -> None:
    """让系统「设置」程序立刻显示新的暂停状态。

    实测（Windows 11 22H2，内部版本 22621.4317）：
    注册表写对了、更新服务也通知过了，但「设置 → Windows 更新」页面
    依然显示旧日期。原因是「设置」程序只在启动那一刻读一次注册表，
    之后一直用内存里的缓存，不会自己刷新 —— 手动改注册表能成，
    只是因为那时「设置」窗口通常是关着的。

    所以这里重启一次「设置」程序，再把它打开到 Windows 更新页。
    """
    killed = False
    try:
        done = subprocess.run(
            ["taskkill.exe", "/F", "/IM", SETTINGS_PROCESS],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        killed = done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        pass

    if killed:
        time.sleep(1.2)

    # 提权进程没法直接把 UWP 设置页拉起来，交给资源管理器中转
    try:
        subprocess.Popen(["explorer.exe", SETTINGS_URI])
    except (OSError, subprocess.SubprocessError):
        pass


def _apply_and_sync() -> None:
    """写注册表 → 通知更新服务 → 重启「设置」程序。"""
    _refresh_update_service()
    _sync_settings_app()


def apply_pause() -> dict:
    """一键修改：把 Windows 更新暂停 PAUSE_DAYS 天。"""
    total_days = PAUSE_DAYS
    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc + timedelta(days=total_days)

    utc_now_text = now_utc.strftime(UX_TIME_FMT)
    utc_end_text = end_utc.strftime(UX_TIME_FMT)
    # 实测：Windows 自己写这两个日期字段时用的是 **UTC**（只是把 T/Z 换成空格），
    # 不是本地时间。写成本地时间虽然也能用，但和系统的写法不一致。
    policy_now_text = now_utc.strftime(POLICY_TIME_FMT)

    try:
        _backup_once()

        with winreg.CreateKeyEx(HKEY, UX_PATH, 0, winreg.KEY_WRITE) as key:
            for name in ("PauseFeatureUpdatesStartTime",
                         "PauseQualityUpdatesStartTime",
                         "PauseUpdatesStartTime"):
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, utc_now_text)
            for name in ("PauseFeatureUpdatesEndTime",
                         "PauseQualityUpdatesEndTime",
                         "PauseUpdatesExpiryTime"):
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, utc_end_text)
            winreg.SetValueEx(key, UX_MAX_DAYS_VALUE, 0, winreg.REG_DWORD, total_days)

        with winreg.CreateKeyEx(HKEY, POLICY_PATH, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "PausedFeatureStatus", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "PausedQualityStatus", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "PausedFeatureDate", 0, winreg.REG_SZ, policy_now_text)
            winreg.SetValueEx(key, "PausedQualityDate", 0, winreg.REG_SZ, policy_now_text)

    except PermissionError:
        return {"ok": False,
                "message": "权限不足：请右键以【管理员身份运行】本程序后重试。"}
    except FileNotFoundError as exc:
        return {"ok": False, "message": f"注册表位置不存在：{exc}"}
    except OSError as exc:
        return {"ok": False, "message": f"写入注册表失败：{exc}"}

    _apply_and_sync()

    local_end = end_utc.astimezone().strftime("%Y-%m-%d")
    return {
        "ok": True,
        "message": (f"设置成功：已暂停 {total_days:,} 天"
                    f"（约 {total_days / DAYS_PER_YEAR:.1f} 年），截止 {local_end}。"
                    f"\n系统「设置 → Windows 更新」已自动打开并刷新。"),
    }


def reset_pause() -> dict:
    """一键还原：清除全部暂停相关注册表项，恢复系统默认。"""
    try:
        _backup_once()

        with winreg.CreateKeyEx(HKEY, UX_PATH, 0, winreg.KEY_WRITE) as key:
            for name in UX_TIME_VALUES + (UX_MAX_DAYS_VALUE,):
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass

        with winreg.CreateKeyEx(HKEY, POLICY_PATH, 0, winreg.KEY_WRITE) as key:
            for name in POLICY_STATUS_VALUES:
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 0)
            for name in POLICY_DATE_VALUES:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass

    except PermissionError:
        return {"ok": False,
                "message": "权限不足：请右键以【管理员身份运行】本程序后重试。"}
    except OSError as exc:
        return {"ok": False, "message": f"清除注册表项失败：{exc}"}

    _apply_and_sync()
    return {"ok": True,
            "message": ("已还原：暂停设置已全部清除，Windows 更新恢复系统默认状态。"
                        "\n系统「设置 → Windows 更新」已自动打开并刷新。")}


def get_status() -> dict:
    """读取真实状态，供界面显示。"""
    status = {
        "admin": _is_admin(),
        "paused": False,
        "summary": "当前未暂停，系统默认状态（最长可暂停 35 天）",
    }

    expiry = None
    max_days = None
    try:
        with winreg.OpenKey(HKEY, UX_PATH, 0, winreg.KEY_READ) as key:
            try:
                expiry, _ = winreg.QueryValueEx(key, "PauseUpdatesExpiryTime")
            except FileNotFoundError:
                expiry = None
            try:
                max_days, _ = winreg.QueryValueEx(key, UX_MAX_DAYS_VALUE)
            except FileNotFoundError:
                max_days = None
    except FileNotFoundError:
        status["summary"] = "未找到 Windows 更新设置项（可能不是 Windows 系统）"

    expiry_dt = _parse_ux_time(expiry)
    if expiry_dt is not None:
        local_end = expiry_dt.astimezone()
        remaining = expiry_dt - datetime.now(timezone.utc)
        if remaining.total_seconds() > 0:
            status["paused"] = True
            status["summary"] = (f"更新已暂停，至 {local_end.strftime('%Y-%m-%d')}"
                                 f"（剩余约 {remaining.days:,} 天）")
        else:
            status["summary"] = (f"上次暂停已于 {local_end.strftime('%Y-%m-%d')} 到期，"
                                 f"当前未暂停")

    if max_days:
        status["summary"] += f"　已放宽上限：{max_days:,} 天"
    return status


# --------------------------------------------------------------------------- #
# Win32 界面
# --------------------------------------------------------------------------- #
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 消息
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_PAINT = 0x000F
WM_COMMAND = 0x0111
WM_DRAWITEM = 0x002B
WM_SETFONT = 0x0030

# 窗口 / 控件样式
WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CLIPCHILDREN = 0x02000000
WS_EX_APPWINDOW = 0x00040000
SS_LEFT = 0x00000000
BS_OWNERDRAW = 0x0000000B

# 绘制
ODS_SELECTED = 0x0001
ODS_DISABLED = 0x0004
ODS_FOCUS = 0x0010
DT_CENTER = 0x0001
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
DT_LEFT = 0x0000
DT_WORDBREAK = 0x0010
TRANSPARENT = 1
DEFAULT_CHARSET = 1
OUT_TT_PRECIS = 5
CLIP_DEFAULT_PRECIS = 0
CLEARTYPE_QUALITY = 5
DEFAULT_PITCH = 0
FW_NORMAL = 400
FW_BOLD = 700
SW_HIDE = 0
SW_SHOW = 5

ID_APPLY = 1001
ID_RESET = 1002

# 图标资源（PyInstaller 把 app.ico 以资源 ID 1 嵌进 exe）
IMAGE_ICON = 1
LR_SHARED = 0x8000
APP_ICON_ID = 1

# 配色
CLR_PAGE = "#eef1f5"
CLR_CARD = "#ffffff"
CLR_STATUS_BG = "#f5f6f8"
CLR_TITLE = "#1f2937"
CLR_MUTED = "#6b7280"
CLR_BODY = "#111827"
CLR_HINT = "#9ca3af"
CLR_BLUE = "#2563eb"
CLR_BLUE_DOWN = "#1d4ed8"
CLR_BLUE_DIS = "#93b4f5"
CLR_WHITE = "#ffffff"
CLR_RED = "#b91c1c"
CLR_RED_DOWN = "#fdecec"
CLR_BORDER = "#d1d5db"
CLR_OK = "#0f7b52"
CLR_ERR = "#b91c1c"


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [
        ("CtlType", wintypes.UINT),
        ("CtlID", wintypes.UINT),
        ("itemID", wintypes.UINT),
        ("itemAction", wintypes.UINT),
        ("itemState", wintypes.UINT),
        ("hwndItem", wintypes.HWND),
        ("hDC", wintypes.HDC),
        ("rcItem", wintypes.RECT),
        ("itemData", ctypes.c_void_p),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM)

# --- 显式声明签名（64 位下必须，否则指针会被截断导致崩溃） ---
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DefWindowProcW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.AdjustWindowRectEx.argtypes = [
    ctypes.POINTER(wintypes.RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.SendMessageW.restype = ctypes.c_longlong
user32.SendMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
user32.DrawTextW.argtypes = [
    wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
    ctypes.POINTER(wintypes.RECT), wintypes.UINT]
user32.FillRect.argtypes = [
    wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
# 图标：第二参数是 MAKEINTRESOURCE(整数) 与字符串指针的联合体，
# 必须声明成 c_void_p，写 LPCWSTR 会报参数类型错误。
user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadImageW.restype = wintypes.HICON
user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE, ctypes.c_void_p, wintypes.UINT,
    ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.DrawFocusRect.argtypes = [
    wintypes.HDC, ctypes.POINTER(wintypes.RECT)]
user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.SetProcessDPIAware.restype = wintypes.BOOL

gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreatePen.restype = wintypes.HPEN
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
gdi32.CreateFontW.restype = wintypes.HFONT
gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.LPCWSTR]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetTextColor.restype = wintypes.COLORREF
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.Rectangle.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]

# --- 其余用到的 API：64 位下必须显式声明，否则句柄会被截断成 32 位 ---
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
gdi32.GetStockObject.restype = wintypes.HGDIOBJ
gdi32.GetStockObject.argtypes = [ctypes.c_int]
user32.MoveWindow.restype = wintypes.BOOL
user32.MoveWindow.argtypes = [
    wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.BOOL]
user32.GetClientRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.InvalidateRect.restype = wintypes.BOOL
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
user32.UpdateWindow.restype = wintypes.BOOL
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.PostQuitMessage.restype = None
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.TranslateMessage.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.c_longlong
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]


def _colorref(hex_color: str) -> int:
    """'#RRGGBB' -> Win32 COLORREF (0x00BBGGRR)"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def _scale_factor() -> float:
    """屏幕 DPI 相对 96 的缩放比。"""
    try:
        hdc = user32.GetDC(None)
        dpi = gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        user32.ReleaseDC(None, hdc)
        return dpi / 96.0 if dpi else 1.0
    except OSError:
        return 1.0


class App:
    """纯 Win32 界面。"""

    CARD_W = 660          # 客户区宽（逻辑像素）
    PAD = 28

    def __init__(self) -> None:
        try:
            user32.SetProcessDPIAware()
        except OSError:
            pass

        self.s = _scale_factor()
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.hwnd = None
        self.ctl = {}
        self.fonts = {}
        self.brushes = {}
        self.busy = False
        self._wndproc_ref = None
        self._pending = None

    # ---------------- 尺寸辅助 ----------------
    def px(self, value: int) -> int:
        return int(value * self.s)

    # ---------------- 创建 ----------------
    def _load_icon(self, size: int):
        """从自身 exe 的资源里取图标（打包后 app.ico 以 ID 1 嵌入）。

        以 python main.py 方式裸跑时取不到，返回 None，窗口就用系统默认图标。
        """
        try:
            h = user32.LoadImageW(self.hinstance, ctypes.c_void_p(APP_ICON_ID),
                                  IMAGE_ICON, size, size, LR_SHARED)
            if h:
                return h
            return user32.LoadIconW(self.hinstance,
                                    ctypes.c_void_p(APP_ICON_ID)) or None
        except OSError:
            return None

    def build(self) -> None:
        self._create_brushes()
        self._create_fonts()

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        self._wndproc_ref = WNDPROC(self._wndproc)
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = self.hinstance
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))  # IDC_ARROW
        wc.hbrBackground = self.brushes["page"]
        wc.lpszClassName = "UpdatePauseToolWnd"
        wc.hIcon = self._load_icon(self.px(32))      # Alt+Tab / 任务栏
        wc.hIconSm = self._load_icon(self.px(16))    # 标题栏左上角
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            raise OSError(f"RegisterClassExW 失败: {ctypes.get_last_error()}")

        style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPCHILDREN
        rect = wintypes.RECT(0, 0, self.px(self.CARD_W), self.px(self._client_height()))
        user32.AdjustWindowRectEx(ctypes.byref(rect), style, False, 0)
        win_w = rect.right - rect.left
        win_h = rect.bottom - rect.top

        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = max(0, (screen_w - win_w) // 2)
        y = max(0, (screen_h - win_h) // 3)

        self.hwnd = user32.CreateWindowExW(
            WS_EX_APPWINDOW, "UpdatePauseToolWnd", APP_TITLE, style,
            x, y, win_w, win_h, None, None, self.hinstance, None)
        if not self.hwnd:
            raise OSError(f"CreateWindowExW 失败: {ctypes.get_last_error()}")

        self._create_controls()
        self._layout_controls()
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.UpdateWindow(self.hwnd)

    def _client_height(self) -> int:
        return 424

    def _create_brushes(self) -> None:
        for name, color in (
            ("page", CLR_PAGE), ("card", CLR_CARD), ("status", CLR_STATUS_BG),
        ):
            self.brushes[name] = gdi32.CreateSolidBrush(_colorref(color))

    def _create_fonts(self) -> None:
        dpi = int(96 * self.s)
        for name, (pt, bold) in (
            ("title", (15, True)), ("subtitle", (10, False)),
            ("btn", (13, True)), ("btn2", (11, False)),
            ("small", (9, False)), ("body", (10, False)),
        ):
            height = -int(pt * dpi / 72)
            self.fonts[name] = gdi32.CreateFontW(
                height, 0, 0, 0, FW_BOLD if bold else FW_NORMAL,
                0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY, DEFAULT_PITCH, "Microsoft YaHei UI")

    def _static(self, key: str, text: str, font: str) -> None:
        h = user32.CreateWindowExW(
            0, "STATIC", text, WS_CHILD | WS_VISIBLE | SS_LEFT,
            0, 0, 10, 10, self.hwnd, None, self.hinstance, None)
        user32.SendMessageW(h, WM_SETFONT, self.fonts[font], True)
        self.ctl[key] = h

    def _create_controls(self) -> None:
        self._static("title", "Windows 更新超长暂停", "title")
        self._static(
            "subtitle",
            f"点一下，把系统更新暂停 {PAUSE_DAYS:,} 天"
            f"（约 {PAUSE_DAYS // DAYS_PER_YEAR} 年）", "subtitle")
        self._static("status_title", "当前状态", "small")
        self._static("status", "正在读取…", "body")
        self._static(
            "tip",
            "修改后重新打开系统「设置→Windows更新」，即可看到暂停日期。\n"
            "暂停日期点开可见暂停周数从5周变成了1428周", "small")

        self.ctl["apply"] = user32.CreateWindowExW(
            0, "BUTTON", f"　一键修改　暂停更新 {PAUSE_DAYS:,} 天　",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            0, 0, 10, 10, self.hwnd, ID_APPLY, self.hinstance, None)
        self.ctl["reset"] = user32.CreateWindowExW(
            0, "BUTTON", "一键还原（恢复系统默认）",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            0, 0, 10, 10, self.hwnd, ID_RESET, self.hinstance, None)

    # ---------------- 布局 ----------------
    def _layout_controls(self) -> None:
        pad = self.px(self.PAD)
        width = self.px(self.CARD_W) - pad * 2
        y = self.px(24)

        self._place("title", pad, y, width, self.px(32)); y += self.px(38)
        self._place("subtitle", pad, y, width, self.px(24)); y += self.px(42)
        self._place("apply", pad, y, width, self.px(68)); y += self.px(80)
        self._place("reset", pad, y, width, self.px(48)); y += self.px(64)
        self._place("status_title", pad, y, width, self.px(20)); y += self.px(24)
        self._place("status", pad, y, width, self.px(72)); y += self.px(78)
        self._place("tip", pad, y, width, self.px(48))

    def _place(self, key: str, x: int, y: int, w: int, h: int) -> None:
        user32.MoveWindow(self.ctl[key], x, y, w, h, True)

    # ---------------- 交互 ----------------
    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        for key in ("apply", "reset"):
            user32.EnableWindow(self.ctl[key], not busy)
            user32.InvalidateRect(self.ctl[key], None, True)

    def set_status(self, text: str, color: str = CLR_BODY) -> None:
        wrapped = self._wrap(text, 72)
        user32.SetWindowTextW(self.ctl["status"], wrapped)
        self._status_color = color
        user32.InvalidateRect(self.ctl["status"], None, True)
        self._layout_controls()

    @staticmethod
    def _units(text: str):
        """把一行拆成不可再拆的最小单元。

        中文按单字拆，英文/数字/半角符号按连续一段拆 ——
        否则会出现 "10,000" 被从中间劈成 "10,0" / "00" 的难看折行。
        """
        out = []
        buf = ""
        for ch in text:
            if ch.isascii() and not ch.isspace():
                buf += ch
                continue
            if buf:
                out.append(buf)
                buf = ""
            if ch == " ":
                if out:
                    out[-1] += " "      # 空格跟在上一段后面，行首不留空格
            else:
                out.append(ch)
        if buf:
            out.append(buf)
        return out

    @classmethod
    def _wrap(cls, text: str, per_line: int) -> str:
        """按"半角宽度"折行：中文算 2，英文数字算 1。

        STATIC 控件不会自动折行，必须自己插 \\n；
        按显示宽度算才能保证中英混排时不会超出控件宽度被切掉。
        """
        lines = []
        for raw in text.split("\n"):
            units = cls._units(raw)
            line = ""
            width = 0
            for unit in units:
                w = 2 if any(ord(c) > 0x2E80 for c in unit) else len(unit)
                if width and width + w > per_line:
                    lines.append(line.rstrip())
                    line, width = "", 0
                line += unit
                width += w
            lines.append(line.rstrip())
        return "\n".join(lines)

    def draw_button(self, dis: DRAWITEMSTRUCT) -> None:
        ctl_id = dis.CtlID
        rc = dis.rcItem
        rect = wintypes.RECT(rc.left, rc.top, rc.right, rc.bottom)

        if ctl_id == ID_APPLY:
            bg, fg, border = CLR_BLUE, CLR_WHITE, None
        else:
            bg, fg, border = CLR_CARD, CLR_RED, CLR_RED

        disabled = bool(dis.itemState & ODS_DISABLED)
        if disabled:
            bg = CLR_BLUE_DIS if ctl_id == ID_APPLY else CLR_CARD
            fg = CLR_WHITE if ctl_id == ID_APPLY else "#e5a3a3"
        elif dis.itemState & ODS_SELECTED:
            bg = CLR_BLUE_DOWN if ctl_id == ID_APPLY else CLR_RED_DOWN

        brush = gdi32.CreateSolidBrush(_colorref(bg))
        user32.FillRect(dis.hDC, ctypes.byref(rect), brush)
        gdi32.DeleteObject(brush)

        if border:
            pen = gdi32.CreatePen(0, max(1, self.px(1)), _colorref(border))
            old_pen = gdi32.SelectObject(dis.hDC, pen)
            old_brush = gdi32.SelectObject(dis.hDC, gdi32.GetStockObject(5))
            gdi32.Rectangle(dis.hDC, rect.left, rect.top, rect.right, rect.bottom)
            gdi32.SelectObject(dis.hDC, old_brush)
            gdi32.SelectObject(dis.hDC, old_pen)
            gdi32.DeleteObject(pen)

        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(dis.hwndItem, buf, 256)
        font = self.fonts["btn"] if ctl_id == ID_APPLY else self.fonts["btn2"]
        old_font = gdi32.SelectObject(dis.hDC, font)
        gdi32.SetBkMode(dis.hDC, TRANSPARENT)
        gdi32.SetTextColor(dis.hDC, _colorref(fg))
        user32.DrawTextW(dis.hDC, buf.value, -1, ctypes.byref(rect),
                         DT_CENTER | DT_VCENTER | DT_SINGLELINE)
        gdi32.SelectObject(dis.hDC, old_font)

        if dis.itemState & ODS_FOCUS:
            user32.DrawFocusRect(dis.hDC, ctypes.byref(rect))

    def draw_static(self, hdc, hwnd_ctl) -> int:
        """让 STATIC 透明绘制，文字颜色按要求变化。"""
        color = getattr(self, "_status_color", CLR_BODY) \
            if hwnd_ctl == self.ctl.get("status") else None
        if color is None:
            if hwnd_ctl == self.ctl.get("title"):
                color = CLR_TITLE
            elif hwnd_ctl == self.ctl.get("subtitle"):
                color = CLR_MUTED
            elif hwnd_ctl == self.ctl.get("tip"):
                color = CLR_HINT
            else:
                color = CLR_MUTED
        gdi32.SetBkMode(hdc, TRANSPARENT)
        gdi32.SetTextColor(hdc, _colorref(color))
        return self.brushes["card"]

    def _paint_self(self) -> None:
        """用白色卡片填充客户区（避开内边距区域）。"""
        hdc = user32.GetDC(self.hwnd)
        rect = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        brush = gdi32.CreateSolidBrush(_colorref(CLR_CARD))
        user32.FillRect(hdc, ctypes.byref(rect), brush)
        gdi32.DeleteObject(brush)
        user32.ReleaseDC(self.hwnd, hdc)

    # ---------------- 消息处理 ----------------
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_COMMAND:
            ctl_id = wparam & 0xFFFF
            if ctl_id == ID_APPLY:
                self._start(apply_pause, "正在写入系统设置…")
                return 0
            if ctl_id == ID_RESET:
                self._start(reset_pause, "正在清除暂停设置…")
                return 0
        elif msg == WM_DRAWITEM:
            dis = ctypes.cast(lparam, ctypes.POINTER(DRAWITEMSTRUCT)).contents
            if dis.CtlID in (ID_APPLY, ID_RESET):
                self.draw_button(dis)
                return 1
        elif msg == 0x0138:  # WM_CTLCOLORSTATIC
            brush = self.draw_static(wparam, lparam)
            if brush:
                return brush
        elif msg == 0x0014:  # WM_ERASEBKGND
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            user32.FillRect(wparam, ctypes.byref(rect), self.brushes["card"])
            return 1
        elif msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---------------- 业务 ----------------
    def _start(self, func, pending_text: str) -> None:
        if self.busy:
            return
        self.set_busy(True)
        self.set_status(pending_text, CLR_MUTED)

        def worker() -> None:
            try:
                res = func()
            except Exception as exc:  # 兜底，避免子线程异常导致界面无反馈
                res = {"ok": False, "message": f"操作失败：{exc}"}
            self._pending = res
            user32.PostMessageW(self.hwnd, 0x8001, 0, 0)  # 自定义消息，回主线程

        threading.Thread(target=worker, daemon=True).start()

    def _handle_custom(self) -> None:
        res = self._pending
        self._pending = None
        if not res:
            return
        self.set_busy(False)
        self.set_status(res.get("message", ""),
                        CLR_OK if res.get("ok") else CLR_ERR)
        self.refresh_status()

    def refresh_status(self) -> None:
        def worker() -> None:
            try:
                st = get_status()
            except Exception as exc:
                st = {"admin": _is_admin(), "paused": False,
                      "summary": f"状态读取失败：{exc}"}
            parts = []
            if not st.get("admin", True):
                parts.append("⚠ 当前不是管理员权限运行，无法写入系统设置。")
            parts.append(st.get("summary", ""))
            self._pending = {"ok": True, "message": "\n".join(parts),
                             "_refresh_only": True}
            user32.PostMessageW(self.hwnd, 0x8002, 0, 0)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_refresh(self) -> None:
        res = self._pending
        self._pending = None
        if not res:
            return
        text = res.get("message", "")
        color = CLR_OK if "已暂停" in text else CLR_BODY
        if "⚠" in text:
            color = CLR_ERR
        self.set_status(text, color)


def main() -> None:
    app = App()
    app.build()
    app.refresh_status()

    msg = wintypes.MSG()
    while True:
        ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret <= 0:
            break
        if msg.message == 0x8001:
            app._handle_custom()
            continue
        if msg.message == 0x8002:
            app._handle_refresh()
            continue
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()
