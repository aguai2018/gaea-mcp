"""`gaea-doctor` - a command-line preflight for the Gaea MCP server.

Run this before wiring the server into an agent. It answers, in one shot:
  * is Gaea installed, and which version/edition
  * where does it build, cache and log
  * is the GUI currently running (which changes how you must build)
  * can the UI Automation helper be compiled (needs the .NET 8 SDK)
  * do the known traps apply to this machine

Exit code is 0 when a build could plausibly succeed, 1 otherwise.
"""
from __future__ import annotations

import os
import shutil
import sys

from .config import describe, find_gaea
from .uia import Uia, UiaError


def main() -> int:
    print("=" * 72)
    print("Gaea MCP preflight")
    print("=" * 72)
    d = describe()
    if not d.get("found"):
        print("  Gaea not found.")
        print(" ", d.get("error"))
        print("  probed:", ", ".join(d.get("probed", [])))
        return 1

    ok = True
    print(f"  install    : {d['root']}")
    print(f"  version    : {d['version']}")
    print(f"  edition    : {d['edition']}")
    print(f"  Gaea.exe   : {d['exe']}")
    print(f"  Swarm.exe  : {d['swarm']}")
    print(f"  logs       : {d['logs_dir']}")
    print(f"  builds     : {d['builds_dir']}")
    print(f"  caches     : {d['caches_dir']}")
    print(f"  GUI running: {d['gui_running']}  {d['running_pids']}")
    print(f"  python     : {d['python']}")

    print("\n  --- traps ---")
    if d.get("problems"):
        for p in d["problems"]:
            print("   !", p)
    else:
        print("    none detected")

    print("\n  --- UI Automation helper ---")
    if sys.platform != "win32":
        print("    skipped (not Windows) - Gaea automation is Windows-only")
        ok = False
    elif not shutil.which("dotnet"):
        print("    .NET SDK not found. The helper is required to drive the GUI.")
        print("    Install .NET 8 SDK from https://dot.net, or pre-build")
        print("    src/gaea_mcp/uia/uia.cs and place uia.exe next to it.")
        ok = False
    else:
        try:
            uia = Uia.ensure()
            print("    built/available:", uia.exe)
            pid = uia.pid()
            print("    Gaea pid seen  :", pid)
            if pid:
                w = uia.run("windows").splitlines()
                print("    windows        :", len(w))
                for line in w[:6]:
                    print("      ", line)
        except UiaError as e:
            print("    FAILED:", e)
            ok = False

    print("\n  --- how to build on this machine ---")
    inst = find_gaea()
    if inst:
        print("    Do NOT run Gaea.Swarm.exe directly: it dies with")
        print("      'IOException: 句柄无效' while the GUI holds the licence.")
        print("    Instead the server drives the GUI: Ctrl+B -> Execute Build")
        print("      -> 'Start Build' (GUI stays) or 'Close Gaea and Build'.")
        print("    Never use `Gaea.exe -Path <file>`: it crashes on this build.")

    print("\n" + ("READY" if ok else "NOT READY - see the notes above"))
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
