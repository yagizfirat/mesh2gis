"""Output format writers."""

from mesh2gis.writers.gpkg import write_gpkg
from mesh2gis.writers.obj import write_obj
from mesh2gis.writers.shapefile import write_multipatch

__all__ = ["write_gpkg", "write_multipatch", "write_obj"]
