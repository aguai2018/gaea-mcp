"""
MCP server exposing the Gaea toolkit to an AI agent.

Tool order matters: call `gaea_doctor` first, then `gaea_create_project`, then
`gaea_validate_in_gaea` (which asks Gaea itself), and only then `gaea_build`.
Skipping the in-Gaea validation is the single biggest cause of wasted time -
the offline audit cannot see everything Gaea's own loader objects to.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from . import gaea as G
from . import outputs as O
from . import terrain as T
from .config import describe, find_gaea
from .uia import Uia, UiaError


def _json(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, indent=2, default=str)


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "The 'mcp' package is required. Install with:\n"
            "  pip install mcp\n"
            f"(import error: {exc})")

    mcp = FastMCP("gaea-mcp")

    # ------------------------------------------------------------------ 0
    @mcp.tool()
    def gaea_doctor() -> str:
        """Probe the machine for Gaea 2 and report everything needed before
        building: install path, version, edition, build/cache/log folders,
        whether the GUI is running, and whether the .NET SDK is available for
        the UI Automation helper. Call this first."""
        return _json(describe())

    @mcp.tool()
    def gaea_list_node_types() -> str:
        """List the node types this toolkit will author, their ports, and the
        default parameters. Types that are known to reject hand-authored
        parameters on Gaea 2.3.0.1 are listed separately with the reason."""
        return _json({
            "safe_nodes": {
                k: {"ports": v.ports, "defaults": v.defaults, "note": v.note}
                for k, v in T.NODE_SPECS.items()
            },
            "unsafe_nodes": T.UNSAFE_NODES,
            "export_formats": T.EXPORT_FORMATS,
            "mesh_formats": T.MESH_FORMATS,
        })

    # ------------------------------------------------------------------ 1
    @mcp.tool()
    def gaea_create_project(
        project_path: str,
        width_m: float = 12000.0,
        relief_m: float = 415.0,
        heightmap: str = "",
        heightmap_relative: bool = True,
        erosion_mask: str = "",
        name: str = "terrain",
        resolution: int = 4096,
        erosion_duration: float = 40.0,
        erosion_downcutting: float = 0.2,
        erosion_seed: int = 12345,
        erosion_scale: float = 0.0,
        export_heightmap: str = "",
        export_color: str = "",
        mesh_output: str = "",
        color_low_rgb: str = "0.10,0.20,0.09",
        color_high_rgb: str = "0.66,0.64,0.60",
        notes: str = "",
    ) -> str:
        """Author a buildable `.terrain` project.

        width_m  - ground span in metres (the window is square).
        relief_m - the elevation SPAN (max - min), not an absolute height.
                   Getting this wrong is the classic realism bug: Gaea defaults
                   to width 5000 / relief 2500 (ratio 0.5) which turns 400 m
                   hills into 2.5 km peaks.
        heightmap        - path to the source heightfield. When
                           heightmap_relative is true the file must sit next to
                           the .terrain file; otherwise it is used as given.
        erosion_mask     - optional 16-bit grayscale PNG; 1 = erode, 0 = protect.
                           Use it to keep a lake or a city plain untouched.
        export_heightmap - output path WITHOUT extension, e.g.
                           ".../out/terrain_heightmap" (Gaea appends .png).
        export_color     - same, for the colourised map.
        mesh_output      - output path for a GLB/OBJ mesh (with extension).

        Returns the audit result and the path written.
        """
        b = T.ProjectBuilder(name=name, width_m=width_m, height_m=relief_m)
        last = None
        proj_dir = os.path.dirname(os.path.abspath(project_path))

        # ---- source -----------------------------------------------------
        if heightmap:
            nid = b.add("File", "Source", node_id=100)
            fn = heightmap
            if heightmap_relative:
                fn = os.path.basename(heightmap)
                # make sure it really is beside the project
                if os.path.abspath(heightmap) != os.path.join(proj_dir, fn):
                    raise ValueError(
                        f"heightmap_relative=True but {heightmap!r} is not in "
                        f"{proj_dir!r}; either pass the copy that is already "
                        "next to the project, or set heightmap_relative=False")
            b.set_file(nid, fn, relative=heightmap_relative)
            last = nid
            adj = b.add("Adjust", "HeightScale", node_id=105)
            b.connect(last, adj)
            last = adj

        # ---- erosion ----------------------------------------------------
        er = b.add("Erosion2", "Erosion", node_id=110,
                   Duration=erosion_duration, Downcutting=erosion_downcutting,
                   Seed=erosion_seed, Enable=True, Version=2)
        if last is not None:
            b.connect(last, er)
        if erosion_scale:
            b.set_params(er, ErosionScale=erosion_scale)
        if erosion_mask:
            mn = b.add("File", "ErosionMask", node_id=170)
            mfn = os.path.basename(erosion_mask) if heightmap_relative else erosion_mask
            b.set_file(mn, mfn, relative=heightmap_relative)
            b.connect(mn, er, dst_port="Mask")
        last = er

        # ---- exports ----------------------------------------------------
        made = []
        if export_heightmap:
            ex = b.add("Export", "HeightmapExport", node_id=101,
                       Format="PNG16")
            b.set_export(ex, os.path.splitext(export_heightmap)[0], "PNG16")
            b.connect(last, ex)
            made.append(f"heightmap -> {os.path.splitext(export_heightmap)[0]}.png")
        if export_color:
            tint = b.add("Tint", "TerrainColor", node_id=130,
                         RenderIntentOverride="Color",
                         Start=_rgb(color_low_rgb), End=_rgb(color_high_rgb))
            b.connect(last, tint)
            ex = b.add("Export", "ColorExport", node_id=150,
                       Format="PNG8", RenderIntentOverride="Color")
            b.set_export(ex, os.path.splitext(export_color)[0], "PNG8")
            b.connect(tint, ex)
            made.append(f"colour -> {os.path.splitext(export_color)[0]}.png")
        if mesh_output:
            ms = b.add("Mesher", "TerrainModel", node_id=300,
                       Format=os.path.splitext(mesh_output)[1].lstrip(".").upper() or "GLB")
            b.connect(last, ms)
            made.append(f"mesh -> {mesh_output}")

        if not made:
            ex = b.add("Export", "HeightmapExport", node_id=101, Format="PNG16")
            b.set_export(ex, os.path.join(proj_dir, "outputs", "heightmap"),
                         "PNG16")
            b.connect(last, ex)
            made.append(f"heightmap -> {os.path.join(proj_dir, 'outputs')}")

        if notes:
            pass
        b.save(project_path, resolution=resolution, selected=last,
               notes_markdown=notes or None)
        audit = b.audit()
        return _json({
            "project_path": os.path.abspath(project_path),
            "exports": made,
            "audit": audit,
            "next_step": ("call gaea_validate_in_gaea to let Gaea itself check "
                          "the graph before building"),
        })

    def _rgb(s: str) -> dict[str, Any]:
        parts = [float(x) for x in s.split(",")]
        while len(parts) < 3:
            parts.append(0.0)
        return {"$id": "0", "R": parts[0], "G": parts[1], "B": parts[2]}

    # ------------------------------------------------------------------ 2
    @mcp.tool()
    def gaea_audit_project(project_path: str) -> str:
        """Offline structural check of a `.terrain`: duplicate/dangling `$id`
        references, unconnected required inputs, missing Version on Erosion2,
        Export paths that wrongly include an extension, and node types known to
        be unsafe. Fast, and works with Gaea closed - but it cannot see
        everything, so follow with gaea_validate_in_gaea."""
        doc, nodes = T.load(project_path)
        asset = doc["Assets"]["$values"][0]
        b = T.ProjectBuilder.__new__(T.ProjectBuilder)
        b.doc = doc
        b._asset = asset
        b.terrain = asset["Terrain"]
        b._nodes = nodes
        b._next_id = 0
        return _json({"path": project_path, "audit": b.audit()})

    @mcp.tool()
    def gaea_summarise_project(project_path: str) -> str:
        """Describe a `.terrain`: terrain definition, build definition, nodes,
        parameters and edges."""
        return _json(T.summarise(project_path))

    # ------------------------------------------------------------------ 3
    @mcp.tool()
    def gaea_validate_in_gaea(project_path: str) -> str:
        """THE IMPORTANT ONE. Open the project in Gaea and read Gaea's own
        session log for validation faults.

        This is how you find out whether the graph is actually buildable.
        Gaea propagates a single bad node downstream, so one failure shows up
        as many nodes reporting "The port In returned bad or no data" - fix the
        FIRST error in the list, not the last.

        Requires the Gaea GUI; it will be started if needed."""
        inst = find_gaea()
        if inst is None:
            return _json({"ok": False, "error": "Gaea not found"})
        try:
            uia = Uia.ensure()
        except UiaError as e:
            return _json({"ok": False, "error": str(e)})
        if not G.running_gaea_pids():
            if not G.launch_gui(inst):
                return _json({"ok": False, "error": "Gaea GUI would not start"})
        ok, problems = G.open_project(inst, project_path, uia)
        log = inst.newest_session_log()
        faults = O.scan_log_for_faults(log) if log else {}
        return _json({
            "ok": ok,
            "project_path": os.path.abspath(project_path),
            "validation_problems": problems,
            "session_log": log,
            "migration_warnings": (faults or {}).get("migration", []),
            "advice": (None if ok else
                       "Fix the FIRST reported node; later reports are usually "
                       "downstream noise. See reference/TROUBLESHOOTING.md."),
        })

    # ------------------------------------------------------------------ 4
    @mcp.tool()
    def gaea_build(project_path: str, mode: str = "close_gui",
                   wait_seconds: float = 900.0) -> str:
        """Build the project and wait for its exports.

        mode="close_gui" (default) invokes 'Close Gaea and Build': Gaea exits to
        release the floating licence and then Swarm runs to completion. This is
        the most reliable path and the only one that works when a single licence
        seat is shared.

        mode="keep_gui" invokes 'Start Build', leaving Gaea open.

        Never call Gaea.Swarm.exe directly - it dies with
        'IOException: 句柄无效' while the GUI holds the licence.

        Returns the build report, the files produced, and any log warnings."""
        res = G.run_build(project_path, mode=mode, wait_seconds=wait_seconds)
        return _json(res.to_dict())

    @mcp.tool()
    def gaea_read_build_report() -> str:
        """Return the most recent build report from Gaea's build folder."""
        inst = find_gaea()
        if inst is None:
            return _json({"error": "Gaea not found"})
        rep = G.read_report(inst)
        return _json(rep or {"error": "no report.json found",
                             "searched": os.path.join(inst.builds_dir, "*",
                                                      "*", "report.json")})

    @mcp.tool()
    def gaea_scan_logs(mode: str = "swarm", tail: int = 200) -> str:
        """Read Gaea's own logs. mode='swarm' for build logs, 'session' for the
        GUI session log (which is where node-validation faults appear)."""
        inst = find_gaea()
        if inst is None:
            return _json({"error": "Gaea not found"})
        path = (inst.newest_swarm_log() if mode == "swarm"
                else inst.newest_session_log())
        if not path:
            return _json({"error": f"no {mode} log found in {inst.logs_dir}"})
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        faults = O.scan_log_for_faults(path)
        return _json({
            "log": path,
            "faults": faults,
            "tail": lines[-max(1, tail):],
        })

    # ------------------------------------------------------------------ 5
    @mcp.tool()
    def gaea_prepare_heightmap(
        source: str,
        out_dir: str,
        min_m: float = 0.0,
        max_m: float = 415.0,
        width_m: float = 12000.0,
        size: int = 0,
        name: str = "heightmap",
        flip_vertical: bool = False,
        flatten_mask: str = "",
        flatten_level_m: float = 0.0,
        invert_mask_for_erosion: bool = True,
        preview: bool = True,
    ) -> str:
        """Turn a raw heightfield into files Gaea can consume.

        Writes:
          <out_dir>/<name>.png      16-bit grayscale, normalised 0..1
          <out_dir>/<name>.r32      headerless float32, values 0..1
          <out_dir>/<name>.json     georeference + statistics
          <out_dir>/<name>_mask.png optional 16-bit erosion mask
          <out_dir>/<name>_preview.png hillshade

        source      - .png/.tif/.r32/.raw. Values are renormalised to min_m..max_m.
        flatten_mask- optional mask image (nonzero = flat region). The region is
                      set to flatten_level_m BEFORE Gaea sees it, which is the
                      only way to get a mathematically flat water plane: Erosion2
                      roughens any surface it is allowed to touch.
        size        - resample to this square size (0 = keep source size).
        """
        g = O.read_grid(source)
        raw = g.data
        g = O.Grid(raw, min_m, max_m, width_m, {"source": os.path.abspath(source)})

        flat_mask = None
        if flatten_mask:
            fm = O.read_grid(flatten_mask).data
            if fm.shape != g.data.shape:
                from PIL import Image as _I
                fm = np.array(_I.fromarray((fm * 65535).astype(np.uint16)).resize(
                    (g.data.shape[1], g.data.shape[0]))) / 65535.0
            flat_mask = fm > 0.5
            target = (flatten_level_m - min_m) / max(max_m - min_m, 1e-9)
            g.data = g.data.copy()
            g.data[flat_mask] = target
            # soften the shoreline by one pixel either side
            from scipy import ndimage as _nd
            ring = _nd.binary_dilation(flat_mask, iterations=2) & ~flat_mask
            g.data[ring] = 0.5 * g.data[ring] + 0.5 * target

        if size and size != g.data.shape[0]:
            from PIL import Image as _I
            u16 = (g.data * 65535).astype(np.uint16)
            im = _I.fromarray(u16.astype(np.int32), mode="I").resize(
                (size, size), _I.BILINEAR)
            g.data = (np.array(im).astype(np.float32) / 65535.0)

        if flip_vertical:
            g = g.flip_vertical()

        os.makedirs(out_dir, exist_ok=True)
        files = {}
        files["png16"] = O.write_heightmap_png(g, os.path.join(out_dir, f"{name}.png"))
        files["r32"] = O.write_r32(g, os.path.join(out_dir, f"{name}.r32"))
        if preview:
            files["preview"] = O.save_hillshade_preview(
                g, os.path.join(out_dir, f"{name}_preview.png"))
        if flat_mask is not None:
            m = (~flat_mask) if invert_mask_for_erosion else flat_mask
            files["erosion_mask"] = O.write_mask_png(
                m, os.path.join(out_dir, f"{name}_mask.png"))
        files["meta"] = O.write_meta(g, os.path.join(out_dir, f"{name}.json"), {
            "flattened": bool(flat_mask is not None),
            "flatten_level_m": flatten_level_m if flat_mask is not None else None,
        })
        return _json({"files": files, "grid": g.summary()})

    @mcp.tool()
    def gaea_make_fractal_heightmap(
        out_dir: str,
        name: str = "fractal",
        size: int = 1024,
        width_m: float = 8000.0,
        relief_m: float = 1500.0,
        seed: int = 1,
        octaves: int = 8,
    ) -> str:
        """Generate a synthetic fractal heightfield when no real DEM is at hand,
        and write it in Gaea-ready form. For real places, prefer a real DEM:
        use gaea_fetch_copernicus_dem."""
        g = O.fractal_dem(size=size, width_m=width_m, relief_m=relief_m,
                          seed=seed, octaves=octaves)
        os.makedirs(out_dir, exist_ok=True)
        files = {
            "png16": O.write_heightmap_png(g, os.path.join(out_dir, f"{name}.png")),
            "r32": O.write_r32(g, os.path.join(out_dir, f"{name}.r32")),
            "preview": O.save_hillshade_preview(
                g, os.path.join(out_dir, f"{name}_preview.png")),
            "meta": O.write_meta(g, os.path.join(out_dir, f"{name}.json")),
        }
        return _json({"files": files, "grid": g.summary()})

    # ------------------------------------------------------------------ 6
    @mcp.tool()
    def gaea_fetch_copernicus_dem(
        lat: float,
        lon: float,
        out_dir: str,
        size_m: float = 12000.0,
        pixels: int = 2048,
        name: str = "dem",
        proxy: str = "",
    ) -> str:
        """Download real elevation for a place from Copernicus DEM GLO-30
        (public AWS Open Data, no key) and cut a square, metric window.

        lat/lon   - window centre (degrees, WGS84).
        size_m    - ground size of the square window in metres.
        pixels    - output grid (2048 is a good default; the source is 30 m).
        proxy     - optional http(s) proxy, e.g. "http://127.0.0.1:7897".

        Writes <out_dir>/<name>.png|.r32|.json plus a hillshade preview and
        reports the detected elevation range so you can set relief_m correctly."""
        import io
        import math
        import requests
        from PIL import Image as _I

        os.makedirs(out_dir, exist_ok=True)
        proxies = {"http": proxy, "https": proxy} if proxy else None

        m_lat = (111132.92 - 559.82 * math.cos(2 * math.radians(lat))
                 + 1.175 * math.cos(4 * math.radians(lat)))
        m_lon = (111412.84 * math.cos(math.radians(lat))
                 - 93.5 * math.cos(3 * math.radians(lat)))
        half_lat = (size_m / 2) / m_lat
        half_lon = (size_m / 2) / m_lon
        lat_min, lat_max = lat - half_lat, lat + half_lat
        lon_min, lon_max = lon - half_lon, lon + half_lon

        # Copernicus tiles are 1x1 degree COGs, one per (lat,lon) degree
        tiles = {}
        for tlat in range(int(math.floor(lat_min)), int(math.floor(lat_max)) + 1):
            for tlon in range(int(math.floor(lon_min)), int(math.floor(lon_max)) + 1):
                ns = "N" if tlat >= 0 else "S"
                ew = "E" if tlon >= 0 else "W"
                tname = (f"Copernicus_DSM_COG_10_{ns}{abs(tlat):02d}_00_"
                         f"{ew}{abs(tlon):03d}_00_DEM")
                url = (f"https://copernicus-dem-30m.s3.amazonaws.com/{tname}/"
                       f"{tname}.tif")
                try:
                    r = requests.get(url, proxies=proxies, timeout=180,
                                     stream=True)
                    r.raise_for_status()
                    cache = os.path.join(out_dir, tname + ".tif")
                    if not os.path.exists(cache):
                        with open(cache, "wb") as fh:
                            for chunk in r.iter_content(1 << 19):
                                fh.write(chunk)
                    tiles[(tlon, tlat)] = np.array(_I.open(cache)).astype(np.float32)
                except Exception as e:
                    return _json({"ok": False,
                                  "error": f"failed to fetch {tname}: {e}"})

        xs = lon_min + (np.arange(pixels) + 0.5) * (lon_max - lon_min) / pixels
        ys = lat_max - (np.arange(pixels) + 0.5) * (lat_max - lat_min) / pixels
        LON, LAT = np.meshgrid(xs, ys)
        dem = np.full((pixels, pixels), np.nan, dtype=np.float32)
        for (tlon, tlat), tile in tiles.items():
            sel = ((LON >= tlon) & (LON < tlon + 1)
                   & (LAT >= tlat) & (LAT < tlat + 1))
            if not sel.any():
                continue
            n = tile.shape[0]
            fx = (LON[sel] - tlon) * n - 0.5
            fy = (tlat + 1.0 - LAT[sel]) * n - 0.5
            x0 = np.clip(np.floor(fx).astype(int), 0, n - 2)
            y0 = np.clip(np.floor(fy).astype(int), 0, n - 2)
            dx, dy = fx - x0, fy - y0
            v = (tile[y0, x0] * (1 - dx) * (1 - dy)
                 + tile[y0, x0 + 1] * dx * (1 - dy)
                 + tile[y0 + 1, x0] * (1 - dx) * dy
                 + tile[y0 + 1, x0 + 1] * dx * dy)
            dem[sel] = v
        if np.isnan(dem).any():
            from scipy import ndimage as _nd
            idx = _nd.distance_transform_edt(np.isnan(dem), return_distances=False,
                                             return_indices=True)
            dem = dem[tuple(idx)]
        dem = np.nan_to_num(dem)

        # despeckle then normalise
        from scipy import ndimage as _nd
        med = _nd.median_filter(dem, size=3)
        spike = np.abs(dem - med) > 45.0
        dem[spike] = med[spike]

        lo, hi = float(dem.min()), float(dem.max())
        g = O.Grid(((dem - lo) / max(hi - lo, 1e-9)).astype(np.float32),
                   lo, hi, size_m,
                   {"source": "Copernicus DEM GLO-30 (AWS Open Data)",
                    "center": {"lat": lat, "lon": lon},
                    "bbox": {"lat_min": lat_min, "lat_max": lat_max,
                             "lon_min": lon_min, "lon_max": lon_max},
                    "suggested_relief_m": round(hi - lo, 2)})
        files = {
            "png16": O.write_heightmap_png(g, os.path.join(out_dir, f"{name}.png")),
            "r32": O.write_r32(g, os.path.join(out_dir, f"{name}.r32")),
            "preview": O.save_hillshade_preview(
                g, os.path.join(out_dir, f"{name}_preview.png")),
            "meta": O.write_meta(g, os.path.join(out_dir, f"{name}.json")),
        }
        return _json({"ok": True, "files": files, "grid": g.summary(),
                      "hint": f"use relief_m={round(hi - lo, 2)} and "
                              f"width_m={size_m} in gaea_create_project"})

    @mcp.tool()
    def gaea_write_erosion_mask(
        out_path: str,
        protect_from: str = "",
        protect_mask: str = "",
        threshold: float = 0.5,
        dilate: int = 4,
    ) -> str:
        """Write a 16-bit grayscale erosion mask for Erosion2's Mask input.

        Either give prevent_from (a heightfield; everything BELOW threshold *
        max is protected, i.e. a flat low area such as a lake) or protect_mask
        (an image whose nonzero pixels are protected).

        The mask is deliberately 16-bit: Gaea mis-reads 8-bit/palette PNGs and
        then applies the mask only partially."""
        if protect_mask:
            m = O.read_grid(protect_mask).data > threshold
        elif protect_from:
            m = O.read_grid(protect_from).data < threshold
        else:
            return _json({"ok": False,
                          "error": "give either protect_from or protect_mask"})
        from scipy import ndimage as _nd
        if dilate:
            m = _nd.binary_dilation(m, iterations=int(dilate))
        O.write_mask_png(~m, out_path)     # 1 = erode (land), 0 = protected
        return _json({"ok": True, "path": os.path.abspath(out_path),
                      "protected_pixels": int(m.sum()),
                      "note": "1.0 = erode, 0.0 = protected"})

    @mcp.tool()
    def gaea_render_preview(heightmap: str, out_path: str,
                            azimuth: float = 315.0, altitude: float = 45.0,
                            z_factor: float = 6.0, max_size: int = 1600) -> str:
        """Render a hillshade preview of a heightfield (PNG/TIF/R32) so you can
        see what you produced without opening Gaea."""
        g = O.read_grid(heightmap)
        sh = O.hillshade(g, azimuth=azimuth, altitude=altitude, z_factor=z_factor)
        from PIL import Image as _I
        im = _I.fromarray((sh * 255).astype(np.uint8))
        if max_size and im.width > max_size:
            im = im.resize((max_size, max_size), _I.LANCZOS)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        im.save(out_path)
        return _json({"ok": True, "path": os.path.abspath(out_path),
                      "grid": g.summary()})

    @mcp.tool()
    def gaea_open_in_gui(project_path: str) -> str:
        """Open a project in the Gaea GUI (useful for the human to inspect).
        Launches Gaea if it is not running. Never use `Gaea.exe -Path`, which
        crashes on this build."""
        inst = find_gaea()
        if inst is None:
            return _json({"ok": False, "error": "Gaea not found"})
        if not G.running_gaea_pids():
            if not G.launch_gui(inst):
                return _json({"ok": False, "error": "Gaea GUI would not start"})
        try:
            uia = Uia.ensure()
            ok, problems = G.open_project(inst, project_path, uia)
        except UiaError as e:
            return _json({"ok": False, "error": str(e)})
        return _json({"ok": ok, "validation_problems": problems})

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
