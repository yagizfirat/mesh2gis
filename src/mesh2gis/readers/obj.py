"""Wavefront OBJ reader.

Deliberately hand-rolled rather than delegated to ``trimesh``: we must preserve
``usemtl`` / ``g`` / ``o`` boundaries as *per-face tags*, and we must keep n-gons
intact. Mesh libraries normalise both away, and for CAD mass models those tags
are frequently the only object separator present in the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from mesh2gis.types import MIN_FACE_VERTICES, Mesh

if TYPE_CHECKING:
    from os import PathLike

__all__ = ["read_obj"]

_FREEFORM = frozenset(
    {
        "cstype",
        "deg",
        "bmat",
        "step",
        "curv",
        "curv2",
        "surf",
        "parm",
        "trim",
        "hole",
        "scrv",
        "sp",
        "end",
    }
)


def read_obj(path: str | PathLike[str], *, encoding: str = "utf-8") -> Mesh:
    """Read an OBJ file into a :class:`~mesh2gis.types.Mesh`.

    Vertex coordinates are parsed as float64. Negative (relative) face indices
    are resolved against the vertex count seen so far, per the OBJ spec.

    Args:
        path: Path to the ``.obj`` file.
        encoding: Text encoding; decoding errors are replaced, not raised,
            because CAD exporters routinely emit stray bytes in comments.

    Returns:
        A mesh with ``usemtl``, ``g`` and ``o`` per-face tags.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If a face references an out-of-range vertex.
    """
    p = Path(path)
    if not p.is_file():
        msg = f"OBJ file not found: {p}"
        raise FileNotFoundError(msg)

    vertices: list[tuple[float, float, float]] = []
    faces: list[np.ndarray] = []
    tag_usemtl: list[str | None] = []
    tag_g: list[str | None] = []
    tag_o: list[str | None] = []

    cur_mtl: str | None = None
    cur_g: str | None = None
    cur_o: str | None = None
    mtl_run = 0

    with p.open("r", encoding=encoding, errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line[0] == "#":
                continue
            key, _, rest = line.partition(" ")
            if key == "v":
                parts = rest.split()
                vertices.append((float(parts[0]), float(parts[1]), float(parts[2])))
            elif key == "f":
                idx = _parse_face(rest, len(vertices))
                if idx.size >= MIN_FACE_VERTICES:
                    faces.append(idx)
                    tag_usemtl.append(f"{cur_mtl}#{mtl_run}" if cur_mtl is not None else None)
                    tag_g.append(cur_g)
                    tag_o.append(cur_o)
            elif key == "usemtl":
                cur_mtl = rest.strip() or None
                mtl_run += 1
            elif key == "g":
                cur_g = rest.strip() or None
            elif key == "o":
                cur_o = rest.strip() or None
            elif key in _FREEFORM:
                continue

    verts = np.asarray(vertices, dtype=np.float64) if vertices else np.empty((0, 3))
    if faces:
        highest = max(int(f.max()) for f in faces)
        if highest >= len(vertices):
            msg = (
                f"face references vertex {highest + 1} but only {len(vertices)} vertices were read"
            )
            raise ValueError(msg)

    return Mesh(
        vertices=verts,
        faces=faces,
        tags={"usemtl": tag_usemtl, "g": tag_g, "o": tag_o},
    )


def _parse_face(rest: str, n_vertices: int) -> np.ndarray:
    """Parse a face statement body into 0-based vertex indices."""
    out: list[int] = []
    for token in rest.split():
        head = token.partition("/")[0]
        if not head:
            continue
        i = int(head)
        out.append(i - 1 if i > 0 else n_vertices + i)
    return np.asarray(out, dtype=np.int64)
