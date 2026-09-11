"""End-to-end acceptance test: have GAEA ITSELF load a project that this
   toolkit authored from nothing, and report whether it validates."""
import glob
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from gaea_mcp import gaea as G          # noqa: E402
from gaea_mcp.config import find_gaea   # noqa: E402
from gaea_mcp.uia import Uia            # noqa: E402

PROJ = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "_selftest", "SelfTest.terrain")

inst = find_gaea()
print("install   :", inst.root if inst else None)
print("version   :", inst.version if inst else None)
print("project   :", PROJ)
print("data files next to it:")
for f in sorted(glob.glob(os.path.join(os.path.dirname(PROJ), "*"))):
    print("   ", os.path.basename(f), os.path.getsize(f))

uia = Uia.ensure()
print("\nuia helper:", uia.exe)
print("Gaea pid  :", uia.pid())

if not G.running_gaea_pids():
    print("launching Gaea GUI ...")
    assert G.launch_gui(inst), "Gaea GUI failed to start"
    uia = Uia.ensure()

print("Gaea pid  :", uia.pid())
print("\nopening the generated project through the GUI ...")
ok, problems = G.open_project(inst, PROJ, uia)

print("\n" + "=" * 62)
print("RESULT:", "CLEAN - Gaea validated the generated project" if ok
      else "PROBLEMS REPORTED")
for p in problems:
    print("   ", p[:160])
if not problems:
    print("    (no node errors, no validation faults, no migration warnings)")
print("=" * 62)

log = inst.newest_session_log()
print("\nsession log:", log)
if log:
    with open(log, encoding="utf-8", errors="replace") as fh:
        tail = fh.read().splitlines()[-12:]
    for line in tail:
        print("   ", line[:150])

sys.exit(0 if ok else 1)
