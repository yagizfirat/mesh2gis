# mesh2gis

Turn CAD mass models into GIS-ready 3D features.

Reads OBJ and DXF meshes, splits them into per-object features, derives building
attributes, and writes **ESRI multipatch shapefiles** or **GeoPackages** — with
no ArcGIS licence, no GDAL, and no compiled dependency beyond NumPy.

```bash
pip install mesh2gis
```

## Why

A mass model exported from Rhino, SketchUp or AutoCAD is a polygon soup. Getting
it into GIS usually means either an ArcGIS licence (for `Import 3D Files`) or a
GDAL toolchain — and even then, the whole file typically lands as a *single*
feature, because CAD exporters rarely write the object separators GIS tools look
for. That makes the result useless for analysis: no per-building height, no
storey count, no attribute table.

`mesh2gis` handles the awkward parts:

- **Object separation.** Six grouping strategies, because every exporter marks
  object boundaries differently — and Rhino marks them with repeated `usemtl`
  runs and no `g`/`o` at all.
- **Axis conversion.** Y-up to Z-up via a rotation, not a coordinate swap, so
  face winding and surface normals survive.
- **Georeferencing.** Offset, scale and CRS in one pass; Turkish TUREF/TM zones
  are built in, everything else via optional `pyproj`.
- **An output schema that fits the data.** Extent, footprint, surface area,
  volume and a `CLOSED` flag are written for every mesh, because they mean
  something for any solid. Storey count and floor area appear only when you
  supply a storey height — a bridge, a machine part or a terrain surface has no
  storeys, and a column of zeros is worse than no column. Pass
  `--storey-height auto` and the grid is inferred from the data. `--keep-tags` carries
  the reader's own labels through.
- **Measurements you can trust.** Merged features are measured part by part, so
  a setback storey counts at its own size rather than the ground footprint's.

## Quick start

Inspect before you convert — this tells you which options you need:

```bash
mesh2gis inspect blocks.obj --group-by usemtl
```

```
source     blocks.obj
vertices   401,436
faces      235,429
  arity    3-gon: 175,111, 4-gon: 60,318
bounds X   437,170.750 … 441,986.688   (span 4,815.938)
bounds Y   -0.250 … 28.800             (span 29.050)
bounds Z   -4,537,329.078 … -4,534,573.043
up axis    y (guess)
tags
  usemtl     8,606 distinct
  g          absent
  o          absent
group_by=usemtl: 8,604 features
  heights  3.2: 4,274, 9.6: 2,167, 12.8: 1,042, 16.0: 642, 19.2: 222
```

That height histogram clustering on multiples of 3.2 is the storey height.
Now convert:

```bash
mesh2gis convert blocks.obj blocks.shp \
    --up y --group-by usemtl --epsg 5254 --storey-height 3.2
```

Or from Python:

```python
import mesh2gis

mesh2gis.convert(
    "blocks.obj",
    "blocks.gpkg",
    up="y",
    group_by="usemtl",
    epsg=5254,
    storey_height=3.2,
    merge_stacks=True,
)
```

Step by step, when you need to look at the mesh in between:

```python
mesh = mesh2gis.read_obj("blocks.obj")
mesh = mesh2gis.transform(mesh, up="y", offset=(436372.01, -4533303.26, 0.0))
blocks = mesh2gis.group(mesh, by="usemtl")
blocks = mesh2gis.merge_stacked(blocks)
mesh2gis.write_multipatch(blocks, "blocks.shp", epsg=5254, storey_height=3.2)
```

## Grouping strategies

| `--group-by`  | Use when |
|---------------|----------|
| `o`, `g`      | The exporter wrote real object or group names. Cleanest. |
| `usemtl`      | Rhino OBJ — material runs are the only object separator. |
| `layer`       | DXF, where the layer is the natural key. |
| `connected`   | No usable tags. Topological; merges buildings sharing a wall. |
| `single`      | You want one feature for the whole mesh. |

`--merge-stacks` is a separate pass for models where one building is a base
volume plus setback storeys. It merges blocks whose footprints overlap *and*
whose top and base elevations meet. It is a heuristic — verify the result before
trusting per-building storey counts.

## Output formats

| Target   | Geometry | Notes |
|----------|----------|-------|
| `.shp`   | MultiPatch (triangle fans) | True 3D solids in ArcGIS. Writes a `.prj` when `--epsg` is given. |
| `.gpkg`  | MultiPolygonZ | Opens in QGIS, GDAL and PostGIS with no extensions. |
| `.obj`   | Wavefront OBJ | Cleaned round-trip back to CAD, with `g` groups added. |

Textures are **not** carried into multipatch or GeoPackage output. For untextured
mass models — the case this package targets — nothing is lost. If your mesh is
photogrammetry with baked textures, use ArcGIS's own `Import 3D Files` instead.

## Known limits

- **OBJ output loses precision on re-read.** Many OBJ parsers use float32; at a
  northing of ~4.5 × 10⁶ that quantises to roughly half a metre. Shapefile and
  GeoPackage store float64. Use `.obj` output for CAD round-trips, not for
  measurement.
- **`merge_stacked` is heuristic.** Buildings sharing both a wall and a storey
  height can be merged incorrectly.

- **Volume is only computed for closed surfaces.** Open blocks get `volume = 0`
  and `closed = false` rather than a number that looks real. Closedness is
  tested on welded coordinates, so unwelded CAD exports are handled correctly.
- No texture, material or LOD support. No scene-layer (SLPK/I3S) output.

## Extras

```bash
pip install 'mesh2gis[dxf]'   # DXF reading (ezdxf)
pip install 'mesh2gis[crs]'   # full EPSG support (pyproj)
pip install 'mesh2gis[all]'
```

Without `[crs]`, EPSG codes 5253–5259 (Turkish TUREF 3-degree TM zones) and 4326
still resolve from a built-in table.

## Documentation

- [Kullanım kılavuzu (TR)](docs/KULLANIM.md) — full CLI and API reference,
  grouping strategies, georeferencing, recipes, troubleshooting
- [Yayınlama kılavuzu (TR)](docs/YAYINLAMA.md) — release and maintenance

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy
```

## License

MIT
