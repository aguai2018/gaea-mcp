<!-- Language / 语言 -->
**🌐 Language:** **English** &nbsp;|&nbsp; [简体中文](README.zh-CN.md)

# gaea-mcp — an MCP server that actually drives Gaea 2

> A QuadSpinner Gaea 2 automation toolkit that **works**: an MCP server plus a
> drop-in Skill package. Not a `.terrain`-file generator toy — a complete path
> from real elevation data to successfully exported output.

**Verified:** every file format, node parameter set and build procedure used
here was tested against **Gaea 2.3.0.1 on Windows**, producing real 4096²
heightmap and colour-map exports.

### Verified / not yet verified — please read

| Capability | Status |
|---|---|
| `.terrain` authoring (`$id` graph, required ports, `Version:2`, Export paths) | ✅ 8 offline self-test groups pass |
| 16-bit greyscale mask writing + bit-depth guard | ✅ measured lake surface 7.150 m, σ 0.0 mm |
| Heightfield/mask IO, normalisation, hillshade, fractal terrain | ✅ verified |
| Real DEM download (Copernicus GLO-30) | ✅ verified against known ground truth |
| **Let Gaea load and validate a project** (`gaea_validate_in_gaea`) | ⚠️ **partially verified**. The log-based verdict is reliable; the automatic `Ctrl+O` open is not on every host |
| **Trigger a build** (`gaea_build`) | ⚠️ **not fully verified**. The build sequence was driven by hand and exported successfully, but it depends on the open step above |

**Known limitation.** The automatic "open project" step sends foreground
keystrokes (`Ctrl+O`) to Gaea. On Windows a background process is often refused
input by the foreground-lock policy — `SetForegroundWindow` can report success
while `SendInput` never reaches the target window. A minimise-then-restore
fallback and an "already loaded" short-circuit are in place, but this was **not
reproducible on every host**.

Workaround: open the project once by hand (`File ▸ Open`). The Build Settings
panel and button invocations that `gaea_build` needs are unaffected.
The proper fix is to move key sending into the C# helper, which shares the
process that activates the window.

---

## Why this exists

Publicly available tools of this kind tend to **produce `.terrain` files Gaea
cannot open, or can open but cannot build**. One such project's own notes say:

> "The CLI subprocess encounters **handle is invalid** errors that do not
> indicate actual file corruption."

That reads the inevitable `Gaea.Swarm.exe` crash as harmless. **It is not**, and
it is exactly where people get stuck. What is actually happening:

| Symptom | Real cause |
|---|---|
| `Gaea.Swarm.exe` → `IOException: 句柄无效` (invalid handle) | **The GUI holds the floating licence seat.** Only the GUI can release it before Swarm runs |
| Build produces nothing, no error, exit 0 | The graph has **no `Export` node**, so Gaea has nothing to do |
| `port In returned bad or no data` | An upstream node **rejected its parameters** — most often an `Erosion2` missing `Version: 2` |
| Every node reports an error | Gaea **propagates one failure downstream**. Fix the **first** error, not the last |
| A mask is only partially applied | The mask was written 8-bit or palette; Gaea read it as 16-bit. **It must be 16-bit greyscale** |

This toolkit bakes all of that into its defaults and its guards.

---

## Install

```bash
# Requires Python 3.10+ and the .NET 8 SDK (the latter builds the GUI helper)
pip install -e .

# Preflight: finds Gaea, can it build the helper, can it reach the GUI
gaea-doctor
```

`gaea-doctor` reports the install path, version, licence type, and the build /
cache / log directories, and checks for the known traps. **Run it before
anything else.**

### Wiring into an AI client

```json
{
  "mcpServers": {
    "gaea": {
      "command": "gaea-mcp"
    }
  }
}
```

---

## Tools

| Tool | Purpose |
|---|---|
| `gaea_doctor` | **Start here.** Installation, version, licence, directories, GUI state, known traps |
| `gaea_list_node_types` | Node types this toolkit will author, their ports and defaults, plus the known-unsafe list and why |
| `gaea_create_project` | Author a buildable `.terrain` (adds `Version:2`, validates export paths, refuses unsafe nodes) |
| `gaea_audit_project` | Offline structural check: `$id` graph, required ports, Export paths, unsafe nodes |
| `gaea_summarise_project` | Read and describe an existing project |
| `gaea_validate_in_gaea` | **The important one.** Have Gaea load the project and read its log for real validation faults |
| `gaea_build` | Trigger a build through UI Automation and wait for the exports (`close_gui` mode is most reliable) |
| `gaea_read_build_report` | Read the most recent build report |
| `gaea_scan_logs` | Read Gaea's build / session logs and extract the error lines |
| `gaea_prepare_heightmap` | Turn raw elevation into Gaea-ready files, with a 16-bit erosion mask and hillshade preview |
| `gaea_make_fractal_heightmap` | Synthetic terrain when no real DEM is available |
| `gaea_fetch_copernicus_dem` | **Download real elevation** (GLO-30, AWS Open Data, no key) |
| `gaea_write_erosion_mask` | Write a 16-bit greyscale erosion mask (1 = erode, 0 = protect) |
| `gaea_render_preview` | Hillshade preview without opening Gaea |
| `gaea_open_in_gui` | Open a project in the GUI for a human to inspect |

---

## Recommended order

```
gaea_doctor                      # confirm the environment
      ↓
gaea_fetch_copernicus_dem        # for a real place (optional)
  or gaea_make_fractal_heightmap
      ↓
gaea_prepare_heightmap           # normalise + build masks
      ↓
gaea_create_project              # author the .terrain
      ↓
gaea_validate_in_gaea            # ★ let Gaea itself judge
      ↓
gaea_build                       # trigger the build
      ↓
gaea_read_build_report           # confirm the outputs
```

**Do not skip `gaea_validate_in_gaea`.** An offline audit cannot see everything
Gaea's loader objects to; skipping it is gambling with build time.

---

## Hard constraints encoded in the code

### `Terrain.Height` is the elevation SPAN, not a Y size

```
Terrain.Width  = ground span in metres
Terrain.Height = max_elevation - min_elevation    <- the relief
Compression    = Height / Width
```

Gaea defaults to `Width=5000 / Height=2500` (ratio 0.5). **Copying that onto real
400 m hills renders 2.5 km peaks** — the single most common source of
unrealistic terrain. West Lake's hills are truly `12000 m / 415 m = 0.0346`.

### Keep the normalisation consistent

```
0.0 ↔ lowest point       1.0 ↔ highest point
norm = (metres - min_m) / (max_m - min_m)
```

### Bitmaps come from `Export`, not `Mesher`

```json
{"$type": "QuadSpinner.Gaea.Nodes.Export, Gaea.Nodes",
 "Format": "PNG16", "Location": "Explicit",
 "OutputPath": "D:/out/terrain_heightmap"}
```

`OutputPath` must **not** include an extension — Gaea appends one per `Format`.

### `Erosion2` must carry `Version: 2`

```json
{"Duration": 40.0, "Downcutting": 0.2, "Seed": 12345,
 "Enable": true, "Version": 2}
```

Without `Version`, Gaea attempts an old-schema migration, null-references, and
every downstream consumer reports `port In returned bad or no data`.

### `RelativePath: true` resolves against the project folder

```json
{"FileName": "heightmap.png", "RelativePath": true}
```

The data file must sit beside the `.terrain`.

### Erosion masks must be 16-bit greyscale

An 8-bit or palette PNG is mis-read as 16-bit:

```
WRN Array length doesn't conform Map resolution! Requested: 16777216, Received: 33554432
```

The mask is then applied only **partially** — the "protected" area still erodes,
silently.

### Flatten water in the data, then protect it with a mask

`Erosion2` erodes everything it is allowed to reach. A lake or plain must be
flattened **before Gaea sees it**, and then protected. Both together are what
produce a mathematically exact water level (measured: mean 7.150 m, σ 0.0 mm).

### How to build

```
Gaea.exe -Path <file>      ✗ crashes on this build
run Gaea.Swarm.exe direct  ✗ always IOException while the GUI holds the licence
Ctrl+Shift+B               ✓ build shortcut (Ctrl+B only opens the settings panel)
GUI: Ctrl+B → Execute Build → "Start Build" | "Close Gaea and Build"
```

`Close Gaea and Build` shuts the GUI down to free the licence and then builds —
**most reliable**, and the only option when one seat is shared.

### Node types that reject hand-written parameters

`Thermal2` · `SatMap` · `WaterColor` · `Lake` · `Sea` · `Rivers` · `Thermal`

They are not unusable — their parameter sets are unknown. To use one, add it in
the GUI, set its parameters, save, and read the exact JSON back.

---

## Layout

```
gaea_mcp/
├─ pyproject.toml
├─ README.md / README.zh-CN.md   docs (EN / ZH)
├─ LICENSE / NOTICE.md           MIT + third-party notices
├─ selftest.py                   offline checks (no Gaea needed)
├─ acceptance.py                 end-to-end check (has Gaea load a generated project)
├─ skill/                        installable AI Skill package
│  └─ gaea-terrain/
│     ├─ SKILL.md
│     └─ reference/
│        ├─ FILE_FORMAT.md
│        ├─ NODES.md
│        ├─ BUILD.md
│        └─ TROUBLESHOOTING.md
└─ src/gaea_mcp/
   ├─ config.py                  locate install, version, licence, directories
   ├─ terrain.py                 .terrain schema + builder + structural audit
   ├─ outputs.py                 heightfield/mask IO, normalisation, hillshade, fractal DEM
   ├─ uia.py                     UI Automation bridge (compiles the C# helper)
   ├─ gaea.py                    launch / open / build / read-report orchestration
   ├─ server.py                  MCP tool definitions
   ├─ doctor.py                  command-line preflight
   └─ uia/uia.cs                 C# helper that drives Gaea by control name
```

## Self-test

```bash
python selftest.py      # offline: file format, $id graph, mask bit depth, guards
python acceptance.py    # online: have Gaea load a generated project and report
```

## Licence

MIT — see [LICENSE](LICENSE). Third-party and trademark notices: [NOTICE.md](NOTICE.md).

This is an **independent, unofficial integration** with no affiliation to
QuadSpinner and contains none of their code or assets. You need your own valid
Gaea 2 licence to use it.
