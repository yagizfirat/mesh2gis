"""DXF reader for 3D face geometry (``ezdxf`` extra).

Handles the entity types CAD mass models actually ship in: ``3DFACE``,
``POLYLINE`` in polyface-mesh flavour, ``MESH``, and ``LWPOLYLINE``/``POLYLINE``
closed profiles that carry a thickness (the AutoCAD way of extruding a
footprint). Layer names become the per-face ``layer`` tag, which is usually the
right grouping key for CAD data.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from mesh2gis.types import MIN_FACE_VERTICES, Mesh

if TYPE_CHECKING:
    from os import PathLike

__all__ = ["read_dxf"]

_MISSING_EZDXF = (
    "Reading DXF requires the 'dxf' extra. Install it with: pip install 'mesh2gis[dxf]'"
)


def read_dxf(
    path: str | PathLike[str],
    *,
    layers: list[str] | None = None,
    extrude_thickness: bool = True,
) -> Mesh:
    """Read 3D geometry from a DXF file.

    Args:
        path: Path to the ``.dxf`` file.
        layers: If given, only entities on these layers are read.
        extrude_thickness: If true, closed polylines carrying a non-zero
            ``thickness`` are extruded into solids. AutoCAD-authored mass models
            often store buildings this way rather than as real 3D faces.

    Returns:
        A mesh with a per-face ``layer`` tag and an ``entity`` tag naming the
        source DXF entity type.

    Raises:
        ImportError: If ``ezdxf`` is not installed.
        FileNotFoundError: If ``path`` does not exist.
    """
    try:
        import ezdxf  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(_MISSING_EZDXF) from exc

    p = Path(path)
    if not p.is_file():
        msg = f"DXF file not found: {p}"
        raise FileNotFoundError(msg)

    doc = ezdxf.readfile(str(p))  # type: ignore[attr-defined]
    msp = doc.modelspace()

    verts: list[tuple[float, float, float]] = []
    faces: list[np.ndarray] = []
    tag_layer: list[str | None] = []
    tag_entity: list[str | None] = []
    index: dict[tuple[float, float, float], int] = {}

    def add_vertex(pt: Any) -> int:
        key = (round(float(pt[0]), 6), round(float(pt[1]), 6), round(float(pt[2]), 6))
        got = index.get(key)
        if got is None:
            got = len(verts)
            index[key] = got
            verts.append(key)
        return got

    def add_face(points: list[Any], layer: str, entity: str) -> None:
        deduped = _dedupe([add_vertex(pt) for pt in points])
        if deduped is None:
            return
        faces.append(np.asarray(deduped, dtype=np.int64))
        tag_layer.append(layer)
        tag_entity.append(entity)

    for e in msp:
        layer = str(getattr(e.dxf, "layer", "0"))
        if layers is not None and layer not in layers:
            continue
        dxftype = e.dxftype()

        if dxftype == "3DFACE":
            add_face([e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3], layer, dxftype)

        elif dxftype == "POLYLINE" and e.is_poly_face_mesh:  # type: ignore[attr-defined]
            for face in e.faces():  # type: ignore[attr-defined]
                add_face([v.dxf.location for v in face], layer, "POLYFACE")

        elif dxftype == "MESH":
            data = e.get_mesh_vertex_cache() if hasattr(e, "get_mesh_vertex_cache") else None
            mesh_verts = list(e.vertices) if hasattr(e, "vertices") else []
            if data is None and mesh_verts:
                for face in e.faces:  # type: ignore[attr-defined]
                    add_face([mesh_verts[i] for i in face], layer, "MESH")

        elif extrude_thickness and dxftype in {"LWPOLYLINE", "POLYLINE"}:
            _extrude(e, dxftype, layer, add_face)

    vertices = np.asarray(verts, dtype=np.float64) if verts else np.empty((0, 3))
    return Mesh(
        vertices=vertices,
        faces=faces,
        tags={"layer": tag_layer, "entity": tag_entity},
    )


def _dedupe(ids: list[int]) -> list[int] | None:
    """Drop repeated corners, or None if too few remain to form a face.

    AutoCAD writes triangles as 3DFACEs whose fourth corner repeats the third,
    so the duplicate has to go before the ring is usable.
    """
    out: list[int] = []
    for i in ids:
        if not out or out[-1] != i:
            out.append(i)
    if len(out) >= MIN_FACE_VERTICES and out[0] == out[-1]:
        out.pop()
    return out if len(out) >= MIN_FACE_VERTICES else None


def _extrude(entity: Any, dxftype: str, layer: str, add_face: Any) -> None:
    """Extrude a closed polyline with non-zero thickness into a closed solid.

    Winding decides which way each face points. The bottom faces down, so its
    ring must run clockwise seen from above; the top faces up and keeps the
    source order. Reversing the two inverts the solid and the computed volume
    comes out wrong rather than merely negative.
    """
    thickness = float(getattr(entity.dxf, "thickness", 0.0) or 0.0)
    if thickness == 0.0 or not getattr(entity, "closed", False):
        return

    if dxftype == "LWPOLYLINE":
        base_z = float(getattr(entity.dxf, "elevation", 0.0) or 0.0)
        ring = [(float(p[0]), float(p[1]), base_z) for p in entity.get_points("xy")]
    else:
        ring = [
            (float(v.dxf.location[0]), float(v.dxf.location[1]), float(v.dxf.location[2]))
            for v in entity.vertices
        ]
    if len(ring) < MIN_FACE_VERTICES:
        return
    if ring[0] == ring[-1]:
        ring.pop()
    if len(ring) < MIN_FACE_VERTICES:
        return

    top = [(x, y, z + thickness) for x, y, z in ring]
    add_face(list(reversed(ring)), layer, f"{dxftype}_BOTTOM")
    add_face(list(top), layer, f"{dxftype}_TOP")
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        add_face([ring[i], ring[j], top[j], top[i]], layer, f"{dxftype}_SIDE")
