import numpy as np
import pytest

from mesh2gis.types import Mesh

CUBE_OBJ = """# test cube, Y-up, 2x2 footprint, height 3
mtllib t.mtl
usemtl Default
v 0 0 0
v 2 0 0
v 2 0 -2
v 0 0 -2
v 0 3 0
v 2 3 0
v 2 3 -2
v 0 3 -2
f 1 4 3 2
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
usemtl Default
v 10 0 -50
v 12 0 -50
v 12 0 -52
v 10 0 -52
v 10 6 -50
v 12 6 -50
v 12 6 -52
v 10 6 -52
f 9 12 11 10
f 13 14 15 16
f 9 10 14 13
f 10 11 15 14
f 11 12 16 15
f 12 9 13 16
cstype bspline
deg 1
curv 0 1 1 2
parm u 0 0 1 1
end
"""


@pytest.fixture
def cube_obj(tmp_path):
    p = tmp_path / "cubes.obj"
    p.write_text(CUBE_OBJ)
    return p


@pytest.fixture
def unit_square_mesh():
    """One flat square at z=0, already Z-up."""
    return Mesh(
        vertices=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]),
        faces=[np.array([0, 1, 2, 3])],
        tags={"usemtl": ["m"], "g": [None], "o": [None]},
    )
