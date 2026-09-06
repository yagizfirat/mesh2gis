"""Core data model shared by readers, grouping and writers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["MIN_FACE_VERTICES", "Block", "Mesh", "clean_label"]


def clean_label(value: str | None) -> str | None:
    """Strip the run counter the OBJ reader appends to repeated `usemtl` names.

    Rhino repeats one material name once per object, so the reader appends
    ``#1``, ``#2`` ... to keep the runs apart. That suffix is bookkeeping and
    must never reach the output table.
    """
    if value is None:
        return None
    head, sep, tail = value.rpartition("#")
    return head if sep and tail.isdigit() else value


MIN_FACE_VERTICES = 3

_XYZ = 3


@dataclass(slots=True)
class Mesh:
    """A polygon soup: shared vertex array plus faces of arbitrary arity.

    Faces are kept as a list of index arrays rather than an ``(F, 3)`` matrix
    because CAD exports mix triangles, quads and n-gons freely, and multipatch
    triangle fans can consume them without triangulation.

    Attributes:
        vertices: ``(N, 3)`` float64 array of coordinates.
        faces: ``F`` arrays of vertex indices, each of length >= 3.
        tags: Per-face labels keyed by source concept -- ``"usemtl"``, ``"g"``,
            ``"o"``, ``"layer"``. Each value is a list of length ``F``.
    """

    vertices: np.ndarray
    faces: list[np.ndarray] = field(default_factory=list)
    tags: dict[str, list[str | None]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Coerce vertices to float64 and check tag lengths."""
        self.vertices = np.asarray(self.vertices, dtype=np.float64)
        if self.vertices.ndim != 2 or self.vertices.shape[1] != _XYZ:  # noqa: PLR2004
            msg = f"vertices must be (N, 3), got {self.vertices.shape}"
            raise ValueError(msg)
        for name, values in self.tags.items():
            if len(values) != len(self.faces):
                msg = f"tag {name!r} has {len(values)} entries but mesh has {len(self.faces)} faces"
                raise ValueError(msg)

    @property
    def n_vertices(self) -> int:
        """Number of vertices in the shared array."""
        return int(self.vertices.shape[0])

    @property
    def n_faces(self) -> int:
        """Number of faces."""
        return len(self.faces)

    def bounds(self) -> tuple[float, float, float, float, float, float]:
        """Return ``(xmin, ymin, zmin, xmax, ymax, zmax)``."""
        if self.n_vertices == 0:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        lo = self.vertices.min(axis=0)
        hi = self.vertices.max(axis=0)
        return (
            float(lo[0]),
            float(lo[1]),
            float(lo[2]),
            float(hi[0]),
            float(hi[1]),
            float(hi[2]),
        )

    def face_vertices(self, index: int) -> np.ndarray:
        """Return the ``(k, 3)`` coordinates of face ``index``."""
        result: np.ndarray = self.vertices[self.faces[index]]
        return result


@dataclass(slots=True)
class Block:
    """One output feature: a subset of a mesh's faces.

    Blocks come out of :mod:`mesh2gis.grouping`. A block never owns vertices --
    it indexes into the parent mesh so that grouping stays cheap on meshes with
    millions of vertices.

    ``parts`` records the blocks a merged block was built from. It matters for
    measurement: stacking two solids face to face produces a union whose
    interface edges are shared by four faces, so the union is not a closed
    manifold and its volume cannot be integrated. Measuring the parts first and
    summing the results avoids the problem entirely, and is also the only way to
    get floor area right when the storeys have different footprints.
    """

    mesh: Mesh
    face_indices: np.ndarray
    label: str | None = None
    parts: list[Block] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Coerce face indices to int64."""
        self.face_indices = np.asarray(self.face_indices, dtype=np.int64)

    def __len__(self) -> int:
        """Number of faces in this block."""
        return int(self.face_indices.size)

    @property
    def faces(self) -> Iterator[np.ndarray]:
        """Iterate the block's faces as vertex-index arrays."""
        for i in self.face_indices:
            yield self.mesh.faces[int(i)]

    def vertex_indices(self) -> np.ndarray:
        """Unique vertex indices touched by this block."""
        if self.face_indices.size == 0:
            return np.empty(0, dtype=np.int64)
        return np.unique(np.concatenate([self.mesh.faces[int(i)] for i in self.face_indices]))

    def vertices(self) -> np.ndarray:
        """Coordinates of the vertices this block touches."""
        result: np.ndarray = self.mesh.vertices[self.vertex_indices()]
        return result

    def bounds(self) -> tuple[float, float, float, float, float, float]:
        """Return ``(xmin, ymin, zmin, xmax, ymax, zmax)`` for this block."""
        pts = self.vertices()
        if pts.size == 0:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        return (
            float(lo[0]),
            float(lo[1]),
            float(lo[2]),
            float(hi[0]),
            float(hi[1]),
            float(hi[2]),
        )
