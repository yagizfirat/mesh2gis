"""Strategies for splitting a polygon soup into output features.

Which strategy is right depends entirely on how the CAD package exported the
file, and there is no reliable way to detect it from the geometry alone:

* ``"o"`` / ``"g"`` -- honoured when the exporter wrote real object or group
  names. Cleanest when available.
* ``"usemtl"`` -- Rhino's OBJ exporter emits no ``g``/``o`` at all and instead
  repeats ``usemtl`` once per object, so the material run becomes the de facto
  object separator.
* ``"layer"`` -- the natural key for DXF.
* ``"connected"`` -- topological fallback: faces sharing a vertex belong
  together. Correct regardless of tags, but merges buildings that were snapped
  to a shared wall.
* ``"single"`` -- everything in one feature.

:func:`merge_stacked` is a separate post-pass: mass models routinely split one
building into a main volume plus setback storeys, and those need recombining
before per-building storey counts mean anything.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from mesh2gis.types import Block, Mesh, clean_label

__all__ = ["GroupBy", "group", "merge_stacked"]

GroupBy = Literal["o", "g", "usemtl", "layer", "connected", "single"]


def group(mesh: Mesh, by: GroupBy = "usemtl", *, drop_empty: bool = True) -> list[Block]:
    """Split ``mesh`` into blocks.

    Args:
        mesh: Source mesh.
        by: Grouping strategy. See module docstring.
        drop_empty: Skip blocks that ended up with no faces.

    Returns:
        Blocks in stable order -- tag order of first appearance, or ascending
        lowest-face-index for ``"connected"``.

    Raises:
        ValueError: If ``by`` is not a known strategy, or names a tag the mesh
            does not carry.
    """
    if by == "single":
        blocks = [Block(mesh, np.arange(mesh.n_faces), label="all")]
    elif by == "connected":
        blocks = _group_connected(mesh)
    elif by in {"o", "g", "usemtl", "layer"}:
        blocks = _group_by_tag(mesh, by)
    else:
        msg = f"unknown grouping strategy {by!r}"
        raise ValueError(msg)

    if drop_empty:
        blocks = [b for b in blocks if len(b) > 0]
    return blocks


def _group_by_tag(mesh: Mesh, tag: str) -> list[Block]:
    values = mesh.tags.get(tag)
    if values is None:
        available = ", ".join(sorted(mesh.tags)) or "none"
        msg = f"mesh has no {tag!r} tag (available: {available})"
        raise ValueError(msg)
    if all(v is None for v in values):
        msg = f"tag {tag!r} is empty for every face; try a different --group-by"
        raise ValueError(msg)

    order: list[str | None] = []
    buckets: dict[str | None, list[int]] = {}
    for i, v in enumerate(values):
        if v not in buckets:
            buckets[v] = []
            order.append(v)
        buckets[v].append(i)

    return [
        Block(mesh, np.asarray(buckets[v], dtype=np.int64), label=clean_label(v)) for v in order
    ]


def _group_connected(mesh: Mesh) -> list[Block]:
    """Union-find over shared vertices."""
    parent = np.arange(mesh.n_vertices, dtype=np.int64)

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = int(parent[root])
        while parent[x] != root:
            parent[x], x = root, int(parent[x])
        return root

    for face in mesh.faces:
        first = find(int(face[0]))
        for v in face[1:]:
            r = find(int(v))
            if r != first:
                parent[r] = first

    buckets: dict[int, list[int]] = {}
    for fi, face in enumerate(mesh.faces):
        buckets.setdefault(find(int(face[0])), []).append(fi)

    ordered = sorted(buckets.values(), key=lambda ids: ids[0])
    return [
        Block(mesh, np.asarray(ids, dtype=np.int64), label=f"part_{n}")
        for n, ids in enumerate(ordered, start=1)
    ]


def merge_stacked(
    blocks: list[Block],
    *,
    tolerance: float = 0.05,
    overlap_ratio: float = 0.3,
) -> list[Block]:
    """Merge blocks that sit vertically on top of one another.

    A block rests on exactly one roof, so each block is matched to the *single*
    best-overlapping candidate beneath it rather than to every candidate that
    qualifies. Merging with all of them chains neighbouring buildings together
    through a shared storey level: with the all-candidates rule this data
    collapsed 8,604 blocks into 4,116 features, 194 of which held two to four
    separate buildings; picking the best match alone yields 4,333, against 4,326
    blocks that actually sit on the ground.

    A candidate qualifies when its top elevation meets the block's base within
    ``tolerance`` and their XY footprints overlap by at least ``overlap_ratio``
    of the smaller one. Both conditions are needed: elevation alone merges
    unrelated neighbours on flat ground, footprint alone merges terraced rows.

    This remains a heuristic on bounding boxes, not true footprint geometry.
    Buildings that share a wall and a storey height can still be merged. Check
    ``n_parts`` in the output before trusting per-building figures -- anything
    above three is worth a look.

    Args:
        blocks: Blocks to merge, typically from :func:`group`.
        tolerance: Vertical gap tolerance in model units.
        overlap_ratio: Minimum XY bounding-box overlap, as a fraction of the
            smaller box's area.

    Returns:
        Merged blocks, ordered by lowest constituent face index. Each carries
        its source blocks in ``parts`` so attributes can be measured per part.
    """
    if not blocks:
        return []

    mesh = blocks[0].mesh
    boxes = np.asarray([b.bounds() for b in blocks], dtype=np.float64)
    parent = list(range(len(blocks)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Index candidates by quantised top elevation so each block only compares
    # against the few whose roofs could actually meet its base.
    step = max(tolerance, 1e-9)
    by_top: dict[int, list[int]] = {}
    for idx, box in enumerate(boxes):
        by_top.setdefault(round(float(box[5]) / step), []).append(idx)

    for i, box in enumerate(boxes):
        key = round(float(box[2]) / step)
        best: int | None = None
        best_overlap = overlap_ratio
        for offset in (-1, 0, 1):
            for j in by_top.get(key + offset, ()):
                if j == i or abs(boxes[j, 5] - box[2]) > tolerance:
                    continue
                score = _xy_overlap(box, boxes[j])
                if score > best_overlap:
                    best, best_overlap = j, score
        if best is None:
            continue
        ri, rj = find(i), find(best)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    merged: dict[int, list[Block]] = {}
    for i, b in enumerate(blocks):
        merged.setdefault(find(i), []).append(b)

    groups = sorted(merged.values(), key=lambda ps: int(min(p.face_indices[0] for p in ps)))
    out: list[Block] = []
    for n, parts in enumerate(groups, start=1):
        ids = np.sort(np.concatenate([p.face_indices for p in parts]))
        keep = list(parts) if len(parts) > 1 else []
        label = parts[0].label if len(parts) == 1 else f"feature_{n}"
        out.append(Block(mesh, ids, label=label, parts=keep))
    return out


def _xy_overlap(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection area of two XY boxes over the smaller box's area."""
    dx = min(a[3], b[3]) - max(a[0], b[0])
    dy = min(a[4], b[4]) - max(a[1], b[1])
    if dx <= 0 or dy <= 0:
        return 0.0
    inter = dx * dy
    area_a = (a[3] - a[0]) * (a[4] - a[1])
    area_b = (b[3] - b[0]) * (b[4] - b[1])
    smaller = min(area_a, area_b)
    return float(inter / smaller) if smaller > 0 else 0.0
