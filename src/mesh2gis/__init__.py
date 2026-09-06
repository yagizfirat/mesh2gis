"""Turn CAD mass models into GIS-ready 3D features.

Reads OBJ and DXF meshes, splits them into per-object features, derives
building attributes and writes ESRI multipatch shapefiles or GeoPackages --
without ArcGIS, GDAL, or any compiled dependency.

Typical use::

    import mesh2gis

    mesh2gis.convert(
        "blocks.obj", "blocks.shp",
        up="y", group_by="usemtl", epsg=5254, storey_height=3.2,
    )

Or step by step, when you need to inspect the mesh first::

    mesh = mesh2gis.read_obj("blocks.obj")
    mesh = mesh2gis.transform(mesh, up="y", offset=(436372.0, -4533303.3, 0.0))
    blocks = mesh2gis.group(mesh, by="usemtl")
    blocks = mesh2gis.merge_stacked(blocks)
    mesh2gis.write_multipatch(blocks, "blocks.shp", epsg=5254)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from mesh2gis.attrs import BlockAttrs, compute
from mesh2gis.crs import UnknownCRSError, wkt_for
from mesh2gis.geometry import UpAxis, detect_up_axis, transform
from mesh2gis.grouping import GroupBy, group, merge_stacked
from mesh2gis.readers import read_dxf, read_obj
from mesh2gis.types import Block, Mesh
from mesh2gis.writers import write_gpkg, write_multipatch, write_obj

if TYPE_CHECKING:
    from collections.abc import Callable
    from os import PathLike

__version__ = "0.2.0"

__all__ = [
    "Block",
    "BlockAttrs",
    "GroupBy",
    "Mesh",
    "UnknownCRSError",
    "UpAxis",
    "__version__",
    "compute",
    "convert",
    "detect_up_axis",
    "group",
    "merge_stacked",
    "read",
    "read_dxf",
    "read_obj",
    "transform",
    "wkt_for",
    "write_gpkg",
    "write_multipatch",
    "write_obj",
]

_READERS: dict[str, Callable[[str | PathLike[str]], Mesh]] = {
    ".obj": read_obj,
    ".dxf": read_dxf,
}
_WRITER_SUFFIXES = frozenset({".shp", ".gpkg", ".obj"})


def read(path: str | PathLike[str]) -> Mesh:
    """Read a mesh, dispatching on file extension.

    Args:
        path: Input ``.obj`` or ``.dxf`` file.

    Returns:
        The parsed mesh.

    Raises:
        ValueError: If the extension is not recognised.
    """
    suffix = Path(path).suffix.lower()
    reader = _READERS.get(suffix)
    if reader is None:
        known = ", ".join(sorted(_READERS))
        msg = f"no reader for {suffix!r} (supported: {known})"
        raise ValueError(msg)
    return reader(path)


def convert(
    source: str | PathLike[str],
    target: str | PathLike[str],
    *,
    up: UpAxis | None = None,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: float = 1.0,
    group_by: GroupBy = "usemtl",
    merge_stacks: bool = False,
    epsg: int | None = None,
    storey_height: float | None = None,
    keep_tags: bool = False,
) -> int:
    """Read, transform, group and write in one call.

    Args:
        source: Input ``.obj`` or ``.dxf``.
        target: Output ``.shp``, ``.gpkg`` or ``.obj``; the writer is chosen
            from the extension.
        up: Vertical axis of the input. ``None`` guesses via
            :func:`~mesh2gis.geometry.detect_up_axis`, which is reliable for
            wide-and-flat mass models but not for single towers.
        offset: World-coordinate shift applied after scaling.
        scale: Uniform scale factor for unit conversion.
        group_by: Feature-splitting strategy.
        merge_stacks: Merge vertically stacked blocks into one feature -- use
            when a building was modelled as a base volume plus setback storeys.
        epsg: CRS of the output coordinates.
        storey_height: Floor-to-floor height used to derive storey counts.
            Supplying it adds the storey and floor-area columns to the output;
            without it those columns are omitted rather than filled with zeros.
        keep_tags: Carry the reader's own labels (material, group, object, DXF
            layer) through as extra columns.

    Returns:
        Number of features written.

    Raises:
        ValueError: If the source or target extension is unsupported.
    """
    suffix = Path(target).suffix.lower()
    if suffix not in _WRITER_SUFFIXES:
        known = ", ".join(sorted(_WRITER_SUFFIXES))
        msg = f"no writer for {suffix!r} (supported: {known})"
        raise ValueError(msg)

    mesh = read(source)
    resolved_up = up if up is not None else detect_up_axis(mesh)
    mesh = transform(mesh, up=resolved_up, offset=offset, scale=scale)

    blocks = group(mesh, by=group_by)
    if merge_stacks:
        blocks = merge_stacked(blocks)

    if suffix == ".obj":
        return write_obj(blocks, target)
    if suffix == ".gpkg":
        return write_gpkg(
            blocks, target, epsg=epsg, storey_height=storey_height, keep_tags=keep_tags
        )
    return write_multipatch(
        blocks, target, epsg=epsg, storey_height=storey_height, keep_tags=keep_tags
    )
