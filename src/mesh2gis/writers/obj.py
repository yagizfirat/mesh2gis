"""OBJ writer, for round-tripping a cleaned model back to CAD.

Blocks are written as ``g`` groups, giving the file the object separators the
original may have lacked. Coordinates are written with 6 decimal places; at
projected-CRS magnitudes that is far below survey precision but still well
inside float64, so nothing is lost that the format could carry anyway.

Beware the reverse trip: many OBJ readers parse into float32, which at a
northing of ~4.5e6 quantises to roughly half a metre. Prefer the shapefile or
GeoPackage writers for anything that will be measured.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from os import PathLike

    from mesh2gis.types import Block

__all__ = ["write_obj"]


def write_obj(
    blocks: list[Block],
    path: str | PathLike[str],
    *,
    precision: int = 6,
    header: str | None = None,
) -> int:
    """Write blocks to a single OBJ file.

    Only vertices actually referenced by the blocks are emitted, so this doubles
    as a way to drop orphaned geometry and free-form curve data.

    Args:
        blocks: Features to write; all must share one mesh.
        path: Output ``.obj`` path.
        precision: Decimal places for coordinates.
        header: Optional comment written at the top of the file.

    Returns:
        Number of groups written.

    Raises:
        ValueError: If ``blocks`` reference more than one mesh.
    """
    if not blocks:
        Path(path).write_text("# mesh2gis: no geometry\n", encoding="utf-8")
        return 0

    mesh = blocks[0].mesh
    if any(b.mesh is not mesh for b in blocks):
        msg = "all blocks must share the same mesh"
        raise ValueError(msg)

    used = np.unique(np.concatenate([b.vertex_indices() for b in blocks]))
    remap = np.full(mesh.n_vertices, -1, dtype=np.int64)
    remap[used] = np.arange(used.size, dtype=np.int64)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fmt = f"%.{precision}f"

    with out.open("w", encoding="utf-8") as fh:
        fh.write(f"# {header}\n" if header else "# written by mesh2gis\n")
        for x, y, z in mesh.vertices[used]:
            fh.write(f"v {fmt % x} {fmt % y} {fmt % z}\n")
        for n, block in enumerate(blocks, start=1):
            name = block.label or f"block_{n:06d}"
            fh.write(f"g {name}\n")
            for face in block.faces:
                fh.write("f " + " ".join(str(int(remap[i]) + 1) for i in face) + "\n")

    return len(blocks)
