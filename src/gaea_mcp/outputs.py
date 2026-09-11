"""
Reading and writing the data files Gaea consumes and produces.

Gaea centrefields are normalised 0..1 and mapped to metres by the project's
own Terrain definition:

    norm = (metres - min_m) / (max_m - min_m)
    Terrain.Width  = ground span in metres
    Terrain.Height = max_m - min_m   (the relief, NOT a Y size)
    compression ratio = Height / Width

Conversions that matter in practice:

* Heightfield for `File`      -> 16-bit grayscale PNG (mode "I;16")
                                 or 32-bit float .r32 (headerless, LE)
* Erosion mask for `Erosion2` -> **16-bit grayscale** PNG.
  1.0 = erode here, 0.0 = protect. Landing this as 8-bit or palette makes Gaea
  read it as 16-bit; it logs
      Array length doesn't conform Map resolution! Requested: N, Received: 2N
  and applies the mask only partially, so the "protected" area still erodes.
* Anything meant to be perfectly flat (a lake surface) should be flattened in
  the source data *before* it reaches Gaea, because Erosion2 will otherwise
  roughen it.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


@dataclass
class Grid:
    """A normalised heightfield plus the georeference it belongs to."""
    data: np.ndarray          # float32, 0..1, row 0 = north
    min_m: float              # metres at value 0.0
    max_m: float              # metres at value 1.0
    width_m: float            # ground span (square)
    meta: dict[str, Any] = None

    @property
    def relief_m(self) -> float:
        return self.max_m - self.min_m

    @property
    def m_per_px(self) -> float:
        return self.width_m / self.data.shape[0]

    def to_metres(self) -> np.ndarray:
        return self.data * self.relief_m + self.min_m

    def flip_vertical(self) -> "Grid":
        return Grid(self.data[::-1].copy(), self.min_m, self.max_m,
                    self.width_m, self.meta)

    def summary(self) -> dict[str, Any]:
        d = self.data
        return {
            "grid": list(d.shape),
            "m_per_px": round(self.m_per_px, 3),
            "width_m": self.width_m,
            "elevation_min_m": round(self.min_m, 3),
            "elevation_max_m": round(self.max_m, 3),
            "relief_m": round(self.relief_m, 3),
            "compression_ratio": round(self.relief_m / self.width_m, 6),
            "normalised_min": float(d.min()),
            "normalised_max": float(d.max()),
            "normalised_mean": float(d.mean()),
        }


# --------------------------------------------------------------------- write
def write_heightmap_png(grid: Grid, path: str, bits: int = 16) -> str:
    """16-bit grayscale PNG - the format Gaea's File node handles best."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if bits == 16:
        u16 = np.clip(grid.data * 65535.0 + 0.5, 0, 65535).astype(np.uint16)
        Image.fromarray(u16.astype(np.int32), mode="I").save(path, format="PNG")
    else:
        u8 = np.clip(grid.data * 255.0 + 0.5, 0, 255).astype(np.uint8)
        Image.fromarray(u8, mode="L").save(path, format="PNG")
    return path


def write_r32(grid: Grid, path: str) -> str:
    """Headerless little-endian float32, values 0..1 (Gaea's own RAW)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(grid.data.astype("<f4").tobytes())
    return path


def write_mask_png(mask: np.ndarray, path: str) -> str:
    """mask: float/bool array, 1 = selected. Always 16-bit grayscale."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    m = np.clip(np.asarray(mask, dtype=np.float32), 0.0, 1.0)
    u16 = (m * 65535.0 + 0.5).astype(np.uint16)
    Image.fromarray(u16.astype(np.int32), mode="I").save(path, format="PNG")
    return path


def write_meta(grid: Grid, path: str, extra: dict[str, Any] | None = None) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    meta = dict(grid.meta or {})
    meta.update(grid.summary())
    if extra:
        meta.update(extra)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    return path


# ---------------------------------------------------------------------- read
def read_grid(path: str) -> Grid:
    """Read a heightfield from PNG/TIFF/EXR-free formats, .r32 or .raw."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".r32":
        raw = np.fromfile(path, dtype="<f4")
        n = int(round(math.sqrt(raw.size)))
        if n * n != raw.size:
            raise ValueError(f"{path}: {raw.size} floats is not a square grid")
        return Grid(raw.reshape(n, n).astype(np.float32), 0.0, 1.0, 1000.0)
    if ext in (".raw", ".r16"):
        raw = np.fromfile(path, dtype="<u2")
        n = int(round(math.sqrt(raw.size)))
        if n * n != raw.size:
            raise ValueError(f"{path}: {raw.size} ushorts is not a square grid")
        return Grid((raw.reshape(n, n).astype(np.float32) / 65535.0),
                    0.0, 1.0, 1000.0)
    if ext in (".png", ".tif", ".tiff"):
        im = Image.open(path)
        a = np.array(im).astype(np.float32)
        if a.ndim == 3:
            a = a[..., 0]
        mx = 65535.0 if a.max() > 255.5 else 255.0
        return Grid(a / mx, 0.0, 1.0, 1000.0)
    raise ValueError(f"unsupported heightfield format: {ext}")


def read_report(path: str) -> dict[str, Any]:
    return json.loads(open(path, encoding="utf-8-sig").read())


def scan_log_for_faults(log_path: str) -> dict[str, list[str]]:
    """Extract the lines that actually explain a failed build."""
    faults = {"errors": [], "warnings": [], "invalid_nodes": [], "migration": []}
    if not os.path.isfile(log_path):
        return faults
    for line in open(log_path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if " ERR " in line:
            faults["errors"].append(s)
        elif " WRN " in line:
            faults["warnings"].append(s)
        if "did not validate" in s or "reported:" in s:
            faults["invalid_nodes"].append(s)
        if "is old. Attempting to migrate" in s or "Migrating" in s:
            faults["migration"].append(s)
    return faults


# ------------------------------------------------------------ synthetic DEMs
def fractal_dem(size: int = 1024, width_m: float = 8000.0,
                relief_m: float = 1500.0, seed: int = 1,
                octaves: int = 8, base_freq: float = 2.0) -> Grid:
    """
    A deterministic fractal heightfield, useful as a fallback when no real DEM
    is available. Value-noise fBm with a mild ridge term.
    """
    rng = np.random.default_rng(seed)

    def value_noise(res: int) -> np.ndarray:
        g = rng.random((res + 1, res + 1), dtype=np.float32)
        g[-1, :] = g[0, :]
        g[:, -1] = g[:, 0]
        ys = np.linspace(0, res, size, endpoint=False)
        xs = np.linspace(0, res, size, endpoint=False)
        y0 = np.floor(ys).astype(int)
        x0 = np.floor(xs).astype(int)
        ty = (ys - y0)[:, None]
        tx = (xs - x0)[None, :]
        sy = ty * ty * (3 - 2 * ty)
        sx = tx * tx * (3 - 2 * tx)
        a = g[np.ix_(y0, x0)]
        b = g[np.ix_(y0, x0 + 1)]
        c = g[np.ix_(y0 + 1, x0)]
        d = g[np.ix_(y0 + 1, x0 + 1)]
        top = a * (1 - sx) + b * sx
        bot = c * (1 - sx) + d * sx
        return top * (1 - sy) + bot * sy

    total = np.zeros((size, size), dtype=np.float32)
    amp, norm, freq = 1.0, 0.0, base_freq
    for _ in range(octaves):
        total += amp * value_noise(max(2, int(freq)))
        norm += amp
        amp *= 0.5
        freq *= 2.0
    n = total / norm
    n = (n - n.min()) / max(n.max() - n.min(), 1e-9)
    # mild ridging for mountain-like crests, then re-stretch so the field
    # genuinely spans 0..1 (otherwise relief_m overstates the real range)
    n = 0.75 * n + 0.25 * (1.0 - np.abs(2.0 * n - 1.0))
    n = (n - n.min()) / max(n.max() - n.min(), 1e-9)
    return Grid(n.astype(np.float32), 0.0, relief_m, width_m,
                {"source": "fractal_dem", "seed": seed})


def hillshade(grid: Grid, azimuth: float = 315.0, altitude: float = 45.0,
              z_factor: float = 6.0) -> np.ndarray:
    z = grid.to_metres()
    px = grid.m_per_px
    gy, gx = np.gradient(z, px, px)
    slope = np.arctan(z_factor * np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, al = math.radians(azimuth), math.radians(altitude)
    sh = (math.sin(al) * np.cos(slope)
          + math.cos(al) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(sh, 0.0, 1.0)


def save_hillshade_preview(grid: Grid, path: str, max_size: int = 1600) -> str:
    sh = hillshade(grid)
    im = Image.fromarray((sh * 255).astype(np.uint8))
    if im.width > max_size:
        im = im.resize((max_size, max_size), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    im.save(path)
    return path
