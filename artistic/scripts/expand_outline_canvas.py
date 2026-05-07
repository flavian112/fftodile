#!/usr/bin/env python3
"""Expand module outline SVG from DEF-sized canvas to full rendered-chip canvas."""

import re
import sys
import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand module outline SVG from DEF-sized canvas to full rendered-chip canvas."
    )
    parser.add_argument("--dx-pt", type=float, default=0.0,
                        help="Additional outline X shift in SVG points")
    parser.add_argument("--dy-pt", type=float, default=0.0,
                        help="Additional outline Y shift in SVG points")
    parser.add_argument("svg", type=Path,
                        help="SVG file to modify in place")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    svg_path = args.svg
    svg = svg_path.read_text()

    viewbox_match = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg)
    image_w_match = re.search(r'<image\s+width="([0-9.]+)"', svg)
    image_h_match = re.search(r'<image\s+width="[0-9.]+"\s+height="([0-9.]+)"', svg)

    if not (viewbox_match and image_w_match and image_h_match):
        print(f"Could not find SVG viewBox/image geometry in {svg_path}", file=sys.stderr)
        return 1

    def_w = float(viewbox_match.group(1))
    def_h = float(viewbox_match.group(2))
    full_w = float(image_w_match.group(1))
    full_h = float(image_h_match.group(1))

    shift_x = (full_w - def_w) / 2.0 + args.dx_pt
    shift_y = (full_h - def_h) / 2.0 + args.dy_pt

    svg = re.sub(
        r'width="[0-9.]+pt" height="[0-9.]+pt" viewBox="0 0 [0-9.]+ [0-9.]+"',
        f'width="{full_w:g}pt" height="{full_h:g}pt" viewBox="0 0 {full_w:g} {full_h:g}"',
        svg,
        count=1,
    )
    svg = re.sub(r'x="-[0-9.]+"', 'x="0"', svg, count=1)
    svg = re.sub(r'y="-[0-9.]+"', 'y="0"', svg, count=1)
    svg = re.sub(r'(<g transform=")', rf'\1translate({shift_x:g},{shift_y:g}) ', svg)

    svg_path.write_text(svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
