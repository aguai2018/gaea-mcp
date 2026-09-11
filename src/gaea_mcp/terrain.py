"""
The `.terrain` schema, and authoring of projects that Gaea actually accepts.

Hard-won facts encoded here (all verified against Gaea 2.3.0.1):

1. A `.terrain` file is plain JSON using Newtonsoft's reference-preserving
   layout: every object carries `"$id"` (a unique string) and references use
   `{"$ref": "<id>"}`. `{"$values": [...]}` wraps collections.
   Hand-written files must therefore mint unique `$id`s per asset and point
   each port's `Parent` at its own node's `$id`.

2. Start from a skeleton written by the *same* Gaea series you are targeting.
   A skeleton from an older series makes Gaea run its migration path, which
   throws `Object reference not set to an instance of an object` at the first
   node that has parameters it does not recognise, and the error then
   propagates downstream so every consumer reports
   `The port In returned bad or bad or no data`. A 2.3-native skeleton avoids
   that entirely.

3. `Erosion2` MUST carry `Version: 2` and the small parameter set below.
   Omitting `Version` is what triggers the migration described in (2).

4. Bitmap output is the `Export` node, NOT `Mesher`. `Mesher` writes meshes.
   `Export` takes `Location: "Explicit"` and an `OutputPath` WITHOUT extension
   (Gaea appends the extension implied by `Format`).

5. A `File` node with `RelativePath: true` resolves against the *project*
   directory, so the data file must sit next to the `.terrain`.

6. To protect a region from erosion, give `Erosion2` a `Mask` input. That mask
   must be a 16-bit grayscale PNG: an 8-bit or palette PNG is mis-read as
   16-bit, and Gaea logs
       Array length doesn't conform Map resolution! Requested: N, Received: 2N
   and only applies the mask partially (the protected region still erodes).

7. Node types that rejected hand-authored parameters in 2.3.0.1 and are
   therefore avoided by this library: Thermal2, SatMap, WaterColor, and
   Combine when used without `RenderIntentOverride`.
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

NS = "QuadSpinner.Gaea.Nodes"

# ---------------------------------------------------------------- skeleton
# A minimal, 2.3-native project used as the structural template. It is written
# out in full (rather than read from an install) so authoring works on any
# machine and produces byte-identical container structure every time.
SKELETON: dict[str, Any] = {
    "$id": "1",
    "Assets": {
        "$id": "2",
        "$values": [{
            "$id": "3",
            "Terrain": {
                "$id": "4",
                "Id": "00000000-0000-0000-0000-000000000000",
                "Nodes": {"$id": "6"},
                "Groups": {"$id": "28"},
                "Notes": {"$id": "29"},
                "GraphTabs": {"$id": "33", "$values": [{
                    "$id": "34", "Name": "Graph 1", "Color": "Brass",
                    "ZoomFactor": 1.0,
                    "ViewportLocation": {"$id": "35", "X": 25000.0, "Y": 25000.0},
                }]},
                "Width": 5000.0,
                "Height": 2500.0,
                "Ratio": 0.5,
                "Regions": {"$id": "36", "$values": []},
            },
            "Automation": {
                "$id": "37",
                "Bindings": {"$id": "38", "$values": []},
                "Expressions": {"$id": "39"},
                "Variables": {"$id": "40"},
            },
            "BuildDefinition": {
                "$id": "41",
                "Type": "Standard",
                "Destination": "<Builds>\\[Filename]\\[+++]",
                "Resolution": 2048,
                "BakeResolution": 2048,
                "TileResolution": 1024,
                "BucketResolution": 2048,
                "NumberOfTiles": 3,
                "EdgeBlending": 0.25,
                "TileZeroIndex": True,
                "TilePattern": "_y%Y%_x%X%",
                "OrganizeFiles": "NodeSubFolder",
            },
            "State": {
                "$id": "42",
                "BakeResolution": 2048,
                "PreviewResolution": 1024,
                "HDResolution": 4096,
                "SelectedNode": 0,
                "NodeBookmarks": {"$id": "43", "$values": []},
                "Viewport": {"$id": "44",
                             "Camera": {"$id": "46"},
                             "RenderMode": "Realistic",
                             "AmbientOcclusion": True,
                             "Shadows": True},
            },
            "BuildProfiles": {"$id": "47"},
        }],
    },
    "Id": "00000000",
    "Branch": 1,
    "Metadata": {
        "$id": "48",
        "Name": "",
        "Description": "",
        "Version": "2.0.6.0",
        "Owner": "",
        "DateCreated": "2026-01-01 00:00:00Z",
        "DateLastBuilt": "2026-01-01 00:00:00Z",
        "DateLastSaved": "2026-01-01 00:00:00Z",
        "ModifiedVersion": "2.3.0.1",
    },
}

# --------------------------------------------------------- node vocabulary
# Short name -> (json property set, ordered port list)
# Port tuples are (Name, Type). "In" on a processor is required.
PORT_PRIMARY_IN = ("In", "PrimaryIn, Required")
PORT_PRIMARY_IN_OPT = ("In", "PrimaryIn")
PORT_PRIMARY_OUT = ("Out", "PrimaryOut")


@dataclass
class NodeSpec:
    short: str
    ports: list[tuple[str, str]]
    defaults: dict[str, Any] = field(default_factory=dict)
    note: str = ""


NODE_SPECS: dict[str, NodeSpec] = {
    "File": NodeSpec("File", [PORT_PRIMARY_IN_OPT, PORT_PRIMARY_OUT],
                     {"RelativePath": True},
                     "Loads a heightfield/mask/colour image. With "
                     "RelativePath=true the file must sit next to the .terrain."),
    "Adjust": NodeSpec("Adjust", [PORT_PRIMARY_IN, PORT_PRIMARY_OUT,
                                  ("Mask", "In")], {"NodeSize": "Small"},
                       "Safe generic processor; also the place to scale height."),
    "Erosion2": NodeSpec(
        "Erosion2",
        [PORT_PRIMARY_IN, PORT_PRIMARY_OUT, ("Mask", "In"),
         ("Flow", "Out"), ("Wear", "Out"), ("Deposits", "Out"),
         ("Precipitation", "In")],
        # The exact set 2.3.0.1 accepts. Version is mandatory.
        {"Duration": 40.0, "Downcutting": 0.2, "Seed": 12345,
         "Enable": True, "Version": 2},
        "Hydraulic erosion. MUST include Version:2 or Gaea migrates and dies."),
    "Height": NodeSpec("Height", [PORT_PRIMARY_IN, PORT_PRIMARY_OUT,
                                  ("Mask", "In")],
                       {"Falloff": 0.05, "NodeSize": "Standard"},
                       "Elevation band mask."),
    "Tint": NodeSpec("Tint", [PORT_PRIMARY_IN, PORT_PRIMARY_OUT],
                     {"RenderIntentOverride": "Color"},
                     "Two-colour ramp. Reliable colouriser in 2.3.0.1."),
    "Combine": NodeSpec(
        "Combine",
        [PORT_PRIMARY_IN, PORT_PRIMARY_OUT, ("Input2", "In"), ("Mask", "In"),
         ("Input3", "In"), ("Input4", "In")],
        {"PortCount": 2, "Ratio": 1.0, "Mode": "Max"},
        "Blend two maps. Include RenderIntentOverride when colour flows."),
    "Export": NodeSpec(
        "Export", [PORT_PRIMARY_IN, PORT_PRIMARY_OUT],
        {"Location": "Explicit", "Format": "PNG16"},
        "Bitmap export. OutputPath excludes the extension."),
    "Mesher": NodeSpec(
        "Mesher", [PORT_PRIMARY_IN, PORT_PRIMARY_OUT],
        {"Format": "GLB", "Scale": "Meter", "Topology": "Quads",
         "VerticesPerSide": 512, "ArtifactReduction": "Med",
         "CreateNormals": True, "CreateUVs": True},
        "Mesh export (GLB/OBJ/FBX). Not for bitmaps."),
    "Constant": NodeSpec("Constant", [PORT_PRIMARY_IN_OPT, PORT_PRIMARY_OUT],
                         {"Height": 0.5, "NodeSize": "Standard"},
                         "Flat plane at a fixed height."),
    "Blur": NodeSpec("Blur", [PORT_PRIMARY_IN, PORT_PRIMARY_OUT,
                              ("Mask", "In")], {},
                     "Smoothing. Parameter names vary by build - use defaults."),
}

# Node types that are known to reject hand-authored parameters on 2.3.0.1.
UNSAFE_NODES = {
    "Thermal2": "rejects hand-authored parameters (downstream ports go bad)",
    "SatMap": "rejects hand-authored parameters",
    "WaterColor": "needs a real water source; null-refs otherwise",
    "Lake": "parameter semantics undocumented; verify before use",
    "Sea": "parameter semantics undocumented; verify before use",
    "Rivers": "verify before use",
    "Thermal": "verify before use",
}

EXPORT_FORMATS = ["PNG8", "PNG16", "EXR", "TIFF", "TIFF16", "TIFF32",
                  "RAW16", "RAW32", "R32", "HDR"]
MESH_FORMATS = ["GLB", "OBJ", "FBX", "DAE", "STL"]


class ProjectBuilder:
    """Build a `.terrain` document node by node."""

    def __init__(self, name: str = "terrain", width_m: float = 5000.0,
                 height_m: float = 2500.0):
        self.doc = copy.deepcopy(SKELETON)
        self.doc["Metadata"]["Name"] = name
        self.doc["Metadata"]["Description"] = name
        self.doc["Id"] = uuid.uuid4().hex[:8]
        self._asset = self.doc["Assets"]["$values"][0]
        self.terrain = self._asset["Terrain"]
        uni = str(uuid.uuid4())
        self.terrain["Id"] = uni
        self._next_id = 1000
        self._nodes: dict[int, dict[str, Any]] = {}
        self._auto_id = 100
        self.set_extent(width_m, height_m)

    # ------------------------------------------------------------- helpers
    def _sid(self) -> str:
        self._next_id += 1
        return str(self._next_id)

    def set_extent(self, width_m: float, height_m: float) -> None:
        """Width = ground span in metres. Height = MAX ELEVATION RANGE in
        metres (not a Y size). Their ratio is Gaea's compression ratio."""
        self.terrain["Width"] = float(width_m)
        self.terrain["Height"] = float(height_m)
        self.terrain["Ratio"] = round(float(height_m) / float(width_m), 6)

    # --------------------------------------------------------------- nodes
    def add(self, short: str, name: str | None = None, node_id: int | None = None,
            x: float | None = None, y: float | None = None,
            **params: Any) -> int:
        if short in UNSAFE_NODES:
            raise ValueError(
                f"node type {short!r} is on the unsafe list: {UNSAFE_NODES[short]}")
        if short not in NODE_SPECS:
            raise ValueError(
                f"unknown node type {short!r}. Known: {sorted(NODE_SPECS)}")
        spec = NODE_SPECS[short]
        nid = node_id if node_id is not None else self._auto_id
        if node_id is None:
            self._auto_id += 1
        if nid in self._nodes:
            raise ValueError(f"node id {nid} already used")

        props = dict(spec.defaults)
        props.update(params)
        if short == "Export":
            props.setdefault("Format", "PNG16")

        node: dict[str, Any] = {"$id": self._sid(),
                                "$type": f"{NS}.{spec.short}, Gaea.Nodes"}
        node.update(props)
        node["Id"] = nid
        node["Name"] = name or f"{spec.short}{nid}"
        px = x if x is not None else 24000 + 500 * (len(self._nodes) % 12)
        py = y if y is not None else 25000 + 400 * (len(self._nodes) // 12)
        node["Position"] = {"$id": self._sid(), "X": float(px), "Y": float(py)}
        node["Ports"] = {"$id": self._sid(),
                         "$values": [{"$id": self._sid(), "Name": pn,
                                      "Type": pt, "IsExporting": True}
                                     for pn, pt in spec.ports]}
        for p in node["Ports"]["$values"]:
            p["Parent"] = {"$ref": node["$id"]}
        node["Modifiers"] = {"$id": self._sid(), "$values": []}
        self._nodes[nid] = node
        return nid

    def connect(self, src: int, dst: int, dst_port: str = "In",
                src_port: str = "Out") -> None:
        if src not in self._nodes:
            raise ValueError(f"no source node {src}")
        if dst not in self._nodes:
            raise ValueError(f"no destination node {dst}")
        port = self._port(dst, dst_port)
        if port is None:
            raise ValueError(
                f"node {dst} ({self._nodes[dst]['Name']}) has no port {dst_port!r}; "
                f"available: {[p['Name'] for p in self._nodes[dst]['Ports']['$values']]}")
        port["Record"] = {"$id": self._sid(), "From": src, "To": dst,
                          "FromPort": src_port, "ToPort": dst_port,
                          "IsValid": True}

    def _port(self, nid: int, name: str) -> dict[str, Any] | None:
        for p in self._nodes[nid]["Ports"]["$values"]:
            if p["Name"] == name:
                return p
        return None

    def set_params(self, nid: int, **params: Any) -> None:
        self._nodes[nid].update(params)

    def set_file(self, nid: int, filename: str, relative: bool = True,
                 is_rgb: bool = False) -> None:
        n = self._nodes[nid]
        n["FileName"] = filename
        n["RelativePath"] = relative
        if is_rgb:
            n["IsRGB"] = True

    def set_export(self, nid: int, output_path: str,
                   fmt: str | None = None) -> None:
        n = self._nodes[nid]
        n["Location"] = "Explicit"
        n["OutputPath"] = output_path
        if fmt:
            n["Format"] = fmt

    # ----------------------------------------------------------- finishing
    def finalise(self, resolution: int = 4096, destination: str | None = None,
                 selected: int | None = None,
                 notes_markdown: str | None = None) -> dict[str, Any]:
        t = self.terrain
        t["Nodes"] = {"$id": t["Nodes"]["$id"]}
        for nid, node in self._nodes.items():
            t["Nodes"][str(nid)] = node

        bd = self._asset["BuildDefinition"]
        bd["Resolution"] = resolution
        bd["BakeResolution"] = resolution
        if destination:
            bd["Destination"] = destination

        st = self._asset["State"]
        st["BakeResolution"] = resolution
        st["HDResolution"] = resolution
        st["SelectedNode"] = selected or (max(self._nodes) if self._nodes else 0)

        if notes_markdown:
            st_note = {"$id": self._sid(), "Id": 1, "Name": "Notes",
                       "Markdown": notes_markdown, "Color": "Brass",
                       "Position": {"$id": self._sid(), "X": 24000.0, "Y": 25800.0},
                       "Size": {"$id": self._sid(), "X": 420.0, "Y": 300.0},
                       "Type": "OnlyText"}
            t["Notes"] = {"$id": t["Notes"]["$id"], "1": st_note}
        return self.doc

    def save(self, path: str, **kw: Any) -> str:
        doc = self.finalise(**kw)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
        return path

    # ------------------------------------------------------------ auditing
    def audit(self) -> dict[str, Any]:
        """Offline structural check - mirrors what Gaea's loader complains about."""
        problems: list[str] = []
        warnings: list[str] = []

        # unique $id across the whole document
        ids: list[str] = []
        dangling: list[str] = []

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                if "$id" in o:
                    ids.append(str(o["$id"]))
                if "$ref" in o:
                    dangling.append(str(o["$ref"]))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(self.doc)
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            problems.append(f"duplicate $id values: {sorted(dupes)[:8]}")
        missing = sorted(set(dangling) - set(ids))
        if missing:
            problems.append(f"$ref targets that do not exist: {missing[:8]}")

        # required inputs connected, and sources exist
        for nid, node in self._nodes.items():
            for p in node["Ports"]["$values"]:
                if "Required" in p["Type"] and not p.get("Record"):
                    problems.append(
                        f"node {nid} ({node['Name']}): required port "
                        f"{p['Name']} is not connected")
                rec = p.get("Record")
                if rec and rec.get("From") not in self._nodes:
                    problems.append(
                        f"node {nid} ({node['Name']}): port {p['Name']} reads from "
                        f"unknown node {rec.get('From')}")

        # unsafe node types
        for nid, node in self._nodes.items():
            short = node["$type"].split(",")[0].rsplit(".", 1)[-1]
            if short in UNSAFE_NODES:
                warnings.append(f"node {nid} uses {short}: {UNSAFE_NODES[short]}")
            if short == "Erosion2" and node.get("Version") != 2:
                problems.append(
                    f"node {nid} Erosion2 is missing Version: 2 - Gaea will try to "
                    "migrate it and every downstream port will fail")

        # at least one export-ish sink
        shorts = [n["$type"].split(",")[0].rsplit(".", 1)[-1]
                  for n in self._nodes.values()]
        if not any(s in ("Export", "Mesher") for s in shorts):
            problems.append("no Export or Mesher node - the build would produce "
                            "nothing")
        for nid, node in self._nodes.items():
            short = node["$type"].split(",")[0].rsplit(".", 1)[-1]
            if short == "Export":
                if node.get("Location") != "Explicit":
                    warnings.append(f"node {nid} Export Location is "
                                    f"{node.get('Location')!r}; 'Explicit' needed "
                                    "for a predictable path")
                op = node.get("OutputPath", "")
                ext = os.path.splitext(op)[1]
                if ext:
                    problems.append(
                        f"node {nid} Export OutputPath must NOT include an "
                        f"extension (found {ext!r})")
                if node.get("Format") not in EXPORT_FORMATS:
                    warnings.append(f"node {nid} Export Format "
                                    f"{node.get('Format')!r} is not in the known "
                                    f"list {EXPORT_FORMATS}")

        return {
            "ok": not problems,
            "problems": problems,
            "warnings": warnings,
            "node_count": len(self._nodes),
            "node_types": sorted(set(shorts)),
            "terrain_definition": {
                "width_m": self.terrain["Width"],
                "height_m": self.terrain["Height"],
                "compression_ratio": self.terrain["Ratio"],
            },
        }


# --------------------------------------------------------------- reading
def load(path: str) -> tuple[dict[str, Any], dict[str, int]]:
    """Load a .terrain and summarise its graph."""
    doc = json.loads(open(path, encoding="utf-8-sig").read())
    asset = doc["Assets"]["$values"][0]
    terrain = asset["Terrain"]
    nodes = {}
    for k, n in terrain["Nodes"].items():
        if k.startswith("$"):
            continue
        nodes[int(n["Id"])] = n
    return doc, nodes


def summarise(path: str) -> dict[str, Any]:
    doc, nodes = load(path)
    asset = doc["Assets"]["$values"][0]
    terrain = asset["Terrain"]
    name = {i: n.get("Name") for i, n in nodes.items()}
    edges = []
    for i, n in nodes.items():
        for p in n["Ports"]["$values"]:
            r = p.get("Record")
            if r:
                edges.append({"from": r["From"], "to": r["To"],
                              "from_port": r["FromPort"], "to_port": r["ToPort"]})
    return {
        "path": path,
        "metadata": {k: v for k, v in doc["Metadata"].items()
                     if not k.startswith("$")},
        "terrain_definition": {
            "width_m": terrain.get("Width"),
            "height_m": terrain.get("Height"),
            "ratio": terrain.get("Ratio"),
        },
        "build_definition": {k: v for k, v in
                             asset.get("BuildDefinition", {}).items()
                             if not k.startswith("$")},
        "nodes": [{
            "id": i,
            "name": n.get("Name"),
            "type": n["$type"].split(",")[0].rsplit(".", 1)[-1],
            "params": {k: v for k, v in n.items()
                       if k not in ("$id", "$type", "Id", "Name", "Position",
                                    "Ports", "Modifiers")},
            "inputs_from": [e["from"] for e in edges if e["to"] == i],
        } for i in sorted(nodes)],
        "node_names": name,
        "edges": edges,
    }
