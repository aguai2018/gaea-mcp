"""Self-test: author a project from scratch and check it is structurally sound.

Uses the system Python (numpy/PIL/scipy are already present there); the MCP
transport needs the `mcp` package, but the authoring/validation logic does not.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import numpy as np  # noqa: E402
from gaea_mcp import outputs as O  # noqa: E402
from gaea_mcp import terrain as T  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest")
os.makedirs(OUT, exist_ok=True)
FAIL = []


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


print("=== 1. synthetic heightfield ===")
g = O.fractal_dem(size=512, width_m=12000.0, relief_m=415.0, seed=7)
s = g.summary()
check("fractal grid", s["grid"] == [512, 512], str(s["grid"]))
check("relief preserved", abs(s["relief_m"] - 415.0) < 1e-6, str(s["relief_m"]))
check("ratio correct", abs(s["compression_ratio"] - 415.0 / 12000.0) < 1e-5)
png = O.write_heightmap_png(g, os.path.join(OUT, "fractal.png"))
r32 = O.write_r32(g, os.path.join(OUT, "fractal.r32"))
meta = O.write_meta(g, os.path.join(OUT, "fractal.json"))
check("png written", os.path.getsize(png) > 1000, f"{os.path.getsize(png)} B")
check("r32 size", os.path.getsize(r32) == 512 * 512 * 4,
      f"{os.path.getsize(r32)} B (want {512*512*4})")

print("\n=== 2. round-trip through the readers ===")
back = O.read_grid(png)
check("png reads back as float01", back.data.dtype == np.float32)
check("png range sane", 0.0 <= back.data.min() and back.data.max() <= 1.0 and back.data.max() > 0.99,
      f"{back.data.min():.4f}..{back.data.max():.4f}")
br = O.read_grid(r32)
check("r32 grid parsed square", br.data.shape == (512, 512), str(br.data.shape))

print("\n=== 3. 16-bit greyscale mask (the trap) ===")
mask = g.data < 0.05
mp = O.write_mask_png(~mask, os.path.join(OUT, "mask.png"))
from PIL import Image
im = Image.open(mp)
arr = np.array(im)
check("mask mode is 16-bit capable", im.mode in ("I", "I;16"), im.mode)
check("mask is 16-bit data", arr.dtype in (np.int32, np.uint16), str(arr.dtype))
check("mask bimodal", set(np.unique(arr).tolist()) <= {0, 65535},
      str(sorted(set(np.unique(arr).tolist()))[:4]))

print("\n=== 4. author a project ===")
proj = os.path.join(OUT, "SelfTest.terrain")
b = T.ProjectBuilder("selftest", width_m=12000.0, height_m=415.0)
src = b.add("File", "Source", node_id=100)
b.set_file(src, "fractal.png", relative=True)
adj = b.add("Adjust", "HeightScale", node_id=105)
b.connect(src, adj)
er = b.add("Erosion2", "Erosion", node_id=110)
b.connect(adj, er)
mn = b.add("File", "ErosionMask", node_id=170)
b.set_file(mn, "mask.png", relative=True)
b.connect(mn, er, dst_port="Mask")
ex = b.add("Export", "HeightmapExport", node_id=101, Format="PNG16")
b.set_export(ex, os.path.join(OUT, "out", "heightmap"), "PNG16")
b.connect(er, ex)
tint = b.add("Tint", "TerrainColor", node_id=130, RenderIntentOverride="Color")
b.connect(er, tint)
ex2 = b.add("Export", "ColorExport", node_id=150, Format="PNG8",
            RenderIntentOverride="Color")
b.set_export(ex2, os.path.join(OUT, "out", "color"), "PNG8")
b.connect(tint, ex2)
b.save(proj, resolution=4096, destination=r"<Builds>\[Filename]\[+++]")

audit = b.audit()
check("audit clean", audit["ok"], json.dumps(audit["problems"]))
check("node count", audit["node_count"] == 7, str(audit["node_count"]))
check("terrain ratio", abs(audit["terrain_definition"]["compression_ratio"]
                           - 415.0 / 12000.0) < 1e-6)

print("\n=== 5. the $id graph is well formed ===")
doc = json.loads(open(proj, encoding="utf-8-sig").read())
ids, refs = [], []


def walk(o):
    if isinstance(o, dict):
        if "$id" in o:
            ids.append(str(o["$id"]))
        if "$ref" in o:
            refs.append(str(o["$ref"]))
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


walk(doc)
check("no duplicate $id", len(ids) == len(set(ids)),
      f"{len(ids)} ids, {len(set(ids))} unique")
check("all $ref resolve", not (set(refs) - set(ids)),
      str(sorted(set(refs) - set(ids))[:5]))

print("\n=== 6. unsafe node types are refused ===")
for bad in ("Thermal2", "SatMap", "WaterColor"):
    try:
        b.add(bad, "nope")
        check(f"refuses {bad}", False, "was allowed")
    except ValueError:
        check(f"refuses {bad}", True)

print("\n=== 7. Export path validation ===")
b2 = T.ProjectBuilder("t", 1000, 100)
q = b2.add("Constant", "C", node_id=100)
e = b2.add("Export", "E", node_id=101)
b2.connect(q, e)
b2.set_export(e, os.path.join(OUT, "bad.png"))     # deliberately wrong
bad_audit = b2.audit()
check("flags OutputPath with extension",
      any("must NOT include an extension" in p for p in bad_audit["problems"]),
      json.dumps(bad_audit["problems"]))

print("\n=== 8. Erosion2 Version guard ===")
b3 = T.ProjectBuilder("t", 1000, 100)
b3.add("Constant", "C", node_id=100)
er3 = b3.add("Erosion2", "E", node_id=110, Version=None)
b3.set_params(er3, Version=None)
del b3._nodes[110]["Version"]
a3 = b3.audit()
check("flags missing Version",
      any("missing Version: 2" in p for p in a3["problems"]),
      json.dumps(a3["problems"]))

print("\n" + "=" * 60)
if FAIL:
    print(f"{len(FAIL)} CHECK(S) FAILED: {FAIL}")
    sys.exit(1)
print("ALL CHECKS PASSED")
print("project:", proj)
