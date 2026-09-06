"""Input format readers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mesh2gis.readers.obj import read_obj

if TYPE_CHECKING:
    from os import PathLike

    from mesh2gis.types import Mesh

__all__ = ["read_dxf", "read_obj"]


def read_dxf(
    path: str | PathLike[str],
    *,
    layers: list[str] | None = None,
    extrude_thickness: bool = True,
) -> Mesh:
    """Read a DXF file. Thin wrapper that defers importing ``ezdxf``.

    Importing :mod:`mesh2gis` must never require the optional ``dxf`` extra, so
    the real implementation is only imported when this is actually called. See
    :func:`mesh2gis.readers.dxf.read_dxf` for the full documentation.

    Args:
        path: Path to the ``.dxf`` file.
        layers: If given, only entities on these layers are read.
        extrude_thickness: Extrude closed polylines carrying a thickness.

    Returns:
        The parsed mesh.

    Raises:
        ImportError: If ``ezdxf`` is not installed.
    """
    from mesh2gis.readers.dxf import read_dxf as _impl  # noqa: PLC0415

    return _impl(path, layers=layers, extrude_thickness=extrude_thickness)
