---
name: gaea-terrain
description: Drive QuadSpinner Gaea 2 on Windows to author real .terrain projects, validate them against Gaea itself, and run builds that actually export heightmaps, colour maps and meshes. Use when the user asks to create terrain in Gaea, to build a heightmap/terrain model from a real place or a DEM, to automate Gaea, to convert elevation data into Gaea-ready files, or when a Gaea project opens but will not build or export anything. Covers the .terrain JSON schema, the node types Gaea 2.3 accepts, the licence trap that makes Gaea.Swarm.exe crash, and the erosion-mask bit-depth trap.
---

# Driving Gaea 2 from an AI agent

This skill encodes what actually works on **Gaea 2.3.0.1 for Windows**, verified
by building and exporting real projects. Read `reference/TROUBLESHOOTING.md`
the moment anything fails — almost every failure has an exact known cause.

## The one rule that saves the most time

**Let Gaea itself validate the project before you build.** An offline look at
the JSON cannot see everything Gaea's loader objects to, and a single bad node
makes Gaea report errors on *every* node downstream of it. `gaea_validate_in_gaea`
reads Gaea's own session log; use it after every change. Skipping it is the main
reason people burn hours generating-and-guessing.

## Standard workflow

```
gaea_doctor                     # 1. environment: install, version, licence, dirs
      ↓
gaea_fetch_copernicus_dem       # 2a. real place  -> real elevation (no API key)
   or gaea_make_fractal_heightmap  # 2b. invented place
      ↓
gaea_prepare_heightmap          # 3. normalise, resample, build masks + preview
      ↓
gaea_create_project             # 4. author the .terrain
      ↓
gaea_validate_in_gaea           # 5. ★ ask Gaea. Fix the FIRST error listed.
      ↓
gaea_build                      # 6. UI-automation build, waits for exports
      ↓
gaea_read_build_report          # 7. confirm Result == "Success"
```

## Non-negotiable facts

**Terrain definition.** `Width` is the ground span in metres; `Height` is the
elevation *span* (max − min), **not** a Y size. Their ratio is the compression
ratio. Gaea defaults to 5000/2500 (ratio 0.5) which turns 400 m hills into
2500 m peaks — always set both from the real data.

**Normalisation.** Heightfields are 0..1 and map to `min_m..max_m` metres:
`norm = (metres − min_m) / (max_m − min_m)`. Keep this consistent between the
data files and the project, or the water level and relief will be wrong.

**Bitmaps come from `Export`, not `Mesher`.** `Export` needs
`Location: "Explicit"` and an `OutputPath` **without** extension.

**`Erosion2` must carry `Version: 2`.** Without it Gaea tries to migrate an
older schema, throws a null reference, and every downstream port fails.

**`File` with `RelativePath: true` resolves against the project folder** — the
data file has to sit beside the `.terrain`.

**Erosion masks must be 16-bit greyscale PNG.** 8-bit or palette PNGs are
mis-read as 16-bit, logged as `Array length doesn't conform Map resolution`,
and applied only partially.

**Flatten water in the data, then protect it with a mask.** Erosion roughens
anything it is allowed to touch, so a lake surface must be flattened before
Gaea sees it.

**Never call `Gaea.Swarm.exe` directly** and never use `Gaea.exe -Path`. Let
the GUI do it (see `reference/BUILD.md`).

**Node types to avoid with hand-written parameters:** `Thermal2`, `SatMap`,
`WaterColor`, `Lake`, `Sea`, `Rivers`, `Thermal`. They are not unusable — their
parameter sets are unknown; add one in the GUI, save, and read the JSON back.

## Reference files

- `reference/FILE_FORMAT.md` — the `.terrain` JSON layout: `$id`/`$ref` graph,
  asset structure, how to mint ids, what to copy from a known-good file
- `reference/NODES.md` — node types, ports and parameter sets that Gaea 2.3
  accepts, plus the unsafe list and why
- `reference/BUILD.md` — launching, loading, triggering a build, where reports
  and outputs land, how to read a build log
- `reference/TROUBLESHOOTING.md` — symptom → cause → fix table. **Start here
  when something breaks.**
