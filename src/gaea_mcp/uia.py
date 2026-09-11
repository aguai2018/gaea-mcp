"""
UI Automation bridge for driving the Gaea window by control name.

Why this exists: Gaea's own UI must perform the build. `Gaea.Swarm.exe`
invoked directly from a shell dies with

    System.IO.IOException: 句柄无效  (invalid handle)

whenever the GUI holds the floating licence - and on a floating licence the
GUI usually does. The working sequence is

    Gaea GUI  ->  Build Settings  ->  Execute Build
              ->  confirmation box  ->  "Start Build"
                                    or "Close Gaea and Build"

"Close Gaea and Build" shuts the GUI down (releasing the licence) and then runs
Swarm to completion; "Start Build" keeps the GUI alive and runs Swarm alongside
it. Both work. Invoking the buttons by their automation Name is reliable;
clicking by pixel coordinate is not, because the app scales with DPI and the
confirmation dialog is a separate window.

This module builds and drives a tiny C# helper (`uia/uia.cs`) that uses
System.Windows.Automation with an *auto-detected* Gaea PID. Tools that
hard-code a PID stop working the moment Gaea restarts.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
UIA_SRC_DIR = os.path.join(HERE, "uia")

# Automation names / ids that matter, all confirmed on 2.3.0.1
BTN_BUILD = "Execute Build"          # Build Settings dialog
BTN_BUILD_ID = "btnBuild"
BTN_CLI = "Copy Command Line"
BTN_CLOSE_BUILD = "Close Gaea and Build"   # confirmation dialog
BTN_START_BUILD = "Start Build"            # confirmation dialog
CONFIRM_WINDOW = "Build and Export?"


class UiaError(RuntimeError):
    pass


def _dotnet() -> str | None:
    return shutil.which("dotnet")


@dataclass
class Uia:
    """Compiled helper + a thin command wrapper."""

    exe: str
    timeout: int = 180

    # --------------------------------------------------------------- build
    @classmethod
    def ensure(cls, workdir: str | None = None) -> "Uia":
        """Compile the helper if needed and return a handle."""
        if not sys.platform == "win32":
            raise UiaError("UI Automation is Windows-only")
        build_dir = workdir or os.path.join(UIA_SRC_DIR, "bin")
        exe = os.path.join(build_dir, "uia.exe")
        if os.path.isfile(exe):
            return cls(exe)
        dn = _dotnet()
        if not dn:
            raise UiaError(
                "the .NET SDK is required to build the UI Automation helper.\n"
                "Install .NET 8 SDK (https://dot.net) or pre-build uia.exe and "
                f"place it at {exe}")
        csproj = os.path.join(UIA_SRC_DIR, "uia.csproj")
        cs = os.path.join(UIA_SRC_DIR, "uia.cs")
        if not (os.path.isfile(csproj) and os.path.isfile(cs)):
            raise UiaError(f"helper sources missing under {UIA_SRC_DIR}")
        r = subprocess.run([dn, "build", "-c", "Release", "-o", build_dir,
                            "--nologo", "-v", "q"],
                           cwd=UIA_SRC_DIR, capture_output=True, text=True,
                           timeout=900)
        if not os.path.isfile(exe):
            raise UiaError("failed to build the UI Automation helper:\n"
                           + (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:])
        return cls(exe)

    # -------------------------------------------------------------- invoke
    def run(self, *args: str) -> str:
        # Capture bytes and decode explicitly: text=True uses the process
        # locale (GBK here) and blows up on Gaea's non-ASCII window titles.
        r = subprocess.run([self.exe] + list(args), capture_output=True,
                           timeout=self.timeout)
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        return (out + err).strip()

    def pid(self) -> int | None:
        out = self.run("pid")
        m = re.search(r"(\d+)", out)
        return int(m.group(1)) if m and int(m.group(1)) > 0 else None

    def alive(self) -> bool:
        return self.pid() is not None

    def find(self, name: str) -> list[str]:
        out = self.run("findc", name)
        return [l.strip() for l in out.splitlines() if "win=" in l]

    def has(self, name: str) -> bool:
        return bool(self.find(name))

    def invoke(self, name: str) -> str:
        return self.run("invoke", name)

    def dump(self, window_filter: str | None = None) -> str:
        return self.run("dump", window_filter) if window_filter else self.run("dump")

    def wait_for(self, name: str, timeout: float = 30.0,
                 poll: float = 1.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self.has(name):
                return True
            time.sleep(poll)
        return False


# --------------------------------------------------------------- Win32 odds
def activate_window(substr: str, exclude: tuple[str, ...] = ()) -> bool:
    """Bring a window whose title contains `substr` to the foreground."""
    import ctypes
    from ctypes import wintypes

    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)

    target = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not u.IsWindowVisible(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        t = buf.value
        if substr.lower() in t.lower() and not any(
                e.lower() in t.lower() for e in exclude):
            target.append(hwnd)
        return True

    u.EnumWindows(cb, 0)
    if not target:
        return False
    hwnd = target[0]

    def is_fg() -> bool:
        return u.GetForegroundWindow() == hwnd

    u.ShowWindow(hwnd, 9)          # SW_RESTORE
    u.BringWindowToTop(hwnd)
    if is_fg():
        return True

    fg = u.GetForegroundWindow()
    tid_fg = u.GetWindowThreadProcessId(fg, None)
    tid_self = k.GetCurrentThreadId()
    attached = False
    try:
        if tid_fg and tid_fg != tid_self:
            attached = bool(u.AttachThreadInput(tid_fg, tid_self, True))
        u.SetForegroundWindow(hwnd)
        u.SetFocus(hwnd)
    finally:
        if attached:
            u.AttachThreadInput(tid_fg, tid_self, False)
    time.sleep(0.4)
    if is_fg():
        return True

    # Windows refuses foreground changes from a background process. Minimising
    # and restoring the target is the one trick that reliably works.
    u.ShowWindow(hwnd, 6)          # SW_MINIMIZE
    time.sleep(0.35)
    u.ShowWindow(hwnd, 9)          # SW_RESTORE
    u.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    return is_fg()


def send_keys(spec: str) -> None:
    """Send a chord such as 'CTRL B' or 'CTRL SHIFT B' to the foreground window."""
    import ctypes
    from ctypes import wintypes

    u = ctypes.WinDLL("user32", use_last_error=True)
    VK = {"CTRL": 0x11, "SHIFT": 0x10, "ALT": 0x12, "ENTER": 0x0D, "ESC": 0x1B,
          "TAB": 0x09, "SPACE": 0x20, "F3": 0x72, "F9": 0x78}

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 24)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    def ev(vk: int, up: bool):
        return INPUT(type=1, u=_U(ki=KEYBDINPUT(wVk=vk, wScan=0,
                                                dwFlags=2 if up else 0,
                                                time=0, dwExtraInfo=None)))

    vks = []
    for part in spec.upper().split():
        vks.append(VK.get(part, ord(part) if len(part) == 1 else 0))
    for v in vks:
        u.SendInput(1, ctypes.byref(ev(v, False)), ctypes.sizeof(INPUT))
        time.sleep(0.05)
    for v in reversed(vks):
        u.SendInput(1, ctypes.byref(ev(v, True)), ctypes.sizeof(INPUT))
        time.sleep(0.05)
