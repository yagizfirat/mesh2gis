import sqlite3
import struct

import numpy as np
import pytest
import shapefile as shp

import mesh2gis
from mesh2gis.crs import UnknownCRSError, wkt_for
from mesh2gis.geometry import detect_up_axis, transform
from mesh2gis.grouping import group, merge_stacked
from mesh2gis.readers.obj import read_obj
from mesh2gis.types import Block, Mesh


def test_reads_vertices_and_faces(cube_obj):
    mesh = read_obj(cube_obj)
    assert mesh.n_vertices == 16
    assert mesh.n_faces == 12


def test_freeform_curve_entities_are_dropped(cube_obj):
    mesh = read_obj(cube_obj)
    assert all(f.size >= 3 for f in mesh.faces)


def test_usemtl_runs_are_disambiguated(cube_obj):
    mesh = read_obj(cube_obj)
    assert len(set(mesh.tags["usemtl"])) == 2, "two runs of the same material name"


def test_negative_face_indices_are_relative(tmp_path):
    p = tmp_path / "rel.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\n")
    mesh = read_obj(p)
    assert mesh.faces[0].tolist() == [0, 1, 2]


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_obj(tmp_path / "nope.obj")


def test_out_of_range_index_raises(tmp_path):
    p = tmp_path / "bad.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nf 1 2 99\n")
    with pytest.raises(ValueError, match="references vertex"):
        read_obj(p)


def test_y_up_conversion_maps_height_to_z(cube_obj):
    mesh = transform(read_obj(cube_obj), up="y")
    _, _, zmin, _, _, zmax = mesh.bounds()
    assert zmin == pytest.approx(0.0)
    assert zmax == pytest.approx(6.0)


def test_y_up_conversion_preserves_handedness(cube_obj):
    """A mirrored transform would invert every face normal."""
    src = read_obj(cube_obj)
    dst = transform(src, up="y")
    face = src.faces[0]
    a, b, c = src.vertices[face[:3]]
    n_before = np.cross(b - a, c - a)
    a2, b2, c2 = dst.vertices[face[:3]]
    n_after = np.cross(b2 - a2, c2 - a2)
    assert np.linalg.norm(n_before) == pytest.approx(np.linalg.norm(n_after))
    assert np.dot(n_after, np.array([n_before[0], -n_before[2], n_before[1]])) > 0


def test_scale_applies_before_offset(unit_square_mesh):
    out = transform(unit_square_mesh, up="z", scale=2.0, offset=(10.0, 0.0, 0.0))
    assert out.vertices[1].tolist() == [12.0, 0.0, 0.0]


def test_zero_scale_rejected(unit_square_mesh):
    with pytest.raises(ValueError, match="non-zero"):
        transform(unit_square_mesh, scale=0.0)


def test_detect_up_axis_on_wide_flat_model(cube_obj):
    assert detect_up_axis(read_obj(cube_obj)) == "y"


def test_group_by_usemtl_splits_objects(cube_obj):
    blocks = group(read_obj(cube_obj), by="usemtl")
    assert len(blocks) == 2
    assert all(len(b) == 6 for b in blocks)


def test_group_connected_matches_tag_grouping(cube_obj):
    mesh = read_obj(cube_obj)
    assert len(group(mesh, by="connected")) == len(group(mesh, by="usemtl"))


def test_group_single_yields_one_feature(cube_obj):
    assert len(group(read_obj(cube_obj), by="single")) == 1


def test_group_by_absent_tag_raises(cube_obj):
    with pytest.raises(ValueError, match="empty for every face"):
        group(read_obj(cube_obj), by="g")


def test_unknown_strategy_raises(cube_obj):
    with pytest.raises(ValueError, match="unknown grouping"):
        group(read_obj(cube_obj), by="nope")  # type: ignore[arg-type]


def test_merge_stacked_joins_a_setback_storey():
    """Base volume 0-10 plus a setback storey 10-13 is one building."""
    verts = []
    faces = []
    for z0, z1, half in ((0.0, 10.0, 5.0), (10.0, 13.0, 3.0)):
        base = len(verts)
        for z in (z0, z1):
            verts += [[-half, -half, z], [half, -half, z], [half, half, z], [-half, half, z]]
        faces += [np.array([base, base + 1, base + 2, base + 3])]
        faces += [np.array([base + 4, base + 5, base + 6, base + 7])]
    mesh = Mesh(vertices=np.array(verts), faces=faces)
    blocks = [Block(mesh, np.array([0, 1])), Block(mesh, np.array([2, 3]))]
    assert len(merge_stacked(blocks)) == 1


def test_merge_stacked_keeps_side_by_side_buildings_apart():
    verts = []
    faces = []
    for x0 in (0.0, 100.0):
        base = len(verts)
        for z in (0.0, 10.0):
            verts += [[x0, 0.0, z], [x0 + 5, 0.0, z], [x0 + 5, 5.0, z], [x0, 5.0, z]]
        faces += [np.array([base, base + 1, base + 2, base + 3])]
        faces += [np.array([base + 4, base + 5, base + 6, base + 7])]
    mesh = Mesh(vertices=np.array(verts), faces=faces)
    blocks = [Block(mesh, np.array([0, 1])), Block(mesh, np.array([2, 3]))]
    assert len(merge_stacked(blocks)) == 2


def test_attributes_of_a_known_box(cube_obj):
    mesh = transform(read_obj(cube_obj), up="y")
    blocks = group(mesh, by="usemtl")
    a = mesh2gis.compute(blocks[0], 1, storey_height=1.5)
    assert a.height == pytest.approx(3.0)
    assert a.storeys == 2
    assert a.base_area == pytest.approx(4.0)
    assert a.volume == pytest.approx(12.0)
    assert a.n_faces == 6


def test_storeys_is_none_without_storey_height(cube_obj):
    """None, not zero: a mesh that is not a building has no storey count."""
    blocks = group(transform(read_obj(cube_obj), up="y"), by="usemtl")
    a = mesh2gis.compute(blocks[0], 1)
    assert a.storeys is None
    assert a.floor_area is None


def test_builtin_turkish_zone_resolves():
    assert 'Central_Meridian",30.0' in wkt_for(5254)


def test_unknown_epsg_raises():
    """Fails the same way whether or not pyproj is installed."""
    with pytest.raises(UnknownCRSError):
        wkt_for(999999)


def test_multipatch_shapefile_roundtrips(cube_obj, tmp_path):
    out = tmp_path / "cubes.shp"
    n = mesh2gis.convert(cube_obj, out, up="y", group_by="usemtl", epsg=5254, storey_height=3.0)
    assert n == 2

    with shp.Reader(str(out)) as r:
        assert r.shapeType == shp.MULTIPATCH
        assert len(r) == 2
        shape = r.shape(0)
        assert set(shape.partTypes) == {shp.TRIANGLE_FAN}
        assert min(shape.z) == pytest.approx(0.0)
        rec = r.record(0)
        assert rec["HEIGHT"] == pytest.approx(3.0)
        assert rec["STOREYS"] == 1
        assert rec["SURF_AREA"] == pytest.approx(32.0)
    assert out.with_suffix(".prj").exists()


def test_no_prj_written_without_epsg(cube_obj, tmp_path):
    out = tmp_path / "nocrs.shp"
    mesh2gis.convert(cube_obj, out, up="y")
    assert not out.with_suffix(".prj").exists()


def test_bad_epsg_fails_before_writing(cube_obj, tmp_path):
    out = tmp_path / "bad.shp"
    with pytest.raises(UnknownCRSError):
        mesh2gis.convert(cube_obj, out, up="y", epsg=999999)
    assert not out.exists()


def test_geopackage_is_valid_and_readable(cube_obj, tmp_path):
    out = tmp_path / "cubes.gpkg"
    n = mesh2gis.convert(cube_obj, out, up="y", epsg=5254, storey_height=3.0)
    assert n == 2

    conn = sqlite3.connect(out)
    try:
        (app_id,) = conn.execute("PRAGMA application_id").fetchone()
        assert app_id == 0x47504B47
        row = conn.execute(
            "SELECT geometry_type_name, srs_id, z FROM gpkg_geometry_columns"
        ).fetchone()
        assert row == ("MULTIPOLYGON", 5254, 1)
        assert conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 2

        blob = conn.execute("SELECT geom FROM blocks LIMIT 1").fetchone()[0]
        assert blob[:2] == b"GP"
        srs = struct.unpack_from("<i", blob, 4)[0]
        assert srs == 5254
        wkb_type = struct.unpack_from("<I", blob, 8 + 32 + 1)[0]
        assert wkb_type == 1006, "MultiPolygonZ"
    finally:
        conn.close()


def test_geopackage_rejects_odd_layer_name(cube_obj, tmp_path):
    with pytest.raises(ValueError, match="alphanumeric"):
        mesh2gis.write_gpkg(
            group(read_obj(cube_obj), by="usemtl"), tmp_path / "x.gpkg", layer="a;b"
        )


def test_obj_writer_emits_groups_and_drops_orphans(cube_obj, tmp_path):
    out = tmp_path / "clean.obj"
    mesh2gis.convert(cube_obj, out, up="y", group_by="usemtl")
    text = out.read_text()
    assert text.count("\ng ") == 2
    assert "curv" not in text
    assert mesh2gis.read_obj(out).n_faces == 12


def test_unsupported_target_extension_raises(cube_obj, tmp_path):
    with pytest.raises(ValueError, match="no writer"):
        mesh2gis.convert(cube_obj, tmp_path / "out.kml")


def test_unsupported_source_extension_raises(tmp_path):
    p = tmp_path / "x.stl"
    p.write_text("")
    with pytest.raises(ValueError, match="no reader"):
        mesh2gis.read(p)


def test_cli_convert_writes_output(cube_obj, tmp_path):
    from mesh2gis.cli import main

    out = tmp_path / "cli.shp"
    code = main(
        [
            "convert",
            str(cube_obj),
            str(out),
            "--up",
            "y",
            "--group-by",
            "usemtl",
            "--epsg",
            "5254",
            "--storey-height",
            "3.0",
            "--quiet",
        ]
    )
    assert code == 0
    with shp.Reader(str(out)) as r:
        assert len(r) == 2


def test_cli_inspect_reports_structure(cube_obj, capsys):
    from mesh2gis.cli import main

    assert main(["inspect", str(cube_obj), "--group-by", "usemtl"]) == 0
    out = capsys.readouterr().out
    assert "vertices   16" in out
    assert "2 features" in out


def test_cli_reports_errors_as_exit_code(tmp_path, capsys):
    from mesh2gis.cli import main

    assert main(["inspect", str(tmp_path / "missing.obj")]) == 1
    assert "error:" in capsys.readouterr().err


def test_storey_hint_finds_a_clean_grid():
    hint = mesh2gis.detect_storey_height([3.2, 6.4, 9.6, 12.8, 16.0])
    assert hint is not None
    assert hint[0] == pytest.approx(3.2)
    assert hint[1] == pytest.approx(1.0)


def test_storey_hint_tolerates_outliers():
    hint = mesh2gis.detect_storey_height([3.2, 6.4, 9.6, 12.8, 16.0, 10.6, 13.8])
    assert hint is not None
    assert hint[0] == pytest.approx(3.2)
    assert 0.6 <= hint[1] < 1.0


def test_storey_hint_gives_up_on_noise():
    noise = [2.7, 5.1, 8.9, 11.3, 17.6, 23.1, 4.4, 19.8]
    assert mesh2gis.detect_storey_height(noise) is None


def test_inspect_measures_height_along_detected_up_axis(cube_obj, capsys):
    """A Y-up file must not have its heights read off the raw Z column."""
    from mesh2gis.cli import main

    assert main(["inspect", str(cube_obj), "--group-by", "usemtl"]) == 0
    out = capsys.readouterr().out
    assert "up=y" in out
    assert "3.0" in out and "6.0" in out, "true heights, not the 2.0 Z-span"


def test_closed_box_reports_closed_and_correct_volume(cube_obj):
    blocks = group(transform(read_obj(cube_obj), up="y"), by="usemtl")
    a = mesh2gis.compute(blocks[0], 1)
    assert a.closed is True
    assert a.volume == pytest.approx(12.0)


def test_open_surface_reports_zero_volume():
    """Two loose faces have no enclosed volume; the raw integral is nonsense."""
    mesh = Mesh(
        vertices=np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 3.0],
                [1.0, 0.0, 3.0],
                [1.0, 1.0, 3.0],
                [0.0, 1.0, 3.0],
            ]
        ),
        faces=[np.array([0, 1, 2, 3]), np.array([4, 5, 6, 7])],
    )
    a = mesh2gis.compute(Block(mesh, np.array([0, 1])), 1)
    assert a.closed is False
    assert a.volume == 0.0
    assert a.height == pytest.approx(3.0)


def test_volume_is_stable_at_projected_coordinates():
    """Integrating about the origin instead of the centroid would lose precision.

    At a TM northing of ~4.5e6 the divergence-theorem terms reach ~1e13 while
    the answer is ~1e3, so the subtraction eats most of the significant digits.
    """
    unit = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ]
    )
    faces = [
        np.array([0, 3, 2, 1]),
        np.array([4, 5, 6, 7]),
        np.array([0, 1, 5, 4]),
        np.array([1, 2, 6, 5]),
        np.array([2, 3, 7, 6]),
        np.array([3, 0, 4, 7]),
    ]
    shift = np.array([437_170.75, 4_534_573.04, 0.0])
    near = mesh2gis.compute(Block(Mesh(unit, faces), np.arange(6)), 1)
    far = mesh2gis.compute(Block(Mesh(unit + shift, faces), np.arange(6)), 1)
    assert near.volume == pytest.approx(1.0)
    assert far.volume == pytest.approx(1.0, abs=1e-6)


def test_closed_flag_reaches_the_shapefile(cube_obj, tmp_path):
    out = tmp_path / "closed.shp"
    mesh2gis.convert(cube_obj, out, up="y", epsg=5254, storey_height=3.0)
    with shp.Reader(str(out)) as r:
        assert r.record(0)["CLOSED"] is True


def test_closed_flag_reaches_the_geopackage(cube_obj, tmp_path):
    out = tmp_path / "closed.gpkg"
    mesh2gis.convert(cube_obj, out, up="y", epsg=5254)
    conn = sqlite3.connect(out)
    try:
        assert conn.execute("SELECT closed FROM blocks LIMIT 1").fetchone()[0] == 1
    finally:
        conn.close()


def test_unwelded_box_is_still_recognised_as_closed():
    """CAD exporters duplicate vertices per face; index matching would fail."""
    corners = np.array(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.0, 2.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 0.0, 3.0],
            [2.0, 0.0, 3.0],
            [2.0, 2.0, 3.0],
            [0.0, 2.0, 3.0],
        ]
    )
    quads = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [3, 0, 4, 7],
    ]
    verts, faces = [], []
    for quad in quads:
        start = len(verts)
        verts.extend(corners[i] for i in quad)
        faces.append(np.arange(start, start + 4))

    mesh = Mesh(vertices=np.array(verts), faces=faces)
    assert mesh.n_vertices == 24, "unwelded: 6 quads x 4 corners"

    a = mesh2gis.compute(Block(mesh, np.arange(6)), 1)
    assert a.closed is True
    assert a.volume == pytest.approx(12.0)


def _stacked_building():
    """Base 10x10x16 with a flush-on-one-side 8x10x3.2 setback storey on top.

    Flush contact is the awkward case: the two solids share vertices along one
    edge, so the union is non-manifold and cannot be integrated as a whole.
    """
    verts, faces = [], []

    def box(bounds):
        x0, x1, y0, y1, z0, z1 = bounds
        start = len(verts)
        for z in (z0, z1):
            verts.extend([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]])
        idx = [
            [0, 3, 2, 1],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7],
        ]
        first = len(faces)
        faces.extend(np.array([start + i for i in q]) for q in idx)
        return np.arange(first, first + 6)

    base = box((0, 10, 0, 10, 0, 16))
    top = box((0, 8, 0, 10, 16, 19.2))
    mesh = Mesh(vertices=np.array(verts, dtype=float), faces=faces)
    return mesh, [Block(mesh, base, label="base"), Block(mesh, top, label="top")]


def test_merged_building_totals_height_and_storeys():
    _, blocks = _stacked_building()
    merged = merge_stacked(blocks)
    assert len(merged) == 1

    a = mesh2gis.compute(merged[0], 1, storey_height=3.2)
    assert a.n_parts == 2
    assert a.z_min == pytest.approx(0.0)
    assert a.z_max == pytest.approx(19.2)
    assert a.height == pytest.approx(19.2)
    assert a.storeys == 6


def test_merged_base_area_is_the_ground_footprint_only():
    """Coverage ratio means the ground footprint, not every storey added up."""
    _, blocks = _stacked_building()
    a = mesh2gis.compute(merge_stacked(blocks)[0], 1, storey_height=3.2)
    assert a.base_area == pytest.approx(100.0)
    assert a.base_area != pytest.approx(180.0), "must not sum the two footprints"


def test_merged_floor_area_counts_the_setback_at_its_own_size():
    """base_area * storeys would overcount: 100*6=600 instead of 100*5+80*1=580."""
    _, blocks = _stacked_building()
    a = mesh2gis.compute(merge_stacked(blocks)[0], 1, storey_height=3.2)
    assert a.floor_area == pytest.approx(580.0)
    assert a.floor_area != pytest.approx(a.base_area * a.storeys)


def test_merged_volume_sums_the_parts_despite_flush_contact():
    """The union is non-manifold here; measuring the parts sidesteps that."""
    mesh, blocks = _stacked_building()
    a = mesh2gis.compute(merge_stacked(blocks)[0], 1, storey_height=3.2)
    assert a.closed is True
    assert a.volume == pytest.approx(100 * 16 + 80 * 3.2)

    whole = Block(mesh, np.arange(mesh.n_faces))
    assert mesh2gis.compute(whole, 1).closed is False


def test_unmerged_block_floor_area_is_footprint_times_storeys():
    _, blocks = _stacked_building()
    a = mesh2gis.compute(blocks[0], 1, storey_height=3.2)
    assert a.n_parts == 1
    assert a.floor_area == pytest.approx(500.0)


def test_single_part_group_is_not_treated_as_merged():
    """A lone block passing through merge_stacked keeps its label and parts=[]."""
    _, blocks = _stacked_building()
    merged = merge_stacked([blocks[0]])
    assert merged[0].parts == []
    assert merged[0].label == "base"


def test_new_fields_reach_the_shapefile(cube_obj, tmp_path):
    out = tmp_path / "fields.shp"
    mesh2gis.convert(cube_obj, out, up="y", epsg=5254, storey_height=3.0)
    with shp.Reader(str(out)) as r:
        names = [f[0] for f in r.fields[1:]]
        assert "FLOOR_AREA" in names
        assert "N_PARTS" in names
        assert r.record(0)["N_PARTS"] == 1


def test_storey_columns_omitted_when_not_a_building(cube_obj, tmp_path):
    """A bridge or a machine part has no storeys; a zero column would lie."""
    out = tmp_path / "generic.shp"
    mesh2gis.convert(cube_obj, out, up="y", epsg=5254)
    with shp.Reader(str(out)) as r:
        names = [f[0] for f in r.fields[1:]]
    assert "STOREYS" not in names
    assert "FLOOR_AREA" not in names
    assert "VOLUME" in names, "geometric columns stay -- they mean something for any mesh"
    assert "SURF_AREA" in names


def test_storey_columns_present_when_storey_height_given(cube_obj, tmp_path):
    out = tmp_path / "building.shp"
    mesh2gis.convert(cube_obj, out, up="y", epsg=5254, storey_height=3.0)
    with shp.Reader(str(out)) as r:
        names = [f[0] for f in r.fields[1:]]
    assert "STOREYS" in names
    assert "FLOOR_AREA" in names


def test_keep_tags_adds_source_columns_without_the_run_suffix(cube_obj, tmp_path):
    out = tmp_path / "tagged.shp"
    mesh2gis.convert(cube_obj, out, up="y", epsg=5254, keep_tags=True)
    with shp.Reader(str(out)) as r:
        names = [f[0] for f in r.fields[1:]]
        assert "USEMTL" in names
        value = r.record(0)["USEMTL"]
    assert value == "Default", "the internal #N run counter must not leak"


def test_tags_absent_by_default(cube_obj, tmp_path):
    out = tmp_path / "untagged.shp"
    mesh2gis.convert(cube_obj, out, up="y", epsg=5254)
    with shp.Reader(str(out)) as r:
        assert "USEMTL" not in [f[0] for f in r.fields[1:]]


def test_geopackage_schema_adapts_too(cube_obj, tmp_path):
    plain = tmp_path / "plain.gpkg"
    full = tmp_path / "full.gpkg"
    mesh2gis.convert(cube_obj, plain, up="y", epsg=5254)
    mesh2gis.convert(cube_obj, full, up="y", epsg=5254, storey_height=3.0, keep_tags=True)

    def columns(path):
        conn = sqlite3.connect(path)
        try:
            return {row[1] for row in conn.execute("PRAGMA table_info(blocks)")}
        finally:
            conn.close()

    assert "storeys" not in columns(plain)
    assert "surface_area" in columns(plain)
    assert {"storeys", "floor_area", "usemtl"} <= columns(full)


def test_surface_area_of_a_known_box(cube_obj):
    """2 x 2 footprint, 3 tall: 2*(2*2) + 4*(2*3) = 32."""
    blocks = group(transform(read_obj(cube_obj), up="y"), by="usemtl")
    assert mesh2gis.compute(blocks[0], 1).surface_area == pytest.approx(32.0)


def test_surface_area_works_on_open_meshes_unlike_volume():
    """Surface area is defined for any mesh; volume needs a closed one."""
    mesh = Mesh(
        vertices=np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]]),
        faces=[np.array([0, 1, 2, 3])],
    )
    a = mesh2gis.compute(Block(mesh, np.array([0])), 1)
    assert a.closed is False
    assert a.volume == 0.0
    assert a.surface_area == pytest.approx(4.0)


def test_tag_value_is_the_most_common_when_a_block_spans_several(cube_obj):
    """Grouping by one key can span several values of another; don't pretend."""
    mesh = transform(read_obj(cube_obj), up="y")
    whole = mesh2gis.group(mesh, by="single")[0]
    a = mesh2gis.compute(whole, 1)
    assert a.tags["usemtl"] == "Default"
    assert a.tags["g"] is None


# ------------------------------------------- automatic storey height


def test_auto_infers_the_grid_from_the_data(tmp_path):
    """Heights on a 3.2 m grid: the caller should not have to say "3.2"."""
    verts: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    for n, storeys in enumerate((1, 3, 4, 5, 2)):
        x0 = n * 20.0
        top = storeys * 3.2
        base = len(verts)
        for y in (0.0, top):
            verts += [
                (x0, y, 0.0),
                (x0 + 10, y, 0.0),
                (x0 + 10, y, -10.0),
                (x0, y, -10.0),
            ]
        for quad in (
            [0, 3, 2, 1],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7],
        ):
            faces.append([base + i for i in quad])

    lines = [f"v {x:.3f} {y:.3f} {z:.3f}" for x, y, z in verts]
    for n in range(5):
        lines.append("usemtl M")
        lines += ["f " + " ".join(str(i + 1) for i in f) for f in faces[n * 6 : (n + 1) * 6]]
    src = tmp_path / "grid.obj"
    src.write_text("\n".join(lines))

    blocks = mesh2gis.group(mesh2gis.transform(mesh2gis.read_obj(src), up="y"), by="usemtl")
    step, coverage = mesh2gis.resolve_storey_height(blocks)
    assert step == pytest.approx(3.2)
    assert coverage == pytest.approx(1.0)

    dst = tmp_path / "auto.shp"
    mesh2gis.convert(src, dst, up="y", storey_height="auto", epsg=5254)
    with shp.Reader(str(dst)) as r:
        assert "STOREYS" in [f[0] for f in r.fields[1:]]
        assert sorted(rec["STOREYS"] for rec in r.records()) == [1, 2, 3, 4, 5]


def test_auto_refuses_rather_than_guessing_on_noise(cube_obj, tmp_path):
    """Two blocks of unrelated heights explain no grid; say so, don't invent one."""
    with pytest.raises(ValueError, match="could not infer a storey height"):
        mesh2gis.convert(cube_obj, tmp_path / "x.shp", up="y", storey_height="auto")


def test_cli_accepts_auto(tmp_path, cube_obj, capsys):
    from mesh2gis.cli import main

    code = main(
        ["convert", str(cube_obj), str(tmp_path / "a.shp"), "--up", "y", "--storey-height", "auto"]
    )
    assert code == 1, "cube heights explain no grid"
    assert "could not infer" in capsys.readouterr().err


def test_cli_rejects_a_bad_storey_height(cube_obj, tmp_path):
    from mesh2gis.cli import main

    with pytest.raises(SystemExit):
        main(["convert", str(cube_obj), str(tmp_path / "a.shp"), "--storey-height", "-2"])
