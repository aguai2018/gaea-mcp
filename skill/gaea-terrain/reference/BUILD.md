# Building with Gaea 2 on Windows

## The licence trap (read this first)

`Gaea.Swarm.exe` is the build engine. Running it yourself usually fails:

```
$ "C:\...\Gaea.Swarm.exe" --filename "C:\proj\terrain.terrain" --silent
Preparing Gaea Build Swarm 2.3.0.1...
Loading devices...
Opening terrain.terrain...
Unhandled exception. System.IO.IOException: 句柄无效     (invalid handle)
```

That message is misleading. The cause is that **Gaea's GUI and Gaea.Swarm each
need a licence seat**, and on a floating licence the running GUI holds it. The
CLI process starts, reads the project, then dies when it cannot proceed.

Consequences:

* `Gaea.Swarm.exe` invoked by you will fail whenever the GUI is running.
* `ERRORLEVEL` is useless — Swarm exits `0` even for a missing file or an
  unknown switch. Read the **build report** instead.
* A project failing via CLI is **not** evidence that the project is wrong. This
  is the exact misreading that ships in some public Gaea MCP servers.

## What actually works

Drive the GUI. It saves the project, releases the licence, and runs Swarm.

```
Ctrl+Shift+B                   build shortcut  (Ctrl+B only opens settings)
   or  Preview ▸ Build and Export
        ↓
Build Settings and Regions dialog
   button  'Execute Build'          (AutomationId btnBuild)
        ↓
'Build and Export?' confirmation dialog
   button  'Start Build'            (AutomationId CommandLink_10)   GUI stays open
   button  'Close Gaea and Build'   (AutomationId CommandLink_11)   GUI exits first
```

`Close Gaea and Build` is the most reliable and is the **only** option that works
when one seat is shared: it shuts Gaea down, freeing the licence, and then Swarm
completes the build. `Start Build` keeps the GUI alive and runs Swarm alongside.

Both buttons are reachable through UI Automation **by name** — no pixel
coordinates, no DPI maths:

```
Get-Process Gaea | Select Id                      # find the PID (never hard-code it)
uia invoke "Execute Build"                        # Build Settings dialog
uia invoke "Close Gaea and Build"                 # confirmation dialog
uia run   title                                   # "Gaea - MyTerrain.terrain"
```

`gaea_build` in this toolkit performs the whole sequence, including waiting for
the exports and collecting the report.

## What not to do

| Don't | Why |
|---|---|
| `Gaea.exe -Path <file>` | crashes this build with "Diagnose Gaea Crash?" |
| Run `Gaea.Swarm.exe` directly | dies while the GUI holds the licence |
| Trust `%ERRORLEVEL%` | Swarm returns 0 on nearly every failure |
| Click GUI buttons by pixel | DPI scaling (a 3840×2160 logical screen captures as 7680×2163) makes coordinates unreliable; use UIA names |
| Hard-code the Gaea PID | it changes on every restart |

## Windows UI Automation notes

* Gaea is WPF, so it exposes **no Win32 child windows** — `EnumChildWindows`
  returns nothing. Use UIA (`System.Windows.Automation`).
* `SetForegroundWindow` is refused when the calling process is not already
  foreground. The reliable workaround is **minimise (`SW_MINIMIZE`) then
  restore (`SW_RESTORE`)**, then `SetForegroundWindow`.
* Detect the file dialog by the Autom `AutomationId` **`1148`** (the "File name"
  combo box). Matching on the button text ("打开"/"Open") gives false positives
  from Gaea's own File menu.
* Modals stack. Before sending a shortcut, check for and dismiss stray windows:
  `Welcome to Gaea`, `Save terrain?`, `Build and Export?`.
* The C# helper must resolve the PID at run time, and must read stdout as
  **UTF-8 with `errors="replace"`** — window titles are non-ASCII and the
  default locale codec will raise, which can silently turn a failure into a
  false "everything is fine".

## Terrain definition

```
Terrain.Width  = ground span (metres)          e.g. 12000
Terrain.Height = max_elevation - min_elevation e.g. 415      <- the SPAN
Terrain.Ratio  = Height / Width                e.g. 0.0346
```

The default 5000 × 2500 (ratio 0.5) is a stylistic default with heavy vertical
exaggeration. Copying it onto real 400 m hills makes 2.5 km peaks. Always set
both from the real data, and keep `BuildDefinition.Resolution` equal to
`Terrain.Height`-consistent m/px in mind:

```
metres per pixel = Width / Resolution
```

## Build definition and outputs

```jsonc
"BuildDefinition": {
  "Type": "Standard",
  "Destination": "<Builds>\\[Filename]\\[+++]",   // tokens: <Builds> [Filename] [Date] [+++]
  "Resolution": 4096,
  "BakeResolution": 4096,
  ...
}
```

Individual outputs are controlled by the graph, not by `Destination`:

* `Export` nodes with `Location: "Explicit"` write exactly where they say.
* `Export`/`Mesher` nodes with `Location: "Build Folder"` land under
  `Destination`.

`<Builds>` expands to Options ▸ Build ▸ Build Output Path, recorded in
`Data\Settings\Preferences.options` under `Locations.Builds`.

Each build creates a numbered subfolder (`\001`, `\002`, …) containing
`report.txt` and `report.json`:

```json
{"Resolution": 4096, "NodeCount": 9, "Result": "Success",
 "Duration": "00:00:19.8261777", "SecondsTaken": {...}}
```

**`Result` is the only trustworthy success signal.**

## Reading the build log

Build logs live in `<install>\Data\Logs\` as `<stamp>-SWARM.txt`. A healthy
build reads:

```
INF Opening ...\terrain.terrain
INF Loading Baked Cache...
INF Invalidating nodes
INF Starting build
INF Building ColorExport
INF [100] DEM - Build Started
INF [100] DEM - Build Finished
INF [101] HeightmapExport - Export Started D:\out\heightmap.png
INF [101] HeightmapExport - Export Finished - 11
```

Lines to treat as real problems:

| Line | Meaning |
|---|---|
| `WRN <Node> is old. Attempting to migrate.` | schema mismatch — the skeleton is the wrong generation |
| `ERR <id> - <Node> failed: Object reference not set...` | that node rejected the parameters |
| `INF (id) <Node> reported: The port In returned bad or no data.` | downstream of the real failure |
| `WRN Array length doesn't conform Map resolution! Requested: N, Received: 2N` | a mask was read at the wrong bit depth (use 16-bit greyscale) |

The GUI's own session log (`Data\Logs\<stamp>.txt`, no `SWARM` in the name) is
where **node validation** faults appear right after a project is opened — that
is the log to read when checking a project, and it is what
`gaea_validate_in_gaea` inspects.

`report.json` being written does **not** imply exports were written: with no
`Export`/`Mesher` node the build succeeds having done nothing.

## Verifying exported output

Do not stop at "the file exists". Check content:

```python
import numpy as np; from PIL import Image
h = np.array(Image.open("heightmap.png"))
print(h.shape, h.dtype, h.min(), h.max())
```

Then cross-check against ground truth — a known water level, a known summit, a
known area. For the West Lake build: detected lake area 5.54 km² vs a true
5.66 km², summit 414.1 m vs the true 412 m, centroid within 0.3 km. That is the
kind of check that catches a silently wrong normalisation.
