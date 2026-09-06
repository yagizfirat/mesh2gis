"""Derived attributes for each output feature.

Two implementation details are easy to get wrong and hard to notice:

Volume is integrated about each block's own centroid rather than the coordinate
origin. In a projected CRS the origin sits millions of metres away, so the
divergence-theorem terms reach ~1e13 while the answer is ~1e3 and the
subtraction destroys most of the significant digits.

Closedness matches edges on welded coordinates, not on vertex indices. CAD
exporters routinely give every face its own copy of its corners -- a Rhino box
arrives with 24 vertices, not 8 -- so an index-based test reports every solid in
the file as open.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from mesh2gis.types import clean_label

if TYPE_CHECKING:
    from mesh2gis.types import Block

__all__ = ["BlockAttrs", "compute"]

_FLAT_TOL = 1e-6
_MANIFOLD = 2
_WELD_DP = 4


@dataclass(slots=True)
class BlockAttrs:
    """Per-feature measurements.

    Attributes:
        block_id: 1-based ordinal.
        label: Grouping label the block came from, if any.
        z_min: Lowest elevation.
        z_max: Highest elevation.
        height: ``z_max - z_min``.
        storeys: ``height / storey_height``, rounded, or ``None`` when no
            storey height was supplied. ``None`` rather than zero because a
            mesh that is not a building has no storey count, and writers omit
            the column entirely rather than filling it with a meaningless zero.
        base_area: Total area of horizontal faces lying at ``z_min`` -- the
            ground footprint, not the sum of every storey.
        floor_area: Total floor area: each part's own footprint multiplied by
            its own storey count, summed. This differs from
            ``base_area * storeys`` whenever the storeys have different
            footprints, which is exactly what a setback storey is. ``None``
            when no storey height was supplied.
        surface_area: Total area of every face. Meaningful for any mesh,
            closed or not -- unlike volume, which needs a closed surface.
        tags: Source tags carried through from the reader (material, group,
            object, DXF layer). Empty unless the caller asked for them.
        n_parts: How many source blocks this feature was merged from; 1 when it
            was not merged.
        volume: Enclosed volume by the divergence theorem, or ``0.0`` when the
            surface is not closed -- an open surface has no well-defined volume
            and the raw sum would be meaningless.
        closed: Whether every edge is shared by exactly two faces. False means
            the block is an open surface or has stray geometry, and ``volume``
            should not be trusted.
        n_faces: Face count.
    """

    block_id: int
    label: str | None
    z_min: float
    z_max: float
    height: float
    base_area: float
    surface_area: float
    volume: float
    closed: bool
    n_parts: int
    n_faces: int
    storeys: int | None = None
    floor_area: float | None = None
    tags: dict[str, str | None] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return the measurements as a plain dict."""
        return asdict(self)


def compute(
    block: Block,
    block_id: int,
    *,
    storey_height: float | None = None,
) -> BlockAttrs:
    """Measure one block.

    Args:
        block: Block to measure.
        block_id: 1-based ordinal written to the output table.
        storey_height: Floor-to-floor height in model units. When given,
            ``storeys`` is derived from it. Mass models from urban design work
            are usually built on a fixed grid (3.0 m, 3.2 m), and the height
            histogram of the input is the quickest way to confirm which.

    Returns:
        The measurements for ``block``.
    """
    if block.parts:
        return _aggregate(block, block_id, storey_height=storey_height)

    pts = block.vertices()
    if pts.size == 0:
        return BlockAttrs(
            block_id=block_id,
            label=block.label,
            z_min=0.0,
            z_max=0.0,
            height=0.0,
            base_area=0.0,
            surface_area=0.0,
            volume=0.0,
            closed=False,
            n_parts=0,
            n_faces=0,
            storeys=_storeys(0.0, storey_height),
            floor_area=None if storey_height is None else 0.0,
            tags=_tags_of(block),
        )

    z_min = float(pts[:, 2].min())
    z_max = float(pts[:, 2].max())
    height = z_max - z_min

    storeys = _storeys(height, storey_height)

    origin = pts.mean(axis=0)

    base_area = 0.0
    surface_area = 0.0
    volume = 0.0
    weld: dict[tuple[float, float, float], int] = {}
    edges: Counter[tuple[int, int]] = Counter()

    def weld_id(vertex_index: int) -> int:
        x, y, z = block.mesh.vertices[vertex_index]
        key = (round(float(x), _WELD_DP), round(float(y), _WELD_DP), round(float(z), _WELD_DP))
        return weld.setdefault(key, len(weld))

    for face in block.faces:
        coords = block.mesh.vertices[face]
        z = coords[:, 2]
        if z.max() - z.min() < _FLAT_TOL and abs(float(z.mean()) - z_min) < _FLAT_TOL:
            base_area += _shoelace(coords[:, 0], coords[:, 1])
        surface_area += _polygon_area(coords - origin)
        volume += _signed_volume(coords - origin)
        welded = [weld_id(int(i)) for i in face]
        for a, b in zip(welded, welded[1:] + welded[:1], strict=True):
            if a != b:
                edges[(min(a, b), max(a, b))] += 1

    closed = bool(edges) and all(count == _MANIFOLD for count in edges.values())

    return BlockAttrs(
        block_id=block_id,
        label=block.label,
        z_min=round(z_min, 4),
        z_max=round(z_max, 4),
        height=round(height, 4),
        base_area=round(base_area, 4),
        surface_area=round(surface_area, 4),
        volume=round(abs(volume), 4) if closed else 0.0,
        closed=closed,
        n_parts=1,
        n_faces=len(block),
        storeys=storeys,
        floor_area=None if storeys is None else round(base_area * storeys, 4),
        tags=_tags_of(block),
    )


def _aggregate(block: Block, block_id: int, *, storey_height: float | None) -> BlockAttrs:
    """Measure a merged block by measuring its parts and combining the results.

    Never integrate over the union: two solids stacked face to face share an
    interface whose edges belong to four faces, so the union is not a closed
    manifold and has no computable volume. The parts are closed solids, and
    their volumes simply add.

    Height and storeys describe the whole building. Base area is the ground
    footprint only -- the parts that actually sit at the lowest elevation --
    because that is what a coverage ratio means. Floor area sums each part's own
    footprint times its own storeys, which is the only way a setback storey is
    counted at its real size.
    """
    parts = [compute(p, 0, storey_height=storey_height) for p in block.parts]

    z_min = min(p.z_min for p in parts)
    z_max = max(p.z_max for p in parts)
    height = z_max - z_min
    storeys = _storeys(height, storey_height)

    ground = sum(p.base_area for p in parts if abs(p.z_min - z_min) < _FLAT_TOL)
    closed = all(p.closed for p in parts)
    floor_area = None if storeys is None else round(sum(p.floor_area or 0.0 for p in parts), 4)

    return BlockAttrs(
        block_id=block_id,
        label=block.label,
        z_min=round(z_min, 4),
        z_max=round(z_max, 4),
        height=round(height, 4),
        base_area=round(ground, 4),
        surface_area=round(sum(p.surface_area for p in parts), 4),
        volume=round(sum(p.volume for p in parts), 4) if closed else 0.0,
        closed=closed,
        n_parts=len(parts),
        n_faces=sum(p.n_faces for p in parts),
        storeys=storeys,
        floor_area=floor_area,
        tags=_tags_of(block) or _tags_of(block.parts[0]),
    )


def _storeys(height: float, storey_height: float | None) -> int | None:
    """Storey count, or None when the caller gave no storey height.

    None is not zero: a mesh that is not a building has no storey count, and
    writers omit the column rather than filling it with a misleading zero.
    """
    if storey_height is None:
        return None
    if storey_height <= 0 or height <= 0:
        return 0
    return round(height / storey_height)


def _tags_of(block: Block) -> dict[str, str | None]:
    """Source tag values for a block, one per tag the reader recorded.

    A block usually carries one value per tag -- that is what grouping keys on --
    but a block grouped by one key can span several values of another. The most
    common value wins, which keeps the column useful without pretending the
    block is uniform.
    """
    tags = block.mesh.tags
    if not tags or block.face_indices.size == 0:
        return {}
    out: dict[str, str | None] = {}
    for name, values in tags.items():
        seen = Counter(values[int(i)] for i in block.face_indices)
        out[name] = clean_label(seen.most_common(1)[0][0])
    return out


def _polygon_area(coords: np.ndarray) -> float:
    """Area of a planar polygon in 3D, via Newell's method."""
    rolled = np.roll(coords, -1, axis=0)
    normal = np.cross(coords, rolled).sum(axis=0)
    return float(np.linalg.norm(normal)) / 2.0


def _shoelace(x: np.ndarray, y: np.ndarray) -> float:
    """Planar polygon area, sign-independent."""
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _signed_volume(coords: np.ndarray) -> float:
    """Contribution of one face to the enclosed volume, via a triangle fan."""
    total = 0.0
    a = coords[0]
    for i in range(1, coords.shape[0] - 1):
        b, c = coords[i], coords[i + 1]
        total += float(np.dot(a, np.cross(b, c))) / 6.0
    return total
