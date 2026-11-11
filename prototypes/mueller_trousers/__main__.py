"""CLI: draft a prototype trouser block and write DXF + JSON.

Examples:
    python -m mueller_trousers --size 40 --out out/trousers.dxf --json out/trousers.json
    python -m mueller_trousers --size 40 --waist-half 37 --hip-half 49
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

from .clo_json import write_clo_json
from .draft import draft_trousers
from .dxf import write_dxf, write_json
from .measurements import SIZE_PRESETS, TrouserMeasurements


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=40, choices=sorted(SIZE_PRESETS))
    parser.add_argument("--print-presets", action="store_true",
                        help="print size presets as JSON and exit")
    parser.add_argument("--out", type=Path, default=Path("trousers.dxf"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--clo-json", type=Path, default=None,
                        help="native CLO pattern JSON output")
    parser.add_argument("--waist-half", type=float, default=None, help="Ст, cm")
    parser.add_argument("--hip-half", type=float, default=None, help="Сб, cm")
    parser.add_argument("--side-length", type=float, default=None, help="Дсб, cm")
    parser.add_argument("--seat-height", type=float, default=None, help="Вс, cm")
    parser.add_argument("--knee-half", type=float, default=None, help="Шк, cm")
    parser.add_argument("--hem-half", type=float, default=None, help="Шн, cm")
    parser.add_argument("--waist-ease", type=float, default=None, help="Пт, cm")
    parser.add_argument("--no-json", action="store_true", help="do not write the sidecar JSON")
    args = parser.parse_args(argv)
    if args.print_presets:
        print(json.dumps({str(size): asdict(preset)
                          for size, preset in sorted(SIZE_PRESETS.items())},
                         ensure_ascii=False, sort_keys=True))
        return 0

    measurements = SIZE_PRESETS[args.size]
    overrides = {
        "waist_half": args.waist_half,
        "hip_half": args.hip_half,
        "side_length": args.side_length,
        "seat_height": args.seat_height,
        "knee_half": args.knee_half,
        "hem_half": args.hem_half,
        "waist_ease": args.waist_ease,
    }
    changes = {key: value for key, value in overrides.items() if value is not None}
    if changes:
        measurements = replace(measurements, **changes)
    if args.size != measurements.size:
        measurements = replace(measurements, size=args.size)

    pattern = draft_trousers(measurements)
    dxf_path = write_dxf(pattern, args.out)
    json_path = None
    if not args.no_json:
        json_path = write_json(pattern, args.json or args.out.with_suffix(".json"))
    clo_path = write_clo_json(pattern, args.clo_json) if args.clo_json else None

    print("method: Mueller & Sohn core prototype")
    print("size: %d" % measurements.size)
    print("measurements: %s" % measurements.__dict__)
    for piece in pattern.pieces:
        x0, y0, x1, y1 = piece.bbox
        print("piece %-10s area=%8.1f cm2 bbox=(%.1f, %.1f)-(%.1f, %.1f) notches=%d"
              % (piece.name, piece.area_cm2, x0, y0, x1, y1, len(piece.notches)))
    print("dxf: %s" % dxf_path)
    if json_path:
        print("json: %s" % json_path)
    if clo_path:
        print("clo json: %s" % clo_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
