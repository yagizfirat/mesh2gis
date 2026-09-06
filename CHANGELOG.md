# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-06

### Added
- **The output schema now adapts to the data.** `STOREYS` and `FLOOR_AREA` are
  written only when a storey height is supplied; a mesh that is not a building
  gets neither, instead of a column of zeros. Geometric columns are always
  written because they mean something for any solid.
- `--keep-tags` / `keep_tags=`: carry the reader's own labels (OBJ material,
  group, object; DXF layer, entity type) through as extra columns.
- `SURF_AREA` / `surface_area`: total area of every face. Unlike volume it is
  defined for open meshes, so it is the one size measure that always works.
- `BlockAttrs.storeys` and `.floor_area` are now `int | None` / `float | None`.
  **BREAKING** for callers that assumed `0`.
- `types.clean_label`, shared by grouping and tag output so the internal
  `usemtl` run counter never reaches a table.
- `FLOOR_AREA` / `floor_area`: total floor area, summed per part as each part's
  own footprint times its own storeys. `BASE_AREA * STOREYS` overcounts whenever
  a building has a setback storey.
- `N_PARTS` / `n_parts`: how many source blocks a feature was merged from.
- `Block.parts`, recording the blocks a merged block was built from.

### Fixed
- Merged features are now measured part by part instead of over the union.
  Stacking two solids face to face produces a non-manifold union whose volume
  cannot be integrated, so merged features previously reported `closed = false`
  and `volume = 0`. On a 4,116-building test set the closed count went from
  1,412 to 4,115 and total volume now matches the unmerged conversion.

## [0.1.0] - 2026-09-04

Initial release.

### Added
- OBJ reader preserving `usemtl` / `g` / `o` as per-face tags and keeping n-gons intact.
- DXF reader (`[dxf]` extra) for `3DFACE`, polyface meshes, `MESH`, and thickness-extruded closed polylines.
- Six grouping strategies plus `merge_stacked` for base-volume-and-setback models.
- Y-up to Z-up conversion by rotation, preserving handedness and face winding.
- Per-feature attributes: height, storeys, footprint area, enclosed volume, and a
  `closed` flag. Volume is integrated about the block centroid (not the coordinate
  origin, which destroys precision in a projected CRS) and reported only for
  closed surfaces. Closedness is tested on welded coordinates so unwelded CAD
  exports are not all reported as open.
- ESRI multipatch shapefile writer with `.prj` sidecar.
- GeoPackage writer (MultiPolygonZ) implemented directly on `sqlite3`.
- Cleaned OBJ writer for CAD round-trips.
- Built-in WKT for Turkish TUREF TM zones (EPSG 5253–5259); full EPSG support via the `[crs]` extra.
- `mesh2gis inspect` and `mesh2gis convert` command line interface.
