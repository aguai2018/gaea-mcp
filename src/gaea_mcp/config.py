"""
Locate a Gaea 2 installation and read its settings.

Everything here was validated on Gaea 2.3.0.1 (Enterprise Floating) on Windows.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

IS_WINDOWS = sys.platform == "win32"

# Places Gaea installs to, in the order we prefer to probe them.
_INSTALL_HINTS = [
    r"D:\Progame Files\Gaea 2",
    r"C:\Program Files\Gaea 2",
    r"C:\Program Files\QuadSpinner\Gaea 2",
    r"D:\Program Files\Gaea 2",
    r"E:\Program Files\Gaea 2",
]


@dataclass
class GaeaInstall:
    root: str
    exe: str
    swarm: str
    data_dir: str
    version: str = "unknown"
    edition: str = "unknown"
    settings: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ---------------------------------------------------------------- paths
    @property
    def logs_dir(self) -> str:
        return os.path.join(self.data_dir, "Logs")

    @property
    def builds_dir(self) -> str:
        loc = (self.settings or {}).get("Locations") or {}
        return loc.get("Builds") or os.path.join(
            os.path.expanduser("~"), "Documents", "Gaea", "Builds")

    @property
    def caches_dir(self) -> str:
        loc = (self.settings or {}).get("Locations") or {}
        return loc.get("Caches") or os.path.join(
            os.path.expanduser("~"), "Documents", "Gaea", "Caches")

    # ------------------------------------------------------------- reports
    def newest_swarm_log(self, after_mtime: float | None = None) -> str | None:
        if not os.path.isdir(self.logs_dir):
            return None
        cands = []
        for p in glob.glob(os.path.join(self.logs_dir, "*SWARM*.txt")):
            if after_mtime is not None and os.path.getmtime(p) < after_mtime:
                continue
            cands.append(p)
        return max(cands, key=os.path.getmtime) if cands else None

    def newest_session_log(self) -> str | None:
        if not os.path.isdir(self.logs_dir):
            return None
        cands = [p for p in glob.glob(os.path.join(self.logs_dir, "*.txt"))
                 if "SWARM" not in os.path.basename(p)
                 and "CRASH" not in os.path.basename(p)]
        return max(cands, key=os.path.getmtime) if cands else None


def _exe_version(path: str) -> str:
    """Read the file version off a Windows PE without extra dependencies."""
    try:
        import ctypes
        from ctypes import wintypes

        ver = ctypes.WinDLL("version")
        GetFileVersionInfoSizeW = ver.GetFileVersionInfoSizeW
        GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR,
                                            ctypes.POINTER(wintypes.DWORD)]
        GetFileVersionInfoSizeW.restype = wintypes.DWORD
        size = GetFileVersionInfoSizeW(path, None)
        if not size:
            return "unknown"
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return "unknown"
        val = ctypes.c_void_p()
        length = wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(val),
                                  ctypes.byref(length)):
            return "unknown"
        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [("dwSignature", wintypes.DWORD),
                        ("dwStrucVersion", wintypes.DWORD),
                        ("dwFileVersionMS", wintypes.DWORD),
                        ("dwFileVersionLS", wintypes.DWORD),
                        ("dwProductVersionMS", wintypes.DWORD),
                        ("dwProductVersionLS", wintypes.DWORD),
                        ("dwFileFlagsMask", wintypes.DWORD),
                        ("dwFileFlags", wintypes.DWORD),
                        ("dwFileOS", wintypes.DWORD),
                        ("dwFileType", wintypes.DWORD),
                        ("dwFileSubtype", wintypes.DWORD),
                        ("dwFileDateMS", wintypes.DWORD),
                        ("dwFileDateLS", wintypes.DWORD)]

        info = ctypes.cast(val, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        ms, ls = info.dwFileVersionMS, info.dwFileVersionLS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return "unknown"


def find_gaea(explicit_root: str | None = None) -> GaeaInstall | None:
    """Return a GaeaInstall, or None when Gaea cannot be located."""
    roots: list[str] = []
    if explicit_root:
        roots.append(explicit_root)
    env = os.environ.get("GAEA_ROOT") or os.environ.get("GAEA2_PATH")
    if env:
        # GAEA2_PATH is documented as the *exe* in older tooling
        roots.append(os.path.dirname(env) if env.lower().endswith(".exe") else env)
    roots.extend(_INSTALL_HINTS)
    if IS_WINDOWS:
        for drive in "CDEFGH":
            roots += glob.glob(rf"{drive}:\*Gaea*")

    seen = set()
    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        exe = os.path.join(root, "Gaea.exe")
        swarm = os.path.join(root, "Gaea.Swarm.exe")
        if not os.path.isfile(exe):
            continue
        data = os.path.join(root, "Data")
        inst = GaeaInstall(root=root, exe=exe, swarm=swarm, data_dir=data)
        inst.version = _exe_version(exe)

        # edition marker: G2F = Enterprise (Floating), etc.
        ed = os.path.join(data, "edition.dat")
        if os.path.isfile(ed):
            inst.edition = open(ed, encoding="utf-8", errors="replace").read().strip()

        prefs = os.path.join(data, "Settings", "Preferences.options")
        if os.path.isfile(prefs):
            try:
                inst.settings = json.loads(open(prefs, encoding="utf-8-sig").read())
            except Exception as e:
                inst.problems.append(f"could not parse Preferences.options: {e}")

        # things that are known to bite
        if not os.path.isfile(swarm):
            inst.problems.append("Gaea.Swarm.exe missing - builds impossible")
        if not os.path.isdir(inst.caches_dir):
            inst.problems.append(
                f"cache dir does not exist: {inst.caches_dir} (Gaea creates it)")
        if not os.path.isdir(os.path.join(root, "Data", "Logs")):
            inst.problems.append("Data\\Logs missing - cannot read build results")
        return inst
    return None


def running_gaea_pids() -> list[int]:
    """PIDs of running Gaea processes, without extra dependencies."""
    if not IS_WINDOWS:
        return []
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Gaea.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        m = re.match(r'"[^"]+","(\d+)"', line.strip())
        if m:
            pids.append(int(m.group(1)))
    return pids


def describe() -> dict[str, Any]:
    """Full environment report - this is what the AI should call first."""
    inst = find_gaea()
    if inst is None:
        return {
            "found": False,
            "error": "Gaea 2 not found. Set GAEA_ROOT to the install folder "
                     "(the one containing Gaea.exe).",
            "probed": _INSTALL_HINTS,
        }
    d = inst.to_dict()
    d["found"] = True
    d["builds_dir"] = inst.builds_dir
    d["caches_dir"] = inst.caches_dir
    d["logs_dir"] = inst.logs_dir
    d["running_pids"] = running_gaea_pids()
    d["gui_running"] = bool(d["running_pids"])
    d["has_dotnet_sdk"] = _has("dotnet")
    d["python"] = sys.version.split()[0]
    return d


def _has(exe: str) -> bool:
    try:
        subprocess.run([exe, "--version"], capture_output=True, timeout=60)
        return True
    except Exception:
        return False
