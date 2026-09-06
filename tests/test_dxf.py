import pytest

import mesh2gis

ezdxf = pytest.importorskip("ezdxf")


@pytest.fixture
def dxf_file(tmp_path):
    """A DXF holding one 3DFACE and one thickness-extruded closed polyline."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    msp.add_3dface(
        [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)],
        dxfattribs={"layer": "ROOF"},
    )
    poly = msp.add_lwpolyline(
        [(100, 0), (110, 0), (110, 10), (100, 10)],
        close=True,
        dxfattribs={"layer": "BUILDINGS", "thickness": 9.0},
    )
    poly.dxf.elevation = 5.0

    path = tmp_path / "blocks.dxf"
    doc.saveas(path)
    return path


def test_reads_3dface_and_extrusion(dxf_file):
    mesh = mesh2gis.read_dxf(dxf_file)
    assert mesh.n_faces == 7
    assert set(mesh.tags["layer"]) == {"ROOF", "BUILDINGS"}


def test_degenerate_fourth_corner_is_collapsed(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_3dface([(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 0)])
    p = tmp_path / "tri.dxf"
    doc.saveas(p)

    mesh = mesh2gis.read_dxf(p)
    assert mesh.faces[0].size == 3


def test_layer_filter(dxf_file):
    mesh = mesh2gis.read_dxf(dxf_file, layers=["BUILDINGS"])
    assert mesh.n_faces == 6
    assert set(mesh.tags["layer"]) == {"BUILDINGS"}


def test_extrusion_can_be_disabled(dxf_file):
    mesh = mesh2gis.read_dxf(dxf_file, extrude_thickness=False)
    assert mesh.n_faces == 1


def test_group_by_layer_and_measure(dxf_file, tmp_path):
    mesh = mesh2gis.read_dxf(dxf_file)
    blocks = mesh2gis.group(mesh, by="layer")
    assert len(blocks) == 2

    building = next(b for b in blocks if b.label == "BUILDINGS")
    attrs = mesh2gis.compute(building, 1, storey_height=3.0)
    assert attrs.z_min == pytest.approx(5.0)
    assert attrs.height == pytest.approx(9.0)
    assert attrs.storeys == 3
    assert attrs.base_area == pytest.approx(100.0)
    assert attrs.volume == pytest.approx(900.0)


def test_convert_dxf_to_multipatch(dxf_file, tmp_path):
    out = tmp_path / "from_dxf.shp"
    n = mesh2gis.convert(dxf_file, out, up="z", group_by="layer", epsg=5254, storey_height=3.0)
    assert n == 2
    assert out.with_suffix(".prj").exists()
