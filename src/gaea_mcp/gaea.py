"""
Orchestrate a real Gaea build: launch the GUI, load the project, trigger the
build through UI Automation, and collect the results.

The important, non-obvious sequencing (all empirically verified):

    Gaea.exe -Path <file>      CRASHES on this build. Never use it.
    Gaea.exe                   start clean, then File > Open via UI Automation
    Ctrl+B                     opens Build Settings
    invoke 'Execute Build'     raises the 'Build and Export?' confirmation
    invoke 'Start Build'       builds with the GUI alive
      or 'Close Gaea and Build'  shuts the GUI down first (faster, and the
                                 only way to build when one licence seat is
                                 shared between GUI and Swarm)

    Gaea.Swarm.exe run directly  -> 'IOException: 句柄无效' while the GUI holds
                                    the licence. This is why we never shell out
                                    to Swarm ourselves.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .config import GaeaInstall, find_gaea, running_gaea_pids
from .uia import BTN_BUILD, BTN_CLOSE_BUILD, BTN_START_BUILD, Uia, UiaError


@dataclass
class BuildResult:
    ok: bool
    stage: str
    message: str = ""
    report: dict[str, Any] | None = None
    report_path: str | None = None
    outputs: list[dict[str, Any]] = field(default_factory=list)
    log_warnings: list[str] = field(default_factory=list)
    log_errors: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "stage": self.stage, "message": self.message,
            "report": self.report, "report_path": self.report_path,
            "outputs": self.outputs, "warnings": self.log_warnings,
            "errors": self.log_errors, "seconds": round(self.seconds, 1),
        }


# --------------------------------------------------------------------- launch
def launch_gui(inst: GaeaInstall, wait: float = 45.0) -> bool:
    """Start Gaea with no project (passing -Path is known to crash)."""
    if running_gaea_pids():
        return True
    subprocess.Popen([inst.exe], cwd=inst.root)
    end = time.time() + wait
    while time.time() < end:
        time.sleep(2)
        if running_gaea_pids():
            time.sleep(6)      # let the window settle
            return True
    return False


def close_gui(timeout: float = 30.0) -> None:
    if not running_gaea_pids():
        return
    subprocess.run(["taskkill", "/IM", "Gaea.exe", "/T", "/F"],
                   capture_output=True, timeout=60)
    end = time.time() + timeout
    while time.time() < end and running_gaea_pids():
        time.sleep(1)


def uia_title(uia: "Uia") -> str:
    """The Gaea main-window title, e.g. 'Gaea - MyTerrain.terrain'."""
    out = uia.run("title").strip().splitlines()
    return out[-1].strip() if out else ""


def open_project(inst: GaeaInstall, project: str, uia: Uia,
                 wait: float = 25.0) -> tuple[bool, list[str]]:
    """Load a project through the GUI and report whether Gaea accepted it.

    Success is judged by the window title containing the project's file name -
    far more reliable than hoping the log was flushed - and by reading Gaea's
    session log for validation faults.
    """
    from .uia import activate_window, send_keys

    if not uia.alive():
        raise UiaError("Gaea is not running")

    project = os.path.abspath(project)
    base = os.path.basename(project)
    if not os.path.isfile(project):
        return False, [f"project does not exist: {project}"]

    log = inst.newest_session_log()
    mark = os.path.getsize(log) if log and os.path.isfile(log) else 0

    # Already showing the project? Then there is nothing to load.
    if base in uia_title(uia):
        return _read_verdict(inst, mark)

    opened = False
    last_err = ""
    for attempt in range(3):
        if not activate_window("Gaea -", exclude=("Swarm", "Diagnose")):
            last_err = ("could not bring the Gaea window to the foreground "
                        "(Windows refused the focus change)")
        time.sleep(1.0)
        send_keys("CTRL O")
        time.sleep(3.0)
        # a dirty document raises "Save terrain?" first
        if uia.has("Save"):
            send_keys("N")
            time.sleep(2.0)
            send_keys("CTRL O")
            time.sleep(3.0)
        if "nofiledialog" in uia.run("hasfiledialog"):
            # no dialog appeared; either it never opened or Gaea is busy
            if base in uia_title(uia):
                opened = True
                break
            last_err = last_err or "the Open dialog never appeared"
            time.sleep(1.5)
            continue
        uia.run("openpath", project)
        time.sleep(wait)
        title = uia_title(uia)
        if base in title:
            opened = True
            break
        last_err = f"window title after opening was {title!r}"

    if not opened:
        return False, [f"could not load {base} into Gaea: {last_err}"]
    return _read_verdict(inst, mark)


def _read_verdict(inst: GaeaInstall, mark: int) -> tuple[bool, list[str]]:
    """Read Gaea's session log from `mark` onward and extract validation faults."""
    problems: list[str] = []
    log = inst.newest_session_log()
    if not (log and os.path.isfile(log)):
        return False, [f"no Gaea session log found in {inst.logs_dir}"]
    try:
        with open(log, encoding="utf-8", errors="replace") as fh:
            tail = fh.read()[mark:]
    except OSError as e:
        return False, [f"could not read Gaea's session log ({log}): {e}"]
    for line in tail.splitlines():
        s = line.strip()
        if ("did not validate" in s or "reported:" in s
                or " ERR " in s or "failed:" in s
                or "is old. Attempting to migrate" in s):
            problems.append(s)
    return (not problems), problems


def _type_path(path: str) -> None:
    """Type a path into the already-focused file dialog and confirm."""
    import ctypes
    from ctypes import wintypes

    u = ctypes.WinDLL("user32", use_last_error=True)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 24)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    for ch in path:
        code = ord(ch)
        for up in (False, True):
            inp = INPUT(type=1, u=_U(ki=KEYBDINPUT(
                wVk=0, wScan=code,
                dwFlags=0x0004 | (0x0002 if up else 0), time=0,
                dwExtraInfo=None)))
            u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.008)
    time.sleep(0.8)
    send_keys("ENTER")


# ---------------------------------------------------------------------- build
def run_build(project: str, mode: str = "close_gui",
              resolution: int | None = None,
              wait_seconds: float = 900.0,
              inst: GaeaInstall | None = None,
              uia: Uia | None = None) -> BuildResult:
    """
    Build `project` and wait for its exports.

    mode:
      "close_gui" (default) invoke 'Close Gaea and Build' - Gaea exits to free
                  the licence, then Swarm runs. Most reliable.
      "keep_gui"  invoke 'Start Build' - Gaea stays open.
    """
    t0 = time.time()
    inst = inst or find_gaea()
    if inst is None:
        return BuildResult(False, "locate", "Gaea installation not found")
    project = os.path.abspath(project)
    if not os.path.isfile(project):
        return BuildResult(False, "locate", f"project not found: {project}")

    try:
        uia = uia or Uia.ensure()
    except UiaError as e:
        return BuildResult(False, "uia", str(e))

    # ---- 1. make sure the GUI is up and the project loaded -----------------
    if not running_gaea_pids():
        if not launch_gui(inst):
            return BuildResult(False, "launch",
                               "Gaea GUI did not start within the timeout")
        uia = Uia.ensure()

    # remember what already exists so we can diff afterwards
    out_dirs = [inst.builds_dir]
    before = _snapshot(inst)

    ok, problems = open_project(inst, project, uia)
    if problems:
        return BuildResult(
            False, "validate",
            "Gaea reported validation problems; fix them before building",
            log_errors=problems)

    # ---- 2. possibly override resolution through the Build Settings tab ----
    # (skipped: the resolution lives in BuildDefinition and is already applied)

    # ---- 3. open Build Settings and reach the confirmation dialog ----------
    from .uia import activate_window, send_keys

    if not uia.has(BTN_BUILD):
        activate_window("Gaea -", exclude=("Swarm", "Diagnose"))
        time.sleep(0.8)
        send_keys("CTRL B")
        if not uia.wait_for(BTN_BUILD, timeout=25):
            return BuildResult(False, "build_settings",
                               "Build Settings dialog never appeared")

    r = uia.invoke(BTN_BUILD)
    if "INVOKED" not in r:
        return BuildResult(False, "execute_build",
                           f"could not invoke 'Execute Build': {r}")

    # ---- 4. the confirmation dialog --------------------------------------
    from .uia import CONFIRM_WINDOW  # noqa: F401  (documentation only)
    target = BTN_CLOSE_BUILD if mode == "close_gui" else BTN_START_BUILD
    if not uia.wait_for(target, timeout=30):
        # some builds skip the confirmation entirely
        if uia.wait_for("Start Build", timeout=2):
            target = "Start Build"
        else:
            return BuildResult(
                False, "confirm",
                "neither 'Start Build' nor 'Close Gaea and Build' appeared; "
                "Gaea is probably showing a different dialog")
    r = uia.invoke(target)
    if "INVOKED" not in r:
        return BuildResult(False, "confirm", f"could not invoke {target!r}: {r}")

    # ---- 5. wait for the exports -----------------------------------------
    log_mark = time.time() - 5
    end = time.time() + wait_seconds
    while time.time() < end:
        time.sleep(5)
        cur = _snapshot(inst)
        new = {k: v for k, v in cur.items() if k not in before}
        if new:
            reports = [p for p in new if p.endswith("report.json")]
            if reports:
                break
            # exports appeared; give the report a moment
            if time.time() - t0 > 20 and not running_gaea_pids():
                time.sleep(5)
                break
    else:
        return BuildResult(False, "timeout",
                           f"no build output within {wait_seconds:.0f}s",
                           seconds=time.time() - t0)

    cur = _snapshot(inst)
    new = sorted(p for p in cur if p not in before)

    # ---- 6. collect the report -------------------------------------------
    result = BuildResult(True, "done", seconds=time.time() - t0)
    reps = sorted((p for p in new if p.endswith("report.json")),
                  key=os.path.getmtime)
    if reps:
        result.report_path = reps[-1]
        try:
            result.report = json.loads(open(reps[-1], encoding="utf-8-sig").read())
            result.ok = str(result.report.get("Result", "")).lower() == "success"
            if not result.ok:
                result.message = f"Gaea reported Result=" \
                                 f"{result.report.get('Result')!r}"
        except Exception as e:
            result.message = f"could not parse report: {e}"
    else:
        result.ok = False
        result.message = "build produced no report.json"

    if new:
        result.outputs = [{"path": p, "bytes": cur[p]} for p in new
                          if not p.endswith(("report.json", "report.txt"))]

    # ---- 7. surface log problems -----------------------------------------
    sw = inst.newest_swarm_log(after_mtime=log_mark)
    if sw:
        for line in open(sw, encoding="utf-8", errors="replace"):
            s = line.strip()
            if " WRN " in line:
                result.log_warnings.append(s)
            elif " ERR " in line:
                result.log_errors.append(s)
            result.log_lines.append(s)
    if result.log_errors:
        # A build can still succeed while logging a node-level error; report it.
        result.message = (result.message + " | " if result.message else "") + \
            f"{len(result.log_errors)} error line(s) in the build log"
    return result


def _snapshot(inst: GaeaInstall) -> dict[str, int]:
    out: dict[str, int] = {}
    for root in (inst.builds_dir, inst.logs_dir):
        if not root or not os.path.isdir(root):
            continue
        for p in glob.glob(os.path.join(root, "**", "*"), recursive=True):
            if os.path.isfile(p):
                try:
                    out[p] = os.path.getsize(p)
                except OSError:
                    pass
    return out


def read_report(inst: GaeaInstall, name_hint: str = "") -> dict[str, Any] | None:
    pats = os.path.join(inst.builds_dir, "*", "*", "report.json")
    reps = sorted(glob.glob(pats), key=os.path.getmtime)
    if not reps:
        return None
    p = reps[-1]
    try:
        d = json.loads(open(p, encoding="utf-8-sig").read())
    except Exception:
        return None
    d["_path"] = p
    return d
