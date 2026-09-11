# Node types Gaea 2.3.0.1 accepts from hand-written JSON

Derived by loading hand-authored projects in Gaea and reading its session log.
A type only counts as "safe" here if a project containing it validates with
**zero** errors, zero validation faults and zero migration warnings.

## Safe

### `File`
```jsonc
{"FileName": "heightmap.png", "RelativePath": true}
```
Ports: `In` (optional), `Out`.
`RelativePath: true` resolves against the **project folder** — the data file
must sit next to the `.terrain`. Use `RelativePath: false` with an absolute
path otherwise. Set `"IsRGB": true` to load a colour image instead.
Cannot load `.r32` reliably; prefer 16-bit PNG.

### `Adjust`
```jsonc
{"NodeSize": "Small"}
```
Ports: `In` (required), `Out`, `Mask` (in).
Cheap pass-through; also carries `Multiply` / `Shaper` for height scaling.

### `Erosion2`  — **`Version: 2` is mandatory**
```jsonc
{"Duration": 40.0, "Downcutting": 0.2, "Seed": 12345,
 "Enable": true, "Version": 2}
```
Ports: `In` (required), `Out`, `Mask` (in), `Flow`, `Wear`, `Deposits` (outs),
`Precipitation` (in).

Without `Version`, Gaea attempts a schema migration and dies with a null
reference; the error propagates and **every** downstream node reports
`The port In returned bad or no data`. This single field is the most common
cause of an "unbuildable" hand-authored project.

`Mask` (in) restricts where erosion applies: 1 = erode, 0 = protected. Provide a
**16-bit greyscale PNG**. Tuning for low-relief terrain: keep `Downcutting`
small (0.05–0.2) and `Duration` moderate (30–60).

### `Height`
```jsonc
{"Range": {"$id": "x", "X": 0.55, "Y": 1.0}, "Falloff": 0.25,
 "NodeSize": "Standard"}
```
Ports: `In` (required), `Out`, `Mask` (in). Elevation-band mask.

### `Tint`
```jsonc
{"Start": {"$id": "a", "R": 0.10, "G": 0.20, "B": 0.09},
 "End":   {"$id": "b", "R": 0.66, "G": 0.64, "B": 0.60},
 "RenderIntentOverride": "Color"}
```
Ports: `In` (required), `Out`.
The reliable colouriser in 2.3.0.1. `RenderIntentOverride: "Color"` is needed
whenever colour data flows.

### `Combine`
```jsonc
{"PortCount": 2, "Ratio": 1.0, "Mode": "Max",
 "RenderIntentOverride": "Color"}
```
Ports: `In` (required), `Out`, `Input2`, `Input3`, `Input4`, `Mask` (all in).
`Mode` ∈ Add, Subtract, Multiply, Max, Min, Difference, Screen, Overlay,
HardLight, GrainMerge. There is **no** Blend mode — use the `Mask` port.
Omit `RenderIntentOverride` for pure height maths; include it for colour.

### `Export`  — this is how bitmaps are written
```jsonc
{"Format": "PNG16", "Location": "Explicit",
 "OutputPath": "D:/out/terrain_heightmap"}
```
Ports: `In` (required), `Out`.
`OutputPath` must **not** carry an extension — Gaea appends one from `Format`.
`Location` ∈ Build Folder / Custom / Explicit. Formats: PNG8, PNG16, EXR, TIFF,
TIFF16, TIFF32, RAW16, RAW32, R32, HDR.

### `Mesher`
```jsonc
{"Format": "GLB", "Scale": "Meter", "Topology": "Quads",
 "VerticesPerSide": 512, "ArtifactReduction": "Med",
 "CreateNormals": true, "CreateUVs": true}
```
Ports: `In` (required), `Out`. Meshes only — **not** bitmaps.

### `Constant`
```jsonc
{"Height": 0.5, "NodeSize": "Standard"}
```
A flat plane at a normalised height. Useful with `Combine(Mode=Max)`.

### `Blur`
Ports: `In` (required), `Out`, `Mask`. Parameter names vary between builds;
omit parameters and use defaults unless you have verified them.

## Unsafe with hand-written parameters

These reject parameters whose names/shapes this toolkit has not verified. In
every observed case the failure mode is a null reference at that node, which
then poisons everything downstream.

| Type | Observed failure |
|---|---|
| `Thermal2` | downstream `TerrainModel/Export`: `port In returned bad or no data` |
| `SatMap` | same |
| `WaterColor` | `WestLakeWater failed: Object reference not set to an instance of an object` — needs a real water source |
| `Lake`, `Sea`, `Rivers` | parameter semantics undocumented; verify before use |
| `Thermal` | verify before use |

**To use any of these safely**: drop one into a project in the GUI, set its
parameters there, save, then read the node's JSON back and copy the exact
parameter names and value shapes into your generator.

## Building the graph

Two habits that pay off:

1. **Minimum viable chain first.** `File → Erosion2 → Export`, build it, confirm
   exports appear. Then add nodes one at a time, re-validating after each. A
   six-stage incremental test pinpoints a bad node in minutes; guessing from a
   full graph can take hours.
2. **Fix the first error only.** Gaea propagates a single upstream failure, so a
   log full of `port In returned bad or no data` usually means exactly one node
   is actually broken — the earliest one listed.

## Useful node inventory (for reference)

106 node types exist in Gaea 2.3. Categories: Primitive, Terrain, Modify,
Surface, Simulate, Derive, Colorize, Output, Utility, Macro. Enumerate the
installed set by scanning `<install>\Examples\*.terrain` for `"$type"` values —
that also gives you real, working parameter sets for each type.
