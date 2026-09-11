# The `.terrain` file format

A `.terrain` file is **plain JSON** serialised by Newtonsoft with reference
preservation. Nothing about it is documented by QuadSpinner — everything below
was derived by reading files that Gaea itself wrote, then confirming that
hand-authored files with the same shape load cleanly.

## Skeleton

```jsonc
{
  "$id": "1",
  "Assets": { "$id": "2", "$values": [ {        // one asset = one terrain
      "$id": "3",
      "Terrain": {
        "$id": "4",
        "Id": "<GUID>",
        "Nodes":     { "$id": "6" },              // node id (as a string) -> node
        "Groups":    { "$id": "28" },
        "Notes":     { "$id": "29" },
        "GraphTabs": { "$id": "33", "$values": [ ... ] },
        "Width":  12000.0,                        // ground span, metres
        "Height": 415.0,                          // elevation SPAN, metres
        "Ratio":  0.034583,                       // Height / Width
        "Regions": { "$id": "36", "$values": [] }
      },
      "Automation":      { "$id": "37", "Bindings": {...}, "Expressions": {...},
                           "Variables": {...} },
      "BuildDefinition": { "$id": "41", "Type": "Standard",
                           "Destination": "<Builds>\\[Filename]\\[+++]",
                           "Resolution": 4096, "BakeResolution": 4096,
                           "TileResolution": 1024, "BucketResolution": 2048,
                           "NumberOfTiles": 3, "EdgeBlending": 0.25,
                           "TileZeroIndex": true,
                           "TilePattern": "_y%Y%_x%X%",
                           "OrganizeFiles": "NodeSubFolder" },
      "State":           { "$id": "42", "BakeResolution": 4096,
                           "PreviewResolution": 1024, "HDResolution": 4096,
                           "SelectedNode": 101,
                           "NodeBookmarks": { "$id": "43", "$values": [] },
                           "Viewport": { "$id": "44", "Camera": { "$id": "46" },
                                         "RenderMode": "Realistic",
                                         "AmbientOcclusion": true,
                                         "Shadows": true } },
      "BuildProfiles":   { "$id": "47" }
  } ] },
  "Id": "6f3a91b2",
  "Branch": 1,
  "Metadata": { "$id": "48", "Name": "", "Description": "",
                "Version": "2.0.6.0",           // schema family
                "Owner": "",
                "DateCreated": "...", "DateLastBuilt": "...", "DateLastSaved": "...",
                "ModifiedVersion": "2.3.0.1" }  // build that wrote it last
}
```

## The `$id` graph — the part that breaks hand-written files

Every object carries a unique `"$id"` **string**. References use
`{"$ref": "<id>"}`. Collections are `{"$id": "...", "$values": [ ... ]}`.

Two rules you must satisfy:

1. **All `$id` values in the document must be unique.** Mint them from a
   counter that starts above anything already present.
2. **Each port's `Parent` must point at its own node's `$id`.**
   Getting this wrong is a silent failure — Gaea loads, then misbehaves.

A port that is *connected* gains a `Record`:

```jsonc
{
  "$id": "71",
  "Name": "In",
  "Type": "PrimaryIn, Required",     // "Required" => the build fails if unconnected
  "Record": { "$id": "72", "From": 110, "To": 101,
              "FromPort": "Out", "ToPort": "In", "IsValid": true },
  "IsExporting": true,
  "Parent": { "$ref": "70" }         // the *node* object's $id
}
```

Note `From`/`To` use the **node id** (the integer `Id`), not the `$id` string.

`IsExporting` appears on every port of every node in files Gaea writes, so it is
**not** an export marker. Exporting is done by `Export`/`Mesher` nodes.

## Node object

```jsonc
"101": {                                  // key is str(node Id)
  "$id": "70",
  "$type": "QuadSpinner.Gaea.Nodes.Export, Gaea.Nodes",
  "Format": "PNG16",                      // node parameters live beside $type
  "Location": "Explicit",
  "OutputPath": "D:/out/terrain_heightmap",
  "Id": 101,
  "Name": "HeightmapExport",
  "Position": { "$id": ... , "X": 25600.0, "Y": 25400.0 },
  "Ports":    { "$id": ..., "$values": [ /* port objects */ ] },
  "Modifiers":{ "$id": ..., "$values": [] }
}
```

## Skeleton generation matters

**Start from a skeleton written by the same Gaea series you are targeting.**
A skeleton from an older series carries `Metadata.Version` like `2.0.5.2` and
Gaea will run its migration path, which throws

```
WRN <Node> is old. Attempting to migrate.
INF File was last saved with 2.0.5.2. Migrating to updated format...
ERR <id> - <Node> failed: Object reference not set to an instance of an object.
```

and then every downstream node reports `The port In returned bad or no data`.
A skeleton with `Version: "2.0.6.0"` / `ModifiedVersion: "2.3.0.1"` avoids this
entirely. The toolkit ships such a skeleton inline in `terrain.py`.

## Reverse-engineering a file you are unsure about

The reliable procedure, in order:

1. Open the project **in the GUI** and save it. Gaea rewrites it canonically —
   diff the before/after to see what it objected to.
2. Check `Data\Autosaves\` for migration backups Gaea keeps.
3. Copy a node you need from a **shipped example** (`<install>\Examples\*.terrain`)
   or from a project this machine has successfully built.
4. Only then hand-author, and validate in Gaea immediately.

## Data-file conventions

| Purpose | Format | Note |
|---|---|---|
| Heightfield input | 16-bit greyscale PNG, or `.r32` | `.r32` = headerless LE float32, 0..1 |
| Erosion mask | **16-bit greyscale PNG** | 8-bit/palette is mis-read; mask applied partially |
| Bitmap output | `Export` node | `PNG8` colour, `PNG16`/`EXR` height |
| Mesh output | `Mesher` node | `GLB`, `OBJ`, `FBX`, … |

`.raw` = headerless LE `uint16` (0..65535). Both `.raw` and `.r32` are square
grids whose side is `sqrt(bytes / bytes_per_sample)`.
