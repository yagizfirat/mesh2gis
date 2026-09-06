"""Command line interface: ``mesh2gis convert`` and ``mesh2gis inspect``."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from typing import TYPE_CHECKING

import mesh2gis
from mesh2gis.crs import UnknownCRSError

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mesh2gis",
        description="Turn CAD mass models into GIS-ready 3D features.",
    )
    parser.add_argument("--version", action="version", version=mesh2gis.__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    ins = sub.add_parser(
        "inspect",
        help="report a mesh's structure without writing anything",
        description=(
            "Print vertex/face counts, bounding box, available grouping tags and "
            "the height histogram. Run this first: it tells you which --group-by "
            "and --storey-height to use."
        ),
    )
    ins.add_argument("source", help="input .obj or .dxf")
    ins.add_argument(
        "--group-by",
        default=None,
        help="preview how many features a strategy would produce",
    )
    ins.add_argument(
        "--up",
        choices=("y", "z"),
        default=None,
        help="vertical axis of the input (default: auto-detect)",
    )

    conv = sub.add_parser("convert", help="read, transform, group and write in one pass")
    conv.add_argument("source", help="input .obj or .dxf")
    conv.add_argument("target", help="output .shp, .gpkg or .obj")
    conv.add_argument(
        "--up",
        choices=("y", "z"),
        default=None,
        help="vertical axis of the input (default: auto-detect)",
    )
    conv.add_argument(
        "--group-by",
        default="usemtl",
        choices=("o", "g", "usemtl", "layer", "connected", "single"),
        help="how to split the mesh into features (default: usemtl)",
    )
    conv.add_argument(
        "--offset",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        default=(0.0, 0.0, 0.0),
        help="world-coordinate shift, applied after scaling",
    )
    conv.add_argument("--scale", type=float, default=1.0, help="uniform scale factor")
    conv.add_argument("--epsg", type=int, default=None, help="CRS of the output")
    conv.add_argument(
        "--storey-height",
        type=_storey_height,
        default=None,
        metavar="M",
        help=(
            "floor-to-floor height, used to derive storey counts; "
            "pass 'auto' to infer it from the block heights"
        ),
    )
    conv.add_argument(
        "--keep-tags",
        action="store_true",
        help="carry source labels (material, group, layer) through as columns",
    )
    conv.add_argument(
        "--merge-stacks",
        action="store_true",
        help="merge vertically stacked blocks into one feature per building",
    )
    conv.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")
    return parser


def _storey_height(value: str) -> float | str:
    """Parse --storey-height: a positive number, or the word 'auto'."""
    if value.strip().lower() == "auto":
        return "auto"
    try:
        number = float(value)
    except ValueError:
        msg = f"expected a number or 'auto', got {value!r}"
        raise argparse.ArgumentTypeError(msg) from None
    if number <= 0:
        msg = f"storey height must be positive, got {number}"
        raise argparse.ArgumentTypeError(msg)
    return number


def _cmd_inspect(args: argparse.Namespace) -> int:
    mesh = mesh2gis.read(args.source)
    xmin, ymin, zmin, xmax, ymax, zmax = mesh.bounds()

    print(f"source     {args.source}")
    print(f"vertices   {mesh.n_vertices:,}")
    print(f"faces      {mesh.n_faces:,}")
    arity = Counter(len(f) for f in mesh.faces)
    print("  arity    " + ", ".join(f"{k}-gon: {v:,}" for k, v in sorted(arity.items())))
    print(f"bounds X   {xmin:,.3f} … {xmax:,.3f}   (span {xmax - xmin:,.3f})")
    print(f"bounds Y   {ymin:,.3f} … {ymax:,.3f}   (span {ymax - ymin:,.3f})")
    print(f"bounds Z   {zmin:,.3f} … {zmax:,.3f}   (span {zmax - zmin:,.3f})")
    up = args.up or mesh2gis.detect_up_axis(mesh)
    print(f"up axis    {up}" + ("" if args.up else " (guess)"))

    print("tags")
    for name, values in mesh.tags.items():
        distinct = len({v for v in values if v is not None})
        state = f"{distinct:,} distinct" if distinct else "absent"
        print(f"  {name:10s} {state}")

    if args.group_by:
        oriented = mesh2gis.transform(mesh, up=up)
        blocks = mesh2gis.group(oriented, by=args.group_by)
        print(f"group_by={args.group_by}: {len(blocks):,} features")
        heights = Counter(round(b.bounds()[5] - b.bounds()[2], 2) for b in blocks)
        top = ", ".join(f"{h}: {n:,}" for h, n in heights.most_common(8))
        print(f"  heights  {top}   (up={up})")
        hint = mesh2gis.detect_storey_height([b.bounds()[5] - b.bounds()[2] for b in blocks])
        if hint:
            step, coverage = hint
            print(
                f"  hint     {coverage:.0%} of heights are multiples of {step} "
                f"-- try --storey-height {step}"
            )
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    log(f"reading {args.source}")
    mesh = mesh2gis.read(args.source)
    log(f"  {mesh.n_vertices:,} vertices, {mesh.n_faces:,} faces")

    up = args.up or mesh2gis.detect_up_axis(mesh)
    if args.up is None:
        log(f"  up axis auto-detected as {up!r} (override with --up)")
    mesh = mesh2gis.transform(mesh, up=up, offset=tuple(args.offset), scale=args.scale)

    blocks = mesh2gis.group(mesh, by=args.group_by)
    log(f"  {len(blocks):,} blocks via {args.group_by!r}")
    if args.merge_stacks:
        blocks = mesh2gis.merge_stacked(blocks)
        log(f"  {len(blocks):,} features after merging stacks")

    storey_height = args.storey_height
    if storey_height == "auto":
        storey_height, coverage = mesh2gis.resolve_storey_height(blocks)
        log(
            f"  storey height inferred as {storey_height} "
            f"({coverage:.0%} of heights fit); this is a guess -- "
            f"pass an explicit value to override"
        )

    suffix = str(args.target).lower()
    if suffix.endswith(".obj"):
        n = mesh2gis.write_obj(blocks, args.target)
    elif suffix.endswith(".gpkg"):
        n = mesh2gis.write_gpkg(
            blocks,
            args.target,
            epsg=args.epsg,
            storey_height=storey_height,
            keep_tags=args.keep_tags,
        )
    elif suffix.endswith(".shp"):
        n = mesh2gis.write_multipatch(
            blocks,
            args.target,
            epsg=args.epsg,
            storey_height=storey_height,
            keep_tags=args.keep_tags,
        )
    else:
        print(f"error: no writer for {args.target}", file=sys.stderr)
        return 2

    if args.epsg is None and not suffix.endswith(".obj"):
        log("  warning: no --epsg given; output has an undefined CRS")
    if storey_height is None and not suffix.endswith(".obj"):
        log("  no --storey-height; storey and floor-area columns omitted")
    log(f"wrote {n:,} features to {args.target}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            return _cmd_inspect(args)
        return _cmd_convert(args)
    except (ValueError, FileNotFoundError, ImportError, UnknownCRSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
