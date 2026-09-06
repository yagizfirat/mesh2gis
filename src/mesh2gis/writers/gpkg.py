"""GeoPackage writer, implemented directly on ``sqlite3``.

A GeoPackage is a SQLite database with a documented schema, so writing one needs
no GDAL, no Fiona and no compiled dependency -- keeping this package installable
anywhere Python is. Geometry is emitted as ``MultiPolygonZ``: every face becomes
a single-ring polygon and the block's faces become one multipolygon.

``PolyhedralSurfaceZ`` would model a closed solid more faithfully, but it sits
outside GeoPackage's core geometry set and support across readers is patchy.
``MultiPolygonZ`` loads in QGIS, GDAL and PostGIS without extensions, which
matters more than formal exactness here.
"""

from __future__ import annotations

import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from mesh2gis.attrs import compute
from mesh2gis.crs import UnknownCRSError, wkt_for
from mesh2gis.types import MIN_FACE_VERTICES

if TYPE_CHECKING:
    from os import PathLike

    import numpy as np

    from mesh2gis.types import Block

__all__ = ["write_gpkg"]

_APPLICATION_ID = 0x47504B47
_USER_VERSION = 10300
_WKB_POLYGON_Z = 1003
_WKB_MULTIPOLYGON_Z = 1006

_SCHEMA = """
CREATE TABLE gpkg_spatial_ref_sys (
    srs_name TEXT NOT NULL,
    srs_id INTEGER NOT NULL PRIMARY KEY,
    organization TEXT NOT NULL,
    organization_coordsys_id INTEGER NOT NULL,
    definition TEXT NOT NULL,
    description TEXT
);
CREATE TABLE gpkg_contents (
    table_name TEXT NOT NULL PRIMARY KEY,
    data_type TEXT NOT NULL,
    identifier TEXT UNIQUE,
    description TEXT DEFAULT '',
    last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
    srs_id INTEGER,
    CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
        REFERENCES gpkg_spatial_ref_sys(srs_id)
);
CREATE TABLE gpkg_geometry_columns (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    geometry_type_name TEXT NOT NULL,
    srs_id INTEGER NOT NULL,
    z TINYINT NOT NULL,
    m TINYINT NOT NULL,
    CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name)
);
"""

_CORE_COLUMNS = [
    ("block_id", "INTEGER"),
    ("label", "TEXT"),
    ("z_min", "DOUBLE"),
    ("z_max", "DOUBLE"),
    ("height", "DOUBLE"),
    ("base_area", "DOUBLE"),
    ("surface_area", "DOUBLE"),
    ("volume", "DOUBLE"),
    ("closed", "INTEGER"),
    ("n_parts", "INTEGER"),
    ("n_faces", "INTEGER"),
]
_STOREY_COLUMNS = [
    ("storeys", "INTEGER"),
    ("floor_area", "DOUBLE"),
]


def _tag_column(tag: str, taken: set[str]) -> str:
    """SQL-safe, unique column name for a source tag."""
    base = "".join(c if c.isalnum() else "_" for c in tag.lower()) or "tag"
    if base[0].isdigit():
        base = f"t_{base}"
    name, n = base, 1
    while name in taken:
        name = f"{base}_{n}"
        n += 1
    taken.add(name)
    return name


def write_gpkg(
    blocks: list[Block],
    path: str | PathLike[str],
    *,
    epsg: int | None = None,
    layer: str = "blocks",
    storey_height: float | None = None,
    keep_tags: bool = False,
) -> int:
    """Write blocks to a GeoPackage as ``MultiPolygonZ`` features.

    The schema adapts to the data: storey columns appear only when
    ``storey_height`` is given, and source tags only when ``keep_tags`` is set.

    Args:
        blocks: Features to write.
        path: Output ``.gpkg`` path. An existing file is replaced.
        epsg: CRS of the coordinates. ``None`` records SRS id ``-1``
            (undefined cartesian).
        layer: Feature table name.
        storey_height: Passed to :func:`mesh2gis.attrs.compute`. Supplying it
            adds the ``storeys`` and ``floor_area`` columns.
        keep_tags: Also write one column per source tag.

    Returns:
        Number of features written.

    Raises:
        UnknownCRSError: If ``epsg`` cannot be resolved to WKT.
        ValueError: If ``layer`` is not a plain identifier.
    """
    if not layer.replace("_", "").isalnum():
        msg = f"layer name must be alphanumeric/underscore, got {layer!r}"
        raise ValueError(msg)

    srs_id = -1 if epsg is None else epsg
    definition = "undefined" if epsg is None else wkt_for(epsg)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)

    conn = sqlite3.connect(out)
    try:
        conn.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
        conn.execute(f"PRAGMA user_version = {_USER_VERSION}")
        conn.executescript(_SCHEMA)
        _seed_srs(conn, srs_id, definition, epsg)

        columns = list(_CORE_COLUMNS)
        if storey_height is not None:
            columns += _STOREY_COLUMNS
        tag_cols: dict[str, str] = {}
        if keep_tags and blocks:
            taken = {c[0] for c in columns} | {"fid", "geom"}
            for tag in blocks[0].mesh.tags:
                tag_cols[tag] = _tag_column(tag, taken)
                columns.append((tag_cols[tag], "TEXT"))

        cols = ", ".join(f"{n} {ty}" for n, ty in columns)
        conn.execute(
            f"CREATE TABLE {layer} (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB, {cols})"
        )
        conn.execute(
            "INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
            (layer, "geom", "MULTIPOLYGON", srs_id, 1, 0),
        )

        placeholders = ", ".join("?" * (len(columns) + 1))
        names = ", ".join(["geom", *[n for n, _ in columns]])
        insert = f"INSERT INTO {layer} ({names}) VALUES ({placeholders})"

        written = 0
        env = [float("inf"), float("inf"), float("-inf"), float("-inf")]
        for i, block in enumerate(blocks, start=1):
            rings = [
                block.mesh.vertices[face] for face in block.faces if face.size >= MIN_FACE_VERTICES
            ]
            if not rings:
                continue
            a = compute(block, i, storey_height=storey_height)
            blob, box = _gpkg_blob(rings, srs_id)
            env = [
                min(env[0], box[0]),
                min(env[1], box[1]),
                max(env[2], box[2]),
                max(env[3], box[3]),
            ]
            row = [
                blob,
                a.block_id,
                a.label,
                a.z_min,
                a.z_max,
                a.height,
                a.base_area,
                a.surface_area,
                a.volume,
                int(a.closed),
                a.n_parts,
                a.n_faces,
            ]
            if storey_height is not None:
                row += [a.storeys, a.floor_area]
            row += [a.tags.get(tag) for tag in tag_cols]
            conn.execute(insert, row)
            written += 1

        if written == 0:
            env = [0.0, 0.0, 0.0, 0.0]
        conn.execute(
            "INSERT INTO gpkg_contents "
            "(table_name, data_type, identifier, description, last_change, "
            " min_x, min_y, max_x, max_y, srs_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                layer,
                "features",
                layer,
                "written by mesh2gis",
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z",
                *env,
                srs_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return written


def _seed_srs(conn: sqlite3.Connection, srs_id: int, definition: str, epsg: int | None) -> None:
    """Insert the SRS rows a valid GeoPackage must contain."""
    rows = [
        ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
        ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
        ("WGS 84 geodetic", 4326, "EPSG", 4326, wkt_for(4326), None),
    ]
    if epsg is not None and epsg not in {-1, 0, 4326}:
        rows.append((f"EPSG:{epsg}", srs_id, "EPSG", epsg, definition, None))
    conn.executemany("INSERT OR REPLACE INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)", rows)


def _gpkg_blob(
    rings: list[np.ndarray], srs_id: int
) -> tuple[bytes, tuple[float, float, float, float]]:
    """Build a GeoPackage geometry blob holding one MultiPolygonZ."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    body = bytearray()
    body += struct.pack("<BII", 1, _WKB_MULTIPOLYGON_Z, len(rings))
    for coords in rings:
        pts = [(float(x), float(y), float(z)) for x, y, z in coords]
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        body += struct.pack("<BIII", 1, _WKB_POLYGON_Z, 1, len(pts))
        for x, y, z in pts:
            body += struct.pack("<ddd", x, y, z)
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)

    header = struct.pack("<ccBBi", b"G", b"P", 0, 0b0000_0011, srs_id)
    envelope = struct.pack("<dddd", min_x, max_x, min_y, max_y)
    return bytes(header + envelope + body), (min_x, min_y, max_x, max_y)


__all__ += ["UnknownCRSError"]
