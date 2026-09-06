"""Coordinate transforms applied between reading and writing.

The Y-up to Z-up conversion is a rotation, ``(X, Y, Z) = (x, -z, y)``, whose
determinant is +1. That keeps the coordinate system right-handed, so face
winding survives and with it multipatch normals and ArcGIS front/back face
shading. A naive ``(x, z, y)`` axis swap has determinant -1: it mirrors the
model and turns every surface inside out.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from mesh2gis.types import Mesh

__all__ = ["UpAxis", "detect_up_axis", "transform"]

UpAxis = Literal["y", "z"]

_Y_UP_TO_Z_UP = np.array(
    [
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0],
    ]
)


def detect_up_axis(mesh: Mesh) -> UpAxis:
    """Guess which axis is vertical from the mesh's aspect ratio.

    Buildings are far wider than they are tall, so the shortest axis of a mass
    model's bounding box is almost always the vertical one. This is a hint for
    interactive use -- always let the caller override it, since a single tall
    tower or a mesh clipped to one block breaks the assumption.

    Args:
        mesh: Mesh to inspect.

    Returns:
        ``"y"`` or ``"z"``.
    """
    _, ymin, zmin, _, ymax, zmax = mesh.bounds()
    span_y = ymax - ymin
    span_z = zmax - zmin
    return "y" if span_y < span_z else "z"


def transform(
    mesh: Mesh,
    *,
    up: UpAxis = "z",
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: float = 1.0,
) -> Mesh:
    """Return a copy of ``mesh`` in Z-up world coordinates.

    Operations apply in order: axis conversion, then scale, then offset. Scaling
    before offsetting means ``scale`` converts model units (e.g. millimetres to
    metres) without also multiplying the georeferencing shift.

    Args:
        mesh: Source mesh; not modified.
        up: Vertical axis of the *input*. ``"y"`` triggers conversion.
        offset: Added after scaling, to place a local model in world coordinates.
        scale: Uniform scale factor.

    Returns:
        A new mesh sharing face and tag data.

    Raises:
        ValueError: If ``scale`` is zero, or ``up`` is not ``"y"`` or ``"z"``.
    """
    if scale == 0:
        msg = "scale must be non-zero"
        raise ValueError(msg)
    if up not in {"y", "z"}:
        msg = f"up must be 'y' or 'z', got {up!r}"
        raise ValueError(msg)

    v = mesh.vertices
    if up == "y":
        v = v @ _Y_UP_TO_Z_UP.T
    if scale != 1.0:
        v = v * scale
    off = np.asarray(offset, dtype=np.float64)
    if off.any():
        v = v + off

    return Mesh(vertices=v, faces=list(mesh.faces), tags=dict(mesh.tags))
