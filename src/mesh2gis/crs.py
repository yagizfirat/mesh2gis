"""EPSG code to WKT resolution.

``pyproj`` is used when installed. A small built-in table covers the Turkish
3-degree Transverse Mercator zones so that the common case works with no GDAL
or PROJ dependency at all -- which is the point of this package.
"""

from __future__ import annotations

__all__ = ["UnknownCRSError", "wkt_for"]


class UnknownCRSError(LookupError):
    """Raised when an EPSG code cannot be resolved to WKT."""


def _turef(code: int, cm: int) -> str:
    return (
        f'PROJCS["TUREF_TM{cm}",GEOGCS["GCS_TUREF",'
        'DATUM["D_Turkish_National_Reference_Frame",'
        'SPHEROID["GRS_1980",6378137.0,298.257222101]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
        'PROJECTION["Transverse_Mercator"],'
        'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],'
        f'PARAMETER["Central_Meridian",{cm}.0],PARAMETER["Scale_Factor",1.0],'
        'PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]'
    )


_BUILTIN: dict[int, str] = {
    5253: _turef(5253, 27),
    5254: _turef(5254, 30),
    5255: _turef(5255, 33),
    5256: _turef(5256, 36),
    5257: _turef(5257, 39),
    5258: _turef(5258, 42),
    5259: _turef(5259, 45),
    4326: (
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
        'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
    ),
}


def wkt_for(epsg: int) -> str:
    """Return ESRI-flavoured WKT for an EPSG code.

    Args:
        epsg: EPSG code.

    Returns:
        WKT string suitable for a ``.prj`` sidecar.

    Raises:
        UnknownCRSError: If the code is neither built in nor resolvable by
            ``pyproj``.
    """
    if epsg in _BUILTIN:
        return _BUILTIN[epsg]
    try:
        from pyproj import CRS  # noqa: PLC0415
    except ImportError as exc:
        msg = (
            f"EPSG:{epsg} is not in the built-in table. "
            "Install the 'crs' extra for full EPSG support: pip install 'mesh2gis[crs]'"
        )
        raise UnknownCRSError(msg) from exc
    try:
        return CRS.from_epsg(epsg).to_wkt("WKT1_ESRI")
    except Exception as exc:  # pragma: no cover - pyproj raises many types
        msg = f"could not resolve EPSG:{epsg}"
        raise UnknownCRSError(msg) from exc
