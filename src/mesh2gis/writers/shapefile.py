"""ESRI multipatch shapefile writer.

Each face becomes its own ``TRIANGLE_FAN`` part. A fan of *k* vertices is
*k - 2* triangles, so triangles and quads both pass through untouched and
n-gons are fanned from their first vertex -- correct for the convex faces CAD
mass models produce, and no triangulation pass is needed.

Multipatch is the only shapefile geometry ArcGIS treats as a true 3D solid.
Writing it keeps texture-free mass models fully usable without an ArcGIS
licence, which the ``Import 3D Files`` geoprocessing route would otherwise
require.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import shapefile as shp

from mesh2gis.attrs import compute
from mesh2gis.crs import UnknownCRSError, wkt_for
from mesh2gis.types import MIN_FACE_VERTICES

if TYPE_CHECKING:
    from os import PathLike

    from mesh2gis.types import Block

__all__ = ["write_multipatch"]

_CORE_FIELDS = [
    ("BLOCK_ID", "N", 10, 0),
    ("LABEL", "C", 64, 0),
    ("Z_MIN", "F", 19, 4),
    ("Z_MAX", "F", 19, 4),
    ("HEIGHT", "F", 19, 4),
    ("BASE_AREA", "F", 19, 4),
    ("SURF_AREA", "F", 19, 4),
    ("VOLUME", "F", 19, 4),
    ("CLOSED", "L", 1, 0),
    ("N_PARTS", "N", 6, 0),
    ("N_FACES", "N", 10, 0),
]
_STOREY_FIELDS = [
    ("STOREYS", "N", 6, 0),
    ("FLOOR_AREA", "F", 19, 4),
]


def _tag_field_name(tag: str, taken: set[str]) -> str:
    """dBASE-safe, unique, 10-character column name for a source tag."""
    base = "".join(c if c.isalnum() else "_" for c in tag.upper())[:10] or "TAG"
    name, n = base, 1
    while name in taken:
        suffix = str(n)
        name = base[: 10 - len(suffix)] + suffix
        n += 1
    taken.add(name)
    return name


def write_multipatch(
    blocks: list[Block],
    path: str | PathLike[str],
    *,
    epsg: int | None = None,
    storey_height: float | None = None,
    keep_tags: bool = False,
) -> int:
    """Write blocks to a multipatch shapefile.

    The schema adapts to the data. Storey columns appear only when
    ``storey_height`` is given, because a mesh that is not a building has no
    storeys and a column of zeros is worse than no column. Source tags are
    written only when asked for.

    Args:
        blocks: Features to write.
        path: Output path; a ``.shp`` suffix is added or reused. Sidecar
            ``.shx``, ``.dbf`` and (with ``epsg``) ``.prj`` land alongside it.
        epsg: CRS for the ``.prj`` sidecar. Omit to write no ``.prj``, leaving
            the CRS undefined for the consumer to set.
        storey_height: Passed to :func:`mesh2gis.attrs.compute`. Supplying it
            adds the ``STOREYS`` and ``FLOOR_AREA`` columns.
        keep_tags: Also write one column per source tag (material, group,
            object, DXF layer), carrying the reader's own labels through.

    Returns:
        Number of features written. Blocks with no usable face are skipped.

    Raises:
        UnknownCRSError: If ``epsg`` cannot be resolved.
    """
    out = Path(path)
    if out.suffix.lower() == ".shp":
        out = out.with_suffix("")
    out.parent.mkdir(parents=True, exist_ok=True)

    prj_wkt = wkt_for(epsg) if epsg is not None else None

    fields = list(_CORE_FIELDS)
    if storey_height is not None:
        fields += _STOREY_FIELDS

    tag_names: dict[str, str] = {}
    if keep_tags and blocks:
        taken = {f[0] for f in fields}
        for tag in blocks[0].mesh.tags:
            tag_names[tag] = _tag_field_name(tag, taken)
            fields.append((tag_names[tag], "C", 64, 0))

    written = 0
    with shp.Writer(str(out), shapeType=shp.MULTIPATCH) as w:
        for name, ftype, size, dec in fields:
            w.field(name, ftype, size, dec)

        for i, block in enumerate(blocks, start=1):
            parts = []
            for face in block.faces:
                if face.size < MIN_FACE_VERTICES:
                    continue
                parts.append([list(map(float, p)) for p in block.mesh.vertices[face]])
            if not parts:
                continue

            a = compute(block, i, storey_height=storey_height)
            row: list[object] = [
                a.block_id,
                (a.label or "")[:64],
                a.z_min,
                a.z_max,
                a.height,
                a.base_area,
                a.surface_area,
                a.volume,
                a.closed,
                a.n_parts,
                a.n_faces,
            ]
            if storey_height is not None:
                row += [a.storeys, a.floor_area]
            row += [(a.tags.get(tag) or "")[:64] for tag in tag_names]

            w.multipatch(parts, [shp.TRIANGLE_FAN] * len(parts))
            w.record(*row)
            written += 1

    if prj_wkt is not None:
        out.with_suffix(".prj").write_text(prj_wkt, encoding="utf-8")

    return written


__all__ += ["UnknownCRSError"]
