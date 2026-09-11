# Troubleshooting: symptom → cause → fix

Read the **first** error Gaea reports. It propagates a single upstream failure,
so one broken node makes every node after it complain.

---

## Build produced nothing (no error, `Result: Success`, zero files)

**Cause.** The graph has no `Export` or `Mesher` node. Gaea considers the build
complete having done nothing, and exits `0`.

**Fix.** Add an `Export` node (bitmaps) or `Mesher` (meshes) and connect it.

**Tell-tale.** The build report says `Nodes: 08 to build` / `00 to export`.

---

## `Gaea.Swarm.exe` → `System.IO.IOException: 句柄无效`

**Cause.** Not a corrupt file. Gaea's GUI holds the single floating-licence seat,
so Swarm dies after reading the project. It also happens for an unrelated
project that built successfully the day before.

**Fix.** Never shell out to Swarm. Let the GUI release the licence:

```
GUI → Ctrl+B → 'Execute Build' → 'Close Gaea and Build'
```

**Don't be fooled** by public tooling that calls this harmless. If you see this
error, your build did **not** run.

---

## Every node reports `The port In returned bad or no data`

**Cause.** One node upstream failed. The most frequent culprits:

1. An `Erosion2` without `Version: 2` — Gaea tries to migrate the schema, the
   migration null-references, and every consumer fails.
2. A node given parameters it does not accept (`Thermal2`, `SatMap`,
   `WaterColor` are known offenders).
3. A `File` node whose file is missing or unreadable, so its `Out` is empty.

**Fix.**
* Add `"Version": 2` to every `Erosion2`.
* Remove or replace the suspect node types.
* Verify every `FileName` resolves. With `RelativePath: true` the file must be
  beside the `.terrain`.

**How to find the real culprit fast:** build the graph incrementally —
`File → node → Export`, validate, then add one node at a time. Each step takes
seconds and names the offending node exactly.

---

## `WRN <Node> is old. Attempting to migrate.`

**Cause.** The project's skeleton came from a different Gaea generation
(`Metadata.Version` like `2.0.5.2` while you run 2.3.x).

**Fix.** Author from a skeleton written by the target generation — `Version`
`2.0.6.0` with `ModifiedVersion` `2.3.0.1` for Gaea 2.3. The toolkit ships one.

**Why it matters.** Migration is where the null references come from; avoid the
code path entirely.

---

## `WRN Array length doesn't conform Map resolution! Requested: N, Received: 2N`

**Cause.** A mask PNG was written 8-bit or palette; Gaea read it as 16-bit, so
the sample count is exactly double.

**Effect.** The mask is applied **partially**, so the region you meant to protect
still erodes. It fails quietly — no error, just wrong output.

**Fix.** Always write masks as **16-bit greyscale**:

```python
from PIL import Image; import numpy as np
u16 = (mask.astype(np.float32) * 65535).astype(np.uint16)
Image.fromarray(u16.astype(np.int32), mode="I").save("mask.png")
```

Verify: `Image.open("mask.png").mode` should be `I` (or `I;16`), and
`np.array(...).max()` should be 65535.

---

## The lake / flat area came out rough and too high

**Cause.** `Erosion2` erodes everything it is allowed to reach, including a
perfectly flat surface. A 7.15 m water plane came out averaging 12.37 m.

**Fix — two parts, both needed:**

1. **Flatten in the data**, before Gaea sees it. Set the region to the target
   height in the source heightmap and renormalise.
2. **Protect it with a mask** on `Erosion2`'s `Mask` port — 1 over land,
   0 over water — as a 16-bit greyscale PNG.

Result on the reference build: mean 7.150 m, standard deviation 0.0 mm.

---

## `Result: Success` but the numbers are wrong / terrain looks exaggerated

**Cause.** `Terrain.Height` is the **elevation span** (max − min), not a Y size.
Leaving Gaea's defaults (Width 5000, Height 2500, ratio 0.5) on real 400 m hills
produces 2.5 km peaks.

**Fix.** Set both from the data:

```
Width  = ground span in metres            e.g. 12000
Height = max_elevation - min_elevation    e.g. 415
```

and keep the normalisation consistent:
`norm = (metres − min_m) / (max_m − min_m)`.

---

## Clicking GUI buttons does nothing

**Cause.** Almost always the click missed. On a HiDPI multi-monitor setup the
logical screen (e.g. 3840×2160) and a screenshot (e.g. 7680×2163) differ by the
scale factor, and `SetCursorPos` takes **logical** coordinates while
screenshots are **physical**.

**Fix.** Stop clicking. Use UI Automation by control name:

```
uia invoke "Execute Build"            # AutomationId btnBuild
uia invoke "Close Gaea and Build"     # AutomationId CommandLink_11
uia invoke "Start Build"              # AutomationId CommandLink_10
```

---

## Keyboard shortcuts don't reach Gaea

**Cause.** `SetForegroundWindow` is refused when your process is not already
foreground (Windows foreground lock).

**Fix.** Minimise then restore the target window before calling
`SetForegroundWindow`:

```python
u.ShowWindow(hwnd, 6)   # SW_MINIMIZE
time.sleep(0.35)
u.ShowWindow(hwnd, 9)   # SW_RESTORE
u.SetForegroundWindow(hwnd)
```

Also dismiss stray modals first (`Welcome to Gaea`, `Save terrain?`,
`Build and Export?`) — they swallow shortcuts.

---

## `uia` reports "no Gaea process" although Gaea is running

**Cause.** The PID was hard-coded. Gaea gets a new PID on every launch.

**Fix.** Resolve it at run time:

```csharp
foreach (var p in Process.GetProcessesByName("Gaea")) { ... }
```

---

## A validation script reports "clean" but nothing actually loaded

**Cause.** The script swallowed an exception. Reading Gaea's log with the
default locale codec (GBK on a Chinese Windows) raises `UnicodeDecodeError` on
non-ASCII content; if that is caught and ignored, "no problems found" is a false
positive.

**Fix.** Decode explicitly and never let an exception become a pass:

```python
with open(log, encoding="utf-8", errors="replace") as fh:
    tail = fh.read()[mark:]
```

Then assert a positive signal — the window title contains the project name,
or the log gained an `Opening ...` line.

---

## `Gaea.exe -Path <file>` shows "Diagnose Gaea Crash?"

**Cause.** That command-line switch is broken on this build.

**Fix.** Launch `Gaea.exe` with no arguments and open via the GUI
(File ▸ Open / `Ctrl+O`).

---

## Detecting a file dialog gives false positives

**Cause.** Matching the button text ("打开"/"Open") also matches Gaea's own File
menu entry.

**Fix.** Detect the dialog by the filename combo box's `AutomationId` `1148`.

---

## Copernicus DEM download fails

**Cause.** On some networks HTTPS is intercepted; `api.quadspinner.com` and
similar endpoints can fail with SSLError even when other hosts work.

**Fix.** Route through a local proxy (`gaea_fetch_copernicus_dem(..., proxy=...)`)
or pre-download the tile. Copernicus DEM GLO-30 is also on AWS Open Data at
`https://copernicus-dem-30m.s3.amazonaws.com/<tile>/<tile>.tif` with tiles named
`Copernicus_DSM_COG_10_N30_00_E120_00_DEM`.

---

## General method, when nothing above fits

1. **Read the log.** `<install>\Data\Logs\` — session log for validation, SWARM
   log for builds. The answer is almost always there.
2. **Shrink the problem.** Reduce to the smallest graph that still reproduces it.
3. **Find a working example.** `<install>\Examples\*.terrain` and anything on
   this machine that has built successfully. Diff your file against one.
4. **Change method after three failures,** not after thirty. Coordinates →
   UI Automation; guessing → reading a known-good file; asserting → observing.
